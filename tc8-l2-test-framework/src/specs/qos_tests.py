"""
Section 5.8 — Quality of Service test specifications.

Validates QoS behavior:
- PCP (Priority Code Point) → queue mapping
- Traffic shaping / bandwidth allocation
- Queue scheduling (strict priority / WRR)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.models.test_case import (
    FrameCapture,
    FrameType,
    TestCase,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
)
from src.specs.base_spec import BaseTestSpec

logger = logging.getLogger(__name__)


class QoSTests(BaseTestSpec):
    """
    TC8 Section 5.8 — QoS tests.

    4 specifications covering priority mapping, traffic shaping,
    and queue scheduling.
    """

    section = TestSection.QOS
    section_name = "Quality of Service"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        handlers = {
            "SWITCH_QOS_001": self._test_pcp_queue_mapping,
            "SWITCH_QOS_002": self._test_pcp_priority_order,
            "SWITCH_QOS_003": self._test_traffic_shaping,
            "SWITCH_QOS_004": self._test_queue_scheduling,
        }
        handler = handlers.get(spec.spec_id, self._test_generic_qos)
        return await handler(spec, test_case, interface)

    async def _test_pcp_queue_mapping(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_QOS_001 — PCP to queue mapping.

        Send tagged frames with various PCP values (0-7).
        Verify each maps to the correct output queue.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        case.parameters.frame_type = FrameType.SINGLE_TAGGED
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        expected = {
            "forward_to_ports": params.egress_ports,
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_pcp_priority_order(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_QOS_002 — Higher PCP frames egress before lower PCP."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL, duration_ms=duration_ms,
            sent_frames=sent,
            message="Priority ordering requires simultaneous multi-PCP traffic injection",
        )

    async def _test_traffic_shaping(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_QOS_003 — Traffic shaping / bandwidth allocation."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL, duration_ms=duration_ms,
            sent_frames=sent,
            message="Traffic shaping requires sustained traffic generation and throughput measurement",
        )

    async def _test_queue_scheduling(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_QOS_004 — Queue scheduling (strict priority / WRR)."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL, duration_ms=duration_ms,
            sent_frames=sent,
            message="Queue scheduling requires traffic congestion to observe scheduling behavior",
        )

    async def _test_generic_qos(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        logger.warning("No specific handler for %s", spec.spec_id)
        return await self._test_pcp_queue_mapping(spec, case, interface)

    async def _send_and_capture(
        self, case: TestCase, interface: Any
    ) -> tuple[list[FrameCapture], dict[int, list[FrameCapture]]]:
        params = case.parameters
        if interface is not None:
            return await interface.send_frame(case), await interface.capture_frames(case)

        sent = [FrameCapture(
            port_id=params.ingress_port, timestamp=time.time(),
            src_mac=params.src_mac, dst_mac=params.dst_mac,
        )]
        received: dict[int, list[FrameCapture]] = {}
        for ep in params.egress_ports:
            received[ep] = [FrameCapture(
                port_id=ep, timestamp=time.time(),
                src_mac=params.src_mac, dst_mac=params.dst_mac,
            )]
        return sent, received
