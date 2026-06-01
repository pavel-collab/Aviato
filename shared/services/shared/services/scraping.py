"""Оркестрация скрапинга: локальный сбор+сохранение и публикация задач в очередь.

Два режима (см. ``ScraperSettings.mode``):
- ``local``    — ``scrape_and_save_local`` скрапит через botasaurus и пишет в БД
  прямо в процессе (dev/CLI/тесты и сам сервис-скрапер при обработке задачи);
- ``rabbitmq`` — ``publish_scrape`` кладёт ``ScrapeTask`` в очередь, а сбор делает
  отдельный масштабируемый сервис-скрапер.

``dispatch_scrape`` выбирает режим — это единая точка для backend/агента/мониторов.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from datetime import datetime

import aio_pika
from shared.core.settings import RabbitMQSettings, ScraperSettings

from shared.scraper import AviasalesScraper, ScrapeTask


# ---------------------------------------------------------------------------
# Локальный сбор + сохранение (использует сервис-скрапер и local-режим)
# ---------------------------------------------------------------------------
def scrape_and_save_local(origin: str, destination: str, departure_date: str, db) -> int:
    """Scrape flights and save to database. Returns number of saved flights."""
    print(f"\n{'=' * 60}")
    print("Starting flight data collection")
    print(f"Route: {origin} -> {destination}")
    print(f"Departure date: {departure_date}")
    print(f"{'=' * 60}\n")

    try:
        search_params = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
        }

        flights = AviasalesScraper.scrape_flights(search_params)

        if not flights:
            print("No flights found. Possible reasons:")
            print("   - Invalid city codes (use IATA codes, e.g.: MOW, LED)")
            print("   - Aviasales changed site structure")
            print("   - No available flights on this date")
            return 0

        saved_count = 0
        for flight in flights:
            try:
                flight_for_db = flight.copy()

                # Temporary solution for timescaledb tables
                flight_for_db["id"] = uuid.uuid4().int % 2147483647

                if isinstance(flight_for_db.get("departure_date"), str):
                    flight_for_db["departure_date"] = datetime.strptime(
                        flight_for_db["departure_date"], "%Y-%m-%d"
                    ).date()
                if isinstance(flight_for_db.get("scraped_at"), str):
                    flight_for_db["scraped_at"] = datetime.fromisoformat(
                        flight_for_db["scraped_at"]
                    )

                db.add_flight_price(flight_for_db)
                saved_count += 1
            except Exception as e:
                print(f"Warning: Error saving flight: {e}")

        print(f"\nSuccessfully saved flights: {saved_count} of {len(flights)}")
        return saved_count

    except Exception as e:
        print(f"Error during data collection: {e}")
        traceback.print_exc()
        return 0


# ---------------------------------------------------------------------------
# Публикация задачи в RabbitMQ (потребляет сервис-скрапер)
# ---------------------------------------------------------------------------
async def publish_scrape(task: ScrapeTask, rabbitmq: RabbitMQSettings) -> None:
    """Опубликовать задачу скрапинга в durable-очередь (persistent-сообщение)."""
    connection = await aio_pika.connect_robust(rabbitmq.url)
    try:
        channel = await connection.channel()
        await channel.declare_queue(rabbitmq.scrape_queue, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(task.model_dump()).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=rabbitmq.scrape_queue,
        )
    finally:
        await connection.close()


def publish_scrape_sync(task: ScrapeTask, rabbitmq: RabbitMQSettings) -> None:
    """Синхронная обёртка над publish_scrape для sync-контекстов (мониторы, CLI)."""
    asyncio.run(publish_scrape(task, rabbitmq))


# ---------------------------------------------------------------------------
# Единая точка: выбрать режим и запустить скрапинг
# ---------------------------------------------------------------------------
def dispatch_scrape(
    task: ScrapeTask,
    *,
    scraper: ScraperSettings,
    rabbitmq: RabbitMQSettings,
    db=None,
) -> int | None:
    """local → собрать+сохранить (вернёт count); rabbitmq → опубликовать (вернёт None)."""
    if scraper.mode == "local":
        if db is None:
            from shared.services.db_factory import get_database

            db = get_database()
        return scrape_and_save_local(task.origin, task.destination, task.departure_date, db)
    publish_scrape_sync(task, rabbitmq)
    return None


# ---------------------------------------------------------------------------
# Блокирующие мониторы (используются CLI: --action monitor / monitor-all)
# ---------------------------------------------------------------------------
def monitor_route(
    origin: str,
    destination: str,
    departure_date: str,
    db,
    *,
    scraper: ScraperSettings,
    rabbitmq: RabbitMQSettings,
    interval_minutes: int = 60,
) -> None:
    """Мониторить один маршрут с заданным интервалом (блокирующий цикл, Ctrl+C)."""
    print(f"\n{'=' * 60}")
    print("MONITORING MODE")
    print(f"Route: {origin} -> {destination}")
    print(f"Departure date: {departure_date}")
    print(f"Collection interval: {interval_minutes} minutes")
    print(f"{'=' * 60}\n")

    iteration = 1
    try:
        while True:
            print(f"\nIteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            dispatch_scrape(
                ScrapeTask(origin=origin, destination=destination, departure_date=departure_date),
                scraper=scraper,
                rabbitmq=rabbitmq,
                db=db,
            )
            print(f"Iteration #{iteration} dispatched")
            iteration += 1
            print(f"\nWaiting {interval_minutes} minutes until next collection...")
            time.sleep(interval_minutes * 60)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        print(f"Total iterations completed: {iteration - 1}")


def monitor_watchlist(
    db,
    *,
    scraper: ScraperSettings,
    rabbitmq: RabbitMQSettings,
    default_interval_minutes: int = 60,
    pause_between_routes: int = 5,
) -> None:
    """Мониторить все включённые маршруты watchlist (блокирующий цикл).

    Watchlist перечитывается в начале каждого цикла; каждый маршрут собирается не
    чаще своего ``interval_min`` (или ``default_interval_minutes``).
    """
    print(f"\n{'=' * 60}")
    print("WATCHLIST MONITORING MODE")
    print(f"Default interval: {default_interval_minutes} minutes")
    print(f"{'=' * 60}\n")

    next_due: dict[tuple[str, str, str], float] = {}
    cycle = 1

    try:
        while True:
            routes = db.get_watchlist(enabled_only=True)

            if not routes:
                print("Watchlist is empty. Add routes with --action watch-add.")
                print(f"Re-checking in {default_interval_minutes} minutes...")
                time.sleep(default_interval_minutes * 60)
                continue

            now = time.monotonic()
            due_routes = []
            for route in routes:
                key = (route.origin, route.destination, str(route.departure_date))
                if next_due.get(key, 0.0) <= now:
                    due_routes.append(route)

            if due_routes:
                print(
                    f"\nCycle #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"- {len(due_routes)} route(s) due"
                )
                for route in due_routes:
                    key = (route.origin, route.destination, str(route.departure_date))
                    interval = route.interval_min or default_interval_minutes
                    dispatch_scrape(
                        ScrapeTask(
                            origin=route.origin,
                            destination=route.destination,
                            departure_date=str(route.departure_date),
                        ),
                        scraper=scraper,
                        rabbitmq=rabbitmq,
                        db=db,
                    )
                    next_due[key] = time.monotonic() + interval * 60
                    time.sleep(pause_between_routes)
                cycle += 1

            now = time.monotonic()
            active_keys = {
                (r.origin, r.destination, str(r.departure_date)) for r in routes
            }
            upcoming = [t for k, t in next_due.items() if k in active_keys and t > now]
            sleep_seconds = min(upcoming) - now if upcoming else default_interval_minutes * 60
            sleep_seconds = max(1.0, min(sleep_seconds, default_interval_minutes * 60))
            print(f"Sleeping {sleep_seconds / 60:.1f} minutes until next due route...")
            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        print("\n\nWatchlist monitoring stopped by user")
        print(f"Total cycles completed: {cycle - 1}")
