"""FastAPI backend AviaTrade — внешняя точка входа в систему.

Через эти ручки запускаются ОСНОВНЫЕ действия приложения и ведётся диалог с
агентом. Два класса операций:

- Лёгкие (синхронно прямо в backend): статистика, watchlist CRUD, управление
  фоновыми мониторами, построение графиков. Блокирующие вызовы уводятся в пул
  потоков (``run_in_threadpool``).
- Тяжёлые (асинхронно через RabbitMQ → worker): скрапинг (браузер) и прогон
  графа агента. Ручка сразу отдаёт ``job_id``, результат забирается через
  ``GET /jobs/{id}``. Для чата с агентом есть и синхронный путь (``/agent/chat``).

Эндпоинты сгруппированы тегами: agent, scrape, stats, charts, watchlist, monitors.

Маршрутизация по слоям:
    POST /scrape            → RabbitMQ → worker → actions.run_scrape
    POST /agent/chat        → langgraph-sdk (синхронно ждём граф)
    POST /agent/chat/async  → RabbitMQ → worker → run_graph
    GET  /stats             → actions.price_stats (прямо, в пуле потоков)
    *    /watchlist, /monitors, /charts → actions.* (прямо, в пуле потоков)
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import actions
from .lg_client import aclose_client, run_graph
from .mq import aclose_mq, get_job, publish_job, set_job
from .openai_api import router as openai_router

_IATA_RE = re.compile(r"^[A-Za-z]{3}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Долгоживущие клиенты (LangGraph SDK, RabbitMQ, Redis) создаются лениво при
    # первом запросе и переиспользуются. На остановке аккуратно закрываем их.
    yield
    await aclose_client()
    await aclose_mq()
    actions.MONITORS.stop_all()


app = FastAPI(title="AviaTrade Backend", version="0.1.0", lifespan=lifespan)

# OpenAI-совместимый API (/v1/models, /v1/chat/completions) для фронтенда OpenWebUI.
app.include_router(openai_router)


# ===========================================================================
# Модели запросов/ответов
# ===========================================================================
class RouteRequest(BaseModel):
    origin: str = Field(..., examples=["MOW"], description="IATA код вылета")
    destination: str = Field(..., examples=["LED"], description="IATA код прилёта")
    departure_date: str = Field(..., examples=["2025-12-15"], description="YYYY-MM-DD")


class WatchRequest(RouteRequest):
    interval_min: int = Field(60, ge=1, le=1440, description="Интервал сбора, мин")


class MonitorRequest(RouteRequest):
    interval_minutes: int = Field(60, ge=1, le=1440)


class ChatRequest(BaseModel):
    message: str


class JobResponse(BaseModel):
    job_id: str
    status: str


def _validate_route(origin: str, destination: str, date: str, allow_past: bool = False):
    """Поднять HTTP 400 при невалидных кодах/дате. Возвращает (origin, dest) в upper."""
    origin, destination = origin.upper().strip(), destination.upper().strip()
    if not _IATA_RE.match(origin):
        raise HTTPException(400, f"Invalid origin IATA code: '{origin}'")
    if not _IATA_RE.match(destination):
        raise HTTPException(400, f"Invalid destination IATA code: '{destination}'")
    if origin == destination:
        raise HTTPException(400, "Origin and destination must differ")
    err = actions.validate_date(date, allow_past=allow_past)
    if err:
        raise HTTPException(400, err)
    return origin, destination


# ===========================================================================
# Health
# ===========================================================================
@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


# ===========================================================================
# Агент (через LangGraph SDK)
# ===========================================================================
@app.post("/agent/chat", tags=["agent"])
async def agent_chat(req: ChatRequest) -> dict:
    """Синхронный диалог с агентом: дождаться граф и сразу вернуть ответ."""
    answer = await run_graph(req.message)
    return {"answer": answer}


@app.post("/agent/chat/async", response_model=JobResponse, tags=["agent"])
async def agent_chat_async(req: ChatRequest) -> JobResponse:
    """Асинхронный диалог: поставить прогон графа в очередь, вернуть job_id."""
    job_id = str(uuid.uuid4())
    await set_job(job_id, {"status": "queued", "type": "chat", "result": None})
    await publish_job(job_id, "chat", {"message": req.message})
    return JobResponse(job_id=job_id, status="queued")


# ===========================================================================
# Скрапинг (тяжёлый → очередь → worker)
# ===========================================================================
@app.post("/scrape", response_model=JobResponse, tags=["scrape"])
async def scrape(req: RouteRequest) -> JobResponse:
    """Поставить разовый скрапинг в очередь. Результат — через GET /jobs/{id}."""
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date)
    job_id = str(uuid.uuid4())
    await set_job(job_id, {"status": "queued", "type": "scrape", "result": None})
    await publish_job(
        job_id,
        "scrape",
        {"origin": origin, "destination": destination, "departure_date": req.departure_date},
    )
    return JobResponse(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", tags=["jobs"])
async def job_status(job_id: str) -> dict:
    """Узнать статус/результат ранее поставленной задачи (scrape или chat)."""
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"job_id": job_id, **job}


# ===========================================================================
# Статистика (лёгкий → прямо в пуле потоков)
# ===========================================================================
@app.get("/stats", tags=["stats"])
async def stats(
    origin: str = Query(...),
    destination: str = Query(...),
    departure_date: str = Query(...),
) -> dict:
    """Структурированная статистика цен по маршруту (история допускает прошлые даты)."""
    origin, destination = _validate_route(origin, destination, departure_date, allow_past=True)
    return await run_in_threadpool(actions.price_stats, origin, destination, departure_date)


# ===========================================================================
# Графики (умеренно тяжёлый → прямо в пуле потоков)
# ===========================================================================
@app.post("/charts", tags=["charts"])
async def charts(req: RouteRequest) -> dict:
    """Построить графики по собранным данным маршрута (сохраняются в charts/)."""
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date, allow_past=True)
    return await run_in_threadpool(actions.run_visualize, origin, destination, req.departure_date)


# ===========================================================================
# Watchlist (лёгкий CRUD)
# ===========================================================================
@app.get("/watchlist", tags=["watchlist"])
async def watchlist_list(enabled_only: bool = False) -> dict:
    routes = await run_in_threadpool(actions.list_watch, enabled_only)
    return {"count": len(routes), "routes": routes}


@app.post("/watchlist", tags=["watchlist"])
async def watchlist_add(req: WatchRequest) -> dict:
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date)
    return await run_in_threadpool(
        actions.add_watch, origin, destination, req.departure_date, req.interval_min
    )


@app.delete("/watchlist", tags=["watchlist"])
async def watchlist_remove(req: RouteRequest) -> dict:
    origin, destination = _validate_route(
        req.origin, req.destination, req.departure_date, allow_past=True
    )
    removed = await run_in_threadpool(
        actions.remove_watch, origin, destination, req.departure_date
    )
    if not removed:
        raise HTTPException(404, "watchlist entry not found")
    return {"removed": True}


# ===========================================================================
# Фоновый мониторинг (потоки-демоны в процессе backend)
# ===========================================================================
@app.get("/monitors", tags=["monitors"])
async def monitors_list() -> dict:
    monitors = await run_in_threadpool(actions.list_monitors)
    return {"count": len(monitors), "monitors": monitors}


@app.post("/monitors", tags=["monitors"])
async def monitor_start(req: MonitorRequest) -> dict:
    """Запустить фоновый мониторинг одного маршрута (неблокирующий поток)."""
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date)
    started, message = await run_in_threadpool(
        actions.start_monitor, origin, destination, req.departure_date, req.interval_minutes
    )
    return {"started": started, "message": message}


@app.post("/monitors/watchlist", tags=["monitors"])
async def monitor_start_watchlist(default_interval_minutes: int = 60) -> dict:
    """Запустить фоновый мониторинг всех включённых маршрутов watchlist."""
    if not (1 <= default_interval_minutes <= 1440):
        raise HTTPException(400, "interval must be between 1 and 1440 minutes")
    started, message = await run_in_threadpool(
        actions.start_watchlist_monitor, default_interval_minutes
    )
    return {"started": started, "message": message}


@app.delete("/monitors/{monitor_key}", tags=["monitors"])
async def monitor_stop(monitor_key: str) -> dict:
    """Остановить фоновый монитор по ключу (см. GET /monitors)."""
    stopped, message = await run_in_threadpool(actions.stop_monitor, monitor_key)
    if not stopped:
        raise HTTPException(404, message)
    return {"stopped": stopped, "message": message}
