"""Оркестрация построения графиков: история из БД → визуализатор → PNG."""

from __future__ import annotations

from typing import Any

from loguru import logger
from shared.analytics.visualizer import FlightPriceVisualizer


def visualize_prices(
    origin: str,
    destination: str,
    departure_date: str,
    db: Any,
    visualizer: FlightPriceVisualizer,
) -> str | None:
    """Visualize price history.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        db: Database instance (duck-typed; provides get_price_history).
        visualizer: FlightPriceVisualizer instance.

    Returns:
        Path to the saved chart image, or None if there was no data / on error.
    """
    logger.info("Getting price history from database")

    try:
        flight_prices = db.get_price_history(origin, destination, departure_date)

        if not flight_prices:
            logger.warning(
                "No data in database for visualization. First collect data with: --action scrape"
            )
            return None

        logger.info(f"Found records in database: {len(flight_prices)}")

        visualizer.print_statistics(flight_prices)
        return visualizer.plot_price_history(
            flight_prices, origin, destination, departure_date
        )
    except Exception as e:
        logger.exception(f"Error during visualization: {e}")
        return None
