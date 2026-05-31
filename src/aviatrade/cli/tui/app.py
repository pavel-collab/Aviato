"""Main Textual TUI application for AviaTrade."""

import asyncio
import os
import time
import uuid
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select, TabbedContent, TabPane
from textual.worker import Worker, get_current_worker

from aviatrade.cli.tui.widgets import AgentPanel, ChartPanel, LogPanel, StatusIndicator
from aviatrade.cli.tui.workers import redirect_output_to_tui
from aviatrade.db import Database
from aviatrade.scraper import AviasalesScraper
from aviatrade.visualization import FlightPriceVisualizer


class AviaTradeApp(App):
    """Textual TUI application for AviaTrade flight price monitoring."""

    CSS_PATH = "styles.tcss"
    TITLE = "AviaTrade - Flight Price Monitor"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "cancel_operation", "Cancel"),
        Binding("f5", "execute", "Execute"),
        Binding("1", "chart_price_history", "Price History"),
        Binding("2", "chart_airlines", "Airlines"),
        Binding("3", "chart_distribution", "Distribution"),
    ]

    def __init__(self) -> None:
        """Initialize the application."""
        super().__init__()
        self.db: Database | None = None
        self.visualizer: FlightPriceVisualizer | None = None
        self._current_worker: Worker[Any] | None = None
        self._monitor_running = False
        self._chart_data: dict[str, Any] | None = None
        self._agent_graph = None
        self._agent_messages: list = []

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with Container(id="main-container"):
            with Vertical(id="input-panel"):
                yield Label("Flight Search Parameters", id="form-title")

                yield Label("Origin (IATA):", classes="form-label")
                yield Input(placeholder="MOW", id="origin-input")

                yield Label("Destination (IATA):", classes="form-label")
                yield Input(placeholder="LED", id="destination-input")

                yield Label("Departure Date:", classes="form-label")
                yield Input(placeholder="YYYY-MM-DD", id="date-input")

                yield Label("Interval (minutes):", classes="form-label")
                yield Input(placeholder="60", id="interval-input", value="60")

                yield Label("Action:", classes="form-label")
                yield Select(
                    [
                        ("Scrape + Visualize", "both"),
                        ("Scrape Flights", "scrape"),
                        ("Visualize Data", "visualize"),
                        ("Monitor Prices", "monitor"),
                        ("Add to Watchlist", "watch-add"),
                        ("Remove from Watchlist", "watch-remove"),
                        ("Show Watchlist", "watch-list"),
                        ("Monitor Watchlist", "monitor-all"),
                        ("AI Agent", "agent"),
                    ],
                    id="action-select",
                    value="both",
                )

                with Horizontal(id="button-row"):
                    yield Button("Execute", id="execute-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn", variant="error", disabled=True)

                yield AgentPanel(id="agent-panel")

            with Vertical(id="output-panel"):
                yield StatusIndicator(id="status-indicator")
                with TabbedContent(id="output-tabs"):
                    with TabPane("Log", id="tab-log"):
                        yield LogPanel(id="log-panel", highlight=True, markup=True)
                    with TabPane("Chart", id="tab-chart"):
                        yield ChartPanel(id="chart-panel")
                        yield Label(
                            "[1] Price History  [2] Airlines  [3] Distribution",
                            id="chart-hint",
                        )

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize on app mount."""
        self._log("AviaTrade TUI started")
        self._log("Connecting to database...")
        await self._initialize_database()
        # Hide agent panel initially
        self.query_one("#agent-panel", AgentPanel).display = False

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle action select change."""
        if event.select.id == "action-select":
            agent_panel = self.query_one("#agent-panel", AgentPanel)
            if event.value == "agent":
                agent_panel.display = True
                self._log("AI Agent mode selected")
                self._log("Enter your request in the agent input field below")
                return

            agent_panel.display = False

            if event.value == "watch-add":
                self._log("Add to Watchlist: fill Origin, Destination, Date and Interval")
            elif event.value == "watch-remove":
                self._log("Remove from Watchlist: fill Origin, Destination and Date")
            elif event.value == "watch-list":
                self._log("Show Watchlist: press Execute (no route fields needed)")
            elif event.value == "monitor-all":
                self._log(
                    "Monitor Watchlist: scrapes every watched route; "
                    "Interval is the default for routes without their own"
                )

    async def _initialize_database(self) -> None:
        """Initialize database connection."""
        self._set_status("loading", "Connecting to database...")
        try:
            self.db = Database()
            self.db.create_tables()
            self.visualizer = FlightPriceVisualizer()
            self._log_success("Database connected successfully")
            self._set_status("success", "Ready")
        except Exception as e:
            self._log_error(f"Database error: {e}")
            self._log("Make sure PostgreSQL is running (docker-compose up -d)")
            self._set_status("error", "Database connection failed")

    def _log(self, message: str) -> None:
        """Write message to log panel."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.write_log(message)

    def _log_success(self, message: str) -> None:
        """Write success message to log panel."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.write_success(message)

    def _log_error(self, message: str) -> None:
        """Write error message to log panel."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.write_error(message)

    def _log_warning(self, message: str) -> None:
        """Write warning message to log panel."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.write_warning(message)

    def _set_status(self, status: str, message: str) -> None:
        """Update status indicator."""
        indicator = self.query_one("#status-indicator", StatusIndicator)
        indicator.update_status(status, message)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "execute-btn":
            await self._execute_action()
        elif event.button.id == "cancel-btn":
            self._cancel_operation()

    def action_execute(self) -> None:
        """Execute action via keyboard shortcut."""
        asyncio.create_task(self._execute_action())

    def action_cancel_operation(self) -> None:
        """Cancel operation via keyboard shortcut."""
        self._cancel_operation()

    def action_chart_price_history(self) -> None:
        """Show price history chart."""
        self._show_chart("price_history")

    def action_chart_airlines(self) -> None:
        """Show airlines chart."""
        self._show_chart("airlines")

    def action_chart_distribution(self) -> None:
        """Show price distribution chart."""
        self._show_chart("distribution")

    def _show_chart(self, chart_type: str) -> None:
        """Switch to chart tab and display the specified chart type."""
        # Switch to chart tab
        tabs = self.query_one("#output-tabs", TabbedContent)
        tabs.active = "tab-chart"

        chart_panel = self.query_one("#chart-panel", ChartPanel)

        if not self._chart_data:
            self._log_warning("No chart data available. Run visualization first.")
            return

        if chart_type == "price_history":
            chart_panel.plot_price_history(
                self._chart_data["timestamps"],
                self._chart_data["min_prices"],
                title=f"Min Price Over Time (Avg: {self._chart_data['avg_price']:.0f} RUB)",
            )
        elif chart_type == "airlines":
            chart_panel.plot_airline_prices(
                self._chart_data["airline_stats"],
                title="Price by Airline",
            )
        elif chart_type == "distribution":
            chart_panel.plot_price_distribution(
                self._chart_data["all_prices"],
                title=f"Price Distribution ({self._chart_data['total_flights']} flights)",
            )

    def _update_chart(self, chart_data: dict[str, Any]) -> None:
        """Update chart data and display price history chart."""
        self._chart_data = chart_data
        # Switch to chart tab and show default chart
        tabs = self.query_one("#output-tabs", TabbedContent)
        tabs.active = "tab-chart"

        chart_panel = self.query_one("#chart-panel", ChartPanel)
        chart_panel.plot_price_history(
            chart_data["timestamps"],
            chart_data["min_prices"],
            title=f"Min Price Over Time (Avg: {chart_data['avg_price']:.0f} RUB)",
        )

    async def _execute_action(self) -> None:
        """Execute the selected action."""
        if self.db is None:
            self._log_error("Database not connected")
            return

        origin = self.query_one("#origin-input", Input).value.strip().upper()
        destination = self.query_one("#destination-input", Input).value.strip().upper()
        date_str = self.query_one("#date-input", Input).value.strip()
        interval_str = self.query_one("#interval-input", Input).value.strip() or "60"
        action = self.query_one("#action-select", Select).value

        # Actions that operate on the whole watchlist don't need a single route.
        route_optional_actions = {"watch-list", "monitor-all", "agent"}

        if action not in route_optional_actions:
            if not all([origin, destination, date_str]):
                self._log_error("Please fill all required fields (Origin, Destination, Date)")
                self._set_status("error", "Missing required fields")
                return

            try:
                departure_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if departure_date < datetime.now().date():
                    self._log_warning(f"Date {date_str} is in the past")
            except ValueError:
                self._log_error("Invalid date format. Use YYYY-MM-DD")
                self._set_status("error", "Invalid date format")
                return

        try:
            interval = int(interval_str)
            if interval < 1:
                raise ValueError("Interval must be positive")
        except ValueError:
            self._log_error("Invalid interval. Must be a positive number")
            self._set_status("error", "Invalid interval")
            return

        self.query_one("#execute-btn", Button).disabled = True
        self.query_one("#cancel-btn", Button).disabled = False

        if action == "scrape":
            self._current_worker = self.run_worker(
                partial(self._scrape_worker, origin, destination, date_str),
                name="scrape",
                exclusive=True,
                thread=True,
            )
        elif action == "visualize":
            self._current_worker = self.run_worker(
                partial(self._visualize_worker, origin, destination, date_str),
                name="visualize",
                exclusive=True,
                thread=True,
            )
        elif action == "monitor":
            self._monitor_running = True
            self._current_worker = self.run_worker(
                partial(self._monitor_worker, origin, destination, date_str, interval),
                name="monitor",
                exclusive=True,
                thread=True,
            )
        elif action == "both":
            self._current_worker = self.run_worker(
                partial(self._both_worker, origin, destination, date_str),
                name="both",
                exclusive=True,
                thread=True,
            )
        elif action == "watch-add":
            self._watch_add(origin, destination, date_str, interval)
        elif action == "watch-remove":
            self._watch_remove(origin, destination, date_str)
        elif action == "watch-list":
            self._watch_list()
        elif action == "monitor-all":
            self._monitor_running = True
            self._current_worker = self.run_worker(
                partial(self._monitor_watchlist_worker, interval),
                name="monitor-all",
                exclusive=True,
                thread=True,
            )
        else:
            # No-op actions (e.g. "agent" is driven by the agent panel).
            self._reset_buttons()

    def _watch_add(self, origin: str, destination: str, date: str, interval: int) -> None:
        """Add a route to the watchlist (fast DB operation, runs inline)."""
        try:
            record = self.db.add_watch(origin, destination, date, interval)
            self._log_success(
                f"Added to watchlist: {record.origin} -> {record.destination} "
                f"on {record.departure_date} (every {record.interval_min} min)"
            )
            self._set_status("success", "Route added to watchlist")
        except Exception as e:
            self._log_error(f"Failed to add route: {e}")
            self._set_status("error", str(e))
        finally:
            self._reset_buttons()

    def _watch_remove(self, origin: str, destination: str, date: str) -> None:
        """Remove a route from the watchlist (fast DB operation, runs inline)."""
        try:
            removed = self.db.remove_watch(origin, destination, date)
            if removed:
                self._log_success(
                    f"Removed from watchlist: {origin} -> {destination} on {date}"
                )
                self._set_status("success", "Route removed from watchlist")
            else:
                self._log_warning(
                    f"No watchlist entry for {origin} -> {destination} on {date}"
                )
                self._set_status("warning", "Route not found in watchlist")
        except Exception as e:
            self._log_error(f"Failed to remove route: {e}")
            self._set_status("error", str(e))
        finally:
            self._reset_buttons()

    def _watch_list(self) -> None:
        """Show the current watchlist in the log panel (fast DB op, runs inline)."""
        try:
            routes = self.db.get_watchlist(enabled_only=False)
            if not routes:
                self._log_warning("Watchlist is empty. Use 'Add to Watchlist' action.")
            else:
                self._log_success(f"Watchlist ({len(routes)} route(s)):")
                for r in routes:
                    state = "enabled" if r.enabled else "disabled"
                    self._log(
                        f"  [{state}] {r.origin} -> {r.destination}  "
                        f"{r.departure_date}  every {r.interval_min} min"
                    )
            self._set_status("success", "Ready")
        except Exception as e:
            self._log_error(f"Failed to read watchlist: {e}")
            self._set_status("error", str(e))
        finally:
            self._reset_buttons()

    def _scrape_route_once(self, origin: str, destination: str, date: str) -> int:
        """Scrape one route and persist it. Returns saved count. Runs in a worker thread."""
        search_params = {
            "origin": origin,
            "destination": destination,
            "departure_date": date,
        }
        flights = AviasalesScraper.scrape_flights(search_params)
        if not flights:
            return 0

        saved = 0
        for flight in flights:
            try:
                flight_for_db = flight.copy()
                flight_for_db["id"] = uuid.uuid4().int % 2147483647
                if isinstance(flight_for_db.get("departure_date"), str):
                    flight_for_db["departure_date"] = datetime.strptime(
                        flight_for_db["departure_date"], "%Y-%m-%d"
                    ).date()
                if isinstance(flight_for_db.get("scraped_at"), str):
                    flight_for_db["scraped_at"] = datetime.fromisoformat(
                        flight_for_db["scraped_at"]
                    )
                self.db.add_flight_price(flight_for_db)
                saved += 1
            except Exception:
                pass
        return saved

    def _monitor_watchlist_worker(self, default_interval_minutes: int) -> None:
        """Worker for continuous monitoring of every enabled watchlist route.

        Re-reads the watchlist each cycle (so routes added/removed are picked up
        live), scrapes due routes sequentially, and honors each route's own
        ``interval_min`` (falling back to ``default_interval_minutes``).
        """
        worker = get_current_worker()

        def log_to_tui(msg: str) -> None:
            if not worker.is_cancelled:
                self.call_from_thread(self._log, msg)

        def route_key(route: Any) -> tuple[str, str, str]:
            return (route.origin, route.destination, str(route.departure_date))

        next_due: dict[tuple[str, str, str], float] = {}
        cycle = 1

        self.call_from_thread(
            self._log,
            f"Starting watchlist monitor (default interval: {default_interval_minutes}min)",
        )

        try:
            while not worker.is_cancelled and self._monitor_running:
                routes = self.db.get_watchlist(enabled_only=True)

                if not routes:
                    self.call_from_thread(
                        self._log_warning, "Watchlist is empty. Add routes to monitor."
                    )
                    self.call_from_thread(
                        self._set_status, "warning", "Watchlist empty - waiting..."
                    )
                    self._interruptible_sleep(worker, default_interval_minutes * 60)
                    continue

                now = time.monotonic()
                due_routes = [r for r in routes if next_due.get(route_key(r), 0.0) <= now]

                if due_routes:
                    self.call_from_thread(
                        self._set_status,
                        "loading",
                        f"Watchlist cycle #{cycle} ({len(due_routes)} due)...",
                    )
                    self.call_from_thread(self._log, f"--- Watchlist cycle #{cycle} ---")

                    for route in due_routes:
                        if worker.is_cancelled or not self._monitor_running:
                            break
                        self.call_from_thread(
                            self._log,
                            f"Scraping {route.origin} -> {route.destination} "
                            f"({route.departure_date})",
                        )
                        try:
                            with redirect_output_to_tui(log_to_tui):
                                saved = self._scrape_route_once(
                                    route.origin, route.destination, str(route.departure_date)
                                )
                            if saved:
                                self.call_from_thread(
                                    self._log_success,
                                    f"{route.origin}->{route.destination}: saved {saved} flights",
                                )
                            else:
                                self.call_from_thread(
                                    self._log_warning,
                                    f"{route.origin}->{route.destination}: no flights found",
                                )
                        except Exception as e:
                            self.call_from_thread(
                                self._log_error,
                                f"{route.origin}->{route.destination} error: {e}",
                            )
                        interval = route.interval_min or default_interval_minutes
                        next_due[route_key(route)] = time.monotonic() + interval * 60

                    cycle += 1

                # Sleep until the nearest route becomes due (capped, interruptible).
                now = time.monotonic()
                active_keys = {route_key(r) for r in routes}
                upcoming = [t for k, t in next_due.items() if k in active_keys and t > now]
                sleep_seconds = (
                    min(upcoming) - now if upcoming else default_interval_minutes * 60
                )
                sleep_seconds = max(1.0, min(sleep_seconds, default_interval_minutes * 60))
                self.call_from_thread(
                    self._set_status,
                    "loading",
                    f"Next route due in {sleep_seconds / 60:.1f}min...",
                )
                self._interruptible_sleep(worker, sleep_seconds)

            self.call_from_thread(
                self._log, f"Watchlist monitor stopped after {cycle - 1} cycle(s)"
            )
            self.call_from_thread(self._set_status, "success", "Monitor stopped")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Watchlist monitor error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self._monitor_running = False
            self.call_from_thread(self._reset_buttons)

    def _interruptible_sleep(self, worker: Worker[Any], seconds: float) -> None:
        """Sleep in 1-second steps, breaking early on cancel or monitor stop."""
        for _ in range(int(seconds)):
            if worker.is_cancelled or not self._monitor_running:
                break
            time.sleep(1)

    def _scrape_worker(self, origin: str, destination: str, date: str) -> int:
        """Worker for scraping operation."""
        worker = get_current_worker()

        def log_to_tui(msg: str) -> None:
            if not worker.is_cancelled:
                self.call_from_thread(self._log, msg)

        self.call_from_thread(self._set_status, "loading", "Scraping flights...")
        self.call_from_thread(self._log, f"Route: {origin} -> {destination}, Date: {date}")

        try:
            with redirect_output_to_tui(log_to_tui):
                search_params = {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": date,
                }

                if worker.is_cancelled:
                    return 0

                flights = AviasalesScraper.scrape_flights(search_params)

                if not flights:
                    self.call_from_thread(self._log_warning, "No flights found")
                    self.call_from_thread(self._set_status, "warning", "No flights found")
                    return 0

                if worker.is_cancelled:
                    return 0

                saved_count = 0
                for flight in flights:
                    try:
                        flight_for_db = flight.copy()
                        flight_for_db["id"] = uuid.uuid4().int % 2147483647

                        if isinstance(flight_for_db.get("departure_date"), str):
                            flight_for_db["departure_date"] = datetime.strptime(
                                flight_for_db["departure_date"], "%Y-%m-%d"
                            ).date()
                        if isinstance(flight_for_db.get("scraped_at"), str):
                            flight_for_db["scraped_at"] = datetime.fromisoformat(
                                flight_for_db["scraped_at"]
                            )

                        self.db.add_flight_price(flight_for_db)
                        saved_count += 1
                    except Exception as e:
                        self.call_from_thread(self._log_warning, f"Error saving flight: {e}")

                self.call_from_thread(
                    self._log_success, f"Saved {saved_count} of {len(flights)} flights"
                )
                self.call_from_thread(self._set_status, "success", f"Saved {saved_count} flights")
                return saved_count

        except Exception as e:
            self.call_from_thread(self._log_error, f"Scrape error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
            return 0
        finally:
            self.call_from_thread(self._reset_buttons)

    def _visualize_worker(self, origin: str, destination: str, date: str) -> None:
        """Worker for visualization operation."""
        worker = get_current_worker()

        def log_to_tui(msg: str) -> None:
            if not worker.is_cancelled:
                self.call_from_thread(self._log, msg)

        self.call_from_thread(self._set_status, "loading", "Loading price history...")

        try:
            with redirect_output_to_tui(log_to_tui):
                flight_prices = self.db.get_price_history(origin, destination, date)

                if not flight_prices:
                    self.call_from_thread(
                        self._log_warning, "No data in database for visualization"
                    )
                    self.call_from_thread(self._log, "First collect data with Scrape action")
                    self.call_from_thread(self._set_status, "warning", "No data found")
                    return

                self.call_from_thread(self._log, f"Found {len(flight_prices)} records in database")

                if worker.is_cancelled:
                    return

                self.visualizer.print_statistics(flight_prices)

                if worker.is_cancelled:
                    return

                # Generate TUI chart data
                chart_data = self.visualizer.get_tui_chart_data(flight_prices)
                if chart_data:
                    self.call_from_thread(self._update_chart, chart_data)
                    self.call_from_thread(
                        self._log_success, "Chart displayed. Use [1][2][3] to switch views"
                    )

                # Also save PNG chart
                chart_path = self.visualizer.plot_price_history(
                    flight_prices, origin, destination, date
                )

                if chart_path:
                    self.call_from_thread(self._log_success, f"PNG saved: {Path(chart_path).name}")
                    self.call_from_thread(self._set_status, "success", "Visualization complete")
                else:
                    self.call_from_thread(self._set_status, "success", "Statistics shown")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Visualization error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self.call_from_thread(self._reset_buttons)

    def _monitor_worker(
        self, origin: str, destination: str, date: str, interval_minutes: int
    ) -> None:
        """Worker for continuous monitoring."""
        worker = get_current_worker()
        iteration = 1

        def log_to_tui(msg: str) -> None:
            if not worker.is_cancelled:
                self.call_from_thread(self._log, msg)

        self.call_from_thread(
            self._log,
            f"Starting monitor: {origin}->{destination}, interval: {interval_minutes}min",
        )

        try:
            while not worker.is_cancelled and self._monitor_running:
                self.call_from_thread(
                    self._set_status, "loading", f"Monitor iteration #{iteration}..."
                )
                self.call_from_thread(self._log, f"--- Iteration #{iteration} ---")

                with redirect_output_to_tui(log_to_tui):
                    try:
                        search_params = {
                            "origin": origin,
                            "destination": destination,
                            "departure_date": date,
                        }
                        flights = AviasalesScraper.scrape_flights(search_params)

                        if flights:
                            saved_count = 0
                            for flight in flights:
                                try:
                                    flight_for_db = flight.copy()
                                    flight_for_db["id"] = uuid.uuid4().int % 2147483647
                                    if isinstance(flight_for_db.get("departure_date"), str):
                                        flight_for_db["departure_date"] = datetime.strptime(
                                            flight_for_db["departure_date"], "%Y-%m-%d"
                                        ).date()
                                    if isinstance(flight_for_db.get("scraped_at"), str):
                                        flight_for_db["scraped_at"] = datetime.fromisoformat(
                                            flight_for_db["scraped_at"]
                                        )
                                    self.db.add_flight_price(flight_for_db)
                                    saved_count += 1
                                except Exception:
                                    pass
                            self.call_from_thread(
                                self._log_success,
                                f"Iteration #{iteration}: saved {saved_count} flights",
                            )
                        else:
                            self.call_from_thread(
                                self._log_warning,
                                f"Iteration #{iteration}: no flights found",
                            )
                    except Exception as e:
                        self.call_from_thread(self._log_error, f"Iteration #{iteration} error: {e}")

                iteration += 1

                self.call_from_thread(
                    self._set_status,
                    "loading",
                    f"Waiting {interval_minutes}min until next...",
                )

                for _ in range(interval_minutes * 60):
                    if worker.is_cancelled or not self._monitor_running:
                        break
                    time.sleep(1)

            self.call_from_thread(self._log, f"Monitor stopped after {iteration - 1} iterations")
            self.call_from_thread(self._set_status, "success", "Monitor stopped")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Monitor error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self._monitor_running = False
            self.call_from_thread(self._reset_buttons)

    def _both_worker(self, origin: str, destination: str, date: str) -> None:
        """Worker for scrape + visualize operation."""
        worker = get_current_worker()

        def log_to_tui(msg: str) -> None:
            if not worker.is_cancelled:
                self.call_from_thread(self._log, msg)

        try:
            self.call_from_thread(self._set_status, "loading", "Scraping flights...")
            self.call_from_thread(self._log, f"Route: {origin} -> {destination}, Date: {date}")

            with redirect_output_to_tui(log_to_tui):
                search_params = {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": date,
                }

                flights = AviasalesScraper.scrape_flights(search_params)

                if not flights:
                    self.call_from_thread(self._log_warning, "No flights found")
                    self.call_from_thread(self._set_status, "warning", "No flights found")
                    return

                if worker.is_cancelled:
                    return

                saved_count = 0
                for flight in flights:
                    try:
                        flight_for_db = flight.copy()
                        flight_for_db["id"] = uuid.uuid4().int % 2147483647
                        if isinstance(flight_for_db.get("departure_date"), str):
                            flight_for_db["departure_date"] = datetime.strptime(
                                flight_for_db["departure_date"], "%Y-%m-%d"
                            ).date()
                        if isinstance(flight_for_db.get("scraped_at"), str):
                            flight_for_db["scraped_at"] = datetime.fromisoformat(
                                flight_for_db["scraped_at"]
                            )
                        self.db.add_flight_price(flight_for_db)
                        saved_count += 1
                    except Exception:
                        pass

                self.call_from_thread(
                    self._log_success, f"Saved {saved_count} of {len(flights)} flights"
                )

                if worker.is_cancelled or saved_count == 0:
                    self.call_from_thread(
                        self._set_status, "warning", "Scrape complete, no visualization"
                    )
                    return

                self.call_from_thread(self._set_status, "loading", "Generating visualization...")

                flight_prices = self.db.get_price_history(origin, destination, date)
                if flight_prices:
                    self.visualizer.print_statistics(flight_prices)

                    # Generate TUI chart
                    chart_data = self.visualizer.get_tui_chart_data(flight_prices)
                    if chart_data:
                        self.call_from_thread(self._update_chart, chart_data)
                        self.call_from_thread(
                            self._log_success, "Chart displayed. Use [1][2][3] to switch views"
                        )

                    # Also save PNG chart
                    chart_path = self.visualizer.plot_price_history(
                        flight_prices, origin, destination, date
                    )
                    if chart_path:
                        self.call_from_thread(
                            self._log_success, f"PNG saved: {Path(chart_path).name}"
                        )

                self.call_from_thread(self._set_status, "success", "Scrape + Visualize complete")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self.call_from_thread(self._reset_buttons)

    def _cancel_operation(self) -> None:
        """Cancel the current operation."""
        self._monitor_running = False
        if self._current_worker and not self._current_worker.is_cancelled:
            self._current_worker.cancel()
            self._log_warning("Operation cancelled by user")
            self._set_status("warning", "Cancelled")
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        """Reset button states."""
        self.query_one("#execute-btn", Button).disabled = False
        self.query_one("#cancel-btn", Button).disabled = True

    def _initialize_agent(self) -> bool:
        """Initialize the AI agent."""
        if self._agent_graph is not None:
            return True

        api_key = os.getenv("OPENROUTER_API_KEY")
        model_name = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
        if not api_key:
            self._log_error("OPENROUTER_API_KEY not set in environment")
            self._log("Set it in your .env file or export OPENROUTER_API_KEY=your_key")
            return False

        try:
            from aviatrade.agent.agent import AgentFactory

            self._agent_graph = AgentFactory.build_agent(model_name=model_name, api_key=api_key)
            self._log_success(f"AI Agent initialized successfully (model: {model_name})")
            return True
        except Exception as e:
            self._log_error(f"Failed to initialize agent: {e}")
            return False

    def on_agent_panel_agent_submit(self, event: AgentPanel.AgentSubmit) -> None:
        """Handle agent submit event from AgentPanel."""
        user_input = event.message.strip()
        if not user_input:
            return

        self._log(f"[bold cyan]You:[/bold cyan] {user_input}")

        self.query_one("#cancel-btn", Button).disabled = False
        self._current_worker = self.run_worker(
            partial(self._agent_worker, user_input),
            name="agent",
            exclusive=True,
            thread=True,
        )

    def _agent_worker(self, user_input: str) -> None:
        """Worker for agent interaction."""
        worker = get_current_worker()

        def log_to_tui(msg: str) -> None:
            if not worker.is_cancelled:
                self.call_from_thread(self._log, msg)

        self.call_from_thread(self._set_status, "loading", "Agent is thinking...")

        try:
            if not self.call_from_thread(self._initialize_agent):
                self.call_from_thread(self._set_status, "error", "Agent not initialized")
                return

            from langchain_core.messages import AIMessage, HumanMessage

            # Add user message to history
            self._agent_messages.append(HumanMessage(content=user_input))

            with redirect_output_to_tui(log_to_tui):
                if worker.is_cancelled:
                    return
                final_state = self._agent_graph.invoke({"messages": self._agent_messages})

            if worker.is_cancelled:
                return

            # Find and display the last AI message
            for msg in reversed(final_state["messages"]):
                if isinstance(msg, AIMessage) and msg.content:
                    self._agent_messages.append(msg)
                    self.call_from_thread(
                        self._log, f"[bold green]Agent:[/bold green] {msg.content}"
                    )
                    break

            self.call_from_thread(self._set_status, "success", "Agent ready")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Agent error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self.call_from_thread(self._reset_buttons)
