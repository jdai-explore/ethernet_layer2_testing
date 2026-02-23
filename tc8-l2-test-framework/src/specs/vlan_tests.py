"""
Section 5.3 — VLAN test specifications.

Validates IEEE 802.1Q / 802.1ad VLAN handling:
- Membership verification, tag insertion/removal
- PVID assignment, priority-tagged frames
- Double-tagged (Q-in-Q) processing
- Reserved VID handling, VLAN filtering
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
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


class VLANTests(BaseTestSpec):
    """
    TC8 Section 5.3 — VLAN testing.

    21 specifications covering VLAN membership, tagging operations,
    PVID behavior, double-tagging, and VLAN filtering.
    """

    section = TestSection.VLAN
    section_name = "VLAN"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to VLAN-specific handler."""
        handlers = {
            "SWITCH_VLAN_001": self._test_vlan_membership,
            "SWITCH_VLAN_002": self._test_vlan_membership_tagged,
            "SWITCH_VLAN_003": self._test_vlan_non_member_drop,
            "SWITCH_VLAN_004": self._test_vlan_tag_insertion,
            "SWITCH_VLAN_005": self._test_vlan_tag_removal,
            "SWITCH_VLAN_006": self._test_pvid_assignment,
            "SWITCH_VLAN_007": self._test_pvid_untagged_ingress,
            "SWITCH_VLAN_008": self._test_priority_tagged,
            "SWITCH_VLAN_009": self._test_reserved_vid_0,
            "SWITCH_VLAN_010": self._test_double_tagged_forwarding,
            "SWITCH_VLAN_011": self._test_vlan_membership_all_ports,
            "SWITCH_VLAN_012": self._test_vlan_isolation,
            "SWITCH_VLAN_013": self._test_trunk_to_access,
            "SWITCH_VLAN_014": self._test_access_to_trunk,
            "SWITCH_VLAN_015": self._test_pvid_mismatch,
            "SWITCH_VLAN_016": self._test_double_tagged_s_vlan,
            "SWITCH_VLAN_017": self._test_double_tagged_c_vlan_preservation,
            "SWITCH_VLAN_018": self._test_double_tagged_strip,
            "SWITCH_VLAN_019": self._test_vlan_filtering_ingress,
            "SWITCH_VLAN_020": self._test_vlan_filtering_egress,
            "SWITCH_VLAN_021": self._test_reserved_vid_4095,
        }

        handler = handlers.get(spec.spec_id, self._test_generic_vlan)
        return await handler(spec, test_case, interface)

    # ── VLAN Membership (001-005) ─────────────────────────────────────

    async def _test_vlan_membership(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_VLAN_001 — VLAN membership verification (untagged).

        Send untagged frame on a port with PVID=X.
        Verify frame forwarded only to ports that are members of VLAN X.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        # Determine expected ports: members of the VID
        dut = self.config.dut_profile
        if dut and dut.port_count == 1:
            logger.warning("[%s] Running in 1-port mode. Forwarding cannot be fully verified as there are no egress ports.", spec.spec_id)

        member_ports = self._get_member_ports(params.vid, params.ingress_port, dut)
        non_member_ports = self._get_non_member_ports(params.vid, params.ingress_port, dut)

        expected = {
            "forward_to_ports": member_ports,
            "blocked_ports": non_member_ports,
            "strict_forwarding": True,
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_vlan_membership_tagged(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_002 — VLAN membership with tagged frames."""
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        case.parameters.frame_type = FrameType.SINGLE_TAGGED
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        member_ports = self._get_member_ports(params.vid, params.ingress_port, dut)
        non_member_ports = self._get_non_member_ports(params.vid, params.ingress_port, dut)

        expected = {
            "forward_to_ports": member_ports,
            "blocked_ports": non_member_ports,
            "strict_forwarding": True,
            "tag_action": "as_configured",
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_vlan_non_member_drop(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_003 — Non-member VLAN frame drop."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()

        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        expected = {
            "forward_to_ports": [],
            "tag_action": "drop",
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_vlan_tag_insertion(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_004 — Tag insertion on untagged ingress to trunk egress."""
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        trunk_ports = [p.port_id for p in (dut.ports if dut else [])
                       if p.is_trunk and p.port_id != params.ingress_port
                       and params.vid in p.vlan_membership]

        expected = {
            "forward_to_ports": trunk_ports,
            "tag_action": "tagged",
            "expected_vid": params.vid,
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_vlan_tag_removal(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_005 — Tag removal on tagged ingress to access egress."""
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        case.parameters.frame_type = FrameType.SINGLE_TAGGED
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        access_ports = [p.port_id for p in (dut.ports if dut else [])
                        if not p.is_trunk and p.port_id != params.ingress_port
                        and params.vid in p.vlan_membership]

        expected = {
            "forward_to_ports": access_ports,
            "tag_action": "untagged",
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    # ── PVID (006-009) ────────────────────────────────────────────────

    async def _test_pvid_assignment(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_006 — PVID assignment validation."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_pvid_untagged_ingress(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_007 — Untagged frame classified to PVID."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.frame_type = FrameType.UNTAGGED
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_priority_tagged(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_008 — Priority-tagged frame (VID=0) handling."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.vid = 0
        case.parameters.frame_type = FrameType.SINGLE_TAGGED
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_reserved_vid_0(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_009 — Reserved VID 0 handling."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.vid = 0
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    # ── Double-Tagged (010, 016-018) ──────────────────────────────────

    async def _test_double_tagged_forwarding(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_010 — Double-tagged frame forwarding."""
        self.log_spec_info(spec)
        dut = self.config.dut_profile
        if dut and not dut.supports_double_tagging:
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.SKIP,
                message="DUT does not support double tagging",
            )
        t0 = time.perf_counter()
        case.parameters.frame_type = FrameType.DOUBLE_TAGGED
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_double_tagged_s_vlan(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_016 — S-VLAN based forwarding for Q-in-Q."""
        return await self._test_double_tagged_forwarding(spec, case, interface)

    async def _test_double_tagged_c_vlan_preservation(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_017 — C-VLAN preservation in double-tagged frames."""
        return await self._test_double_tagged_forwarding(spec, case, interface)

    async def _test_double_tagged_strip(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_018 — Outer S-VLAN tag stripping."""
        return await self._test_double_tagged_forwarding(spec, case, interface)

    # ── VLAN Isolation & Trunk/Access (011-015) ───────────────────────

    async def _test_vlan_membership_all_ports(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_011 — Verify VLAN membership across all ports."""
        return await self._test_vlan_membership(spec, case, interface)

    async def _test_vlan_isolation(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_012 — VLAN isolation between VLANs."""
        return await self._test_vlan_non_member_drop(spec, case, interface)

    async def _test_trunk_to_access(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_013 — Trunk to access port tag removal."""
        return await self._test_vlan_tag_removal(spec, case, interface)

    async def _test_access_to_trunk(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_014 — Access to trunk port tag insertion."""
        return await self._test_vlan_tag_insertion(spec, case, interface)

    async def _test_pvid_mismatch(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_015 — PVID mismatch between ports."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    # ── VLAN Filtering (019-021) ──────────────────────────────────────

    async def _test_vlan_filtering_ingress(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_019 — Ingress VLAN filtering."""
        return await self._test_vlan_non_member_drop(spec, case, interface)

    async def _test_vlan_filtering_egress(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_020 — Egress VLAN filtering."""
        return await self._test_vlan_non_member_drop(spec, case, interface)

    async def _test_reserved_vid_4095(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_VLAN_021 — Reserved VID 4095 handling."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.vid = 4095
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {"tag_action": "drop", **spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_generic_vlan(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """Fallback handler."""
        logger.warning("No specific handler for %s", spec.spec_id)
        return await self._test_vlan_membership(spec, case, interface)

    # ── Helpers ───────────────────────────────────────────────────────

    async def _send_and_capture(
        self, case: TestCase, interface: Any
    ) -> tuple[list[FrameCapture], dict[int, list[FrameCapture]]]:
        """Send test frame and capture responses."""
        params = case.parameters
        if interface is not None:
            sent = await interface.send_frame(case)
            received = await interface.capture_frames(case)
            return sent, received

        # Simulation mode
        sent = [FrameCapture(
            port_id=params.ingress_port, timestamp=time.time(),
            src_mac=params.src_mac, dst_mac=params.dst_mac,
        )]
        received: dict[int, list[FrameCapture]] = {}
        dut = self.config.dut_profile
        if dut:
            for p in dut.ports:
                if p.port_id != params.ingress_port and params.vid in p.vlan_membership:
                    received[p.port_id] = [FrameCapture(
                        port_id=p.port_id, timestamp=time.time(),
                        src_mac=params.src_mac, dst_mac=params.dst_mac,
                    )]
        return sent, received

    @staticmethod
    def _get_member_ports(vid: int, ingress: int, dut: Any) -> list[int]:
        if dut is None:
            return []
        return [p.port_id for p in dut.ports
                if vid in p.vlan_membership and p.port_id != ingress]

    @staticmethod
    def _get_non_member_ports(vid: int, ingress: int, dut: Any) -> list[int]:
        if dut is None:
            return []
        return [p.port_id for p in dut.ports
                if vid not in p.vlan_membership and p.port_id != ingress]
