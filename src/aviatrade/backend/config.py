"""Конфигурация backend — всё через переменные окружения (12-factor).

Имена полей читаются из ENV без учёта регистра: ``langgraph_url`` ← LANGGRAPH_URL.
Дефолты указывают на имена сервисов из docker-compose, чтобы внутри сети Docker
ничего дополнительно настраивать не пришлось. При локальном запуске
(``uv run uvicorn aviatrade.backend.main:app``) переопредели их через .env.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Куда backend ходит за графом агента. Это внутренний REST API LangGraph
    # Server (сервис langgraph-server), наружу его не публикуем.
    langgraph_url: str = "http://langgraph-server:8000"
    # Имя графа из langgraph.json (graphs: {"aviatrade_agent": ...}).
    graph_id: str = "aviatrade_agent"

    # Брокер прикладного уровня: ручка API → очередь → worker.
    # Через него уходят ТЯЖЁЛЫЕ задачи: скрапинг (браузер) и прогон графа.
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    job_queue: str = "aviatrade_jobs"

    # Хранилище статусов/результатов задач. Берём ОТДЕЛЬНУЮ логическую БД (/1),
    # чтобы не пересекаться с Redis, который LangGraph Server использует под свою
    # внутреннюю очередь run-ов (та живёт в БД /0).
    redis_url: str = "redis://redis:6379/1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
