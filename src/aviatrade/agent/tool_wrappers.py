from langchain.tools import tool
import pandas as pd

from aviatrade.cli.lib import scrape_and_save, visualize_prices, monitor_prices
from aviatrade.db import Database
from aviatrade.visualization import FlightPriceVisualizer

@tool
def scrape_and_save_tool(origin: str, destination: str, departure_date: str) -> None:
    """Scrape flights and save to database.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        db: Database instance.
    """
    try:
        db = Database()
        db.create_tables()
        print("Database ready")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("   Make sure PostgreSQL is running (docker-compose up -d)")
        return -1
    
    scrape_and_save(origin, destination, departure_date, db)

@tool
def visualize_prices_tool(origin: str, destination: str, departure_date: str) -> None:
    """Visualize price history.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
    """

    try:
        db = Database()
        db.create_tables()
        print("Database ready")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("   Make sure PostgreSQL is running (docker-compose up -d)")
        return
    
    visualizer = FlightPriceVisualizer()
    visualize_prices(origin, destination, departure_date, db, visualizer)

@tool
def monitor_prices_tool(
    origin: str,
    destination: str,
    departure_date: str,
    interval_minutes: int = 60
    ) -> None:
    """Monitor prices at specified interval.

    Args:
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        departure_date: Departure date in YYYY-MM-DD format.
        interval_minutes: Interval between scrapes in minutes.
    """

    try:
        db = Database()
        db.create_tables()
        print("Database ready")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("   Make sure PostgreSQL is running (docker-compose up -d)")
        return
    
    monitor_prices(
        origin, destination, departure_date, db, interval_minutes
    )

@tool
def get_price_stats_tool(
    origin: str,
    destination: str,
    departure_date: str
    ) -> str:
    """
    Docstring for get_price_stats_tool
    
    :param origin: Description
    :type origin: str
    :param destination: Description
    :type destination: str
    :param departure_date: Description
    :type departure_date: str

    Return
        String with statistics
    """
    try:
        db = Database()
        db.create_tables()
        print("Database ready")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("   Make sure PostgreSQL is running (docker-compose up -d)")
        return
    
    flight_prices = db.get_price_history(origin, destination, departure_date)

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
            }
        )

    df = pd.DataFrame(data)

    # 1. Minimum price over time
    interval = "1H"
    df["scraped_bin"] = df["scraped_at"].dt.floor(interval)
    min_prices = df.groupby("scraped_bin")["price"].min().reset_index()


    # 2. Average price
    avg_price = df["price"].mean()

    # 3. Top airlines
    top_airlines = df["airline"].value_counts().head(10).index
    df_top = df[df["airline"].isin(top_airlines)]

    result_str = f"""
General statistic for date: {departure_date}

Min prices: {min_prices.to_json()}

Top airlines information: {df_top.to_json()}

Average price: {avg_price}
"""