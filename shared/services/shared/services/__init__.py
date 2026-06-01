"""shared.services — use-cases AviaTrade: скрапинг (local/queue), мониторинг, БД.

Намеренно НЕ импортирует визуализацию (matplotlib): сервис-скрапер зависит от
этого пакета и должен оставаться лёгким. Построение графиков живёт в
``shared.analytics``.
"""

from shared.services.db_factory import get_database
from shared.services.monitoring import MONITORS, BackgroundMonitorManager
from shared.services.scraping import (
    dispatch_scrape,
    monitor_route,
    monitor_watchlist,
    publish_scrape,
    publish_scrape_sync,
    scrape_and_save_local,
)

__all__ = [
    "get_database",
    "MONITORS",
    "BackgroundMonitorManager",
    "dispatch_scrape",
    "publish_scrape",
    "publish_scrape_sync",
    "scrape_and_save_local",
    "monitor_route",
    "monitor_watchlist",
]
