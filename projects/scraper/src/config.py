"""Конфигурация сервиса-скрапера (pydantic-settings + YAML)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from shared.core.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)

settings_path = os.getenv(
    "SETTINGS_PATH", str(Path(__file__).resolve().parents[1] / "config.yaml")
)


class ScraperServiceSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(yaml_file=settings_path)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    # Одновременно обрабатываемых задач на одну реплику (браузер — тяжёлый).
    prefetch_count: int = 1


config = ScraperServiceSettings()
