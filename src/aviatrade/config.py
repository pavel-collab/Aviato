"""Конфигурация CLI-инструмента AviaTrade (pydantic-settings + YAML).

CLI — это локальный инструмент (не деплой-сервис), поэтому его настройки лежат в
корневом ``config.yaml`` (или указанном через ``SETTINGS_PATH``). Берёт те же
общие модели из ``shared.core``, что и сервисы. Если YAML нет — действуют дефолты
(localhost, ``scraper.mode=local``), что удобно для разработки без инфраструктуры.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from shared.core.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    LangGraphSettings,
    LLMSettings,
    RabbitMQSettings,
    ScraperSettings,
)

settings_path = os.getenv(
    "SETTINGS_PATH", str(Path(__file__).resolve().parents[2] / "config.yaml")
)


class CliSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(yaml_file=settings_path)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)


config = CliSettings()
