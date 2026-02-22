"""
Test runner engine — orchestrates test case execution.

Handles test case generation from spec definitions, execution sequencing,
parallel port testing, tiered execution, and progress reporting.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from itertools import product
from typing import Any, Callable

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager
from src.utils.log_capture import TestLogCapture
from src.specs.spec_registry import SpecRegistry
from src.models.test_case import (
    DUTProfile,
    FrameCapture,
    FrameType,
    ProtocolType,
    TestCase,
    TestCaseParameters,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
    TestSuiteReport,
    TestTier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, str, TestStatus | None], None]


# ---------------------------------------------------------------------------
# Test Case Generator
# ---------------------------------------------------------------------------


class TestCaseGenerator:
    """
    Generates concrete test cases by expanding spec definitions across
    parameter combinations (ports × VIDs × frame types × TPIDs × protocols).

    Supports smart sampling for tiered execution.
    """

    def __init__(self, dut_profile: DUTProfile, config: ConfigManager) -> None:
        self.dut = dut_profile
        self.config = config

    def generate(
        self,
        spec: TestSpecDefinition,
        tier: TestTier = TestTier.FULL,
    ) -> list[TestCase]:
        """Generate all test cases for a single specification."""
        tier_cfg = self.config.get_tier_config(tier)

        # Determine parameter ranges based on tier
        vid_range = self._get_vid_range(spec, tier_cfg)
        frame_types = self._get_frame_types(spec)
        tpid_values = spec.applicable_tpids
        port_pairs = self._get_port_pairs(spec, tier_cfg)

        cases: list[TestCase] = []
        for ingress, egress in port_pairs:
            for vid in vid_range:
                for frame_type in frame_types:
                    tpids = tpid_values if frame_type != FrameType.UNTAGGED else [0x8100]
                    for tpid in tpids:
                        case_id = self._make_case_id(spec, ingress, egress, vid, frame_type, tpid)
                        cases.append(TestCase(
                            case_id=case_id,
                            spec_id=spec.spec_id,
                            tc8_reference=spec.tc8_reference,
                            section=spec.section,
                            tier=tier,
                            parameters=TestCaseParameters(
                                ingress_port=ingress,
                                egress_ports=egress if isinstance(egress, list) else [egress],
                                vid=vid,
                                frame_type=frame_type,
                                tpid=tpid,
                            ),
                            description=f"{spec.title} — Port {ingress}→{egress}, VID={vid}, {frame_type.value}",
                        ))

        logger.info(
            "Generated %d test cases for %s (tier=%s)",
            len(cases), spec.spec_id, tier.value,
        )
        return cases

    def _get_vid_range(self, spec: TestSpecDefinition, tier_cfg: Any) -> list[int]:
        """Determine VID range based on spec and tier sampling."""
        full_range = spec.parameters.get("vid_range", [1, 4095])

        if isinstance(tier_cfg.vid_sampling, list):
            return tier_cfg.vid_sampling

        if tier_cfg.vid_sampling == "all":
            start, end = full_range[0], full_range[1] if len(full_range) > 1 else full_range[0]
            return list(range(start, end + 1))

        # Default: representative sample
        return [0, 1, 100, 1000, 2048, 4094, 4095]

    def _get_frame_types(self, spec: TestSpecDefinition) -> list[FrameType]:
        """Get applicable frame types for a spec."""
        return spec.applicable_frame_types

    def _get_port_pairs(self, spec: TestSpecDefinition, tier_cfg: Any) -> list[tuple[int, int]]:
        """Generate ingress/egress port pair combinations."""
        port_ids = [p.port_id for p in self.dut.ports]
        if not port_ids:
            port_ids = list(range(self.dut.port_count))

        if tier_cfg.port_sampling == "first_pair":
            if len(port_ids) >= 2:
                return [(port_ids[0], port_ids[1])]
            return [(port_ids[0], port_ids[0])]

        if tier_cfg.port_sampling == "all_pairs":
            return [(i, e) for i, e in product(port_ids, port_ids) if i != e]

        # all_combinations (default)
        return [(i, e) for i, e in product(port_ids, port_ids) if i != e]

    @staticmethod
    def _make_case_id(
        spec: TestSpecDefinition,
        ingress: int,
        egress: int | list[int],
        vid: int,
        frame_type: FrameType,
        tpid: int,
    ) -> str:
        """Generate a unique, human-readable test case ID."""
        eg = egress if isinstance(egress, int) else "_".join(str(e) for e in egress)
        ft_short = {"untagged": "UT", "single_tagged": "ST", "double_tagged": "DT"}
        return (
            f"{spec.spec_id}_P{ingress}_P{eg}_V{vid}"
            f"_{ft_short.get(frame_type.value, 'XX')}"
            f"_T{tpid:04X}"
        )


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------


class TestRunner:
    """
    Main test execution engine.

    Orchestrates the full testing workflow:
    1. Load configuration and specs
    2. Generate test cases for the selected tier
    3. Execute test cases with session isolation
    4. Validate results
    5. Generate report
    """

    def __init__(
        self,
        config: ConfigManager,
        session_manager: SessionManager,
        validator: ResultValidator | None = None,
        interface: Any = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.session = session_manager
        self.validator = validator or ResultValidator()
        self.interface = interface
        self.progress_callback = progress_callback
        self._running = False
        self._cancel_requested = False

        # Initialize spec registry for section-specific dispatch
        try:
            self._spec_registry = SpecRegistry(config, self.validator)
            logger.info("SpecRegistry loaded — %d sections", len(self._spec_registry.supported_sections))
        except Exception as exc:
            logger.warning("SpecRegistry unavailable (fallback to generic): %s", exc)
            self._spec_registry = None

    @property
    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        """Request cancellation of the current test run."""
        self._cancel_requested = True
        logger.info("Test run cancellation requested")

    async def run_suite(
        self,
        tier: TestTier = TestTier.SMOKE,
        sections: list[TestSection] | None = None,
        spec_ids: list[str] | None = None,
    ) -> TestSuiteReport:
        """
        Execute a full test suite.

        Args:
            tier: Execution tier (smoke/core/full).
            sections: Optional filter — only run specs from these sections.
            spec_ids: Optional filter — only run these specific spec IDs.

        Returns:
            TestSuiteReport with all results.
        """
        self._running = True
        self._cancel_requested = False

        dut = self.config.dut_profile
        if dut is None:
            raise RuntimeError("No DUT profile loaded — call config.load_dut_profile() first")

        # Resolve spec list
        specs = self._resolve_specs(tier, sections, spec_ids)
        logger.info(
            "Starting %s suite: %d specs, DUT=%s (%d ports)",
            tier.value, len(specs), dut.name, dut.port_count,
        )

        # Generate all test cases
        generator = TestCaseGenerator(dut, self.config)
        all_cases: list[TestCase] = []
        for spec in specs:
            all_cases.extend(generator.generate(spec, tier))

        logger.info("Total test cases to execute: %d", len(all_cases))

        # Create report
        report = TestSuiteReport(
            report_id=str(uuid.uuid4())[:8],
            dut_profile=dut,
            tier=tier,
            total_cases=len(all_cases),
        )

        # Execute test cases
        t0 = time.perf_counter()
        for idx, case in enumerate(all_cases):
            if self._cancel_requested:
                logger.info("Test run cancelled at case %d/%d", idx + 1, len(all_cases))
                break

            result = await self._execute_case(case)
            report.results.append(result)

            # Update counters
            match result.status:
                case TestStatus.PASS:
                    report.passed += 1
                case TestStatus.FAIL:
                    report.failed += 1
                case TestStatus.INFORMATIONAL:
                    report.informational += 1
                case TestStatus.SKIP:
                    report.skipped += 1
                case TestStatus.ERROR:
                    report.errors += 1

            # Progress callback
            if self.progress_callback:
                self.progress_callback(idx + 1, len(all_cases), case.case_id, result.status)

        report.duration_s = time.perf_counter() - t0
        self._running = False

        logger.info(
            "Suite complete: %d passed, %d failed, %d info, %d skip, %d error (%.1fs)",
            report.passed, report.failed, report.informational,
            report.skipped, report.errors, report.duration_s,
        )
        return report

    async def _execute_case(self, case: TestCase) -> TestResult:
        """Execute a single test case within a managed session."""

        with TestLogCapture() as capture:
            logger.debug("Executing: %s", case.case_id)
            try:
                async with self.session.test_session() as session:
                    if not session.is_clean:
                        result = TestResult(
                            case_id=case.case_id,
                            spec_id=case.spec_id,
                            tc8_reference=case.tc8_reference,
                            section=case.section,
                            status=TestStatus.ERROR,
                            message="Session setup failed — DUT not in clean state",
                        )
                        result.log_entries = capture.entries
                        return result

                    # Try spec registry first (section-specific logic)
                    if self._spec_registry is not None and self._spec_registry.has_handler(case.section):
                        spec = self.config.spec_definitions.get(case.spec_id)
                        if spec is not None:
                            handler = self._spec_registry.get_handler(case.section)
                            result = await handler.execute_spec(spec, case, self.interface)
                            result.log_entries = capture.entries
                            return result

                    # Fallback: generic send/capture flow
                    t0 = time.perf_counter()

                    # Build and send frame
                    sent_frames = await self._send_test_frame(case)

                    # Capture responses on all ports
                    received_frames = await self._capture_responses(case)

                    duration_ms = (time.perf_counter() - t0) * 1000

                    # Build expected outcome from spec
                    spec = self.config.spec_definitions.get(case.spec_id)
                    expected = spec.expected_result if spec else {}

                    # Add dynamic port expectations
                    expected = self._build_dynamic_expected(case, expected)

                    # Validate
                    result = self.validator.validate(
                        case, sent_frames, received_frames, expected, duration_ms
                    )
                    result.log_entries = capture.entries
                    return result

            except Exception as exc:
                logger.exception("Error executing %s: %s", case.case_id, exc)
                result = TestResult(
                    case_id=case.case_id,
                    spec_id=case.spec_id,
                    tc8_reference=case.tc8_reference,
                    section=case.section,
                    status=TestStatus.ERROR,
                    message=f"Framework error: {exc}",
                    error_detail=str(exc),
                )
                result.log_entries = capture.entries
                return result


    async def _send_test_frame(self, case: TestCase) -> list[FrameCapture]:
        """Send test frame(s) via the DUT interface."""
        if self.interface is None:
            logger.warning("No DUT interface configured — simulating send")
            return [FrameCapture(
                port_id=case.parameters.ingress_port,
                timestamp=time.time(),
                src_mac=case.parameters.src_mac,
                dst_mac=case.parameters.dst_mac,
            )]

        return await self.interface.send_frame(case)

    async def _capture_responses(
        self, case: TestCase
    ) -> dict[int, list[FrameCapture]]:
        """Capture response frames from all DUT ports."""
        if self.interface is None:
            logger.warning("No DUT interface configured — returning empty captures")
            return {}

        timeout = self.config.defaults.frame_timeout_s
        return await self.interface.capture_frames(case, timeout=timeout)

    def _build_dynamic_expected(
        self, case: TestCase, spec_expected: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Build dynamic expected outcome based on test case parameters
        and DUT profile.
        """
        expected = dict(spec_expected)
        dut = self.config.dut_profile
        if dut is None:
            return expected

        # If forward_to is "member_ports_only", resolve to actual port IDs
        forward_rule = expected.get("forward_to", "")
        if forward_rule == "member_ports_only":
            vid = case.parameters.vid
            member_ports = [
                p.port_id for p in dut.ports
                if vid in p.vlan_membership and p.port_id != case.parameters.ingress_port
            ]
            expected["forward_to_ports"] = member_ports
            expected["blocked_ports"] = [
                p.port_id for p in dut.ports
                if p.port_id not in member_ports and p.port_id != case.parameters.ingress_port
            ]

        elif forward_rule == "all_ports":
            expected["forward_to_ports"] = [
                p.port_id for p in dut.ports
                if p.port_id != case.parameters.ingress_port
            ]

        return expected

    def _resolve_specs(
        self,
        tier: TestTier,
        sections: list[TestSection] | None,
        spec_ids: list[str] | None,
    ) -> list[TestSpecDefinition]:
        """Resolve which specs to run based on filters."""
        if spec_ids:
            return [
                self.config.spec_definitions[sid]
                for sid in spec_ids
                if sid in self.config.spec_definitions
            ]

        specs = self.config.get_specs_for_tier(tier)

        if sections:
            specs = [s for s in specs if s.section in sections]

        return specs
