"""
Section 5.7 — Time Synchronization test specification.

Validates gPTP (IEEE 802.1AS) timestamp correction accuracy.
This section has only 1 specification but requires hardware
timestamping for meaningful results.
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
    TimingTier,
)
from src.specs.base_spec import BaseTestSpec

logger = logging.getLogger(__name__)


class TimeTests(BaseTestSpec):
    """
    TC8 Section 5.7 — Time Synchronization tests.

    1 specification: gPTP residence time correction accuracy.
    Requires Tier C timing hardware for valid results.
    """

    section = TestSection.TIME_SYNC
    section_name = "Time Synchronization"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        handlers = {
            "SWITCH_TIME_001": self._test_gptp_timestamp_accuracy,
        }
        handler = handlers.get(spec.spec_id, self._test_gptp_timestamp_accuracy)
        return await handler(spec, test_case, interface)

    async def _test_gptp_timestamp_accuracy(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_TIME_001 — gPTP residence time correction accuracy.

        Requires Tier C (±1µs) timing hardware. Without it, the result
        is classified as INFORMATIONAL with a timing limitation note.
        """
        self.log_spec_info(spec)

        # Check DUT gPTP support
        dut = self.config.dut_profile
        if dut and not dut.supports_gptp:
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.SKIP,
                message="DUT does not support gPTP — time sync test skipped",
            )

        t0 = time.perf_counter()
        params = case.parameters

        # In real execution: send PTP Sync messages, measure correction field
        sent: list[FrameCapture] = [FrameCapture(
            port_id=params.ingress_port, timestamp=time.time(),
            src_mac=params.src_mac, dst_mac="01:80:c2:00:00:0e",  # gPTP multicast
            ethertype=0x88F7,  # PTP EtherType
        )]

        duration_ms = (time.perf_counter() - t0) * 1000

        # Without Tier C hardware, report as informational
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            duration_ms=duration_ms,
            timing_tier=TimingTier.TIER_A,
            sent_frames=sent,
            message=(
                "gPTP timestamp accuracy requires Tier C (±1µs) hardware. "
                "Current measurement uses Tier A (±1ms) — result is informational only."
            ),
            warnings=["Timing limitation: Tier A accuracy insufficient for gPTP validation"],
        )
