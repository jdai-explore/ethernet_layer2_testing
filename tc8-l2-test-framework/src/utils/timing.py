"""
High-resolution timing utilities.

Provides timing measurement with documented accuracy tiers:
- Tier A: ±1 ms  (Python perf_counter)
- Tier B: ±100 µs (NIC hardware timestamps via SO_TIMESTAMPING)
- Tier C: ±1 µs  (External hardware — PPS/GPS, C extension)
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

from src.models.test_case import TimingTier

logger = logging.getLogger(__name__)


@dataclass
class TimingMeasurement:
    """Result of a timing measurement."""

    start_ns: int
    end_ns: int
    tier: TimingTier

    @property
    def duration_ns(self) -> int:
        return self.end_ns - self.start_ns

    @property
    def duration_us(self) -> float:
        return self.duration_ns / 1_000

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000

    @property
    def duration_s(self) -> float:
        return self.duration_ns / 1_000_000_000


class HighResTimer:
    """
    High-resolution timer with configurable accuracy tier.

    Usage::

        timer = HighResTimer(tier=TimingTier.TIER_A)
        with timer.measure() as measurement:
            # ... timed operation ...
        print(f"Duration: {measurement.duration_ms:.3f} ms")
    """

    def __init__(self, tier: TimingTier = TimingTier.TIER_A) -> None:
        self.tier = tier
        self._calibration_offset_ns: int = 0

    def now_ns(self) -> int:
        """Get current time in nanoseconds."""
        if self.tier == TimingTier.TIER_A:
            return time.perf_counter_ns()
        elif self.tier == TimingTier.TIER_B:
            # TODO: Implement SO_TIMESTAMPING for NIC hardware timestamps
            return time.perf_counter_ns()
        else:
            # TODO: Implement PPS/GPS hardware time source
            return time.perf_counter_ns()

    @contextmanager
    def measure(self) -> Generator[TimingMeasurement, None, None]:
        """Context manager for timing a block of code."""
        m = TimingMeasurement(start_ns=self.now_ns(), end_ns=0, tier=self.tier)
        try:
            yield m
        finally:
            m.end_ns = self.now_ns()

    def calibrate(self, iterations: int = 100) -> float:
        """
        Calibrate timer by measuring overhead.

        Returns mean measurement overhead in nanoseconds.
        """
        overheads: list[int] = []
        for _ in range(iterations):
            t0 = self.now_ns()
            t1 = self.now_ns()
            overheads.append(t1 - t0)

        self._calibration_offset_ns = sum(overheads) // len(overheads)
        logger.info(
            "Timer calibrated: mean overhead = %d ns (%s)",
            self._calibration_offset_ns, self.tier.value,
        )
        return float(self._calibration_offset_ns)

    @property
    def accuracy_description(self) -> str:
        """Human-readable accuracy description for reports."""
        descriptions = {
            TimingTier.TIER_A: "±1 ms (Python perf_counter — software timer)",
            TimingTier.TIER_B: "±100 µs (NIC hardware timestamps — SO_TIMESTAMPING)",
            TimingTier.TIER_C: "±1 µs (External hardware — PPS/GPS reference)",
        }
        return descriptions.get(self.tier, "Unknown")


def sleep_precise(duration_s: float) -> None:
    """
    Busy-wait sleep for more precise short durations.

    Python's time.sleep() has ~1-15 ms granularity on most OSes.
    This function busy-waits for durations < 10 ms, falls back to
    time.sleep() for longer durations to avoid CPU waste.
    """
    if duration_s <= 0:
        return

    if duration_s > 0.01:  # > 10 ms: use regular sleep
        time.sleep(duration_s)
        return

    # Busy-wait for short durations
    target = time.perf_counter() + duration_s
    while time.perf_counter() < target:
        pass
