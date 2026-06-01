"""Command-line interface for AviaTrade flight price monitoring."""

import argparse
from datetime import datetime

from aviatrade.cli.lib import run_agent
from aviatrade.config import config
from shared.analytics import FlightPriceVisualizer, visualize_prices
from shared.scraper import ScrapeTask
from shared.services import (
    dispatch_scrape,
    get_database,
    monitor_route,
    monitor_watchlist,
)


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Flight price monitoring for Aviasales.ru",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape flights Moscow -> Saint-Petersburg on 2025-01-15
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action scrape

  # Visualize price history
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action visualize

  # Monitor with 30-minute interval
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action monitor --interval 30

  # Scrape and visualize together
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action both

  # Add a route to the multi-direction watchlist
  aviatrade --origin MOW --destination AER --date 2025-01-15 --action watch-add --interval 30

  # Show the watchlist
  aviatrade --action watch-list

  # Remove a route from the watchlist
  aviatrade --origin MOW --destination AER --date 2025-01-15 --action watch-remove

  # Monitor every route in the watchlist (multi-direction)
  aviatrade --action monitor-all --interval 60

  # Run AI agent (talks to the LangGraph server via SDK)
  aviatrade --action agent

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

    # Agent mode doesn't require origin/destination/date
    if args.action == "agent":
        print("Starting AviaTrade AI Agent mode")
        run_agent()
        print("\nDone!")
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
                print(f"Warning: specified date ({args.date}) is in the past")
        except ValueError:
            print("Error: Invalid date format. Use YYYY-MM-DD format")
            return

    # Initialize
    print("Starting AviaTrade flight price monitoring")
    print(f"Scraper mode: {config.scraper.mode}")
    print("Initializing database...")

    try:
        db = get_database(config.database)
        print("Database ready")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("   Make sure PostgreSQL is running (docker-compose up -d)")
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
            print("Scrape task queued (mode=rabbitmq). Data will appear once the scraper processes it.")
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
        print(
            f"Added to watchlist: {record.origin} -> {record.destination} "
            f"on {record.departure_date} (every {record.interval_min} min)"
        )
    elif args.action == "watch-remove":
        removed = db.remove_watch(args.origin, args.destination, args.date)
        if removed:
            print(
                f"Removed from watchlist: {args.origin} -> {args.destination} on {args.date}"
            )
        else:
            print(
                f"No watchlist entry found for {args.origin} -> {args.destination} on {args.date}"
            )
    elif args.action == "watch-list":
        routes = db.get_watchlist(enabled_only=False)
        if not routes:
            print("Watchlist is empty. Add routes with --action watch-add.")
        else:
            print(f"\nWatchlist ({len(routes)} route(s)):")
            print("-" * 60)
            for r in routes:
                state = "enabled " if r.enabled else "disabled"
                print(
                    f"  [{state}] {r.origin} -> {r.destination}  {r.departure_date}  "
                    f"every {r.interval_min} min"
                )

    print("\nDone!")


if __name__ == "__main__":
    main()
