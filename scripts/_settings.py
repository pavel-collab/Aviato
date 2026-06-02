"""Конфигурация для скриптов ручного тестирования (pydantic-settings + YAML).

Это вспомогательный модуль (не самостоятельный скрипт), общий для скриптов в
``scripts/``. Берёт те же общие модели из ``shared.core``, что и деплой-сервисы,
и читает корневой ``config.yaml`` (или путь из ``SETTINGS_PATH``). Если YAML нет —
действуют дефолты (localhost, ``scraper.mode=local``), что удобно для отладки без
поднятой инфраструктуры.
"""

from __future__ import annotations

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
    resolve_settings_path,
)

# scripts/_settings.py -> parents[1] == корень репозитория, где лежит config.yaml.
settings_path = resolve_settings_path(str(Path(__file__).resolve().parents[1] / "config.yaml"))


class CliSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(yaml_file=settings_path)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)


config = CliSettings()
