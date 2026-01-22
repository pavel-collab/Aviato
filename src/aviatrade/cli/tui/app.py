"""Main Textual TUI application for AviaTrade."""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Select
from textual.worker import Worker, get_current_worker

from aviatrade.cli.tui.widgets import LogPanel, StatusIndicator
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
    ]

    def __init__(self) -> None:
        """Initialize the application."""
        super().__init__()
        self.db: Database | None = None
        self.visualizer: FlightPriceVisualizer | None = None
        self._current_worker: Worker[Any] | None = None
        self._monitor_running = False

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
                    ],
                    id="action-select",
                    value="both",
                )

                with Horizontal(id="button-row"):
                    yield Button("Execute", id="execute-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn", variant="error", disabled=True)

            with Vertical(id="output-panel"):
                yield StatusIndicator(id="status-indicator")
                yield Label("Application Log", id="log-title")
                yield LogPanel(id="log-panel", highlight=True, markup=True)

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize on app mount."""
        self._log("AviaTrade TUI started")
        self._log("Connecting to database...")
        await self._initialize_database()

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
                self._scrape_worker(origin, destination, date_str),
                name="scrape",
                exclusive=True,
            )
        elif action == "visualize":
            self._current_worker = self.run_worker(
                self._visualize_worker(origin, destination, date_str),
                name="visualize",
                exclusive=True,
            )
        elif action == "monitor":
            self._monitor_running = True
            self._current_worker = self.run_worker(
                self._monitor_worker(origin, destination, date_str, interval),
                name="monitor",
                exclusive=True,
            )
        elif action == "both":
            self._current_worker = self.run_worker(
                self._both_worker(origin, destination, date_str),
                name="both",
                exclusive=True,
            )

    async def _scrape_worker(self, origin: str, destination: str, date: str) -> int:
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
                self.call_from_thread(
                    self._set_status, "success", f"Saved {saved_count} flights"
                )
                return saved_count

        except Exception as e:
            self.call_from_thread(self._log_error, f"Scrape error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
            return 0
        finally:
            self.call_from_thread(self._reset_buttons)

    async def _visualize_worker(self, origin: str, destination: str, date: str) -> None:
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
                    self.call_from_thread(
                        self._log, "First collect data with Scrape action"
                    )
                    self.call_from_thread(self._set_status, "warning", "No data found")
                    return

                self.call_from_thread(
                    self._log, f"Found {len(flight_prices)} records in database"
                )

                if worker.is_cancelled:
                    return

                self.visualizer.print_statistics(flight_prices)

                if worker.is_cancelled:
                    return

                chart_path = self.visualizer.plot_price_history(
                    flight_prices, origin, destination, date
                )

                if chart_path:
                    self.call_from_thread(
                        self._log_success, f"Chart saved: {Path(chart_path).name}"
                    )
                    self.call_from_thread(
                        self._set_status, "success", "Visualization complete"
                    )
                else:
                    self.call_from_thread(self._set_status, "success", "Statistics shown")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Visualization error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self.call_from_thread(self._reset_buttons)

    async def _monitor_worker(
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
                self.call_from_thread(
                    self._log, f"--- Iteration #{iteration} ---"
                )

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
                        self.call_from_thread(
                            self._log_error, f"Iteration #{iteration} error: {e}"
                        )

                iteration += 1

                self.call_from_thread(
                    self._set_status,
                    "loading",
                    f"Waiting {interval_minutes}min until next...",
                )

                for _ in range(interval_minutes * 60):
                    if worker.is_cancelled or not self._monitor_running:
                        break
                    await asyncio.sleep(1)

            self.call_from_thread(
                self._log, f"Monitor stopped after {iteration - 1} iterations"
            )
            self.call_from_thread(self._set_status, "success", "Monitor stopped")

        except Exception as e:
            self.call_from_thread(self._log_error, f"Monitor error: {e}")
            self.call_from_thread(self._set_status, "error", str(e))
        finally:
            self._monitor_running = False
            self.call_from_thread(self._reset_buttons)

    async def _both_worker(self, origin: str, destination: str, date: str) -> None:
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
                    self.call_from_thread(self._set_status, "warning", "Scrape complete, no visualization")
                    return

                self.call_from_thread(self._set_status, "loading", "Generating visualization...")

                flight_prices = self.db.get_price_history(origin, destination, date)
                if flight_prices:
                    self.visualizer.print_statistics(flight_prices)
                    chart_path = self.visualizer.plot_price_history(
                        flight_prices, origin, destination, date
                    )
                    if chart_path:
                        self.call_from_thread(
                            self._log_success, f"Chart saved: {Path(chart_path).name}"
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
