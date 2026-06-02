"""Конфигурация сервиса-скрапера (pydantic-settings + YAML)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from shared.core.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    LoggingSettings,
    RabbitMQSettings,
    RedisSettings,
    resolve_settings_path,
)

settings_path = resolve_settings_path(str(Path(__file__).resolve().parents[1] / "config.yaml"))


class ScraperServiceSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(yaml_file=settings_path)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    # Одновременно обрабатываемых задач на одну реплику (браузер — тяжёлый).
    prefetch_count: int = 1


config = ScraperServiceSettings()
