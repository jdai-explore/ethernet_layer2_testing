"""
Section 5.9 — Configuration test specifications.

Validates DUT configuration behavior:
- Factory default validation
- Configuration persistence across power cycles
- AUTOSAR testability protocol interface
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


class ConfigTests(BaseTestSpec):
    """
    TC8 Section 5.9 — Configuration tests.

    3 specifications covering defaults, persistence, and config interface.
    """

    section = TestSection.CONFIGURATION
    section_name = "Configuration"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        handlers = {
            "SWITCH_CFG_001": self._test_factory_defaults,
            "SWITCH_CFG_002": self._test_config_persistence,
            "SWITCH_CFG_003": self._test_config_interface,
        }
        handler = handlers.get(spec.spec_id, self._test_generic_config)
        return await handler(spec, test_case, interface)

    async def _test_factory_defaults(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_CFG_001 — Factory default configuration.

        After reset-to-factory, verify switch operates with documented
        default settings (PVID=1, default VLAN membership, no filters).
        """
        self.log_spec_info(spec)
        dut = self.config.dut_profile

        if dut and not dut.can_reset:
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.SKIP,
                message="DUT does not support reset — factory defaults test skipped",
            )

        t0 = time.perf_counter()

        # In real execution: trigger factory reset, then verify config
        sent: list[FrameCapture] = []
        duration_ms = (time.perf_counter() - t0) * 1000

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL, duration_ms=duration_ms,
            message="Factory defaults validation requires DUT reset capability and config readback",
        )

    async def _test_config_persistence(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_CFG_002 — Configuration persistence across power cycle.

        Change a setting, power cycle, verify setting persists.
        """
        self.log_spec_info(spec)
        dut = self.config.dut_profile

        if dut and not dut.can_reset:
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.SKIP,
                message="DUT does not support power cycling — persistence test skipped",
            )

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            message="Config persistence requires power cycle capability",
        )

    async def _test_config_interface(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_CFG_003 — AUTOSAR testability protocol interface.

        Verify the DUT exposes a configuration interface
        (AUTOSAR Testability Protocol or UDS/DoIP).
        """
        self.log_spec_info(spec)
        dut = self.config.dut_profile

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "AUTOSAR Testability Protocol interface check — "
                "requires DUT communication channel (UDS/DoIP/Testability)"
            ),
        )

    async def _test_generic_config(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        logger.warning("No specific handler for %s", spec.spec_id)
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=f"Generic config test for {spec.spec_id}",
        )
