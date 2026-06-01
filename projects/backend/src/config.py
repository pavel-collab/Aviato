"""Конфигурация backend (pydantic-settings + YAML)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from shared.core.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    LangGraphSettings,
    RabbitMQSettings,
    RedisSettings,
    ScraperSettings,
)

settings_path = os.getenv(
    "SETTINGS_PATH", str(Path(__file__).resolve().parents[1] / "config.yaml")
)


class BackendSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(yaml_file=settings_path)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    host: str = "0.0.0.0"
    port: int = 8000


config = BackendSettings()
