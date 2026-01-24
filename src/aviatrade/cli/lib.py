import time
import traceback
import uuid
from datetime import datetime

from aviatrade.scraper import AviasalesScraper
from aviatrade.db import Database
from aviatrade.visualization import FlightPriceVisualizer


def scrape_and_save(
    origin: str, destination: str, departure_date: str, db: Database
) -> int:
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
            print(
                f"\nIteration #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            saved_count = scrape_and_save(origin, destination, departure_date, db)
            if saved_count > 0:
                print(f"Iteration #{iteration} completed successfully")

            iteration += 1
            print(f"\nWaiting {interval_minutes} minutes until next collection...")
            time.sleep(interval_minutes * 60)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        print(f"Total iterations completed: {iteration - 1}")


def run_agent() -> None:
    """Run the AI agent in interactive mode."""
    import os
    from langchain_core.messages import HumanMessage, AIMessage

    # Lazy import to avoid loading agent dependencies unless needed
    from aviatrade.agent.agent import AgentFactory, AgentState

    api_key = os.getenv("OPENROUTER_API_KEY")
    model_name = os.getenv("MODEL_NAME")

    if not api_key:
        print("Error: OPENROUTER_API_KEY not set in environment")
        print("   Set it in your .env file or export OPENROUTER_API_KEY=your_key")
        return
    
    if not model_name:
        model_name = "openai/gpt-4o-mini"

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

            if user_input.lower() in ('exit', 'quit'):
                print("Exiting agent mode")
                break

            initial_state = AgentState(
                messages=[HumanMessage(content=user_input)],
                max_reflection_iterations=3,
                reflection_iterations=0
            )

            final_state = compiled_graph.invoke(initial_state)

            print(f"-- DEBUG --\n\tEnd of the agent work\n\tAgent message history len: {len(final_state['messages'])}")

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