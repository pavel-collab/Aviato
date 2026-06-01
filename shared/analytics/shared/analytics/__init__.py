"""shared.analytics — визуализация цен (matplotlib) и расчёт статистики."""

from shared.analytics.charts import visualize_prices
from shared.analytics.stats import compute_price_stats, render_stats_report
from shared.analytics.visualizer import FlightPriceVisualizer

__all__ = [
    "FlightPriceVisualizer",
    "compute_price_stats",
    "render_stats_report",
    "visualize_prices",
]
