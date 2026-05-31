"""Worker utilities for AviaTrade TUI."""

import sys
from collections.abc import Callable
from contextlib import contextmanager


class TUIOutputStream:
    """Custom stream that redirects output to TUI log panel."""

    def __init__(self, log_callback: Callable[[str], None]):
        """Initialize with a callback function for logging.

        Args:
            log_callback: Function to call with each line of output.
        """
        self.log_callback = log_callback
        self.buffer = ""

    def write(self, text: str) -> int:
        """Write text, calling callback for each complete line.

        Args:
            text: Text to write.

        Returns:
            Number of characters written.
        """
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.log_callback(line)
        return len(text)

    def flush(self) -> None:
        """Flush remaining buffer."""
        if self.buffer.strip():
            self.log_callback(self.buffer)
            self.buffer = ""


@contextmanager
def redirect_output_to_tui(log_callback: Callable[[str], None]):
    """Context manager to redirect stdout/stderr to TUI log panel.

    Args:
        log_callback: Function to call with each line of output.

    Yields:
        None
    """
    tui_stream = TUIOutputStream(log_callback)
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        sys.stdout = tui_stream  # type: ignore[assignment]
        sys.stderr = tui_stream  # type: ignore[assignment]
        yield
    finally:
        tui_stream.flush()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
