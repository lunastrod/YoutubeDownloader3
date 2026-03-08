from collections.abc import Callable
import time


class Logger:
    def __init__(self):
        self.verbose = False
        self._on_line: Callable[[str], None] | None = None
        self._on_progress: Callable[[float], None] | None = None
        self._start_time = time.time()

    # Set the callback that receives log lines
    def set_callback(self, on_line: Callable[[str], None]) -> None:
        self._on_line = on_line

    # Set the callback that receives progress updates (0.0 to 1.0)
    def set_progress_callback(self, on_progress: Callable[[float], None]) -> None:
        self._on_progress = on_progress

    # Log a line unconditionally
    def log(self, line: str) -> None:
        if self._on_line:
            self._on_line(line)

    # Log a line only if verbose is enabled
    def log_verbose(self, line: str) -> None:
        if self.verbose and self._on_line:
            elapsed = time.time() - self._start_time
            self._on_line(f"[{elapsed:.2f}s] {line}")

    # Update progress (0.0 to 1.0)
    def set_progress(self, value: float) -> None:
        if self._on_progress:
            self._on_progress(value)


logger = Logger()