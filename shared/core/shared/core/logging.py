"""Минимальный помощник логирования (stdlib) для сервисов AviaTrade.

Лёгкая замена разрозненным ``print()``: единый формат, уровень из аргумента.
Намеренно без тяжёлых зависимостей — сервисы могут заменить на loguru при желании.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Однократно настроить корневой логгер (идемпотентно)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Получить именованный логгер (с ленивой настройкой формата)."""
    configure_logging()
    return logging.getLogger(name)
