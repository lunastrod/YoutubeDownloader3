import os
import subprocess
import threading
from collections.abc import Callable
import logger as log


class ProcessRunner:
    def __init__(self):
        self.processes: list[subprocess.Popen] = []
        self.lock = threading.Lock()

    # Run a command. If on_line is provided, streams stdout line by line. Returns (stdout, returncode).
    def run(self, cmd: list[str], on_line: Callable[[str], None] | None = None) -> tuple[str, int]:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)        # Add the process to the list of active processes
        with self.lock:
            self.processes.append(proc)
        exe = os.path.basename(cmd[0])
        # Read stdout line by line
        stdout_lines = []
        for line in proc.stdout:
            line = line.rstrip()
            stdout_lines.append(line)
            log.logger.log_verbose(f"STDOUT {exe}: {line}")
            if on_line:
                on_line(line)
        proc.wait()
        # Read stderr after stdout is done
        for line in proc.stderr.read().splitlines():
            log.logger.log_verbose(f"STDERR {exe}: {line}")
        code = proc.returncode
        # Remove the process from the list of active processes
        with self.lock:
            if proc in self.processes:
                self.processes.remove(proc)
        return "\n".join(stdout_lines), code

    # Terminate all active subprocesses
    def cancel(self):
        with self.lock:
            for proc in self.processes:
                proc.terminate()