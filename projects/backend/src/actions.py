"""Прикладные действия backend поверх общих библиотек (shared.*).

Лёгкие операции (статистика, графики, watchlist, мониторы) выполняются прямо в
backend (синхронно, в пуле потоков). Тяжёлый скрапинг сюда не входит — он
публикуется в очередь из ручки /scrape и выполняется сервисом-скрапером.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from shared.analytics import FlightPriceVisualizer, compute_price_stats, visualize_prices
from shared.services import MONITORS, get_database
from src.config import config


def _db():
    return get_database(config.database)


# --- Графики ----------------------------------------------------------------
def run_visualize(origin: str, destination: str, departure_date: str) -> dict[str, Any]:
    db = _db()
    history = db.get_price_history(origin, destination, departure_date)
    if not history:
        return {"generated": False, "reason": "no data for this route/date"}
    path = visualize_prices(
        origin,
        destination,
        departure_date,
        db,
        FlightPriceVisualizer(output_dir=config.charts.output_dir),
    )
    if not path:
        return {"generated": False, "reason": "no data for this route/date"}
    url = f"{config.charts.public_base_url.rstrip('/')}/{os.path.basename(path)}"
    return {"generated": True, "data_points": len(history), "url": url}


# --- Статистика -------------------------------------------------------------
def price_stats(origin: str, destination: str, departure_date: str) -> dict[str, Any]:
    history = _db().get_price_history(origin, destination, departure_date)
    return compute_price_stats(origin, destination, departure_date, history)


# --- Watchlist --------------------------------------------------------------
def _watch_to_dict(w: Any) -> dict[str, Any]:
    return {
        "origin": w.origin,
        "destination": w.destination,
        "departure_date": str(w.departure_date),
        "interval_min": w.interval_min,
        "enabled": w.enabled,
    }


def add_watch(
    origin: str, destination: str, departure_date: str, interval_min: int = 60
) -> dict[str, Any]:
    return _watch_to_dict(_db().add_watch(origin, destination, departure_date, interval_min))


def remove_watch(origin: str, destination: str, departure_date: str) -> bool:
    return _db().remove_watch(origin, destination, departure_date)


def list_watch(enabled_only: bool = False) -> list[dict[str, Any]]:
    return [_watch_to_dict(w) for w in _db().get_watchlist(enabled_only=enabled_only)]


# --- Фоновый мониторинг -----------------------------------------------------
def start_monitor(
    origin: str, destination: str, departure_date: str, interval_minutes: int = 60
) -> tuple[bool, str]:
    return MONITORS.start_route(origin, destination, departure_date, interval_minutes)


def start_watchlist_monitor(default_interval_minutes: int = 60) -> tuple[bool, str]:
    return MONITORS.start_watchlist(default_interval_minutes)


def stop_monitor(monitor_key: str) -> tuple[bool, str]:
    return MONITORS.stop(monitor_key)


def list_monitors() -> list[dict[str, Any]]:
    return MONITORS.list_active()


# --- Валидация --------------------------------------------------------------
def validate_date(date_str: str, allow_past: bool = False) -> str | None:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return f"Date must be in YYYY-MM-DD format, got: '{date_str}'"
    if not allow_past and d < datetime.now().date():
        return f"Date {date_str} is in the past. Use a future date."
    return None
