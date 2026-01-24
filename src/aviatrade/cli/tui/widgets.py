"""Custom widgets for AviaTrade TUI."""

from datetime import datetime
from typing import Any

import plotext as plt
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import RichLog, Static
from textual_plotext import PlotextPlot


class StatusIndicator(Static):
    """Status indicator with icon and message."""

    status: reactive[str] = reactive("idle")
    message: reactive[str] = reactive("Ready")

    STATUS_CONFIG = {
        "idle": ("[dim]\u25cf[/dim]", "status-idle"),
        "loading": ("[yellow]\u25cb[/yellow]", "status-loading"),
        "success": ("[green]\u2713[/green]", "status-success"),
        "error": ("[red]\u2717[/red]", "status-error"),
        "warning": ("[orange1]\u26a0[/orange1]", "status-warning"),
    }

    def render(self) -> Text:
        """Render the status indicator."""
        icon, _ = self.STATUS_CONFIG.get(self.status, ("[dim]\u25cf[/dim]", "status-idle"))
        return Text.from_markup(f"{icon} {self.message}")

    def watch_status(self, new_status: str) -> None:
        """Update CSS class when status changes."""
        for status_name, (_, css_class) in self.STATUS_CONFIG.items():
            self.remove_class(css_class)
        _, css_class = self.STATUS_CONFIG.get(new_status, (None, "status-idle"))
        self.add_class(css_class)

    def update_status(self, status: str, message: str) -> None:
        """Update the status indicator."""
        self.status = status
        self.message = message


class LogPanel(RichLog):
    """Log panel that captures application messages with timestamps."""

    def write_log(self, message: str) -> None:
        """Write a timestamped message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.write(Text.from_markup(f"[dim]{timestamp}[/dim] {message}"))

    def write_success(self, message: str) -> None:
        """Write a success message."""
        self.write_log(f"[green]{message}[/green]")

    def write_error(self, message: str) -> None:
        """Write an error message."""
        self.write_log(f"[red]{message}[/red]")

    def write_warning(self, message: str) -> None:
        """Write a warning message."""
        self.write_log(f"[orange1]{message}[/orange1]")

    def write_info(self, message: str) -> None:
        """Write an info message."""
        self.write_log(f"[blue]{message}[/blue]")


class ChartPanel(PlotextPlot):
    """Chart panel for displaying price charts in TUI."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the chart panel."""
        super().__init__(**kwargs)
        self._has_data = False

    def on_mount(self) -> None:
        """Initialize with empty chart."""
        self.show_placeholder()

    def show_placeholder(self) -> None:
        """Show placeholder when no data available."""
        self._has_data = False
        self.plt.clear_figure()
        self.plt.title("Price Chart")
        self.plt.xlabel("Time")
        self.plt.ylabel("Price (RUB)")
        self.plt.theme("dark")
        self.refresh()

    def plot_price_history(
        self,
        timestamps: list[datetime],
        prices: list[float],
        title: str = "Minimum Price Over Time",
    ) -> None:
        """Plot price history chart.

        Args:
            timestamps: List of datetime objects for x-axis.
            prices: List of prices for y-axis.
            title: Chart title.
        """
        if not timestamps or not prices:
            self.show_placeholder()
            return

        self._has_data = True
        self.plt.clear_figure()
        self.plt.theme("dark")

        # Convert timestamps to string labels for better display
        time_labels = [ts.strftime("%H:%M") for ts in timestamps]
        x_values = list(range(len(prices)))

        self.plt.plot(x_values, prices, marker="braille", color="cyan")
        self.plt.title(title)
        self.plt.xlabel("Collection Time")
        self.plt.ylabel("Price (RUB)")

        # Set x-axis labels (show subset if too many)
        if len(time_labels) > 10:
            step = len(time_labels) // 10
            xticks = x_values[::step]
            xlabels = time_labels[::step]
        else:
            xticks = x_values
            xlabels = time_labels

        self.plt.xticks(xticks, xlabels)

        # Add horizontal line for average
        avg_price = sum(prices) / len(prices)
        self.plt.hline(avg_price, color="red")

        self.refresh()

    def plot_airline_prices(
        self,
        airline_data: dict[str, tuple[float, float, float]],
        title: str = "Price by Airline (Min/Avg/Max)",
    ) -> None:
        """Plot airline price comparison.

        Args:
            airline_data: Dict with airline name -> (min, avg, max) prices.
            title: Chart title.
        """
        if not airline_data:
            self.show_placeholder()
            return

        self._has_data = True
        self.plt.clear_figure()
        self.plt.theme("dark")

        airlines = list(airline_data.keys())[:8]  # Limit to 8 for display
        min_prices = [airline_data[a][0] for a in airlines]
        avg_prices = [airline_data[a][1] for a in airlines]
        max_prices = [airline_data[a][2] for a in airlines]

        self.plt.stacked_bar(
            airlines,
            [min_prices, [a - m for a, m in zip(avg_prices, min_prices)]],
            label=["Min", "To Avg"],
            color=["green", "yellow"],
        )

        self.plt.title(title)
        self.plt.xlabel("Airline")
        self.plt.ylabel("Price (RUB)")

        self.refresh()

    def plot_price_distribution(
        self,
        prices: list[float],
        title: str = "Price Distribution",
    ) -> None:
        """Plot price distribution histogram.

        Args:
            prices: List of prices.
            title: Chart title.
        """
        if not prices:
            self.show_placeholder()
            return

        self._has_data = True
        self.plt.clear_figure()
        self.plt.theme("dark")

        self.plt.hist(prices, bins=15, color="magenta")
        self.plt.title(title)
        self.plt.xlabel("Price (RUB)")
        self.plt.ylabel("Count")

        # Add vertical lines for mean and median
        avg_price = sum(prices) / len(prices)
        median_price = sorted(prices)[len(prices) // 2]

        self.plt.vline(avg_price, color="red")
        self.plt.vline(median_price, color="green")

        self.refresh()
