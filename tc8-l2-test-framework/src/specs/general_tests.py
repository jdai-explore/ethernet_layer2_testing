"""
Section 5.4 — General test specifications.

Validates fundamental Ethernet switching behavior:
- Unicast forwarding, broadcast flooding, multicast handling
- Frame size limits (min/max/runt/jumbo)
- Startup time, link state transitions
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.core.result_validator import ResultValidator
from src.core.config_manager import ConfigManager
from src.models.test_case import (
    DUTProfile,
    FrameCapture,
    FrameType,
    TestCase,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
    TimingTier,
)
from src.specs.base_spec import BaseTestSpec

logger = logging.getLogger(__name__)


class GeneralTests(BaseTestSpec):
    """
    TC8 Section 5.4 — General switching tests.

    Covers basic forwarding, frame sizes, error handling,
    startup behavior, and link state management.
    """

    section = TestSection.GENERAL
    section_name = "General"

    # ── Spec dispatch table ───────────────────────────────────────────

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to spec-specific handler based on spec_id."""
        handlers = {
            "SWITCH_GEN_001": self._test_unicast_forwarding,
            "SWITCH_GEN_002": self._test_broadcast_flooding,
            "SWITCH_GEN_003": self._test_multicast_forwarding,
            "SWITCH_GEN_004": self._test_unknown_unicast,
            "SWITCH_GEN_005": self._test_minimum_frame_size,
            "SWITCH_GEN_006": self._test_maximum_frame_size,
            "SWITCH_GEN_007": self._test_runt_frame_handling,
            "SWITCH_GEN_008": self._test_startup_time,
            "SWITCH_GEN_009": self._test_link_up_event,
            "SWITCH_GEN_010": self._test_link_down_event,
        }

        handler = handlers.get(spec.spec_id, self._test_generic)
        return await handler(spec, test_case, interface)

    # ── Individual spec handlers ──────────────────────────────────────

    async def _test_unicast_forwarding(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_001 — Known unicast forwarding.

        Send a unicast frame with a known destination MAC.
        Verify it is forwarded ONLY to the port where the destination
        MAC was previously learned, not flooded to all ports.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        sent_frames: list[FrameCapture] = []
        received: dict[int, list[FrameCapture]] = {}

        if interface is not None:
            # Step 1: Pre-learn destination MAC on the egress port.
            # Send a frame FROM dst_mac on the expected egress port
            # so the DUT associates dst_mac with that port.
            if params.egress_ports:
                learning_case = case.model_copy(update={
                    "parameters": case.parameters.model_copy(update={
                        "src_mac": params.dst_mac,
                        "dst_mac": params.src_mac,
                        "ingress_port": params.egress_ports[0],
                    }),
                })
                await interface.send_frame(learning_case)
                await asyncio.sleep(0.5)  # Allow DUT to process learning

            # Step 2: Send actual test frame and capture
            sent_frames, received = await interface.send_and_capture(case)
        else:
            # Simulation mode — create synthetic frames
            sent_frames = [FrameCapture(
                port_id=params.ingress_port,
                timestamp=time.time(),
                src_mac=params.src_mac,
                dst_mac=params.dst_mac,
            )]
            # Simulate: unicast should go to learned port only
            for ep in params.egress_ports:
                received[ep] = [FrameCapture(
                    port_id=ep,
                    timestamp=time.time(),
                    src_mac=params.src_mac,
                    dst_mac=params.dst_mac,
                )]

        duration_ms = (time.perf_counter() - t0) * 1000

        # Validate: frame should arrive only on egress port(s)
        expected = {
            "forward_to_ports": params.egress_ports,
            "strict_forwarding": True,
            **spec.expected_result,
        }

        return self.validator.validate(case, sent_frames, received, expected, duration_ms)

    async def _test_broadcast_flooding(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_002 — Broadcast frame flooding.

        Send a broadcast frame. Verify it is flooded to ALL other ports
        (not reflected back to ingress port).
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        bcast_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"dst_mac": "ff:ff:ff:ff:ff:ff"}),
        })

        sent_frames: list[FrameCapture] = []
        received: dict[int, list[FrameCapture]] = {}

        if interface is not None:
            sent_frames = await interface.send_frame(bcast_case)
            received = await interface.capture_frames(bcast_case)
        else:
            sent_frames = [FrameCapture(
                port_id=params.ingress_port, timestamp=time.time(),
                src_mac=params.src_mac, dst_mac="ff:ff:ff:ff:ff:ff",
            )]
            dut = self.config.dut_profile
            if dut:
                for p in dut.ports:
                    if p.port_id != params.ingress_port:
                        received[p.port_id] = [FrameCapture(
                            port_id=p.port_id, timestamp=time.time(),
                            src_mac=params.src_mac, dst_mac="ff:ff:ff:ff:ff:ff",
                        )]

        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_other_ports = [
            p.port_id for p in (dut.ports if dut else [])
            if p.port_id != params.ingress_port
        ]

        expected = {
            "forward_to_ports": all_other_ports,
            "strict_forwarding": False,
            **spec.expected_result,
        }

        return self.validator.validate(bcast_case, sent_frames, received, expected, duration_ms)

    async def _test_multicast_forwarding(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_003 — Multicast frame forwarding.

        Send a multicast frame. Verify it is forwarded to all ports
        in the multicast group (or flooded if no IGMP snooping).
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        mcast_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"dst_mac": "01:00:5e:00:00:01"}),
        })

        sent_frames: list[FrameCapture] = []
        received: dict[int, list[FrameCapture]] = {}

        if interface is not None:
            sent_frames = await interface.send_frame(mcast_case)
            received = await interface.capture_frames(mcast_case)
        else:
            sent_frames = [FrameCapture(
                port_id=params.ingress_port, timestamp=time.time(),
                src_mac=params.src_mac, dst_mac="01:00:5e:00:00:01",
            )]
            dut = self.config.dut_profile
            if dut:
                for p in dut.ports:
                    if p.port_id != params.ingress_port:
                        received[p.port_id] = [FrameCapture(
                            port_id=p.port_id, timestamp=time.time(),
                            src_mac=params.src_mac, dst_mac="01:00:5e:00:00:01",
                        )]

        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_other = [p.port_id for p in (dut.ports if dut else [])
                     if p.port_id != params.ingress_port]

        expected = {"forward_to_ports": all_other, **spec.expected_result}
        return self.validator.validate(mcast_case, sent_frames, received, expected, duration_ms)

    async def _test_unknown_unicast(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_004 — Unknown unicast flooding.

        Send a unicast frame with an unknown destination MAC.
        Verify it is flooded to all other ports.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        unknown_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"dst_mac": "02:ff:ff:ff:ff:ff"}),
        })

        sent_frames: list[FrameCapture] = []
        received: dict[int, list[FrameCapture]] = {}

        if interface is not None:
            sent_frames = await interface.send_frame(unknown_case)
            received = await interface.capture_frames(unknown_case)
        else:
            sent_frames = [FrameCapture(
                port_id=params.ingress_port, timestamp=time.time(),
                src_mac=params.src_mac, dst_mac="02:ff:ff:ff:ff:ff",
            )]
            dut = self.config.dut_profile
            if dut:
                for p in dut.ports:
                    if p.port_id != params.ingress_port:
                        received[p.port_id] = [FrameCapture(
                            port_id=p.port_id, timestamp=time.time(),
                            src_mac=params.src_mac, dst_mac="02:ff:ff:ff:ff:ff",
                        )]

        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_other = [p.port_id for p in (dut.ports if dut else [])
                     if p.port_id != params.ingress_port]

        expected = {"forward_to_ports": all_other, **spec.expected_result}
        return self.validator.validate(unknown_case, sent_frames, received, expected, duration_ms)

    async def _test_minimum_frame_size(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_005 — Minimum Ethernet frame size (64 bytes).

        Verify the switch correctly forwards minimum-size frames.
        """
        self.log_spec_info(spec)
        min_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"payload_size": 64}),
        })
        return await self._test_unicast_forwarding(spec, min_case, interface)

    async def _test_maximum_frame_size(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_006 — Maximum Ethernet frame size (1518 bytes).

        Verify the switch correctly forwards maximum-size frames.
        """
        self.log_spec_info(spec)
        max_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"payload_size": 1518}),
        })
        return await self._test_unicast_forwarding(spec, max_case, interface)

    async def _test_runt_frame_handling(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_007 — Runt frame handling.

        Send a frame smaller than 64 bytes. Verify the switch either
        drops or pads the frame (behavior is implementation-specific).
        """
        self.log_spec_info(spec)
        # OS network stacks (Scapy included) pad Ethernet frames to 64 bytes.
        # Actually injecting a sub-64-byte frame requires AF_PACKET with ETH_P_ALL
        # and explicit manual padding suppression — not available in the current
        # Scapy send path.  Mark as SKIP with a clear hardware-required note.
        return TestResult(
            case_id=case.case_id,
            spec_id=case.spec_id,
            tc8_reference=case.tc8_reference,
            section=case.section,
            status=TestStatus.SKIP,
            message=(
                "Runt frame injection requires raw AF_PACKET socket with ETH_P_ALL "
                "and padding suppression — not supported by the current Scapy send path. "
                "Run this test with a dedicated hardware traffic generator."
            ),
        )

    async def _test_startup_time(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_GEN_008 — Switch startup time measurement.

        Measure time from power-on/reset to first successful frame forwarding.
        Requires DUT reset capability.
        """
        self.log_spec_info(spec)
        dut = self.config.dut_profile

        if dut is None or not dut.can_reset:
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.SKIP,
                message="DUT does not support reset — startup time test skipped",
            )

        t0 = time.perf_counter()
        # In real execution, would trigger DUT reset and measure time to first frame
        duration_ms = (time.perf_counter() - t0) * 1000

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            duration_ms=duration_ms,
            message="Startup time measurement requires physical DUT reset",
        )

    async def _test_link_up_event(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_GEN_009 — Link-up event handling."""
        self.log_spec_info(spec)
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            message="Link event tests require physical cable manipulation",
        )

    async def _test_link_down_event(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_GEN_010 — Link-down event handling."""
        self.log_spec_info(spec)
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            message="Link event tests require physical cable manipulation",
        )

    async def _test_generic(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """Fallback handler for unrecognized spec IDs."""
        self.log_spec_info(spec)
        logger.warning("No specific handler for %s — running generic forwarding test", spec.spec_id)
        return await self._test_unicast_forwarding(spec, case, interface)
