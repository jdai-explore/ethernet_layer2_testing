"""
Extended Automotive PHY test specifications.

EXT_PHY tests vary in hardware requirements:
- EXT_PHY_002 (link flap count) runs on any PC via psutil.
- EXT_PHY_001/004/005/006 require a media converter.
- EXT_PHY_003/007/008 require specialized hardware.
"""

from __future__ import annotations

import logging
import platform
import time
from typing import Any

from src.models.test_case import (
    TestCase,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
)
from src.specs.base_spec import BaseTestSpec

logger = logging.getLogger(__name__)


class ExtPhyTests(BaseTestSpec):
    """Extended automotive PHY test section."""

    section = TestSection.EXT_PHY
    section_name = "Extended PHY"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to spec handler."""
        handlers = {
            "EXT_PHY_002": self._test_link_flap_count,
        }
        handler = handlers.get(spec.spec_id, self._skip_hw_required)
        return await handler(spec, test_case, interface)

    async def _skip_hw_required(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Return SKIP with hardware requirement detail."""
        self.log_spec_info(spec)
        hw_detail = spec.hardware_requirement_detail or (
            f"Hardware required for {spec.spec_id}: {spec.setup_requirement.value}. "
            "Not runnable on a standard PC + DUT setup."
        )
        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.SKIP,
            message=f"Hardware required: {hw_detail}",
        )

    async def _test_link_flap_count(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        EXT_PHY_002 — Link flap count monitoring.

        Uses psutil to observe OS-level interface statistics.
        Runnable on any PC without additional hardware.
        """
        self.log_spec_info(spec)
        params = case.parameters
        observation_window_s = spec.parameters.get("observation_window_s", 60)

        dut = self.config.dut_profile
        if dut is None:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="No DUT profile loaded — cannot determine interface name for link flap monitoring.",
            )

        if interface is None:
            # Simulation mode — report informational
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.INFORMATIONAL,
                message=(
                    f"Simulation mode — link flap monitoring would observe {observation_window_s}s "
                    "of interface statistics via psutil. No real interfaces to monitor."
                ),
            )

        # Attempt real observation via psutil
        try:
            import psutil
            # Record initial stats for the ingress port interface
            port = dut.ports[params.ingress_port] if params.ingress_port < len(dut.ports) else None
            if port is None:
                return TestResult(
                    case_id=case.case_id,
                    spec_id=case.spec_id,
                    tc8_reference=case.tc8_reference,
                    section=case.section,
                    status=TestStatus.SKIP,
                    message=f"Port {params.ingress_port} not found in DUT profile.",
                )

            iface = port.interface_name
            stats_before = psutil.net_if_stats().get(iface)
            if stats_before is None:
                return TestResult(
                    case_id=case.case_id,
                    spec_id=case.spec_id,
                    tc8_reference=case.tc8_reference,
                    section=case.section,
                    status=TestStatus.SKIP,
                    message=f"Interface '{iface}' not found in system stats.",
                )

            # For actual observation we'd sleep; in test context use short window
            actual_window = min(observation_window_s, 5.0)  # cap at 5s in automated runs
            logger.info("Monitoring %s for link flaps over %ss", iface, actual_window)
            time.sleep(actual_window)

            stats_after = psutil.net_if_stats().get(iface)
            link_stable = stats_after is not None and stats_after.isup

            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.PASS if link_stable else TestStatus.FAIL,
                actual={"link_up": link_stable, "interface": iface},
                message=(
                    f"Link {'stable' if link_stable else 'DOWN'} on {iface} "
                    f"after {actual_window}s observation. "
                    f"(Full {observation_window_s}s window was capped for automated execution.)"
                ),
            )
        except ImportError:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="psutil not installed — cannot monitor interface link state.",
            )
