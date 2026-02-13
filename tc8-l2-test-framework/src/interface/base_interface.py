"""
Abstract base interface for DUT communication.

All DUT interfaces (Scapy, raw socket, TCP stub, USB) implement this
protocol. Provides the contract for sending/receiving Ethernet frames
to/from the Device Under Test.
"""

from __future__ import annotations

import abc
import logging
from typing import Any

from src.models.test_case import FrameCapture, PortConfig, TestCase

logger = logging.getLogger(__name__)


class BaseDUTInterface(abc.ABC):
    """
    Abstract base class for DUT communication interfaces.

    Subclasses must implement:
    - initialize() — set up network interfaces
    - shutdown() — clean up resources
    - send_frame() — transmit a test frame to a DUT port
    - capture_frames() — receive frames from DUT ports
    - check_link() — verify link status on a port
    """

    def __init__(self, ports: list[PortConfig]) -> None:
        self.ports = {p.port_id: p for p in ports}
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ── Lifecycle ─────────────────────────────────────────────────────

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Initialize all network interfaces for testing."""
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Release all network interface resources."""
        ...

    async def __aenter__(self) -> BaseDUTInterface:
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.shutdown()

    # ── Frame Operations ──────────────────────────────────────────────

    @abc.abstractmethod
    async def send_frame(self, test_case: TestCase) -> list[FrameCapture]:
        """
        Build and send a test frame based on test case parameters.

        Returns a list of FrameCapture objects representing what was sent.
        """
        ...

    @abc.abstractmethod
    async def capture_frames(
        self,
        test_case: TestCase,
        timeout: float = 2.0,
    ) -> dict[int, list[FrameCapture]]:
        """
        Capture frames from all DUT egress ports.

        Args:
            test_case: The test case being executed.
            timeout: Max time to wait for frames (seconds).

        Returns:
            Dict mapping port_id → list of captured frames.
        """
        ...

    # ── Link Management ───────────────────────────────────────────────

    @abc.abstractmethod
    async def check_link(self, port_id: int) -> bool:
        """Check whether the link is up on the given port."""
        ...

    async def check_all_links(self) -> dict[int, bool]:
        """Check link status on all configured ports."""
        results = {}
        for port_id in self.ports:
            results[port_id] = await self.check_link(port_id)
        return results

    # ── Port Info ─────────────────────────────────────────────────────

    def get_port(self, port_id: int) -> PortConfig | None:
        """Get port configuration by ID."""
        return self.ports.get(port_id)

    def get_interface_name(self, port_id: int) -> str:
        """Get the OS interface name for a port."""
        port = self.ports.get(port_id)
        if port is None:
            raise ValueError(f"Unknown port ID: {port_id}")
        return port.interface_name
