"""
Scapy-based DUT interface implementation.

Uses Scapy for Ethernet frame construction, sending, and sniffing.
Primary interface for development and testing on standard NICs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.interface.base_interface import BaseDUTInterface
from src.models.test_case import (
    FrameCapture,
    FrameType,
    PortConfig,
    TestCase,
)

logger = logging.getLogger(__name__)

try:
    from scapy.all import (
        ARP,
        Dot1Q,
        Ether,
        AsyncSniffer,
        ICMP,
        IP,
        Raw,
        conf,
        get_if_hwaddr,
        sendp,
        sniff,
    )
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    logger.warning("Scapy not available — ScapyInterface will not function")


class ScapyInterface(BaseDUTInterface):
    """
    Scapy-based DUT communication interface.

    Uses Scapy's sendp/sniff for frame-level Ethernet communication.
    Supports tagged/untagged/double-tagged frames with configurable
    TPID, VID, and PCP values.

    Requirements:
    - Linux: root/sudo for raw socket access
    - Windows: Npcap driver installed
    """

    def __init__(self, ports: list[PortConfig]) -> None:
        super().__init__(ports)
        self._sniffers: dict[int, Any] = {}

    async def initialize(self) -> None:
        """Initialize Scapy and verify interface access."""
        if not SCAPY_AVAILABLE:
            raise RuntimeError(
                "Scapy is not installed. Install with: pip install scapy"
            )

        # Verify all interfaces exist
        for port_id, port in self.ports.items():
            try:
                mac = get_if_hwaddr(port.interface_name)
                logger.info(
                    "Port %d: %s (MAC=%s) — ready",
                    port_id, port.interface_name, mac,
                )
            except Exception as e:
                logger.error(
                    "Port %d: interface %s not accessible: %s",
                    port_id, port.interface_name, e,
                )
                raise RuntimeError(
                    f"Cannot access interface {port.interface_name}: {e}"
                ) from e

        self._initialized = True
        logger.info("ScapyInterface initialized with %d ports", len(self.ports))
        
        import platform
        if platform.system() == "Windows":
            logger.info("Running on Windows — Note: VLAN tags may be stripped by NIC drivers unless Npcap 'Dot1Q' support is enabled.")

    async def shutdown(self) -> None:
        """Stop all sniffers and clean up."""
        for port_id, sniffer in self._sniffers.items():
            if sniffer and sniffer.running:
                sniffer.stop()
                logger.debug("Stopped sniffer on port %d", port_id)
        self._sniffers.clear()
        self._initialized = False
        logger.info("ScapyInterface shutdown complete")

    async def send_frame(self, test_case: TestCase) -> list[FrameCapture]:
        """Build and send test frame on the ingress port."""
        params = test_case.parameters
        port = self.get_port(params.ingress_port)
        if port is None:
            raise ValueError(f"Ingress port {params.ingress_port} not configured")

        # Build Ethernet frame
        frame = self._build_frame(test_case)

        # Send via Scapy
        iface = port.interface_name
        t_send = time.time()

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sendp(frame, iface=iface, verbose=False),
        )

        logger.debug(
            "Sent frame on port %d (%s): %s → %s, VID=%d, type=%s",
            params.ingress_port, iface,
            params.src_mac, params.dst_mac,
            params.vid, params.frame_type.value,
        )

        return [FrameCapture(
            port_id=params.ingress_port,
            timestamp=t_send,
            src_mac=params.src_mac,
            dst_mac=params.dst_mac,
            ethertype=frame[Ether].type if hasattr(frame, '__getitem__') else 0,
            vlan_tags=self._extract_vlan_tags(frame) if SCAPY_AVAILABLE else [],
            payload_size=len(frame),
        )]

    async def capture_frames(
        self,
        test_case: TestCase,
        timeout: float = 2.0,
    ) -> dict[int, list[FrameCapture]]:
        """
        Capture frames on all egress ports for the given timeout.

        Uses Scapy AsyncSniffer on each port concurrently.
        """
        params = test_case.parameters
        capture_ports = [
            pid for pid in self.ports
            if pid != params.ingress_port
        ]

        results: dict[int, list[FrameCapture]] = {}

        # Start sniffers on all egress ports
        sniff_tasks = []
        for pid in capture_ports:
            port = self.ports[pid]
            sniff_tasks.append(
                self._sniff_port(pid, port.interface_name, timeout, params.dst_mac)
            )

        # Gather results
        captured = await asyncio.gather(*sniff_tasks)
        for pid, frames in zip(capture_ports, captured):
            results[pid] = frames

        return results

    async def _sniff_port(
        self,
        port_id: int,
        iface: str,
        timeout: float,
        filter_mac: str | None = None,
    ) -> list[FrameCapture]:
        """Sniff frames on a single port."""
        captures: list[FrameCapture] = []

        def packet_handler(pkt: Any) -> None:
            if Ether not in pkt:
                return
            # Filter by destination MAC if specified
            if filter_mac and pkt[Ether].dst.lower() != filter_mac.lower():
                return
            captures.append(FrameCapture(
                port_id=port_id,
                timestamp=time.time(),
                src_mac=pkt[Ether].src,
                dst_mac=pkt[Ether].dst,
                ethertype=pkt[Ether].type,
                vlan_tags=self._extract_vlan_tags(pkt),
                payload_size=len(pkt),
            ))

        # Run sniffer in executor to avoid blocking
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sniff(
                iface=iface,
                prn=packet_handler,
                timeout=timeout,
                store=False,
            ),
        )

        logger.debug("Captured %d frames on port %d (%s)", len(captures), port_id, iface)
        return captures

    async def check_link(self, port_id: int) -> bool:
        """Check if the network interface link is up."""
        port = self.get_port(port_id)
        if port is None:
            return False

        try:
            import psutil
            stats = psutil.net_if_stats()
            iface_stats = stats.get(port.interface_name)
            if iface_stats is None:
                logger.warning("Interface %s not found in system stats", port.interface_name)
                return False
            return iface_stats.isup
        except ImportError:
            logger.warning("psutil not available — assuming link is up")
            return True

    # ── Frame Construction ────────────────────────────────────────────

    def _build_frame(self, test_case: TestCase) -> Any:
        """Build a Scapy Ethernet frame based on test case parameters."""
        params = test_case.parameters

        # Base Ethernet header
        frame = Ether(src=params.src_mac, dst=params.dst_mac)

        # Add VLAN tags based on frame type
        if params.frame_type == FrameType.SINGLE_TAGGED:
            frame = frame / Dot1Q(vlan=params.vid, type=params.tpid)

        elif params.frame_type == FrameType.DOUBLE_TAGGED:
            # Outer (S-VLAN) + Inner (C-VLAN)
            outer_tpid = 0x88A8
            inner_vid = params.custom.get("inner_vid", params.vid)
            frame = frame / Dot1Q(vlan=params.vid, type=outer_tpid)
            frame = frame / Dot1Q(vlan=inner_vid, type=0x8100)

        # Add protocol payload
        if params.protocol == "arp":
            frame = frame / ARP()
        else:
            # Default: ICMP over IP
            frame = frame / IP(src="10.0.0.1", dst="10.0.0.2") / ICMP()

        # Pad to minimum frame size
        current_len = len(frame)
        if current_len < params.payload_size:
            frame = frame / Raw(load=b"\x00" * (params.payload_size - current_len))

        return frame

    @staticmethod
    def _extract_vlan_tags(pkt: Any) -> list[dict[str, Any]]:
        """Extract VLAN tag information from a captured packet."""
        tags: list[dict[str, Any]] = []

        if not SCAPY_AVAILABLE:
            return tags

        layer = pkt
        while layer:
            if Dot1Q in layer:
                dot1q = layer[Dot1Q]
                tags.append({
                    "vid": dot1q.vlan,
                    "pcp": dot1q.prio,
                    "dei": dot1q.id,
                    "tpid": dot1q.type,
                })
                layer = dot1q.payload
            else:
                break

        return tags
