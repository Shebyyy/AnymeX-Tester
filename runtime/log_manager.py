import collections
import datetime
import io
import logging
import threading
from typing import List, Optional


class LogSession:
    """Captures system logs and JVM JAR logs for a specific test run."""

    def __init__(self, name: str):
        self.name = name
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.lines: List[str] = []
        self._lock = threading.Lock()

    def add_line(self, line: str):
        if not line:
            return
        clean = line.rstrip()
        if not clean:
            return
        with self._lock:
            self.lines.append(clean)

    def is_meaningful(self) -> bool:
        """Determines if the session captured actual useful logs (not empty or false/noise)."""
        with self._lock:
            if not self.lines:
                return False
            total_content = "".join(self.lines).strip()
            # If less than 40 chars or fewer than 2 entries, treat as empty/false
            if len(total_content) < 40 or len(self.lines) < 2:
                return False
            return True

    def finish(self, status: str = "COMPLETED") -> str:
        end_time = datetime.datetime.now(datetime.timezone.utc)
        duration = (end_time - self.start_time).total_seconds()

        header = [
            "=" * 78,
            f"AnymeX Extension Test Log: {self.name}",
            f"Started:  {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')} ({duration:.2f}s)",
            f"Result:   {status}",
            "=" * 78,
            "",
            "--- [SYSTEM & JVM RUNTIME LOGS] ---",
        ]

        footer = [
            "",
            "=" * 78,
            f"END OF LOG [{status}]",
            "=" * 78,
        ]

        with self._lock:
            content = header + self.lines + footer
        return "\n".join(content)


class _SessionLogHandler(logging.Handler):
    """Captures system logs into LogManager and any active test sessions."""

    def __init__(self, manager: "LogManager"):
        super().__init__()
        self.manager = manager
        self.setFormatter(logging.Formatter("[%(asctime)s] [SYSTEM/%(name)s]: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.manager.record_system_log(msg)
        except Exception:
            self.handleError(record)


class LogManager:
    """Central manager for capturing full system and JVM sidecar logs."""

    _instance: Optional["LogManager"] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._recent_logs: collections.deque = collections.deque(maxlen=2000)
        self._active_sessions: List[LogSession] = []
        self._lock = threading.Lock()

        # Attach handler to root logger
        self._handler = _SessionLogHandler(self)
        root = logging.getLogger()
        root.addHandler(self._handler)

        self._initialized = True

    def start_session(self, name: str) -> LogSession:
        session = LogSession(name)
        with self._lock:
            self._active_sessions.append(session)
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        session.add_line(f"[{now_str}] [SYSTEM]: Initialized test session for '{name}'")
        return session

    def stop_session(self, session: LogSession):
        with self._lock:
            if session in self._active_sessions:
                self._active_sessions.remove(session)

    def record_system_log(self, formatted_message: str):
        with self._lock:
            self._recent_logs.append(formatted_message)
            for s in self._active_sessions:
                s.add_line(formatted_message)

    def record_jar_log(self, raw_line: str, is_stderr: bool = True):
        clean = raw_line.strip()
        if not clean:
            return
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{now_str}] [JAR]: {clean}"

        with self._lock:
            self._recent_logs.append(entry)
            for s in self._active_sessions:
                s.add_line(entry)

    def get_recent_logs(self, max_lines: int = 300) -> str:
        with self._lock:
            items = list(self._recent_logs)[-max_lines:]
        return "\n".join(items) if items else ""


log_manager = LogManager()
