import time
import traceback
import uuid
from datetime import datetime

from aviatrade.db import Database
from aviatrade.scraper import AviasalesScraper
from aviatrade.visualization import FlightPriceVisualizer


def scrape_and_save(origin: str, destination: str, departure_date: str, db: Database) -> int:
    """Scrape flights and save to database.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        db: Database instance.

    Returns:
        Number of saved flights.
    """
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


def visualize_prices(
    origin: str,
    destination: str,
    departure_date: str,
    db: Database,
    visualizer: FlightPriceVisualizer,
) -> None:
    """Visualize price history.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        db: Database instance.
        visualizer: FlightPriceVisualizer instance.
    """
    print(f"\n{'=' * 60}")
    print("Getting price history from database")
    print(f"{'=' * 60}\n")

    try:
        flight_prices = db.get_price_history(origin, destination, departure_date)

        if not flight_prices:
            print("No data in database for visualization")
            print("   First collect data with: --action scrape")
            return

        print(f"Found records in database: {len(flight_prices)}")

        visualizer.print_statistics(flight_prices)
        visualizer.plot_price_history(flight_prices, origin, destination, departure_date)
    except Exception as e:
        print(f"Error during visualization: {e}")
        traceback.print_exc()


def monitor_prices(
    origin: str,
    destination: str,
    departure_date: str,
    db: Database,
    interval_minutes: int = 60,
) -> None:
    """Monitor prices at specified interval.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        db: Database instance.
        visualizer: FlightPriceVisualizer instance.
        interval_minutes: Interval between scrapes in minutes.
    """
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

            saved_count = scrape_and_save(origin, destination, departure_date, db)
            if saved_count > 0:
                print(f"Iteration #{iteration} completed successfully")

            iteration += 1
            print(f"\nWaiting {interval_minutes} minutes until next collection...")
            time.sleep(interval_minutes * 60)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        print(f"Total iterations completed: {iteration - 1}")


def monitor_watchlist(
    db: Database,
    default_interval_minutes: int = 60,
    pause_between_routes: int = 5,
) -> None:
    """Monitor every enabled route in the watchlist.

    The watchlist is re-read at the start of every cycle, so routes added or
    removed (via CLI, agent, or TUI) are picked up without restarting the
    monitor. Routes are scraped sequentially to stay gentle on Aviasales and
    avoid parallel browser sessions.

    Each route is scraped only once its own ``interval_min`` has elapsed since
    its last scrape; the loop sleeps until the nearest due route. A route with
    ``interval_min`` unset falls back to ``default_interval_minutes``.

    Args:
        db: Database instance.
        default_interval_minutes: Fallback interval for routes without one.
        pause_between_routes: Seconds to wait between consecutive route scrapes.
    """
    print(f"\n{'=' * 60}")
    print("WATCHLIST MONITORING MODE")
    print(f"Default interval: {default_interval_minutes} minutes")
    print(f"{'=' * 60}\n")

    # Tracks the next due monotonic timestamp per route key.
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
                    scrape_and_save(
                        route.origin,
                        route.destination,
                        str(route.departure_date),
                        db,
                    )
                    next_due[key] = time.monotonic() + interval * 60
                    time.sleep(pause_between_routes)

                cycle += 1

            # Sleep until the nearest route becomes due (cap to keep the
            # watchlist fresh for newly added routes).
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


def run_agent() -> None:
    """Run the AI agent in interactive mode."""
    import os

    from langchain_core.messages import AIMessage, HumanMessage

    # Lazy import to avoid loading agent dependencies unless needed
    from aviatrade.agent.agent import AgentFactory

    # TODO: get from config
    api_key = os.getenv("OPENROUTER_API_KEY")
    model_name = os.getenv("MODEL_NAME")

    if not api_key:
        print("Error: OPENROUTER_API_KEY not set in environment")
        print("   Set it in your .env file or export OPENROUTER_API_KEY=your_key")
        return

    if not model_name:
        model_name = "openai/gpt-4o-mini"

    # TODO: remove prints and add logs
    print(f"\n{'=' * 60}")
    print("AI AGENT MODE")
    print("Available commands:")
    print("   - Scrape flight prices from Aviasales")
    print("   - Visualize price history")
    print("   - Monitor prices at intervals")
    print("   - Get price statistics")
    print("Type 'exit' or 'quit' to leave agent mode")
    print(f"{'=' * 60}\n")

    try:
        compiled_graph = AgentFactory.build_agent(model_name=model_name, api_key=api_key)
    except Exception as e:
        print(f"Error initializing agent: {e}")
        return

    while True:
        try:
            user_input = input("Agent> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Exiting agent mode")
                break

            final_state = compiled_graph.invoke(
                {"messages": [HumanMessage(content=user_input)]}
            )

            print(
                f"-- DEBUG --\n\tEnd of the agent work\n\tAgent message history len: {len(final_state['messages'])}"
            )

            # Print the last AI message as response
            for msg in reversed(final_state["messages"]):
                if isinstance(msg, AIMessage) and msg.content:
                    print(f"\n{msg.content}\n")
                    break

        except KeyboardInterrupt:
            print("\n\nAgent mode interrupted")
            break
        except Exception as e:
            print(f"Error: {e}")
