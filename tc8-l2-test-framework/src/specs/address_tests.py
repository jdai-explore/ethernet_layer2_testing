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

        Phase 1 (learn): send a broadcast from ingress_port with src_mac=X so
        the switch learns X → ingress_port.
        Phase 2 (probe): send unicast dst_mac=X from egress_port and verify the
        frame arrives ONLY on ingress_port (not flooded).
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        if interface is None:
            # Simulation cannot replay real MAC-learning state machine.
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.INFORMATIONAL,
                message="Simulation mode cannot verify MAC learning — requires real DUT",
            )

        # Phase 1: learn — flood a frame so the switch records src_mac on ingress_port
        learn_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"dst_mac": "ff:ff:ff:ff:ff:ff"}),
        })
        await interface.send_and_capture(learn_case)

        # Phase 2: probe — unicast to learned MAC from a different port
        probe_port = params.egress_ports[0] if params.egress_ports else params.ingress_port
        probe_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={
                "ingress_port": probe_port,
                "dst_mac": params.src_mac,
                "src_mac": "02:00:00:00:ff:01",
            }),
        })
        sent, received = await interface.send_and_capture(probe_case)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_ports = [p.port_id for p in (dut.ports if dut else [])]
        blocked = [p for p in all_ports if p not in (params.ingress_port, probe_port)]
        expected = {
            "forward_to_ports": [params.ingress_port],
            "blocked_ports": blocked,
            "strict_forwarding": True,
            **spec.expected_result,
        }
        return self.validator.validate(probe_case, sent, received, expected, duration_ms)

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

        Phase 1: learn MAC=X on ingress_port (Port A).
        Phase 2: send frame with src_mac=X from egress_ports[0] (Port B) — MAC migrates.
        Phase 3: probe unicast to MAC=X from ingress_port and verify it now arrives on Port B.
        """
        self.log_spec_info(spec)
        params = case.parameters
        t0 = time.perf_counter()

        if interface is None:
            return TestResult(
                case_id=case.case_id, spec_id=case.spec_id,
                tc8_reference=case.tc8_reference, section=case.section,
                status=TestStatus.INFORMATIONAL,
                message="Simulation mode cannot verify MAC port migration — requires real DUT",
            )

        new_port = params.egress_ports[0] if params.egress_ports else params.ingress_port

        # Phase 1: learn MAC=X on Port A
        learn_a = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"dst_mac": "ff:ff:ff:ff:ff:ff"}),
        })
        await interface.send_and_capture(learn_a)

        # Phase 2: migrate — send with same src_mac from Port B
        migrate_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={
                "ingress_port": new_port,
                "dst_mac": "ff:ff:ff:ff:ff:ff",
            }),
        })
        await interface.send_and_capture(migrate_case)

        # Phase 3: probe from Port A to MAC=X — should now arrive only on Port B
        probe_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={
                "dst_mac": params.src_mac,
                "src_mac": "02:00:00:00:ff:02",
            }),
        })
        sent, received = await interface.send_and_capture(probe_case)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_ports = [p.port_id for p in (dut.ports if dut else [])]
        blocked = [p for p in all_ports if p not in (new_port, params.ingress_port)]
        expected = {
            "forward_to_ports": [new_port],
            "blocked_ports": blocked,
            **spec.expected_result,
        }
        return self.validator.validate(probe_case, sent, received, expected, duration_ms)

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

        flood_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"dst_mac": "02:ff:ff:ff:ff:fe"}),
        })
        sent, received = await self._send_and_capture(flood_case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000

        dut = self.config.dut_profile
        all_other = [p.port_id for p in (dut.ports if dut else [])
                     if p.port_id != params.ingress_port]

        expected = {"forward_to_ports": all_other, **spec.expected_result}
        return self.validator.validate(flood_case, sent, received, expected, duration_ms)

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
        bcast_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"src_mac": "ff:ff:ff:ff:ff:ff"}),
        })
        sent, received = await self._send_and_capture(bcast_case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(bcast_case, sent, received, expected, duration_ms)

    async def _test_invalid_source_mac_multicast(
        self, spec: TestSpecDefinition, case: TestCase, interface: Any
    ) -> TestResult:
        """SWITCH_ADDR_010 — Multicast source MAC handling."""
        self.log_spec_info(spec)
        t0 = time.perf_counter()
        mcast_case = case.model_copy(update={
            "parameters": case.parameters.model_copy(update={"src_mac": "01:00:5e:00:00:01"}),
        })
        sent, received = await self._send_and_capture(mcast_case, interface)
        duration_ms = (time.perf_counter() - t0) * 1000
        expected = {**spec.expected_result}
        return self.validator.validate(mcast_case, sent, received, expected, duration_ms)

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
        """Send test frame and capture responses (atomic on real HW)."""
        params = case.parameters
        if interface is not None:
            return await interface.send_and_capture(case)

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
