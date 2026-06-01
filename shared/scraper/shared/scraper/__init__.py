"""shared.scraper — браузерный скрапер Aviasales и контракт задач скрапинга."""

from shared.scraper.aviasales import AviasalesScraper
from shared.scraper.schemas import FlightRecord, ScrapeResult, ScrapeTask

__all__ = ["AviasalesScraper", "ScrapeTask", "FlightRecord", "ScrapeResult"]
