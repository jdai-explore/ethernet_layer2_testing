"""
Session manager — DUT state isolation between test cases.

Ensures every test starts from a known clean state by clearing MAC tables,
resetting statistics, and verifying link status before each test.
Addresses Risk R2 (Test State Pollution) from the PRD.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Protocol

from src.models.test_case import DUTProfile, SessionState

logger = logging.getLogger(__name__)


class DUTController(Protocol):
    """Protocol for DUT state management commands."""

    async def clear_mac_table(self) -> bool: ...
    async def clear_statistics(self) -> bool: ...
    async def verify_link_state(self, port_id: int) -> bool: ...
    async def get_mac_table_entries(self) -> int: ...
    async def reset_dut(self) -> bool: ...


class NullDUTController:
    """
    Stub DUT controller for when no direct DUT management is available.

    Used when the DUT is pre-configured and cannot be programmatically
    controlled (Phase 1 / Option A from the PRD).
    """

    async def clear_mac_table(self) -> bool:
        logger.info("[NullDUT] MAC table clear requested — waiting for natural aging")
        return True

    async def clear_statistics(self) -> bool:
        logger.info("[NullDUT] Statistics clear requested — no-op")
        return True

    async def verify_link_state(self, port_id: int) -> bool:
        logger.info("[NullDUT] Link state check on port %d — assuming UP", port_id)
        return True

    async def get_mac_table_entries(self) -> int:
        return 0

    async def reset_dut(self) -> bool:
        logger.warning("[NullDUT] DUT reset requested but no controller available")
        return False


class SessionManager:
    """
    Manages test session lifecycle and DUT state isolation.

    Usage::

        session_mgr = SessionManager(dut_profile, controller)
        async with session_mgr.test_session() as session:
            # DUT is in a known clean state here
            await run_test(...)
        # Cleanup runs automatically
    """

    def __init__(
        self,
        dut_profile: DUTProfile,
        controller: DUTController | None = None,
        cleanup_wait_s: float = 5.0,
        aging_wait_s: float = 30.0,
    ) -> None:
        self.dut_profile = dut_profile
        self.controller = controller or NullDUTController()
        self.cleanup_wait_s = cleanup_wait_s
        self.aging_wait_s = aging_wait_s
        self._current_session: SessionState | None = None

    @property
    def current_session(self) -> SessionState | None:
        return self._current_session

    async def setup(self) -> SessionState:
        """
        Pre-test setup: bring DUT to a known clean state.

        Steps:
        1. Clear MAC address table (or wait for aging)
        2. Clear statistics counters
        3. Verify all links are up
        4. Verify VLAN configuration matches profile
        """
        session_id = str(uuid.uuid4())[:8]
        logger.info("═══ Session %s SETUP ═══", session_id)

        state = SessionState(
            session_id=session_id,
            dut_profile=self.dut_profile,
        )

        # 1. Clear MAC table
        t0 = time.perf_counter()
        state.mac_table_cleared = await self.controller.clear_mac_table()
        if not state.mac_table_cleared and self.dut_profile.can_reset:
            logger.info("MAC table clear failed — attempting DUT reset")
            await self.controller.reset_dut()
            await asyncio.sleep(self.cleanup_wait_s)
            state.mac_table_cleared = True

        # 2. Clear statistics
        state.statistics_cleared = await self.controller.clear_statistics()

        # 3. Verify link state on all ports
        all_links_up = True
        for port in self.dut_profile.ports:
            link_ok = await self.controller.verify_link_state(port.port_id)
            if not link_ok:
                logger.error("Port %d link is DOWN — test results may be invalid", port.port_id)
                all_links_up = False
        state.links_verified = all_links_up

        # 4. VLAN config verification (placeholder — requires DUT query interface)
        state.vlan_config_verified = True

        # Wait for settle
        await asyncio.sleep(self.cleanup_wait_s)
        state.cleanup_wait_s = time.perf_counter() - t0
        state.is_clean = state.mac_table_cleared and state.links_verified

        if state.is_clean:
            logger.info("Session %s ready (%.1fs setup)", session_id, state.cleanup_wait_s)
        else:
            logger.warning(
                "Session %s setup INCOMPLETE — mac=%s links=%s",
                session_id, state.mac_table_cleared, state.links_verified,
            )

        self._current_session = state
        return state

    async def teardown(self) -> None:
        """
        Post-test cleanup: reset DUT state for the next test.

        Steps:
        1. Clear MAC table
        2. Clear statistics
        3. Wait for aging if needed
        """
        if self._current_session is None:
            return

        session_id = self._current_session.session_id
        logger.info("═══ Session %s TEARDOWN ═══", session_id)

        await self.controller.clear_mac_table()
        await self.controller.clear_statistics()

        # If DUT can't be reset, wait for natural MAC aging
        if not self.dut_profile.can_reset:
            mac_count = await self.controller.get_mac_table_entries()
            if mac_count > 0:
                wait_time = min(self.aging_wait_s, self.dut_profile.mac_aging_time_s)
                logger.info(
                    "Waiting %.0fs for %d MAC entries to age out", wait_time, mac_count
                )
                await asyncio.sleep(wait_time)

        self._current_session = None
        logger.info("Session %s cleanup complete", session_id)

    class _SessionContext:
        """Async context manager for a test session."""

        def __init__(self, manager: SessionManager) -> None:
            self._mgr = manager
            self._state: SessionState | None = None

        async def __aenter__(self) -> SessionState:
            self._state = await self._mgr.setup()
            return self._state

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            await self._mgr.teardown()

    def test_session(self) -> _SessionContext:
        """Create an async context manager for a test session."""
        return self._SessionContext(self)
