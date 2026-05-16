"""
Extended DUT Management Channel test specifications.

EXT_MGMT_001 and EXT_MGMT_002 (DoIP/UDS over standard Ethernet) are
runnable on a basic PC + DUT setup if the ECU supports DoIP.
EXT_MGMT_003–005 require AUTOSAR stacks, SSH, or vendor-specific hardware.
"""

from __future__ import annotations

import logging
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


class ExtMgmtTests(BaseTestSpec):
    """Extended DUT management channel test section."""

    section = TestSection.EXT_MGMT
    section_name = "Extended DUT Management"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to spec handler."""
        handlers = {
            "EXT_MGMT_001": self._test_doip_ecu_reset,
            "EXT_MGMT_002": self._test_uds_config_readback,
        }
        handler = handlers.get(spec.spec_id, self._skip_hw_required)
        return await handler(spec, test_case, interface)

    async def _skip_hw_required(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Return SKIP for tests requiring specialized management hardware."""
        self.log_spec_info(spec)
        hw_detail = spec.hardware_requirement_detail or (
            f"{spec.spec_id} requires specialized management interface. "
            "Not available on standard PC + DUT setup."
        )
        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.SKIP,
            message=f"Hardware required: {hw_detail}",
        )

    async def _test_doip_ecu_reset(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        EXT_MGMT_001 — DoIP ECU Reset via UDS 0x11.

        Runnable on PC + DUT if ECU exposes DoIP. Returns INFORMATIONAL
        since DoIP client implementation is not yet included in the framework.
        """
        self.log_spec_info(spec)
        if interface is None:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="Simulation mode — DoIP ECU Reset requires real DUT with DoIP server.",
            )

        dut = self.config.dut_profile
        if dut and not dut.can_reset:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message=(
                    "DUT profile has can_reset=false. "
                    "Set can_reset=true and configure reset_command in the DUT profile "
                    "to enable EXT_MGMT_001 DoIP reset testing."
                ),
            )

        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "EXT_MGMT_001: DoIP ECU reset is architecturally feasible on this setup. "
                "A DoIP client implementation is required in the framework to execute this test. "
                "Add DoIP client support (ISO 13400-2) and configure the DUT's DoIP server "
                "address in the DUT profile to enable automated execution."
            ),
        )

    async def _test_uds_config_readback(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        EXT_MGMT_002 — UDS Configuration Readback via DoIP.

        Runnable on PC if ECU exposes DoIP. Returns INFORMATIONAL
        since UDS/DoIP client is not yet implemented in the framework.
        """
        self.log_spec_info(spec)
        if interface is None:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="Simulation mode — UDS readback requires real DUT with DoIP server.",
            )

        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "EXT_MGMT_002: UDS ReadDataByIdentifier (0x22) over DoIP is feasible on this setup. "
                "A DoIP/UDS client implementation and the DID mapping for the target ECU are "
                "required in the framework. Add DoIP client support to enable automated execution."
            ),
        )
