"""Custom widgets for AviaTrade TUI."""

from datetime import datetime

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import RichLog, Static


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
