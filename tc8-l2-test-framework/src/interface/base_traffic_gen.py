"""
Abstract base class for traffic generation.

Separates sustained / burst traffic generation from the per-frame DUT
interface (BaseDUTInterface). Allows a hardware traffic generator to be
substituted for the default ScapyTrafficGen without changing spec code.

Accuracy tiers:
  ScapyTrafficGen  — PC NIC + Scapy: burst-only, ±30% rate accuracy
  HardwareTrafficGen — dedicated tgen (e.g. Ixia, Spirent): line-rate,
                       sub-1% accuracy (future; not yet implemented)
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scapy.packet import Packet


@dataclass
class BurstResult:
    """Result of a burst transmission."""
    frames_sent: int
    frames_received: int
    duration_s: float
    achieved_pps: float
    achieved_mbps: float
    loss_rate_pct: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class ThroughputResult:
    """Result of a throughput measurement."""
    offered_pps: float
    achieved_pps: float
    achieved_mbps: float
    frame_size_bytes: int
    duration_s: float
    loss_pct: float
    is_accurate: bool   # False when measured on a standard PC NIC
    warnings: list[str] = field(default_factory=list)


class BaseTrafficGen(abc.ABC):
    """
    Abstract traffic generator interface.

    Spec handlers use this to send bursts and measure throughput without
    knowing whether the underlying implementation is Scapy or hardware.
    """

    @property
    @abc.abstractmethod
    def is_hardware_accurate(self) -> bool:
        """
        True if this generator can produce hardware-accurate rate measurements.
        False for Scapy-based generators (±30% rate, OS scheduler dependent).
        """
        ...

    @abc.abstractmethod
    async def send_burst(
        self,
        frames: list["Packet"],
        iface: str,
        count: int = 1,
        inter_frame_gap_s: float = 0.0,
    ) -> BurstResult:
        """
        Send a burst of frames as fast as possible (or with optional gap).

        Args:
            frames: list of Scapy Packet objects to send in sequence
            iface: OS interface name to transmit on
            count: repeat the frame list this many times
            inter_frame_gap_s: minimum gap between frames (0 = wire speed)
        """
        ...

    @abc.abstractmethod
    async def measure_throughput(
        self,
        frames: list["Packet"],
        iface: str,
        duration_s: float,
        capture_iface: str | None = None,
    ) -> ThroughputResult:
        """
        Send frames continuously for duration_s and measure achieved rate.

        Args:
            frames: frame pattern to repeat
            iface: transmit interface name
            duration_s: test duration in seconds
            capture_iface: interface to count received frames on (optional)
        """
        ...

    def accuracy_warning(self) -> str:
        """Return a standard accuracy caveat string for INFORMATIONAL results."""
        if self.is_hardware_accurate:
            return ""
        return (
            "Rate measurement performed with ScapyTrafficGen on a standard PC NIC. "
            "Accuracy is approximately ±30% due to OS scheduler jitter and Scapy "
            "overhead. For production conformance testing use a dedicated traffic "
            "generator (e.g. Ixia, Spirent, or RFC 2544-capable NIC)."
        )
