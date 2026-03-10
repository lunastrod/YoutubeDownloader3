from collections.abc import Callable
import time


class Logger:
    def __init__(self):
        self.verbose = False
        self._on_line: Callable[[str, str | None], None] | None = None
        self._on_progress: Callable[[float], None] | None = None
        self._start_time = time.time()

    def set_callback(self, on_line: Callable[[str, str | None], None]) -> None:
        self._on_line = on_line

    def set_progress_callback(self, on_progress: Callable[[float], None]) -> None:
        self._on_progress = on_progress

    def write_line(self, line: str, color: str | None = None) -> None:
        if self._on_line:
            self._on_line(line, color)

    def log(self, line: str) -> None:
        self.write_line(line)

    def warning(self, line: str) -> None:
        self.write_line(line, color="yellow")

    def error(self, line: str) -> None:
        self.write_line(line, color="red")

    def log_verbose(self, line: str) -> None:
        if self.verbose:
            elapsed = time.time() - self._start_time
            self.write_line(f"[{elapsed:.2f}s] {line}", color="gray")

    def set_progress(self, value: float) -> None:
        if self._on_progress:
            self._on_progress(value)


logger = Logger()