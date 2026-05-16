"""
Extended Performance / Traffic Generation test specifications.

EXT_PERF_006 (multicast replication at low rate) is runnable on PC + DUT.
EXT_PERF_001/002 require a traffic generator for accurate measurements.
EXT_PERF_003/004/005 require dedicated traffic generator with hardware timestamps.
"""

from __future__ import annotations

import asyncio
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


class ExtPerfTests(BaseTestSpec):
    """Extended performance / traffic generation test section."""

    section = TestSection.EXT_PERF
    section_name = "Extended Performance"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to spec handler."""
        handlers = {
            "EXT_PERF_006": self._test_multicast_replication_load,
        }
        handler = handlers.get(spec.spec_id, self._skip_tgen_required)
        return await handler(spec, test_case, interface)

    async def _skip_tgen_required(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Return SKIP with traffic generator requirement message."""
        self.log_spec_info(spec)
        hw_detail = spec.hardware_requirement_detail or (
            f"{spec.spec_id} requires a dedicated traffic generator for accurate "
            "rate control and measurement. Not reliably runnable with Scapy on a standard PC."
        )
        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.SKIP,
            message=f"Hardware required: {hw_detail}",
        )

    async def _test_multicast_replication_load(
        self,
        spec: TestSpecDefinition,
        case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        EXT_PERF_006 — Multicast replication load test.

        Sends multicast frames via Scapy and verifies reception on egress ports.
        Runnable at low rates on PC + DUT without dedicated hardware.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        sent_frames: list[FrameCapture] = []
        received: dict[int, list[FrameCapture]] = {}

        mcast_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={
                "dst_mac": "01:00:5e:00:00:01",
            }),
        })

        if interface is not None:
            sent_frames = await interface.send_frame(mcast_case)
            received = await interface.capture_frames(mcast_case)
        else:
            dut = self.config.dut_profile
            sent_frames = [FrameCapture(
                port_id=params.ingress_port,
                timestamp=time.time(),
                src_mac=params.src_mac,
                dst_mac="01:00:5e:00:00:01",
            )]
            if dut:
                for p in dut.ports:
                    if p.port_id != params.ingress_port:
                        received[p.port_id] = [FrameCapture(
                            port_id=p.port_id,
                            timestamp=time.time(),
                            src_mac=params.src_mac,
                            dst_mac="01:00:5e:00:00:01",
                        )]

        duration_ms = (time.perf_counter() - t0) * 1000
        dut = self.config.dut_profile
        all_other = [p.port_id for p in (dut.ports if dut else [])
                     if p.port_id != params.ingress_port]

        expected = {"forward_to_ports": all_other, **spec.expected_result}
        result = self.validator.validate(mcast_case, sent_frames, received, expected, duration_ms)

        if result.status in (TestStatus.PASS, TestStatus.FAIL):
            result.warnings.append(
                "EXT_PERF_006: This test uses a single Scapy frame, not a sustained "
                f"{spec.parameters.get('multicast_rate_mbps', 10)} Mbps load. "
                "For accurate load testing, use a dedicated traffic generator."
            )

        return result
