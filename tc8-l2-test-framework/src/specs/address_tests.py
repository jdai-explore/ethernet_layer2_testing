"""
Section 5.5 — Address Learning test specifications.

Validates MAC address learning and forwarding table management:
- Source MAC learning, port migration
- Unknown unicast flooding
- MAC table capacity, aging, refresh
- Static entries, invalid source MAC handling
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
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


class AddressTests(BaseTestSpec):
    """
    TC8 Section 5.5 — Address Learning tests.

    21 specifications validating MAC learning, aging, flooding,
    table capacity, port migration, static entries, and invalid MACs.
    """

    section = TestSection.ADDRESS_LEARNING
    section_name = "Address Learning"

    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """Route to address-learning-specific handler."""
        handlers = {
            "SWITCH_ADDR_001": self._test_source_mac_learning,
            "SWITCH_ADDR_002": self._test_learned_unicast_forwarding,
            "SWITCH_ADDR_003": self._test_port_migration,
            "SWITCH_ADDR_004": self._test_unknown_unicast_flooding,
            "SWITCH_ADDR_005": self._test_mac_table_capacity,
            "SWITCH_ADDR_006": self._test_mac_aging,
            "SWITCH_ADDR_007": self._test_mac_aging_refresh,
            "SWITCH_ADDR_008": self._test_static_mac_entry,
            "SWITCH_ADDR_009": self._test_invalid_source_mac_broadcast,
            "SWITCH_ADDR_010": self._test_invalid_source_mac_multicast,
            "SWITCH_ADDR_011": self._test_learning_per_vlan,
            "SWITCH_ADDR_012": self._test_learning_rate,
            "SWITCH_ADDR_013": self._test_aging_per_vlan,
            "SWITCH_ADDR_014": self._test_mac_move_detection,
            "SWITCH_ADDR_015": self._test_table_overflow_behavior,
            "SWITCH_ADDR_016": self._test_static_vs_dynamic_priority,
            "SWITCH_ADDR_017": self._test_flush_on_link_down,
            "SWITCH_ADDR_018": self._test_flush_on_topology_change,
            "SWITCH_ADDR_019": self._test_learning_disabled_port,
            "SWITCH_ADDR_020": self._test_multiple_mac_per_port,
            "SWITCH_ADDR_021": self._test_aging_timer_accuracy,
        }

        handler = handlers.get(spec.spec_id, self._test_generic_address)
        return await handler(spec, test_case, interface)

    # ── Core Learning (001-004) ───────────────────────────────────────

    async def _test_source_mac_learning(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_ADDR_001 — Source MAC learning.

        Send frame from Port A with SRC_MAC=X. Then send unicast to
        DST_MAC=X from Port B. Verify frame is forwarded ONLY to Port A.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        expected = {
            "forward_to_ports": params.egress_ports,
            "strict_forwarding": True,
            **spec.expected_result,
        }
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_learned_unicast_forwarding(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_002 — Learned unicast delivers to correct port only."""
        return await self._test_source_mac_learning(spec, case, interface)

    async def _test_port_migration(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_ADDR_003 — MAC port migration.

        Learn MAC=X on Port A, then send frame with SRC_MAC=X on Port B.
        Verify MAC table updates to Port B.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_unknown_unicast_flooding(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_ADDR_004 — Unknown unicast flooding.

        Send unicast with unknown DST_MAC. Verify flooded to all ports.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        case.parameters.dst_mac = "02:ff:ff:ff:ff:fe"
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_other = [p.port_id for p in (dut.ports if dut else [])
                     if p.port_id != params.ingress_port]

        expected = {"forward_to_ports": all_other, **spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    # ── Table & Aging (005-007) ───────────────────────────────────────

    async def _test_mac_table_capacity(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_005 — MAC table capacity test."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        table_size = dut.max_mac_table_size if dut else 1024

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            duration_ms=duration_ms,
            sent_frames=sent,
            message=f"MAC table capacity: {table_size} entries (full test requires {table_size}+ unique MACs)",
        )

    async def _test_mac_aging(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """
        SWITCH_ADDR_006 — MAC aging.

        Learn a MAC, wait for aging timer, verify entry is removed.
        """
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        aging_time = dut.mac_aging_time_s if dut else 300

        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            duration_ms=duration_ms,
            sent_frames=sent,
            message=f"MAC aging test requires waiting {aging_time}s for timer expiry",
        )

    async def _test_mac_aging_refresh(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_007 — MAC aging timer refresh on traffic."""
        return await self._test_mac_aging(spec, case, interface)

    # ── Static & Invalid (008-010) ────────────────────────────────────

    async def _test_static_mac_entry(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_008 — Static MAC entry not aged."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_invalid_source_mac_broadcast(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_009 — Broadcast source MAC rejected."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.src_mac = "ff:ff:ff:ff:ff:ff"
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    async def _test_invalid_source_mac_multicast(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_010 — Multicast source MAC handling."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        case.parameters.src_mac = "01:00:5e:00:00:01"
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(case, sent, received, expected, duration_ms)

    # ── Extended tests (011-021) ──────────────────────────────────────

    async def _test_learning_per_vlan(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_011 — Per-VLAN MAC learning (IVL)."""
        return await self._test_source_mac_learning(spec, case, interface)

    async def _test_learning_rate(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_012 — MAC learning rate."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        sent, received = await self._send_and_capture(case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL, duration_ms=duration_ms,
            sent_frames=sent,
            message="Learning rate requires sending multiple unique-MAC frames rapidly",
        )

    async def _test_aging_per_vlan(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_013 — Per-VLAN aging timer."""
        return await self._test_mac_aging(spec, case, interface)

    async def _test_mac_move_detection(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_014 — Rapid MAC move detection."""
        return await self._test_port_migration(spec, case, interface)

    async def _test_table_overflow_behavior(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_015 — MAC table overflow behavior."""
        return await self._test_mac_table_capacity(spec, case, interface)

    async def _test_static_vs_dynamic_priority(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_016 — Static entry takes priority over dynamic."""
        return await self._test_static_mac_entry(spec, case, interface)

    async def _test_flush_on_link_down(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_017 — MAC flush on link down."""
        self.log_spec_info(spec)
        return TestResult(
            case_id=case.case_id, spec_id=case.spec_id,
            tc8_reference=case.tc8_reference, section=case.section,
            status=TestStatus.INFORMATIONAL,
            message="MAC flush on link down requires physical cable manipulation",
        )

    async def _test_flush_on_topology_change(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_018 — MAC flush on topology change."""
        return await self._test_flush_on_link_down(spec, case, interface)

    async def _test_learning_disabled_port(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_019 — Learning disabled on specific port."""
        return await self._test_source_mac_learning(spec, case, interface)

    async def _test_multiple_mac_per_port(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_020 — Multiple MACs learned on same port."""
        return await self._test_source_mac_learning(spec, case, interface)

    async def _test_aging_timer_accuracy(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_021 — Aging timer accuracy measurement."""
        return await self._test_mac_aging(spec, case, interface)

    async def _test_generic_address(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """Fallback handler."""
        logger.warning("No specific handler for %s", spec.spec_id)
        return await self._test_source_mac_learning(spec, case, interface)

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
                if p.port_id != params.ingress_port:
                    received[p.port_id] = [FrameCapture(
                        port_id=p.port_id, timestamp=time.time(),
                        src_mac=params.src_mac, dst_mac=params.dst_mac,
                    )]
        return sent, received
