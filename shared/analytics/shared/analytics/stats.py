"""Статистика цен: структурированная (для API) и текстовый отчёт (для агента).

Единое место для расчёта статистики — раньше логика дублировалась в
``backend/actions.price_stats`` (dict) и ``agent/tools.get_price_stats_tool``
(текст). ``compute_price_stats`` отдаёт dict для JSON-ответа, ``render_stats_report``
— человекочитаемый отчёт для субагента-аналитика.

Обе функции принимают ``history`` — список ORM-объектов FlightPrice
(результат ``Database.get_price_history``).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def compute_price_stats(
    origin: str, destination: str, departure_date: str, history: list[Any]
) -> dict[str, Any]:
    """Структурированная статистика по маршруту для JSON-ответа API."""
    if not history:
        return {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "data_points": 0,
            "stats": None,
        }

    df = pd.DataFrame(
        [
            {
                "scraped_at": fp.scraped_at,
                "price": fp.price,
                "airline": fp.airline or "Unknown",
                "stops": fp.stops if fp.stops is not None else 0,
            }
            for fp in history
        ]
    )

    df["scraped_bin"] = df["scraped_at"].dt.floor("1h")
    trend = df.groupby("scraped_bin")["price"].min().reset_index()
    trend_change_pct: float | None = None
    if len(trend) >= 2:
        first, last = trend.iloc[0]["price"], trend.iloc[-1]["price"]
        if first:
            trend_change_pct = round((last - first) / first * 100, 1)

    airlines = (
        df.groupby("airline")["price"]
        .agg(["min", "mean", "max", "count"])
        .round(0)
        .sort_values("min")
        .head(10)
    )

    return {
        "origin": origin,
        "destination": destination,
        "departure_date": departure_date,
        "data_points": int(len(df)),
        "stats": {
            "min": round(float(df["price"].min()), 2),
            "max": round(float(df["price"].max()), 2),
            "avg": round(float(df["price"].mean()), 2),
            "median": round(float(df["price"].median()), 2),
            "currency": "RUB",
            "collection_sessions": int(len(trend)),
            "trend_change_pct": trend_change_pct,
            "direct_flights": int((df["stops"] == 0).sum()),
            "connecting_flights": int((df["stops"] > 0).sum()),
            "by_airline": [
                {
                    "airline": airline,
                    "min": float(row["min"]),
                    "avg": float(row["mean"]),
                    "max": float(row["max"]),
                    "count": int(row["count"]),
                }
                for airline, row in airlines.iterrows()
            ],
        },
    }


def render_stats_report(
    origin: str, destination: str, departure_date: str, history: list[Any]
) -> str:
    """Подробный человекочитаемый отчёт по ценам (для субагента-аналитика)."""
    if not history:
        return f"""NO DATA AVAILABLE

Route: {origin} -> {destination}
Date: {departure_date}

No price data found in database for this route and date.
Recommendation: trigger a scrape first to collect flight data."""

    data = []
    for fp in history:
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

    min_price = df["price"].min()
    max_price = df["price"].max()
    avg_price = df["price"].mean()
    median_price = df["price"].median()
    std_price = df["price"].std()
    total_records = len(df)

    price_range = max_price - min_price
    price_variance_pct = (std_price / avg_price * 100) if avg_price > 0 else 0

    airline_stats = df.groupby("airline").agg({"price": ["min", "mean", "max", "count"]}).round(0)
    airline_stats.columns = ["min_price", "avg_price", "max_price", "flight_count"]
    airline_stats = airline_stats.sort_values("min_price").head(10)

    best_deals = df.nsmallest(5, "price")[
        ["airline", "price", "departure_time", "stops", "duration"]
    ]

    direct_flights = df[df["stops"] == 0]
    connecting_flights = df[df["stops"] > 0]

    direct_avg = direct_flights["price"].mean() if len(direct_flights) > 0 else None
    connecting_avg = connecting_flights["price"].mean() if len(connecting_flights) > 0 else None

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

    result += """

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
            result += f"\n• Savings with connection: ~{savings:,.0f} RUB ({savings / direct_avg * 100:.0f}% cheaper)"
        else:
            result += f"\n• Direct flights are {abs(savings):,.0f} RUB cheaper on average"

    result += """

💡 KEY INSIGHTS
───────────────────────────────────────────────────────────────"""

    cheapest_airline = airline_stats.index[0] if len(airline_stats) > 0 else "Unknown"
    result += f"\n• Best Value Airline: {cheapest_airline} (starting from {min_price:,.0f} RUB)"

    if price_variance_pct > 30:
        result += (
            f"\n• High price variance ({price_variance_pct:.0f}%) - shop around for better deals"
        )
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
