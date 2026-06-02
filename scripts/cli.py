#!/usr/bin/env python
"""Скрипт ручного тестирования AviaTrade поверх ``shared.*``.

Самодостаточный CLI: позволяет вручную дёрнуть скрапинг/визуализацию/мониторинг и
watchlist напрямую через общие библиотеки, а также поговорить с агентом через
LangGraph Server — не поднимая backend/OpenWebUI. Это инструмент разработчика, а
не деплой-сервис, поэтому он живёт в ``scripts/`` и запускается напрямую:

    uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action scrape
    uv run python scripts/cli.py --action watch-list
    uv run python scripts/cli.py --action monitor-all --interval 60
    uv run python scripts/cli.py --action agent
"""

import argparse
from datetime import datetime

from _settings import config
from loguru import logger

from shared.analytics import FlightPriceVisualizer, visualize_prices
from shared.core import setup_logging
from shared.scraper import ScrapeTask
from shared.services import (
    dispatch_scrape,
    get_database,
    monitor_route,
    monitor_watchlist,
)


def run_agent() -> None:
    """Интерактивный диалог с агентом через LangGraph Server (langgraph-sdk).

    Скрипт выступает клиентом сервиса агента: отправляет каждое сообщение в
    развёрнутый граф по SDK и печатает финальный ответ. Сначала поднимите сервер
    (``uv run --project projects/agent --extra langgraph langgraph dev`` для
    локальной отладки или docker-сервис ``agent``) и укажите ``langgraph.url`` в
    config.yaml.
    """
    from langgraph_sdk import get_sync_client

    logger.info("AI AGENT MODE")
    logger.info(
        f"LangGraph server: {config.langgraph.url} (graph: {config.langgraph.graph_id})"
    )
    logger.info("Type 'exit' or 'quit' to leave agent mode")

    try:
        client = get_sync_client(url=config.langgraph.url)
    except Exception as e:
        logger.error(f"Error connecting to LangGraph server: {e}")
        return

    while True:
        try:
            user_input = input("Agent> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                logger.info("Exiting agent mode")
                break

            thread = client.threads.create()
            result = client.runs.wait(
                thread["thread_id"],
                config.langgraph.graph_id,
                input={"messages": [{"role": "human", "content": user_input}]},
            )

            messages = result.get("messages", []) if isinstance(result, dict) else []
            if messages:
                last = messages[-1]
                content = last.get("content", "") if isinstance(last, dict) else str(last)
                logger.info(content)
            else:
                logger.info("(no response)")

        except KeyboardInterrupt:
            logger.info("Agent mode interrupted")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


def main() -> None:
    """Точка входа скрипта ручного тестирования."""
    parser = argparse.ArgumentParser(
        description="Flight price monitoring for Aviasales.ru (manual-testing CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape flights Moscow -> Saint-Petersburg on 2026-09-15
  uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action scrape

  # Visualize price history
  uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action visualize

  # Monitor with 30-minute interval
  uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action monitor --interval 30

  # Scrape and visualize together
  uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action both

  # Add a route to the multi-direction watchlist
  uv run python scripts/cli.py --origin MOW --destination AER --date 2026-09-15 --action watch-add --interval 30

  # Show the watchlist
  uv run python scripts/cli.py --action watch-list

  # Remove a route from the watchlist
  uv run python scripts/cli.py --origin MOW --destination AER --date 2026-09-15 --action watch-remove

  # Monitor every route in the watchlist (multi-direction)
  uv run python scripts/cli.py --action monitor-all --interval 60

  # Run AI agent (talks to the LangGraph server via SDK)
  uv run python scripts/cli.py --action agent

Popular IATA codes for Russian cities:
  MOW - Moscow, LED - Saint-Petersburg, SVX - Yekaterinburg
  KZN - Kazan, OVB - Novosibirsk, AER - Sochi
        """,
    )

    parser.add_argument("--origin", required=False, help="Origin city IATA code (e.g.: MOW)")
    parser.add_argument(
        "--destination", required=False, help="Destination city IATA code (e.g.: LED)"
    )
    parser.add_argument("--date", required=False, help="Departure date in YYYY-MM-DD format")
    parser.add_argument(
        "--action",
        choices=[
            "scrape",
            "visualize",
            "monitor",
            "both",
            "agent",
            "monitor-all",
            "watch-add",
            "watch-list",
            "watch-remove",
        ],
        default="both",
        help=(
            "Action: scrape, visualize, monitor, both, agent, "
            "monitor-all, watch-add, watch-list, watch-remove (default: both)"
        ),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between collections in minutes (for monitor mode, default: 60)",
    )

    args = parser.parse_args()

    setup_logging(config.logging.level)

    # Agent mode doesn't require origin/destination/date
    if args.action == "agent":
        logger.info("Starting AviaTrade AI Agent mode")
        run_agent()
        logger.info("Done!")
        return

    # Actions that operate on the whole watchlist don't need a single route.
    route_optional_actions = {"monitor-all", "watch-list"}

    if args.action not in route_optional_actions:
        # Check required arguments for route-specific CLI modes
        if not all([args.origin, args.destination, args.date]):
            parser.error(
                "--origin, --destination, and --date are required (or use --action agent)"
            )

        # Validate date
        try:
            departure_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            if departure_date < datetime.now().date():
                logger.warning(f"Specified date ({args.date}) is in the past")
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD format")
            return

    # Initialize
    logger.info("Starting AviaTrade flight price monitoring")
    logger.info(f"Scraper mode: {config.scraper.mode}")
    logger.info("Initializing database...")

    try:
        db = get_database(config.database)
        logger.info("Database ready")
    except Exception as e:
        logger.error(
            f"Error connecting to database: {e}. "
            "Make sure PostgreSQL is running (docker compose up -d postgres)"
        )
        return

    visualizer = FlightPriceVisualizer()

    def _scrape(origin: str, destination: str, date: str) -> int | None:
        """Dispatch scraping per configured mode; returns saved count (local) or None (queued)."""
        result = dispatch_scrape(
            ScrapeTask(origin=origin, destination=destination, departure_date=date),
            scraper=config.scraper,
            rabbitmq=config.rabbitmq,
            db=db,
        )
        if result is None:
            logger.info(
                "Scrape task queued (mode=rabbitmq). "
                "Data will appear once the scraper processes it."
            )
        return result

    # Execute actions
    if args.action == "scrape":
        _scrape(args.origin, args.destination, args.date)
    elif args.action == "visualize":
        visualize_prices(args.origin, args.destination, args.date, db, visualizer)
    elif args.action == "monitor":
        monitor_route(
            args.origin,
            args.destination,
            args.date,
            db,
            scraper=config.scraper,
            rabbitmq=config.rabbitmq,
            interval_minutes=args.interval,
        )
    elif args.action == "both":
        saved = _scrape(args.origin, args.destination, args.date)
        # In local mode visualize the freshly collected data; in queue mode the
        # data is collected asynchronously, so visualize whatever is already stored.
        if saved is None or saved > 0:
            visualize_prices(args.origin, args.destination, args.date, db, visualizer)
    elif args.action == "monitor-all":
        monitor_watchlist(
            db,
            scraper=config.scraper,
            rabbitmq=config.rabbitmq,
            default_interval_minutes=args.interval,
        )
    elif args.action == "watch-add":
        record = db.add_watch(args.origin, args.destination, args.date, args.interval)
        logger.info(
            f"Added to watchlist: {record.origin} -> {record.destination} "
            f"on {record.departure_date} (every {record.interval_min} min)"
        )
    elif args.action == "watch-remove":
        removed = db.remove_watch(args.origin, args.destination, args.date)
        if removed:
            logger.info(
                f"Removed from watchlist: {args.origin} -> {args.destination} on {args.date}"
            )
        else:
            logger.info(
                f"No watchlist entry found for {args.origin} -> {args.destination} on {args.date}"
            )
    elif args.action == "watch-list":
        routes = db.get_watchlist(enabled_only=False)
        if not routes:
            logger.info("Watchlist is empty. Add routes with --action watch-add.")
        else:
            lines = [f"Watchlist ({len(routes)} route(s)):"]
            for r in routes:
                state = "enabled " if r.enabled else "disabled"
                lines.append(
                    f"  [{state}] {r.origin} -> {r.destination}  {r.departure_date}  "
                    f"every {r.interval_min} min"
                )
            logger.info("\n".join(lines))

    logger.info("Done!")


if __name__ == "__main__":
    main()
