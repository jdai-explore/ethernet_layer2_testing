"""
Per-test log capture utility.

Provides a context manager that temporarily intercepts Python logger output
during a single test case execution and collects messages as LogEntry objects.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.models.test_case import LogEntry


class _CaptureHandler(logging.Handler):
    """Internal logging handler that collects records into a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestLogCapture:
    """
    Context manager: captures Python logger output into LogEntry list.

    Usage::

        with TestLogCapture() as capture:
            # ... run test case ...
            result.log_entries = capture.entries
    """

    # Only capture from our own modules
    TARGET_LOGGERS = [
        "src.core.test_runner",
        "src.core.result_validator",
        "src.core.session_manager",
        "src.specs",  # parent covers all spec handlers
    ]

    def __init__(self, level: int = logging.DEBUG) -> None:
        self._level = level
        self._handler = _CaptureHandler()
        self._handler.setLevel(level)
        self._attached_loggers: list[logging.Logger] = []
        self._original_levels: dict[str, int] = {}

    def __enter__(self) -> "TestLogCapture":
        # Attach handler to each target logger and lower level to capture all
        for name in self.TARGET_LOGGERS:
            logger = logging.getLogger(name)
            self._original_levels[name] = logger.level
            logger.setLevel(self._level)
            logger.addHandler(self._handler)
            self._attached_loggers.append(logger)
        return self

    def __exit__(self, *args: Any) -> None:
        # Detach handler and restore original levels
        for logger in self._attached_loggers:
            logger.removeHandler(self._handler)
        for name, original_level in self._original_levels.items():
            logging.getLogger(name).setLevel(original_level)
        self._attached_loggers.clear()
        self._original_levels.clear()

    @property
    def entries(self) -> list[LogEntry]:
        """Convert captured logging records to LogEntry models."""
        result: list[LogEntry] = []
        for rec in self._handler.records:
            result.append(
                LogEntry(
                    timestamp=rec.created,
                    level=rec.levelname,
                    source=rec.name.rsplit(".", 1)[-1] if "." in rec.name else rec.name,
                    message=rec.getMessage(),
                )
            )
        return result

    def clear(self) -> None:
        """Clear captured records."""
        self._handler.records.clear()
