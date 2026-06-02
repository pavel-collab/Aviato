"""Единая конфигурация AviaTrade на pydantic-settings, загружаемая из YAML.

По образцу монорепо retrieval-experiments: базовый ``BaseServiceSettings``
читает настройки ТОЛЬКО из YAML-файла (env/.env игнорируются), а конкретные
сервисы наследуются от него и указывают свой ``yaml_file`` через
``SettingsConfigDict``. Путь к YAML переопределяется переменной ``SETTINGS_PATH``.

Секреты (ключ OpenRouter, пароли БД) живут в ``config.yaml`` каждого сервиса
(в .gitignore); в гит коммитится только ``config.example.yaml`` с плейсхолдерами.

Вложенные модели (Database/RabbitMQ/Redis/LLM/LangGraph/Scraper) переиспользуются
всеми сервисами — каждый берёт в свой Settings только нужные секции.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
)
from shared.core.logging import LogLevel


def resolve_settings_path(fallback: str = "config.yaml") -> str:
    """Путь к YAML-конфигу: переменная ``SETTINGS_PATH`` или ``fallback``."""
    env = os.getenv("SETTINGS_PATH")
    if env:
        return str(Path(env))
    return fallback


class BaseServiceSettings(BaseSettings):
    """База для настроек сервиса: источник конфигурации — только YAML-файл."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Только YAML: env-переменные, .env и init-аргументы НЕ участвуют —
        # вся конфигурация задаётся в config.yaml (12-factor через монтирование).
        return (YamlConfigSettingsSource(settings_cls),)


# ---------------------------------------------------------------------------
# Вложенные секции конфигурации
# ---------------------------------------------------------------------------
class DatabaseSettings(BaseModel):
    """TimescaleDB (PostgreSQL). Драйвер синхронный (psycopg2)."""

    host: str = "localhost"
    port: int = 5432
    user: str = "flight_user"
    password: str = "flight_password"
    database: str = "flight_prices"

    @property
    def dsn(self) -> str:
        """Синхронная строка подключения SQLAlchemy/psycopg2."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class RabbitMQSettings(BaseModel):
    """Брокер задач. Две очереди: скрапинг и прикладные job-и backend-а."""

    host: str = "localhost"
    port: int = 5672
    user: str = "guest"
    password: str = "guest"
    # Очередь задач скрапинга (потребляет сервис scraper, competing consumers).
    scrape_queue: str = "scrape_tasks"
    # Прикладная очередь backend → worker (асинхронный прогон графа агента).
    job_queue: str = "aviatrade_jobs"

    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/"


class RedisSettings(BaseModel):
    """Хранилище статусов/результатов задач (отдельная логическая БД /1)."""

    host: str = "localhost"
    port: int = 6379
    db: int = 1

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


class LLMSettings(BaseModel):
    """Модель агента через OpenRouter (заменяет os.getenv в make_model)."""

    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/gpt-4o-mini"


class LangGraphSettings(BaseModel):
    """Адрес LangGraph Server и имя графа (для langgraph-sdk в backend)."""

    url: str = "http://localhost:8123"
    graph_id: str = "aviatrade_agent"


class LoggingSettings(BaseModel):
    """Уровень логирования сервиса (loguru). Принимает строку ``"INFO"`` или число."""

    level: LogLevel = Field(default=LogLevel.INFO)


class ScraperSettings(BaseModel):
    """Как запускать скрапинг и параметры самого скрапера.

    mode:
      - ``rabbitmq`` — публиковать задачу в очередь (дефолт; сервис scraper её берёт);
      - ``local``    — legacy: скрапить и сохранять в процессе вызова (нужен Chromium
        на хосте, брокер не нужен; синхронный saved_count).
    """

    mode: Literal["rabbitmq", "local"] = "rabbitmq"
    headless: bool = True
    max_flights: int = 20


class ChartsSettings(BaseModel):
    """Куда сохранять PNG-графики и по какому публичному URL их отдаёт backend.

    Граф агента пишет картинку в ``output_dir`` (том, общий с backend), а в ответ
    возвращает markdown-ссылку ``{public_base_url}/{файл}.png``. Backend отдаёт этот
    каталог статикой (mount ``/static``). ``public_base_url`` должен быть достижим из
    БРАУЗЕРА пользователя (OpenWebUI рендерит ``<img>``), поэтому это host-facing адрес
    backend (``localhost:8000``), а НЕ имя сервиса в сети compose.
    """

    output_dir: str = "charts"
    public_base_url: str = "http://localhost:8000/static"
