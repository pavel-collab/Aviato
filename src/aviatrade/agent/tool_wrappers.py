from langchain.tools import tool
import pandas as pd
import re
from datetime import datetime

from aviatrade.cli.lib import scrape_and_save, visualize_prices, monitor_prices
from aviatrade.db import Database
from aviatrade.visualization import FlightPriceVisualizer


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
    """Validate IATA airport code.

    Returns:
        Tuple of (is_valid, message)
    """
    code = code.upper().strip()
    if len(code) != 3:
        return False, f"IATA code must be 3 characters, got: '{code}'"
    if not code.isalpha():
        return False, f"IATA code must contain only letters, got: '{code}'"
    # We accept any 3-letter code, but warn if not in known list
    return True, ""


def validate_date(date_str: str) -> tuple[bool, str]:
    """Validate date format and value.

    Returns:
        Tuple of (is_valid, message)
    """
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return False, f"Date must be in YYYY-MM-DD format, got: '{date_str}'"

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        if date_obj < today:
            return False, f"Date {date_str} is in the past. Please use a future date."
        return True, ""
    except ValueError as e:
        return False, f"Invalid date: {e}"


def get_database() -> tuple[Database | None, str]:
    """Get database connection with error handling.

    Returns:
        Tuple of (database_instance, error_message)
    """
    try:
        db = Database()
        db.create_tables()
        return db, ""
    except Exception as e:
        return None, f"Database connection error: {e}. Make sure PostgreSQL is running (docker-compose up -d)"


@tool
def scrape_and_save_tool(origin: str, destination: str, departure_date: str) -> str:
    """Scrape current flight prices from Aviasales and save to database.

    Use this tool to collect fresh flight data for a specific route and date.
    The data will be saved to the database for later analysis.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        Status message indicating success or failure
    """
    # Validate inputs
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
        saved_count = scrape_and_save(origin, destination, departure_date, db)

        if saved_count > 0:
            return f"""SUCCESS: Scraped and saved {saved_count} flights.
Route: {origin} -> {destination}
Date: {departure_date}

You can now use get_price_stats_tool to analyze the collected data."""
        else:
            return f"""WARNING: No flights found for this route.
Route: {origin} -> {destination}
Date: {departure_date}

Possible reasons:
- No available flights on this date
- Invalid airport codes
- Route not served by Aviasales"""
    except Exception as e:
        return f"ERROR: Failed to scrape flights: {e}"

@tool
def visualize_prices_tool(origin: str, destination: str, departure_date: str) -> str:
    """Generate visual price charts from stored flight data.

    Creates matplotlib visualizations showing price trends, airline comparisons,
    and other insights. Charts are saved to the /charts directory.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        Status message indicating success or failure
    """
    # Validate inputs
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
        visualizer = FlightPriceVisualizer()
        visualize_prices(origin, destination, departure_date, db, visualizer)
        return f"""SUCCESS: Price visualization charts generated.
Route: {origin} -> {destination}
Date: {departure_date}

Charts have been saved to the /charts directory."""
    except Exception as e:
        return f"ERROR: Failed to generate visualization: {e}"


@tool
def monitor_prices_tool(
    origin: str,
    destination: str,
    departure_date: str,
    interval_minutes: int = 60
) -> str:
    """Start continuous price monitoring at specified intervals.

    WARNING: This is a long-running operation that will block until manually stopped.
    Only use when the user explicitly requests continuous monitoring.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format
        interval_minutes: Interval between scrapes in minutes (default: 60)

    Returns:
        Status message (only returned when monitoring stops)
    """
    # Validate inputs
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

    if interval_minutes < 1:
        return "ERROR: Interval must be at least 1 minute."

    if interval_minutes > 1440:
        return "ERROR: Interval cannot exceed 1440 minutes (24 hours)."

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        print(f"Starting price monitoring for {origin} -> {destination}")
        print(f"Interval: {interval_minutes} minutes. Press Ctrl+C to stop.")
        monitor_prices(origin, destination, departure_date, db, interval_minutes)
        return "Monitoring stopped."
    except KeyboardInterrupt:
        return f"""Monitoring stopped by user.
Route: {origin} -> {destination}
Interval: {interval_minutes} minutes"""
    except Exception as e:
        return f"ERROR: Monitoring failed: {e}"

@tool
def get_price_stats_tool(
    origin: str,
    destination: str,
    departure_date: str
) -> str:
    """Get detailed price statistics for flight route analysis.

    Use this tool to get comprehensive price statistics including:
    - Overall price metrics (min, max, average, median)
    - Price breakdown by airline
    - Price trend analysis over time
    - Recommendations based on data

    This is the PRIMARY tool for analyzing flight prices. Use it when users ask
    for price analysis, recommendations, or want to understand pricing patterns.

    Args:
        origin: Origin airport IATA code (e.g., MOW for Moscow)
        destination: Destination airport IATA code (e.g., AER for Sochi)
        departure_date: Departure date in YYYY-MM-DD format

    Returns:
        Detailed statistics string with price analysis ready for interpretation
    """
    # Validate inputs
    origin = origin.upper().strip()
    destination = destination.upper().strip()

    valid, msg = validate_iata_code(origin)
    if not valid:
        return f"ERROR: Invalid origin code. {msg}"

    valid, msg = validate_iata_code(destination)
    if not valid:
        return f"ERROR: Invalid destination code. {msg}"

    # For stats, we allow past dates (historical data)
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', departure_date):
        return f"ERROR: Date must be in YYYY-MM-DD format, got: '{departure_date}'"

    db, error = get_database()
    if error:
        return f"ERROR: {error}"

    try:
        flight_prices = db.get_price_history(origin, destination, departure_date)
    except Exception as e:
        return f"ERROR: Failed to retrieve price data: {e}"

    if not flight_prices:
        return f"""NO DATA AVAILABLE

Route: {origin} -> {destination}
Date: {departure_date}

No price data found in database for this route and date.
Recommendation: Use scrape_and_save_tool first to collect flight data."""

    data = []
    for fp in flight_prices:
        data.append(
            {
                "scraped_at": fp.scraped_at,
                "price": fp.price,
                "airline": fp.airline if fp.airline else "Unknown",
                "departure_date": fp.departure_date,
                "stops": fp.stops if fp.stops is not None else 0,
                "flight_number": fp.flight_number if fp.flight_number else "N/A",
                "departure_time": fp.departure_time if fp.departure_time else "N/A",
                "duration": fp.duration if fp.duration else "N/A",
            }
        )

    df = pd.DataFrame(data)

    # Overall statistics
    min_price = df["price"].min()
    max_price = df["price"].max()
    avg_price = df["price"].mean()
    median_price = df["price"].median()
    std_price = df["price"].std()
    total_records = len(df)

    # Price variance analysis
    price_range = max_price - min_price
    price_variance_pct = (std_price / avg_price * 100) if avg_price > 0 else 0

    # Airline analysis
    airline_stats = df.groupby("airline").agg({
        "price": ["min", "mean", "max", "count"]
    }).round(0)
    airline_stats.columns = ["min_price", "avg_price", "max_price", "flight_count"]
    airline_stats = airline_stats.sort_values("min_price").head(10)

    # Best deals (cheapest flights)
    best_deals = df.nsmallest(5, "price")[["airline", "price", "departure_time", "stops", "duration"]]

    # Stops analysis
    direct_flights = df[df["stops"] == 0]
    connecting_flights = df[df["stops"] > 0]

    direct_avg = direct_flights["price"].mean() if len(direct_flights) > 0 else None
    connecting_avg = connecting_flights["price"].mean() if len(connecting_flights) > 0 else None

    # Time-based trend (if multiple scrape sessions)
    df["scraped_bin"] = df["scraped_at"].dt.floor("1h")
    time_trend = df.groupby("scraped_bin")["price"].min().reset_index()

    trend_direction = "stable"
    if len(time_trend) >= 2:
        first_price = time_trend.iloc[0]["price"]
        last_price = time_trend.iloc[-1]["price"]
        price_change = ((last_price - first_price) / first_price) * 100
        if price_change > 5:
            trend_direction = f"INCREASING (+{price_change:.1f}%)"
        elif price_change < -5:
            trend_direction = f"DECREASING ({price_change:.1f}%)"
        else:
            trend_direction = f"STABLE ({price_change:+.1f}%)"

    # Build result string
    result = f"""
═══════════════════════════════════════════════════════════════
FLIGHT PRICE ANALYSIS REPORT
Route: {origin} → {destination}
Departure Date: {departure_date}
Data Points: {total_records} flights analyzed
═══════════════════════════════════════════════════════════════

📊 OVERALL PRICE STATISTICS
───────────────────────────────────────────────────────────────
• Minimum Price:  {min_price:,.0f} RUB
• Maximum Price:  {max_price:,.0f} RUB
• Average Price:  {avg_price:,.0f} RUB
• Median Price:   {median_price:,.0f} RUB
• Price Range:    {price_range:,.0f} RUB
• Price Variance: {price_variance_pct:.1f}% ({"high variance - prices vary significantly" if price_variance_pct > 30 else "moderate variance" if price_variance_pct > 15 else "low variance - stable prices"})

📈 PRICE TREND
───────────────────────────────────────────────────────────────
• Trend Direction: {trend_direction}
• Data Collection Sessions: {len(time_trend)}

✈️ TOP 5 CHEAPEST FLIGHTS
───────────────────────────────────────────────────────────────"""

    for idx, row in best_deals.iterrows():
        stops_text = "Direct" if row["stops"] == 0 else f"{row['stops']} stop(s)"
        result += f"\n• {row['price']:,.0f} RUB - {row['airline']} ({stops_text}, {row['departure_time']}, {row['duration']})"

    result += f"""

🏢 PRICE BY AIRLINE (Top 10, sorted by cheapest)
───────────────────────────────────────────────────────────────"""

    for airline, stats in airline_stats.iterrows():
        result += f"\n• {airline}: {stats['min_price']:,.0f} - {stats['max_price']:,.0f} RUB (avg: {stats['avg_price']:,.0f}, {int(stats['flight_count'])} flights)"

    result += f"""

🔄 DIRECT vs CONNECTING FLIGHTS
───────────────────────────────────────────────────────────────
• Direct Flights: {len(direct_flights)} available"""
    if direct_avg:
        result += f" (avg: {direct_avg:,.0f} RUB)"
    result += f"\n• Connecting Flights: {len(connecting_flights)} available"
    if connecting_avg:
        result += f" (avg: {connecting_avg:,.0f} RUB)"

    if direct_avg and connecting_avg:
        savings = direct_avg - connecting_avg
        if savings > 0:
            result += f"\n• Savings with connection: ~{savings:,.0f} RUB ({savings/direct_avg*100:.0f}% cheaper)"
        else:
            result += f"\n• Direct flights are {abs(savings):,.0f} RUB cheaper on average"

    result += f"""

💡 KEY INSIGHTS
───────────────────────────────────────────────────────────────"""

    # Generate insights
    cheapest_airline = airline_stats.index[0] if len(airline_stats) > 0 else "Unknown"
    result += f"\n• Best Value Airline: {cheapest_airline} (starting from {min_price:,.0f} RUB)"

    if price_variance_pct > 30:
        result += f"\n• High price variance ({price_variance_pct:.0f}%) - shop around for better deals"
    elif price_variance_pct < 15:
        result += f"\n• Low price variance ({price_variance_pct:.0f}%) - prices are consistent across airlines"

    if "INCREASING" in trend_direction:
        result += "\n• ⚠️ Prices are rising - consider booking soon"
    elif "DECREASING" in trend_direction:
        result += "\n• 📉 Prices are dropping - may be worth waiting for better deals"

    result += """
═══════════════════════════════════════════════════════════════
"""

    return result