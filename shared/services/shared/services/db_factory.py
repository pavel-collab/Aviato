"""Фабрика подключений к БД: один Database на DSN (с авто-созданием таблиц).

Раньше каждый вызывающий делал ``Database(); db.create_tables()``. Теперь сервисы
передают свою ``DatabaseSettings`` (из YAML), а фабрика кэширует экземпляр по DSN
и один раз создаёт таблицы.
"""

from __future__ import annotations

from functools import lru_cache

from shared.core.settings import DatabaseSettings

from shared.db import Database


@lru_cache(maxsize=8)
def _build(dsn: str) -> Database:
    db = Database(dsn)
    db.create_tables()
    return db


def get_database(db_settings: DatabaseSettings | None = None) -> Database:
    """Вернуть кэшированный Database для указанных настроек (или дефолтных)."""
    settings = db_settings or DatabaseSettings()
    return _build(settings.dsn)
