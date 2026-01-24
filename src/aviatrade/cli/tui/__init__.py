"""Interactive TUI for AviaTrade flight price monitoring."""

from aviatrade.cli.tui.app import AviaTradeApp

__all__ = ["AviaTradeApp", "main"]


def main() -> None:
    """Entry point for TUI application."""
    app = AviaTradeApp()
    app.run()
