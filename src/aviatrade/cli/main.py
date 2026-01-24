"""Command-line interface for AviaTrade flight price monitoring."""

import argparse
from datetime import datetime

from aviatrade.db import Database
from aviatrade.visualization import FlightPriceVisualizer

from lib import scrape_and_save, visualize_prices, monitor_prices


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Flight price monitoring for Aviasales.ru",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch interactive TUI
  aviatrade --tui

  # Scrape flights Moscow -> Saint-Petersburg on 2025-01-15
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action scrape

  # Visualize price history
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action visualize

  # Monitor with 30-minute interval
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action monitor --interval 30

  # Scrape and visualize together
  aviatrade --origin MOW --destination LED --date 2025-01-15 --action both

Popular IATA codes for Russian cities:
  MOW - Moscow, LED - Saint-Petersburg, SVX - Yekaterinburg
  KZN - Kazan, OVB - Novosibirsk, AER - Sochi
        """,
    )

    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch interactive TUI instead of CLI",
    )
    parser.add_argument(
        "--origin", required=False, help="Origin city IATA code (e.g.: MOW)"
    )
    parser.add_argument(
        "--destination", required=False, help="Destination city IATA code (e.g.: LED)"
    )
    parser.add_argument("--date", required=False, help="Departure date in YYYY-MM-DD format")
    parser.add_argument(
        "--action",
        choices=["scrape", "visualize", "monitor", "both"],
        default="both",
        help="Action: scrape, visualize, monitor, or both (default: both)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between collections in minutes (for monitor mode, default: 60)",
    )

    args = parser.parse_args()

    # Launch TUI if requested
    if args.tui:
        from aviatrade.cli.tui import main as tui_main

        tui_main()
        return

    # Check required arguments for CLI mode
    if not all([args.origin, args.destination, args.date]):
        parser.error("--origin, --destination, and --date are required (or use --tui for interactive mode)")

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
    print("Initializing database...")

    try:
        db = Database()
        db.create_tables()
        print("Database ready")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("   Make sure PostgreSQL is running (docker-compose up -d)")
        return

    visualizer = FlightPriceVisualizer()

    # Execute actions
    if args.action == "scrape":
        scrape_and_save(args.origin, args.destination, args.date, db)
    elif args.action == "visualize":
        visualize_prices(args.origin, args.destination, args.date, db, visualizer)
    elif args.action == "monitor":
        monitor_prices(
            args.origin, args.destination, args.date, db, args.interval
        )
    elif args.action == "both":
        saved = scrape_and_save(args.origin, args.destination, args.date, db)
        if saved > 0:
            visualize_prices(args.origin, args.destination, args.date, db, visualizer)

    print("\nDone!")


if __name__ == "__main__":
    main()
