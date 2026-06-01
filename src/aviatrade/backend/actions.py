"""Прикладные действия backend — тонкий адаптер над «исходными функциями».

Здесь backend дёргает РОВНО те же низкоуровневые функции приложения, что и
агентный граф:

- ``aviatrade.cli.lib`` — scrape_and_save / visualize_prices;
- ``aviatrade.db.Database`` — watchlist CRUD, история цен;
- ``aviatrade.agent.monitoring.MONITORS`` — фоновый мониторинг (потоки-демоны).

Отличие от инструментов агента (``aviatrade.agent.tools``): инструменты возвращают
ТЕКСТОВЫЕ отчёты для LLM, а эти функции — структурированные ``dict`` для JSON-ответа
REST API. Так два пути (агент и backend) остаются независимыми, но переиспользуют
один и тот же исполнительный слой.

Все функции здесь СИНХРОННЫЕ и блокирующие (БД, браузер, matplotlib). В FastAPI
их вызывают через пул потоков (``run_in_threadpool``), а тяжёлый скрапинг — в
отдельном worker-процессе.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from aviatrade.agent.monitoring import MONITORS
from aviatrade.cli.lib import scrape_and_save, visualize_prices
from aviatrade.db import Database
from aviatrade.visualization import FlightPriceVisualizer

# Процесс-локальный экземпляр БД: один engine на процесс backend/worker вместо
# нового на каждый запрос. create_tables идемпотентен.
_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
        _db.create_tables()
    return _db


# ---------------------------------------------------------------------------
# Скрапинг (тяжёлый — исполняется worker-ом)
# ---------------------------------------------------------------------------
def run_scrape(origin: str, destination: str, departure_date: str) -> dict[str, Any]:
    """Собрать актуальные цены и сохранить в БД. Возвращает количество записей."""
    saved = scrape_and_save(origin, destination, departure_date, get_db())
    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "saved_count": saved,
    }


# ---------------------------------------------------------------------------
# Графики (умеренно тяжёлый — matplotlib; исполняется в пуле потоков)
# ---------------------------------------------------------------------------
def run_visualize(origin: str, destination: str, departure_date: str) -> dict[str, Any]:
    """Построить графики по собранным данным. Возвращает статус."""
    history = get_db().get_price_history(origin, destination, departure_date)
    if not history:
        return {"generated": False, "reason": "no data for this route/date"}
    visualizer = FlightPriceVisualizer()
    visualize_prices(origin, destination, departure_date, get_db(), visualizer)
    return {"generated": True, "data_points": len(history), "output_dir": "charts"}


# ---------------------------------------------------------------------------
# Статистика цен (лёгкий — чтение БД + агрегации; синхронно)
# ---------------------------------------------------------------------------
def price_stats(origin: str, destination: str, departure_date: str) -> dict[str, Any]:
    """Структурированная статистика по маршруту для JSON-ответа API."""
    history = get_db().get_price_history(origin, destination, departure_date)
    if not history:
        return {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "data_points": 0,
            "stats": None,
        }

    df = pd.DataFrame(
        [
            {
                "scraped_at": fp.scraped_at,
                "price": fp.price,
                "airline": fp.airline or "Unknown",
                "stops": fp.stops if fp.stops is not None else 0,
            }
            for fp in history
        ]
    )

    # Тренд по часовым бинам (минимум цены в каждом окне сбора).
    df["scraped_bin"] = df["scraped_at"].dt.floor("1h")
    trend = df.groupby("scraped_bin")["price"].min().reset_index()
    trend_change_pct: float | None = None
    if len(trend) >= 2:
        first, last = trend.iloc[0]["price"], trend.iloc[-1]["price"]
        if first:
            trend_change_pct = round((last - first) / first * 100, 1)

    airlines = (
        df.groupby("airline")["price"]
        .agg(["min", "mean", "max", "count"])
        .round(0)
        .sort_values("min")
        .head(10)
    )

    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "data_points": int(len(df)),
        "stats": {
            "min": round(float(df["price"].min()), 2),
            "max": round(float(df["price"].max()), 2),
            "avg": round(float(df["price"].mean()), 2),
            "median": round(float(df["price"].median()), 2),
            "currency": "RUB",
            "collection_sessions": int(len(trend)),
            "trend_change_pct": trend_change_pct,
            "direct_flights": int((df["stops"] == 0).sum()),
            "connecting_flights": int((df["stops"] > 0).sum()),
            "by_airline": [
                {
                    "airline": airline,
                    "min": float(row["min"]),
                    "avg": float(row["mean"]),
                    "max": float(row["max"]),
                    "count": int(row["count"]),
                }
                for airline, row in airlines.iterrows()
            ],
        },
    }


# ---------------------------------------------------------------------------
# Watchlist (лёгкий — CRUD по БД; синхронно)
# ---------------------------------------------------------------------------
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
    record = get_db().add_watch(origin, destination, departure_date, interval_min)
    return _watch_to_dict(record)


def remove_watch(origin: str, destination: str, departure_date: str) -> bool:
    return get_db().remove_watch(origin, destination, departure_date)


def list_watch(enabled_only: bool = False) -> list[dict[str, Any]]:
    return [_watch_to_dict(w) for w in get_db().get_watchlist(enabled_only=enabled_only)]


# ---------------------------------------------------------------------------
# Фоновый мониторинг (потоки-демоны живут в процессе backend; синхронно)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Валидация (общая для ручек)
# ---------------------------------------------------------------------------
def validate_date(date_str: str, allow_past: bool = False) -> str | None:
    """Вернуть текст ошибки или None, если дата валидна (YYYY-MM-DD)."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return f"Date must be in YYYY-MM-DD format, got: '{date_str}'"
    if not allow_past and d < datetime.now().date():
        return f"Date {date_str} is in the past. Use a future date."
    return None
