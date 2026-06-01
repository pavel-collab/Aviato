"""Конфигурация агентного сервиса (pydantic-settings + YAML).

Берёт общие модели из ``shared.core``. ``llm`` питает ``make_model`` (раньше
читался из os.getenv), ``database``/``scraper``/``rabbitmq`` нужны инструментам
(чтение БД, постановка задач скрапинга, фоновый мониторинг).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from shared.core.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    LLMSettings,
    RabbitMQSettings,
    ScraperSettings,
    resolve_settings_path,
)

settings_path = resolve_settings_path(str(Path(__file__).resolve().parents[1] / "config.yaml"))


class AgentSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(yaml_file=settings_path)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


config = AgentSettings()
