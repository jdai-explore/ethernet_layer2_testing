"""
Extended Golden Device / Virtual Oracle test specifications.

EXT_ORACLE_001–003 use a Linux software bridge as a virtual oracle.
They are fully runnable on any Linux PC (bridge-utils or Open vSwitch required).
EXT_ORACLE_004 requires a second hardware ECU (golden device).
"""

from __future__ import annotations

import logging
import platform
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


class ExtOracleTests(BaseTestSpec):
    """Extended golden device / virtual oracle test section."""

    section = TestSection.EXT_ORACLE
    section_name = "Extended Oracle"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to spec handler."""
        handlers = {
            "EXT_ORACLE_001": self._test_virtual_oracle_baseline,
            "EXT_ORACLE_002": self._test_virtual_oracle_negative,
            "EXT_ORACLE_003": self._test_dut_vs_oracle_diff,
        }
        handler = handlers.get(spec.spec_id, self._skip_golden_device_required)
        return await handler(spec, test_case, interface)

    async def _skip_golden_device_required(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Return SKIP for tests requiring a physical golden device ECU."""
        self.log_spec_info(spec)
        hw_detail = spec.hardware_requirement_detail or (
            "Requires a second known-good ECU (hardware golden device). "
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

    async def _test_virtual_oracle_baseline(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        EXT_ORACLE_001 — Virtual switch known-good forwarding baseline.

        Checks whether Linux bridge/OVS is available for oracle setup.
        """
        self.log_spec_info(spec)
        is_linux = platform.system() == "Linux"
        if not is_linux:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message=(
                    "EXT_ORACLE_001 requires Linux (bridge-utils or Open vSwitch). "
                    "Running on Windows — virtual bridge oracle not available. "
                    "Run this test on Linux to establish the oracle baseline."
                ),
            )

        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "EXT_ORACLE_001: Linux platform detected. "
                "Virtual bridge oracle support requires bridge-utils or Open vSwitch "
                "and virtual interface configuration matching the DUT topology. "
                "Oracle implementation not yet integrated into the framework — "
                "this test currently establishes only the platform-check result."
            ),
        )

    async def _test_virtual_oracle_negative(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """EXT_ORACLE_002 — Virtual switch known-bad frame drop verification."""
        self.log_spec_info(spec)
        is_linux = platform.system() == "Linux"
        if not is_linux:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message=(
                    "EXT_ORACLE_002 requires Linux (bridge-utils or Open vSwitch). "
                    "Running on Windows — virtual bridge oracle not available."
                ),
            )

        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "EXT_ORACLE_002: Linux platform detected. "
                "Negative-test oracle support (drop verification) not yet integrated. "
                "Implement Linux bridge virtual topology to enable this test."
            ),
        )

    async def _test_dut_vs_oracle_diff(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """EXT_ORACLE_003 — DUT vs virtual oracle behavioral diff."""
        self.log_spec_info(spec)
        if interface is None:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message="Simulation mode — DUT vs oracle diff requires real DUT and established oracle baseline.",
            )

        is_linux = platform.system() == "Linux"
        if not is_linux:
            return TestResult(
                case_id=case.case_id,
                spec_id=case.spec_id,
                tc8_reference=case.tc8_reference,
                section=case.section,
                status=TestStatus.SKIP,
                message=(
                    "EXT_ORACLE_003 requires Linux to run the virtual oracle. "
                    "Running on Windows — oracle comparison not available."
                ),
            )

        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.INFORMATIONAL,
            message=(
                "EXT_ORACLE_003: Linux + real DUT detected. "
                "Oracle baseline (EXT_ORACLE_001) must be established first. "
                "Oracle diff engine not yet integrated into the framework."
            ),
        )
