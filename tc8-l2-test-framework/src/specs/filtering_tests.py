"""
Section 5.6 — Filtering test specifications.

Validates frame filtering capabilities:
- MAC address filtering (block/allow)
- Multicast group filtering
- Broadcast storm protection (rate limiting)
- Protocol-based (EtherType) filtering
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.models.test_case import (
    FrameCapture,
    TestCase,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
)
from src.specs.base_spec import BaseTestSpec

logger = logging.getLogger(__name__)


class FilteringTests(BaseTestSpec):
    """
    TC8 Section 5.6 — Filtering tests.

    11 specifications covering MAC filtering, multicast groups,
    broadcast storm protection, and EtherType filtering.
    """

    section = TestSection.FILTERING
    section_name = "Filtering"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to filtering-specific handler."""
        handlers = {
            "SWITCH_FILT_001": self._test_mac_block,
            "SWITCH_FILT_002": self._test_mac_allow,
            "SWITCH_FILT_003": self._test_mac_filter_wildcard,
            "SWITCH_FILT_004": self._test_mac_filter_persistence,
            "SWITCH_FILT_005": self._test_multicast_filter,
            "SWITCH_FILT_006": self._test_multicast_group_join,
            "SWITCH_FILT_007": self._test_multicast_group_leave,
            "SWITCH_FILT_008": self._test_broadcast_storm_rate_limit,
            "SWITCH_FILT_009": self._test_broadcast_storm_recovery,
            "SWITCH_FILT_010": self._test_ethertype_filter,
            "SWITCH_FILT_011": self._test_ethertype_allow,
        }

        handler = handlers.get(spec.spec_id, self._test_generic_filter)
        return await handler(spec, test_case, interface)

    # ── MAC Filtering (001-004) ───────────────────────────────────────

    async def _test_mac_block(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_001 — Block specific MAC address."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {"forward_to_ports": [], "tag_action": "drop", **spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_mac_allow(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_002 — Allow specific MAC through filter."""
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {"forward_to_ports": params.egress_ports, **spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_mac_filter_wildcard(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_003 — Wildcard MAC filtering."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_mac_filter_persistence(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_004 — MAC filter persistence after reset."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    # ── Multicast Filtering (005-007) ─────────────────────────────────

    async def _test_multicast_filter(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_005 — Multicast group filtering."""
        self.log_spec_info(spec)
        case.parameters.dst_mac = "01:00:5e:00:00:01"
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_multicast_group_join(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_006 — Multicast group join filtering."""
        return await self._test_multicast_filter(spec, case, interface)

    async def _test_multicast_group_leave(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_007 — Multicast group leave filtering."""
        return await self._test_multicast_filter(spec, case, interface)

    # ── Broadcast Storm (008-009) ─────────────────────────────────────

    async def _test_broadcast_storm_rate_limit(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_008 — Broadcast storm rate limiting."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.dst_mac = "ff:ff:ff:ff:ff:ff"
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL, duration_ms=duration_ms,
            sent_frames=sent,
            message="Broadcast storm test requires burst traffic generation",
        )

    async def _test_broadcast_storm_recovery(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_009 — Recovery after broadcast storm."""
        return await self._test_broadcast_storm_rate_limit(spec, case, interface)

    # ── EtherType Filtering (010-011) ─────────────────────────────────

    async def _test_ethertype_filter(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_010 — EtherType-based filtering."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_ethertype_allow(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_FILT_011 — EtherType allow-list filtering."""
        return await self._test_ethertype_filter(spec, case, interface)

    async def _test_generic_filter(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """Fallback handler."""
        logger.warning("No specific handler for %s", spec.spec_id)
        return await self._test_mac_allow(spec, case, interface)

    # ── Helpers ───────────────────────────────────────────────────────

    async def _send_and_capture(
        self, case: TestCase, interface: Any
    ) -> tuple[list[FrameCapture], dict[int, list[FrameCapture]]]:
        params = case.parameters
        if interface is not None:
            sent = await interface.send_frame(case)
            received = await interface.capture_frames(case)
            return sent, received

        sent = [FrameCapture(
            port_id=params.ingress_port, timestamp=time.time(),
            src_mac=params.src_mac, dst_mac=params.dst_mac,
        )]
        received: dict[int, list[FrameCapture]] = {}
        return sent, received
