"""Контракт между продюсерами задач скрапинга и сервисом-скрапером.

``ScrapeTask`` — полезная нагрузка сообщения в очереди ``scrape_tasks``
(публикуют backend, агент и мониторы; потребляет сервис scraper).
"""

from __future__ import annotations

from pydantic import BaseModel


class ScrapeTask(BaseModel):
    """Задача на сбор цен по одному маршруту/дате."""

    origin: str
    destination: str
    departure_date: str  # YYYY-MM-DD
    # Если задан — скрапер запишет статус/результат в Redis под этим ключом,
    # чтобы backend мог отдать его через GET /jobs/{job_id}.
    job_id: str | None = None
