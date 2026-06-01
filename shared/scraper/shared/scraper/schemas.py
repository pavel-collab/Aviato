"""Контракт между продюсерами задач скрапинга и сервисом-скрапером.

``ScrapeTask`` — это полезная нагрузка сообщения в очереди ``scrape_tasks``
(публикуют backend, агент и мониторы; потребляет сервис scraper).
``FlightRecord`` — описание одного собранного рейса (для типизации/валидации;
сам скрапер возвращает обычные dict-и, совместимые с этой схемой).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScrapeTask(BaseModel):
    """Задача на сбор цен по одному маршруту/дате."""

    origin: str
    destination: str
    departure_date: str  # YYYY-MM-DD
    # Если задан — скрапер запишет статус/результат в Redis под этим ключом,
    # чтобы backend мог отдать его через GET /jobs/{job_id}.
    job_id: str | None = None


class FlightRecord(BaseModel):
    """Один собранный рейс (поля совпадают с колонками flight_prices)."""

    origin: str
    destination: str
    departure_date: str  # YYYY-MM-DD (для JSON-передачи)
    price: float
    currency: str = "RUB"
    airline: str | None = None
    flight_number: str | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    duration: str | None = None
    stops: int | None = 0
    scraped_at: str | None = None  # ISO datetime

    model_config = {"extra": "ignore"}


class ScrapeResult(BaseModel):
    """Итог обработки одной задачи (пишется в Redis при наличии job_id)."""

    status: str = Field(description="queued | running | done | error")
    saved_count: int = 0
    error: str | None = None
