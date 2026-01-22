"""
AviaTrade - Flight price monitoring system for Aviasales.ru
"""

__version__ = "1.0.0"

from aviatrade.core.config import config
from aviatrade.db.database import Database
from aviatrade.db.models import FlightPrice
from aviatrade.scraper.aviasales import AviasalesScraper
from aviatrade.visualization.visualizer import FlightPriceVisualizer

__all__ = [
    "config",
    "Database",
    "FlightPrice",
    "AviasalesScraper",
    "FlightPriceVisualizer",
]
