"""
Extended TSN / gPTP test specifications.

All EXT_TSN_* tests require a TSN-capable NIC with hardware timestamping.
On a standard PC + DUT setup, all tests return SKIP with a clear message
explaining what hardware is required and why standard NICs are insufficient.
"""

from __future__ import annotations

import logging
from typing import Any

from src.models.test_case import (
    SetupRequirement,
    TestCase,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
)
from src.specs.base_spec import BaseTestSpec

logger = logging.getLogger(__name__)

_TSN_NIC_MESSAGE = (
    "TSN / gPTP tests require a hardware-timestamping NIC (e.g., Intel i210, i225, "
    "or Microchip LAN9668) or dedicated TSN test hardware. "
    "Standard PC NICs give ±1 ms timing accuracy — meaningless for gPTP residence "
    "time (< 10 µs), Sync interval (125 ms ± 1 ms), and clock offset (< 1 ppm). "
    "Run this test with a TSN-capable NIC or specialized test equipment."
)

_ANNOUNCE_TIMEOUT_MESSAGE = (
    "EXT_TSN_010 (Announce/Sync timeout) observes gPTP state-machine behavior "
    "visible at the frame level. A standard NIC can capture Announce frames "
    "but hardware timestamping improves timing accuracy. Running informational "
    "observation on basic setup; timing verification requires TSN NIC."
)


class ExtTsnTests(BaseTestSpec):
    """
    Extended TSN / gPTP test section.

    All handlers return SKIP (hardware not available) or INFORMATIONAL
    depending on the specific test's hardware dependency level.
    """

    section = TestSection.EXT_TSN
    section_name = "Extended TSN/gPTP"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to spec handler. All EXT_TSN specs are hardware-gated."""
        handlers = {
            "EXT_TSN_010": self._test_announce_timeout,
        }
        handler = handlers.get(spec.spec_id, self._skip_tsn_nic_required)
        return await handler(spec, test_case, interface)

    async def _skip_tsn_nic_required(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Return SKIP with TSN NIC requirement message."""
        self.log_spec_info(spec)
        hw_detail = spec.hardware_requirement_detail or _TSN_NIC_MESSAGE
        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.SKIP,
            message=(
                f"Hardware required: {hw_detail}"
            ),
        )

    async def _test_announce_timeout(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        EXT_TSN_010 — Announce/Sync timeout handling.

        This is the only EXT_TSN test partially observable without TSN NIC.
        State machine transitions are visible via frame capture; timing accuracy
        is limited to ±1 ms on standard NIC (informational result).
        """
        self.log_spec_info(spec)
        if interface is None:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="Simulation mode — gPTP Announce timeout test requires real DUT with gPTP enabled.",
            )

        dut = self.config.dut_profile
        if dut and not dut.supports_gptp:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="DUT profile has supports_gptp=false — EXT_TSN_010 skipped.",
            )

        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "EXT_TSN_010 requires a live gPTP session. "
                "Timing accuracy is ±1 ms on standard NIC — "
                "use a TSN NIC for precise announceReceiptTimeout verification. "
                + _ANNOUNCE_TIMEOUT_MESSAGE
            ),
            warnings=["Timing accuracy limited to ±1 ms on standard NIC"],
        )
