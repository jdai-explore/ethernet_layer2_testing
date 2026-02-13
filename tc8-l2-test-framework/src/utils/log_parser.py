"""
Log capture and parsing utilities.

Captures test execution logs, Scapy output, and DUT responses
into structured formats for report generation and debugging.
"""

from __future__ import annotations

import logging
import io
import time
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """A single log entry with structured metadata."""

    timestamp: datetime
    level: str
    source: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class TestLogCapture:
    """
    Captures and organises test execution logs.

    Usage::

        log_capture = TestLogCapture("SWITCH_VLAN_001")
        log_capture.start()
        # ... run test ...
        log_capture.info("Frame sent on port 0", {"vid": 100})
        log_capture.stop()
        entries = log_capture.get_entries()
    """

    def __init__(self, test_id: str, max_entries: int = 10000) -> None:
        self.test_id = test_id
        self.max_entries = max_entries
        self._entries: list[LogEntry] = []
        self._running = False
        self._start_time: float | None = None

    def start(self) -> None:
        self._running = True
        self._start_time = time.perf_counter()
        self._entries.clear()
        self._add("INFO", "capture", f"Log capture started for {self.test_id}")

    def stop(self) -> None:
        elapsed = time.perf_counter() - (self._start_time or 0)
        self._add("INFO", "capture", f"Log capture stopped ({elapsed:.3f}s)")
        self._running = False

    def info(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._add("INFO", self.test_id, message, data)

    def warning(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._add("WARNING", self.test_id, message, data)

    def error(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._add("ERROR", self.test_id, message, data)

    def debug(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._add("DEBUG", self.test_id, message, data)

    def frame_sent(self, port: int, frame_summary: str) -> None:
        self._add("INFO", "frame", f"TX port {port}: {frame_summary}")

    def frame_received(self, port: int, frame_summary: str) -> None:
        self._add("INFO", "frame", f"RX port {port}: {frame_summary}")

    def get_entries(self, level: str | None = None) -> list[LogEntry]:
        if level:
            return [e for e in self._entries if e.level == level]
        return list(self._entries)

    def get_text(self) -> str:
        """Get all log entries as formatted text."""
        lines = []
        for entry in self._entries:
            ts = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
            lines.append(f"[{ts}] [{entry.level:7s}] [{entry.source}] {entry.message}")
        return "\n".join(lines)

    def save(self, path: Path) -> None:
        """Save log entries to a file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.get_text(), encoding="utf-8")
        logger.info("Log saved to %s (%d entries)", path, len(self._entries))

    def _add(
        self,
        level: str,
        source: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        if len(self._entries) >= self.max_entries:
            return
        self._entries.append(LogEntry(
            timestamp=datetime.now(),
            level=level,
            source=source,
            message=message,
            data=data or {},
        ))
