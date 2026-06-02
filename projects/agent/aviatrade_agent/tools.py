"""Инструменты (tools) агентного графа AviaTrade.

Инструмент в LangChain — функция с декоратором ``@tool``; docstring и сигнатура
становятся JSON-схемой, которую видит модель. Поэтому docstring — часть промпта.

Инструменты сгруппированы по субагентам:
- ANALYSIS_TOOLS — анализ временных рядов цен (get_price_stats_tool);
- CHARTS_TOOLS   — построение диаграмм (visualize_prices_tool);
- OPS_TOOLS      — разовый скрапинг, watchlist и ФОНОВЫЙ мониторинг.

Источники данных и действия берутся из общих библиотек (shared.*), а параметры —
из YAML-конфига сервиса (``config``). Разовый скрапинг теперь ПУБЛИКУЕТСЯ как
задача (в режиме rabbitmq её обрабатывает масштабируемый сервис-скрапер); в
local-режиме собирается на месте. Фоновый мониторинг — неблокирующий (потоки).
"""

import os
import re
from datetime import datetime

from langchain.tools import tool

from aviatrade_agent.config import config
from shared.analytics import FlightPriceVisualizer, render_stats_report, visualize_prices
from shared.scraper import ScrapeTask
from shared.services import MONITORS, dispatch_scrape
from shared.services import get_database as _get_database

# Настроить фоновый мониторинг под конфиг этого сервиса (БД, режим скрапера, MQ).
MONITORS.configure(
    database=config.database, scraper=config.scraper, rabbitmq=config.rabbitmq
)

# Valid IATA codes for Russian cities
VALID_IATA_CODES = {
    "MOW": "Moscow",
    "LED": "Saint-Petersburg",
    "AER": "Sochi",
    "SVX": "Yekaterinburg",
    "KZN": "Kazan",
    "OVB": "Novosibirsk",
    "VVO": "Vladivostok",
    "KRR": "Krasnodar",
    "ROV": "Rostov-on-Don",
    "UFA": "Ufa",
}


def validate_iata_code(code: str) -> tuple[bool, str]:
    """Validate IATA airport code. Returns (is_valid, message)."""
    code = code.upper().strip()
    if len(code) != 3:
        return False, f"IATA code must be 3 characters, got: '{code}'"
    if not code.isalpha():
        return False, f"IATA code must contain only letters, got: '{code}'"
    return True, ""


def validate_date(date_str: str) -> tuple[bool, str]:
    """Validate date format and value. Returns (is_valid, message)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False, f"Date must be in YYYY-MM-DD format, got: '{date_str}'"
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        if date_obj < today:
            return False, f"Date {date_str} is in the past. Please use a future date."
        return True, ""
    except ValueError as e:
        return False, f"Invalid date: {e}"


def get_database():
    """Get database connection with error handling. Returns (db, error_message).

    Использует кэширующую фабрику shared.services (один Database на DSN + auto
    create_tables), DSN берётся из конфига сервиса.
    """
    try:
        return _get_database(config.database), ""
    except Exception as e:
        return (
            None,
            f"Database connection error: {e}. Make sure PostgreSQL is running (docker-compose up -d)",
        )


# ===========================================================================
# OPS: разовый скрапинг (публикуется как задача; см. режим scraper.mode)
# ===========================================================================
@tool
def scrape_and_save_tool(origin: str, destination: str, departure_date: str) -> str:
    """Collect current flight prices from Aviasales for a route and save them.

    Submits a scraping job. In production (rabbitmq mode) the job is queued and a
    scalable scraper service collects + stores the data shortly after; in local
    mode the data is scraped and saved immediately.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        Status message indicating the job was submitted (or saved count in local mode)
    """
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    valid, msg = validate_iata_code(origin)
    if not valid:
        return f"ERROR: Invalid origin code. {msg}"
    valid, msg = validate_iata_code(destination)
    if not valid:
        return f"ERROR: Invalid destination code. {msg}"
    valid, msg = validate_date(departure_date)
    if not valid:
        return f"ERROR: {msg}"
    if origin == destination:
        return "ERROR: Origin and destination cannot be the same."

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        result = dispatch_scrape(
            ScrapeTask(origin=origin, destination=destination, departure_date=departure_date),
            scraper=config.scraper,
            rabbitmq=config.rabbitmq,
            db=db,
        )
    except Exception as e:
        return f"ERROR: Failed to submit scrape: {e}"

    if result is None:
        return (
            f"SUCCESS: Scrape task queued for {origin} -> {destination} on {departure_date}.\n"
            "Data will be collected shortly by the scraper service. Use "
            "get_price_stats_tool a bit later to analyze it."
        )
    if result > 0:
        return (
            f"SUCCESS: Scraped and saved {result} flights for {origin} -> {destination} "
            f"on {departure_date}. You can now use get_price_stats_tool."
        )
    return (
        f"WARNING: No flights found for {origin} -> {destination} on {departure_date} "
        "(no availability, invalid codes, or route not served)."
    )


# ===========================================================================
# CHARTS: построение диаграмм
# ===========================================================================
@tool
def visualize_prices_tool(origin: str, destination: str, departure_date: str) -> str:
    """Generate a visual price chart from stored flight data.

    Creates a matplotlib visualization (price trends, airline comparison, price
    distribution) and returns a markdown image link the user can see in the chat.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        A markdown image link to the generated chart, or an error/warning message
    """
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    valid, msg = validate_iata_code(origin)
    if not valid:
        return f"ERROR: Invalid origin code. {msg}"
    valid, msg = validate_iata_code(destination)
    if not valid:
        return f"ERROR: Invalid destination code. {msg}"
    valid, msg = validate_date(departure_date)
    if not valid:
        return f"ERROR: {msg}"

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        visualizer = FlightPriceVisualizer(output_dir=config.charts.output_dir)
        chart_path = visualize_prices(origin, destination, departure_date, db, visualizer)
    except Exception as e:
        return f"ERROR: Failed to generate visualization: {e}"

    if not chart_path:
        return (
            f"WARNING: No stored price data for {origin} -> {destination} on "
            f"{departure_date}. Collect data first with scrape_and_save_tool, then retry."
        )

    filename = os.path.basename(chart_path)
    url = f"{config.charts.public_base_url.rstrip('/')}/{filename}"
    # Возвращаем готовую markdown-картинку и просим модель вставить её ДОСЛОВНО —
    # OpenWebUI отрендерит <img> по этой ссылке (backend отдаёт PNG статикой /static).
    return (
        f"SUCCESS: Price chart generated for {origin} -> {destination} on {departure_date}. "
        "Include the following markdown image in your reply VERBATIM so the user can see it:\n\n"
        f"![Price chart {origin}-{destination} {departure_date}]({url})"
    )


# ===========================================================================
# ANALYSIS: анализ временных рядов цен
# ===========================================================================
@tool
def get_price_stats_tool(origin: str, destination: str, departure_date: str) -> str:
    """Get detailed price statistics for flight route analysis.

    Use this tool to get comprehensive price statistics including overall metrics,
    breakdown by airline, trend analysis, and recommendations. This is the PRIMARY
    tool for analyzing flight prices.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        Detailed statistics string with price analysis ready for interpretation
    """
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    valid, msg = validate_iata_code(origin)
    if not valid:
        return f"ERROR: Invalid origin code. {msg}"
    valid, msg = validate_iata_code(destination)
    if not valid:
        return f"ERROR: Invalid destination code. {msg}"

    # For stats, we allow past dates (historical data)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", departure_date):
        return f"ERROR: Date must be in YYYY-MM-DD format, got: '{departure_date}'"

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        flight_prices = db.get_price_history(origin, destination, departure_date)
    except Exception as e:
        return f"ERROR: Failed to retrieve price data: {e}"

    return render_stats_report(origin, destination, departure_date, flight_prices)


# ===========================================================================
# OPS: управление watchlist (несколько направлений)
# ===========================================================================
@tool
def add_to_watchlist_tool(
    origin: str, destination: str, departure_date: str, interval_minutes: int = 60
) -> str:
    """Add a flight route to the multi-direction monitoring watchlist.

    Use this when the user wants to track several routes at once. Adding an
    existing route updates its interval and re-enables it.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format
        interval_minutes: Per-route collection interval in minutes (default: 60)

    Returns:
        Status message indicating success or failure
    """
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    valid, msg = validate_iata_code(origin)
    if not valid:
        return f"ERROR: Invalid origin code. {msg}"
    valid, msg = validate_iata_code(destination)
    if not valid:
        return f"ERROR: Invalid destination code. {msg}"
    valid, msg = validate_date(departure_date)
    if not valid:
        return f"ERROR: {msg}"
    if origin == destination:
        return "ERROR: Origin and destination cannot be the same."
    if interval_minutes < 1 or interval_minutes > 1440:
        return "ERROR: Interval must be between 1 and 1440 minutes."

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        record = db.add_watch(origin, destination, departure_date, interval_minutes)
        return (
            f"SUCCESS: Added {record.origin} -> {record.destination} on "
            f"{record.departure_date} to the watchlist (every {record.interval_min} min)."
        )
    except Exception as e:
        return f"ERROR: Failed to add route to watchlist: {e}"


@tool
def remove_from_watchlist_tool(origin: str, destination: str, departure_date: str) -> str:
    """Remove a flight route from the multi-direction monitoring watchlist.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        Status message indicating success or failure
    """
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", departure_date):
        return f"ERROR: Date must be in YYYY-MM-DD format, got: '{departure_date}'"

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        removed = db.remove_watch(origin, destination, departure_date)
        if removed:
            return (
                f"SUCCESS: Removed {origin} -> {destination} on "
                f"{departure_date} from the watchlist."
            )
        return (
            f"WARNING: No watchlist entry found for {origin} -> {destination} "
            f"on {departure_date}."
        )
    except Exception as e:
        return f"ERROR: Failed to remove route from watchlist: {e}"


@tool
def list_watchlist_tool() -> str:
    """List all routes on the multi-direction monitoring watchlist.

    Returns:
        A formatted list of watchlist routes, or a message if it is empty
    """
    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        routes = db.get_watchlist(enabled_only=False)
    except Exception as e:
        return f"ERROR: Failed to read watchlist: {e}"

    if not routes:
        return "The watchlist is empty. Add routes with add_to_watchlist_tool."

    lines = [f"WATCHLIST ({len(routes)} route(s)):"]
    for r in routes:
        state = "enabled" if r.enabled else "disabled"
        lines.append(
            f"- [{state}] {r.origin} -> {r.destination} on {r.departure_date} "
            f"(every {r.interval_min} min)"
        )
    return "\n".join(lines)


# ===========================================================================
# OPS: ФОНОВЫЙ мониторинг (неблокирующий)
# ===========================================================================
@tool
def start_monitor_tool(
    origin: str, destination: str, departure_date: str, interval_minutes: int = 60
) -> str:
    """Start continuous price monitoring for one route IN THE BACKGROUND.

    Launches a background thread and returns immediately, so it is safe to call
    from the agent graph. Each cycle submits a scrape job. Use
    list_active_monitors_tool to check status and stop_monitor_tool to stop.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format
        interval_minutes: Interval between scrapes in minutes (default: 60)

    Returns:
        Status message confirming the background monitor started
    """
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    valid, msg = validate_iata_code(origin)
    if not valid:
        return f"ERROR: Invalid origin code. {msg}"
    valid, msg = validate_iata_code(destination)
    if not valid:
        return f"ERROR: Invalid destination code. {msg}"
    valid, msg = validate_date(departure_date)
    if not valid:
        return f"ERROR: {msg}"
    if interval_minutes < 1 or interval_minutes > 1440:
        return "ERROR: Interval must be between 1 and 1440 minutes."

    started, message = MONITORS.start_route(
        origin, destination, departure_date, interval_minutes
    )
    prefix = "SUCCESS" if started else "WARNING"
    return f"{prefix}: {message}"


@tool
def start_watchlist_monitor_tool(default_interval_minutes: int = 60) -> str:
    """Start continuous monitoring of EVERY watchlist route IN THE BACKGROUND.

    Launches a background thread that submits scrape jobs for all enabled
    watchlist routes (honoring each route's interval) and returns immediately.

    Args:
        default_interval_minutes: Fallback interval for routes without their own

    Returns:
        Status message confirming the background watchlist monitor started
    """
    if default_interval_minutes < 1 or default_interval_minutes > 1440:
        return "ERROR: Interval must be between 1 and 1440 minutes."

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        routes = db.get_watchlist(enabled_only=True)
    except Exception as e:
        return f"ERROR: Failed to read watchlist: {e}"

    if not routes:
        return (
            "ERROR: The watchlist has no enabled routes. "
            "Add routes with add_to_watchlist_tool first."
        )

    started, message = MONITORS.start_watchlist(default_interval_minutes)
    prefix = "SUCCESS" if started else "WARNING"
    return f"{prefix}: {message}"


@tool
def stop_monitor_tool(monitor_key: str) -> str:
    """Stop a running background monitor by its key.

    Use list_active_monitors_tool first to get the key. For a single route the
    key looks like 'MOW-AER-2025-12-15'; for the watchlist monitor it is
    'watchlist'.

    Args:
        monitor_key: The key of the monitor to stop

    Returns:
        Status message indicating whether the monitor was stopped
    """
    stopped, message = MONITORS.stop(monitor_key.strip())
    prefix = "SUCCESS" if stopped else "WARNING"
    return f"{prefix}: {message}"


@tool
def list_active_monitors_tool() -> str:
    """List all currently running background monitors and their status.

    Returns:
        A formatted list of active monitors, or a message if none are running
    """
    monitors = MONITORS.list_active()
    if not monitors:
        return "No background monitors are currently running."

    lines = [f"ACTIVE MONITORS ({len(monitors)}):"]
    for m in monitors:
        status = "alive" if m["alive"] else "stopped"
        line = (
            f"- [{m['key']}] {m['description']} - every {m['interval_minutes']} min "
            f"({status}, {m['cycles']} cycle(s), started {m['started_at']}"
        )
        if m["last_run"]:
            line += f", last run {m['last_run']}"
        if m["last_error"]:
            line += f", last error: {m['last_error']}"
        line += ")"
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# Группировка инструментов по субагентам
# ===========================================================================
ANALYSIS_TOOLS = [get_price_stats_tool]

CHARTS_TOOLS = [visualize_prices_tool]

OPS_TOOLS = [
    scrape_and_save_tool,
    add_to_watchlist_tool,
    remove_from_watchlist_tool,
    list_watchlist_tool,
    start_monitor_tool,
    start_watchlist_monitor_tool,
    stop_monitor_tool,
    list_active_monitors_tool,
]
