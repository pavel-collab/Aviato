"""shared.core — общая конфигурация (pydantic-settings + YAML) и логирование сервисов AviaTrade."""

from shared.core.logging import LogLevel, setup_logging

__all__ = ["LogLevel", "setup_logging"]
