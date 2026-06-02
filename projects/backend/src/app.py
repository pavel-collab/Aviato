"""FastAPI backend AviaTrade — внешняя точка входа.

Тяжёлый скрапинг публикуется в очередь ``scrape_queue`` (его берёт масштабируемый
сервис-скрапер). Асинхронный диалог с агентом — через ``job_queue`` + worker.
Лёгкие операции (статистика, графики, watchlist, мониторы) — синхронно в пуле
потоков. OpenAI-совместимые ручки (/v1/*) подключены для фронтенда OpenWebUI.
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from shared.core import setup_logging
from shared.scraper import ScrapeTask
from shared.services import MONITORS, publish_scrape
from src import actions
from src.config import config
from src.lg_client import aclose_client, run_graph
from src.mq import aclose_mq, get_job, publish_job, set_job
from src.openai_api import router as openai_router

_IATA_RE = re.compile(r"^[A-Za-z]{3}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(config.logging.level)
    # Фоновые мониторы (если их запустят через API) публикуют scrape-задачи —
    # настроим их под конфиг backend (БД/режим скрапера/RabbitMQ).
    MONITORS.configure(
        database=config.database, scraper=config.scraper, rabbitmq=config.rabbitmq
    )
    yield
    await aclose_client()
    await aclose_mq()
    MONITORS.stop_all()


app = FastAPI(title="AviaTrade Backend", version="0.1.0", lifespan=lifespan)
app.include_router(openai_router)


class RouteRequest(BaseModel):
    origin: str = Field(..., examples=["MOW"])
    destination: str = Field(..., examples=["LED"])
    departure_date: str = Field(..., examples=["2025-12-15"])


class WatchRequest(RouteRequest):
    interval_min: int = Field(60, ge=1, le=1440)


class MonitorRequest(RouteRequest):
    interval_minutes: int = Field(60, ge=1, le=1440)


class ChatRequest(BaseModel):
    message: str


class JobResponse(BaseModel):
    job_id: str
    status: str


def _validate_route(origin: str, destination: str, date: str, allow_past: bool = False):
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


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


# --- Агент (LangGraph SDK) --------------------------------------------------
@app.post("/agent/chat", tags=["agent"])
async def agent_chat(req: ChatRequest) -> dict:
    answer = await run_graph(req.message)
    return {"answer": answer}


@app.post("/agent/chat/async", response_model=JobResponse, tags=["agent"])
async def agent_chat_async(req: ChatRequest) -> JobResponse:
    job_id = str(uuid.uuid4())
    await set_job(job_id, {"status": "queued", "type": "chat", "result": None})
    await publish_job(job_id, "chat", {"message": req.message})
    return JobResponse(job_id=job_id, status="queued")


# --- Скрапинг (публикуется в scrape_queue → сервис scraper) -----------------
@app.post("/scrape", response_model=JobResponse, tags=["scrape"])
async def scrape(req: RouteRequest) -> JobResponse:
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date)
    job_id = str(uuid.uuid4())
    await set_job(job_id, {"status": "queued", "saved_count": 0})
    await publish_scrape(
        ScrapeTask(
            origin=origin,
            destination=destination,
            departure_date=req.departure_date,
            job_id=job_id,
        ),
        config.rabbitmq,
    )
    return JobResponse(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", tags=["jobs"])
async def job_status(job_id: str) -> dict:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"job_id": job_id, **job}


# --- Статистика / графики ---------------------------------------------------
@app.get("/stats", tags=["stats"])
async def stats(
    origin: str = Query(...),
    destination: str = Query(...),
    departure_date: str = Query(...),
) -> dict:
    origin, destination = _validate_route(origin, destination, departure_date, allow_past=True)
    return await run_in_threadpool(actions.price_stats, origin, destination, departure_date)


@app.post("/charts", tags=["charts"])
async def charts(req: RouteRequest) -> dict:
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date, allow_past=True)
    return await run_in_threadpool(actions.run_visualize, origin, destination, req.departure_date)


# --- Watchlist --------------------------------------------------------------
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


# --- Фоновый мониторинг -----------------------------------------------------
@app.get("/monitors", tags=["monitors"])
async def monitors_list() -> dict:
    monitors = await run_in_threadpool(actions.list_monitors)
    return {"count": len(monitors), "monitors": monitors}


@app.post("/monitors", tags=["monitors"])
async def monitor_start(req: MonitorRequest) -> dict:
    origin, destination = _validate_route(req.origin, req.destination, req.departure_date)
    started, message = await run_in_threadpool(
        actions.start_monitor, origin, destination, req.departure_date, req.interval_minutes
    )
    return {"started": started, "message": message}


@app.post("/monitors/watchlist", tags=["monitors"])
async def monitor_start_watchlist(default_interval_minutes: int = 60) -> dict:
    if not (1 <= default_interval_minutes <= 1440):
        raise HTTPException(400, "interval must be between 1 and 1440 minutes")
    started, message = await run_in_threadpool(
        actions.start_watchlist_monitor, default_interval_minutes
    )
    return {"started": started, "message": message}


@app.delete("/monitors/{monitor_key}", tags=["monitors"])
async def monitor_stop(monitor_key: str) -> dict:
    stopped, message = await run_in_threadpool(actions.stop_monitor, monitor_key)
    if not stopped:
        raise HTTPException(404, message)
    return {"stopped": stopped, "message": message}
