"""Оркестрация построения графиков: история из БД → визуализатор → PNG."""

from __future__ import annotations

import traceback
from typing import Any

from shared.analytics.visualizer import FlightPriceVisualizer


def visualize_prices(
    origin: str,
    destination: str,
    departure_date: str,
    db: Any,
    visualizer: FlightPriceVisualizer,
) -> None:
    """Visualize price history.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        db: Database instance (duck-typed; provides get_price_history).
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
