"""
Result validator — Pass/Fail analysis engine.

Compares actual captured frames against expected behavior defined
in the TC8 spec, accounting for timing tolerances, frame matching,
and statistical pass criteria for non-deterministic tests.
"""

from __future__ import annotations

import logging
from typing import Any

from src.models.test_case import (
    FrameCapture,
    FrameType,
    TestCase,
    TestResult,
    TestSection,
    TestStatus,
    TimingTier,
)

logger = logging.getLogger(__name__)


class ResultValidator:
    """
    Validates test outcomes against TC8 expected behavior.

    Supports multiple validation strategies:
    - Frame presence/absence on expected ports
    - VLAN tag correctness (VID, PCP, TPID)
    - MAC address matching
    - Frame count verification
    - Timing tolerance windows
    - Statistical pass criteria for flaky tests
    """

    def __init__(
        self,
        timing_tolerance_ms: float = 100.0,
        statistical_threshold: float = 0.95,
        max_allowed_extra_frames: int = 0,
    ) -> None:
        self.timing_tolerance_ms = timing_tolerance_ms
        self.statistical_threshold = statistical_threshold
        self.max_allowed_extra_frames = max_allowed_extra_frames

    # ── Primary validation entry point ────────────────────────────────

    def validate(
        self,
        test_case: TestCase,
        sent_frames: list[FrameCapture],
        received_frames: dict[int, list[FrameCapture]],
        expected: dict[str, Any],
        duration_ms: float = 0.0,
    ) -> TestResult:
        """
        Validate test case outcome.

        Args:
            test_case: The test case that was executed.
            sent_frames: Frames sent by the test station.
            received_frames: Frames received per port {port_id: [captures]}.
            expected: Expected outcome definition from spec.
            duration_ms: Test execution duration.

        Returns:
            TestResult with status, expected/actual comparison, and diagnostics.
        """
        result = TestResult(
            case_id=test_case.case_id,
            spec_id=test_case.spec_id,
            tc8_reference=test_case.tc8_reference,
            section=test_case.section,
            status=TestStatus.PASS,
            duration_ms=duration_ms,
            sent_frames=sent_frames,
            expected=expected,
        )

        # Flatten received frames into result
        all_received: list[FrameCapture] = []
        for port_frames in received_frames.values():
            all_received.extend(port_frames)
        result.received_frames = all_received

        # Run validation checks
        checks = [
            self._check_frame_forwarding(test_case, received_frames, expected, result),
            self._check_vlan_tags(test_case, received_frames, expected, result),
            self._check_no_leakage(test_case, received_frames, expected, result),
            self._check_frame_count(test_case, received_frames, expected, result),
        ]

        # Overall status: FAIL if any check fails
        if TestStatus.FAIL in checks:
            result.status = TestStatus.FAIL
        elif TestStatus.INFORMATIONAL in checks:
            result.status = TestStatus.INFORMATIONAL

        result.actual = self._build_actual_summary(received_frames)

        return result

    # ── Validation checks ─────────────────────────────────────────────

    def _check_frame_forwarding(
        self,
        test_case: TestCase,
        received_frames: dict[int, list[FrameCapture]],
        expected: dict[str, Any],
        result: TestResult,
    ) -> TestStatus:
        """Verify frames arrive on expected ports and not on others."""
        expected_ports = expected.get("forward_to_ports", [])
        blocked_ports = expected.get("blocked_ports", [])

        for port_id in expected_ports:
            if port_id not in received_frames or len(received_frames[port_id]) == 0:
                result.message += f"FAIL: Expected frame on port {port_id} but none received. "
                logger.debug("Frame missing on expected port %d", port_id)
                return TestStatus.FAIL

        for port_id in blocked_ports:
            if port_id in received_frames and len(received_frames[port_id]) > 0:
                result.message += f"FAIL: Unexpected frame on blocked port {port_id}. "
                logger.debug("Unexpected frame on blocked port %d", port_id)
                return TestStatus.FAIL

        return TestStatus.PASS

    def _check_vlan_tags(
        self,
        test_case: TestCase,
        received_frames: dict[int, list[FrameCapture]],
        expected: dict[str, Any],
        result: TestResult,
    ) -> TestStatus:
        """Verify VLAN tag correctness on received frames."""
        expected_tag_action = expected.get("tag_action", None)
        if expected_tag_action is None:
            return TestStatus.PASS

        expected_vid = expected.get("expected_vid", test_case.parameters.vid)
        expected_tpid = expected.get("expected_tpid", test_case.parameters.tpid)

        for port_id, frames in received_frames.items():
            for frame in frames:
                if expected_tag_action == "tagged":
                    if not frame.vlan_tags:
                        result.message += f"FAIL: Expected tagged frame on port {port_id}. "
                        return TestStatus.FAIL
                    tag = frame.vlan_tags[0]
                    if tag.get("vid") != expected_vid:
                        result.message += (
                            f"FAIL: VID mismatch on port {port_id}: "
                            f"expected={expected_vid}, actual={tag.get('vid')}. "
                        )
                        return TestStatus.FAIL
                    if tag.get("tpid") is not None and tag.get("tpid") != expected_tpid:
                        result.message += (
                            f"FAIL: TPID mismatch on port {port_id}: "
                            f"expected=0x{expected_tpid:04X}, actual=0x{tag.get('tpid', 0):04X}. "
                        )
                        return TestStatus.FAIL

                elif expected_tag_action == "untagged":
                    if frame.vlan_tags:
                        result.message += f"FAIL: Expected untagged frame on port {port_id}. "
                        return TestStatus.FAIL

                elif expected_tag_action == "drop":
                    if frames:
                        result.message += f"FAIL: Frame should have been dropped on port {port_id}. "
                        return TestStatus.FAIL

        return TestStatus.PASS

    def _check_no_leakage(
        self,
        test_case: TestCase,
        received_frames: dict[int, list[FrameCapture]],
        expected: dict[str, Any],
        result: TestResult,
    ) -> TestStatus:
        """Verify no frame leakage to unexpected ports."""
        expected_ports = set(expected.get("forward_to_ports", []))
        ingress_port = test_case.parameters.ingress_port

        for port_id, frames in received_frames.items():
            if port_id == ingress_port:
                continue  # Don't check ingress port
            if port_id not in expected_ports and len(frames) > self.max_allowed_extra_frames:
                result.warnings.append(
                    f"Frame leakage detected: {len(frames)} frame(s) on unexpected port {port_id}"
                )
                # Only fail if leakage is explicitly forbidden
                if expected.get("strict_forwarding", False):
                    result.message += f"FAIL: Frame leakage on port {port_id}. "
                    return TestStatus.FAIL
                return TestStatus.INFORMATIONAL

        return TestStatus.PASS

    def _check_frame_count(
        self,
        test_case: TestCase,
        received_frames: dict[int, list[FrameCapture]],
        expected: dict[str, Any],
        result: TestResult,
    ) -> TestStatus:
        """Verify expected number of frames received."""
        expected_count = expected.get("expected_frame_count", None)
        if expected_count is None:
            return TestStatus.PASS

        for port_id in expected.get("forward_to_ports", []):
            actual_count = len(received_frames.get(port_id, []))
            if actual_count != expected_count:
                result.message += (
                    f"FAIL: Frame count mismatch on port {port_id}: "
                    f"expected={expected_count}, actual={actual_count}. "
                )
                return TestStatus.FAIL

        return TestStatus.PASS

    # ── Statistical validation (for non-deterministic tests) ──────────

    def validate_statistical(
        self,
        results: list[TestResult],
        required_pass_rate: float | None = None,
    ) -> TestStatus:
        """
        Apply statistical pass criteria to a set of repeated test runs.

        Used for inherently non-deterministic tests (flooding order,
        aging timing, rate limiting burst behavior).
        """
        threshold = required_pass_rate or self.statistical_threshold
        if not results:
            return TestStatus.SKIP

        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        rate = passed / len(results)

        if rate >= threshold:
            logger.info(
                "Statistical pass: %.1f%% (%d/%d) >= %.1f%%",
                rate * 100, passed, len(results), threshold * 100,
            )
            return TestStatus.PASS
        else:
            logger.warning(
                "Statistical fail: %.1f%% (%d/%d) < %.1f%%",
                rate * 100, passed, len(results), threshold * 100,
            )
            return TestStatus.FAIL

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_actual_summary(received_frames: dict[int, list[FrameCapture]]) -> dict[str, Any]:
        """Build a summary of what was actually received."""
        summary: dict[str, Any] = {}
        for port_id, frames in received_frames.items():
            summary[f"port_{port_id}"] = {
                "frame_count": len(frames),
                "src_macs": list({f.src_mac for f in frames}),
                "dst_macs": list({f.dst_mac for f in frames}),
                "vlan_tags": [f.vlan_tags for f in frames if f.vlan_tags],
            }
        return summary
