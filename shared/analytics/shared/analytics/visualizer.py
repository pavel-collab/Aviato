"""Flight price visualization module using matplotlib and seaborn."""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Configure plot style
sns.set_theme(style="whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)
plt.rcParams["font.size"] = 10


class FlightPriceVisualizer:
    """Visualizer for flight price analysis and statistics."""

    def __init__(self, output_dir: str | Path = "charts"):
        """Initialize visualizer.

        Args:
            output_dir: Directory for saving chart images.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_price_history(
        self,
        flight_prices: list[Any],
        origin: str,
        destination: str,
        departure_date: date | None = None,
    ) -> str | None:
        """Generate price history visualization.

        Args:
            flight_prices: List of FlightPrice ORM objects.
            origin: Origin airport IATA code.
            destination: Destination airport IATA code.
            departure_date: Optional departure date for filtering.

        Returns:
            Path to saved chart image, or None if no data.
        """
        if not flight_prices:
            print("No data to visualize")
            return None

        # Convert to DataFrame
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

        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(
            f"Price Analysis: {origin} -> {destination}",
            fontsize=16,
            fontweight="bold",
        )

        # 1. Minimum price over time
        interval = "1h"
        df["scraped_bin"] = df["scraped_at"].dt.floor(interval)
        min_prices = df.groupby("scraped_bin")["price"].min().reset_index()

        axes[0, 0].plot(
            min_prices["scraped_bin"],
            min_prices["price"],
            marker="o",
            linewidth=2,
            markersize=8,
            color="#2E86AB",
        )
        axes[0, 0].set_title("Minimum Price by Collection Time", fontsize=12, fontweight="bold")
        axes[0, 0].set_xlabel("Collection Time", fontsize=10)
        axes[0, 0].set_ylabel("Price (RUB)", fontsize=10)
        axes[0, 0].tick_params(axis="x", rotation=45)
        axes[0, 0].grid(True, alpha=0.3)

        # Add average line
        avg_price = df["price"].mean()
        axes[0, 0].axhline(
            y=avg_price,
            color="red",
            linestyle="--",
            label=f"Average: {avg_price:.0f} RUB",
            alpha=0.7,
        )
        axes[0, 0].legend()

        # 2. Price distribution by airline (boxplot)
        top_airlines = df["airline"].value_counts().head(10).index
        df_top = df[df["airline"].isin(top_airlines)]

        if len(df_top) > 0:
            sns.boxplot(data=df_top, y="airline", x="price", ax=axes[0, 1], palette="Set2")
            axes[0, 1].set_title("Price Distribution by Airline", fontsize=12, fontweight="bold")
            axes[0, 1].set_xlabel("Price (RUB)", fontsize=10)
            axes[0, 1].set_ylabel("Airline", fontsize=10)

        # 3. Scatter plot: all prices over time by airline
        airlines = df["airline"].unique()
        colors = sns.color_palette("husl", n_colors=min(len(airlines), 10))

        for idx, airline in enumerate(list(airlines)[:10]):
            airline_data = df[df["airline"] == airline]
            axes[1, 0].scatter(
                airline_data["scraped_at"],
                airline_data["price"],
                label=airline,
                alpha=0.6,
                s=100,
                color=colors[idx],
            )

        axes[1, 0].set_title(
            "All Prices Over Time (Top 10 Airlines)", fontsize=12, fontweight="bold"
        )
        axes[1, 0].set_xlabel("Collection Time", fontsize=10)
        axes[1, 0].set_ylabel("Price (RUB)", fontsize=10)
        axes[1, 0].tick_params(axis="x", rotation=45)
        axes[1, 0].legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
        axes[1, 0].grid(True, alpha=0.3)

        # 4. Price histogram
        axes[1, 1].hist(df["price"], bins=30, color="#A23B72", alpha=0.7, edgecolor="black")
        axes[1, 1].axvline(
            df["price"].mean(),
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Mean: {df['price'].mean():.0f} RUB",
        )
        axes[1, 1].axvline(
            df["price"].median(),
            color="green",
            linestyle="--",
            linewidth=2,
            label=f"Median: {df['price'].median():.0f} RUB",
        )
        axes[1, 1].set_title("Price Distribution", fontsize=12, fontweight="bold")
        axes[1, 1].set_xlabel("Price (RUB)", fontsize=10)
        axes[1, 1].set_ylabel("Number of Flights", fontsize=10)
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3, axis="y")

        plt.tight_layout()

        # Save chart
        filename = f"{origin}_{destination}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches="tight")
        print(f"Chart saved: {filepath}")

        plt.close(fig)

        return str(filepath)

    def print_statistics(self, flight_prices: list[Any]) -> None:
        """Print price statistics to console.

        Args:
            flight_prices: List of FlightPrice ORM objects.
        """
        if not flight_prices:
            print("No data for statistics")
            return

        prices = [fp.price for fp in flight_prices]

        print("\n" + "=" * 60)
        print("PRICE STATISTICS")
        print("=" * 60)
        print(f"Total flights found: {len(flight_prices)}")
        print(f"Minimum price: {min(prices):.2f} RUB")
        print(f"Maximum price: {max(prices):.2f} RUB")
        print(f"Average price: {sum(prices) / len(prices):.2f} RUB")
        print(f"Median price: {sorted(prices)[len(prices) // 2]:.2f} RUB")

        # Statistics by airline
        airlines: dict[str, list[float]] = {}
        for fp in flight_prices:
            airline = fp.airline if fp.airline else "Unknown"
            if airline not in airlines:
                airlines[airline] = []
            airlines[airline].append(fp.price)

        print("\nPrices by airline:")
        for airline, airline_prices in sorted(airlines.items(), key=lambda x: min(x[1])):
            avg = sum(airline_prices) / len(airline_prices)
            print(
                f"  {airline}: from {min(airline_prices):.2f} to {max(airline_prices):.2f} RUB "
                f"(avg: {avg:.2f})"
            )

        print("=" * 60 + "\n")
