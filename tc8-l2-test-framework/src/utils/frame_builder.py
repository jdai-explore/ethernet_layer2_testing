"""
Ethernet frame builder utilities.

Provides high-level helpers for constructing IEEE 802.3 / 802.1Q / 802.1ad
frames used across all TC8 Layer 2 test specifications.
"""

from __future__ import annotations

import logging
import struct
from typing import Any

logger = logging.getLogger(__name__)

try:
    from scapy.all import ARP, Dot1Q, Ether, ICMP, IP, Raw
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TPID_8021Q = 0x8100    # IEEE 802.1Q C-VLAN
TPID_8021AD = 0x88A8   # IEEE 802.1ad S-VLAN (Provider Bridge)
TPID_LEGACY = 0x9100   # Legacy double-tagging

MIN_FRAME_SIZE = 64     # Minimum Ethernet frame (excl. preamble/FCS)
MAX_FRAME_SIZE = 1518   # Standard max frame
JUMBO_FRAME_SIZE = 9216 # Jumbo frame

BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
NULL_MAC = "00:00:00:00:00:00"


# ---------------------------------------------------------------------------
# Frame Builder
# ---------------------------------------------------------------------------


class FrameBuilder:
    """
    High-level Ethernet frame construction.

    Provides factory methods for common TC8 test frame patterns:
    - Untagged unicast/multicast/broadcast
    - Single-tagged (802.1Q)
    - Double-tagged (802.1ad / Q-in-Q)
    - ARP requests/replies
    - ICMP echo
    - Custom payload sizes
    """

    def __init__(
        self,
        default_src_mac: str = "02:00:00:00:00:01",
        default_dst_mac: str = "02:00:00:00:00:02",
    ) -> None:
        self.default_src_mac = default_src_mac
        self.default_dst_mac = default_dst_mac

    # ── Untagged Frames ───────────────────────────────────────────────

    def untagged_unicast(
        self,
        src_mac: str | None = None,
        dst_mac: str | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """Build an untagged unicast Ethernet frame."""
        frame = Ether(
            src=src_mac or self.default_src_mac,
            dst=dst_mac or self.default_dst_mac,
        ) / IP(src="10.0.0.1", dst="10.0.0.2") / ICMP()
        return self._pad_frame(frame, payload_size)

    def untagged_broadcast(
        self,
        src_mac: str | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """Build an untagged broadcast Ethernet frame."""
        return self.untagged_unicast(
            src_mac=src_mac,
            dst_mac=BROADCAST_MAC,
            payload_size=payload_size,
        )

    def untagged_multicast(
        self,
        src_mac: str | None = None,
        multicast_mac: str = "01:00:5e:00:00:01",
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """Build an untagged multicast Ethernet frame."""
        return self.untagged_unicast(
            src_mac=src_mac,
            dst_mac=multicast_mac,
            payload_size=payload_size,
        )

    # ── Single-Tagged Frames (802.1Q) ─────────────────────────────────

    def single_tagged(
        self,
        vid: int,
        pcp: int = 0,
        dei: int = 0,
        tpid: int = TPID_8021Q,
        src_mac: str | None = None,
        dst_mac: str | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """
        Build a single-tagged 802.1Q Ethernet frame.

        Args:
            vid: VLAN Identifier (0-4095)
            pcp: Priority Code Point (0-7)
            dei: Drop Eligible Indicator (0-1)
            tpid: Tag Protocol Identifier (default 0x8100)
        """
        frame = Ether(
            src=src_mac or self.default_src_mac,
            dst=dst_mac or self.default_dst_mac,
            type=tpid,
        ) / Dot1Q(vlan=vid, prio=pcp, id=dei)
        frame = frame / IP(src="10.0.0.1", dst="10.0.0.2") / ICMP()
        return self._pad_frame(frame, payload_size)

    def single_tagged_broadcast(
        self,
        vid: int,
        pcp: int = 0,
        src_mac: str | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """Build a single-tagged broadcast frame."""
        return self.single_tagged(
            vid=vid, pcp=pcp,
            src_mac=src_mac, dst_mac=BROADCAST_MAC,
            payload_size=payload_size,
        )

    # ── Double-Tagged Frames (802.1ad / Q-in-Q) ──────────────────────

    def double_tagged(
        self,
        outer_vid: int,
        inner_vid: int,
        outer_tpid: int = TPID_8021AD,
        inner_tpid: int = TPID_8021Q,
        outer_pcp: int = 0,
        inner_pcp: int = 0,
        src_mac: str | None = None,
        dst_mac: str | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """
        Build a double-tagged (Q-in-Q / 802.1ad) frame.

        Outer = Service VLAN (S-VLAN), Inner = Customer VLAN (C-VLAN).
        """
        frame = Ether(
            src=src_mac or self.default_src_mac,
            dst=dst_mac or self.default_dst_mac,
            type=outer_tpid,
        )
        frame = frame / Dot1Q(vlan=outer_vid, prio=outer_pcp, type=inner_tpid)
        frame = frame / Dot1Q(vlan=inner_vid, prio=inner_pcp)
        frame = frame / IP(src="10.0.0.1", dst="10.0.0.2") / ICMP()
        return self._pad_frame(frame, payload_size)

    # ── ARP Frames ────────────────────────────────────────────────────

    def arp_request(
        self,
        src_mac: str | None = None,
        src_ip: str = "10.0.0.1",
        dst_ip: str = "10.0.0.2",
        vid: int | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """Build an ARP request frame (optionally VLAN-tagged)."""
        src = src_mac or self.default_src_mac
        frame = Ether(src=src, dst=BROADCAST_MAC)
        if vid is not None:
            frame = frame / Dot1Q(vlan=vid)
        frame = frame / ARP(
            op="who-has",
            hwsrc=src,
            psrc=src_ip,
            pdst=dst_ip,
        )
        return self._pad_frame(frame, payload_size)

    def arp_reply(
        self,
        src_mac: str | None = None,
        dst_mac: str | None = None,
        src_ip: str = "10.0.0.2",
        dst_ip: str = "10.0.0.1",
        vid: int | None = None,
        payload_size: int = MIN_FRAME_SIZE,
    ) -> Any:
        """Build an ARP reply frame."""
        src = src_mac or self.default_src_mac
        dst = dst_mac or self.default_dst_mac
        frame = Ether(src=src, dst=dst)
        if vid is not None:
            frame = frame / Dot1Q(vlan=vid)
        frame = frame / ARP(
            op="is-at",
            hwsrc=src,
            psrc=src_ip,
            hwdst=dst,
            pdst=dst_ip,
        )
        return self._pad_frame(frame, payload_size)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _pad_frame(frame: Any, target_size: int) -> Any:
        """Pad frame to reach minimum/target size."""
        current = len(frame)
        if current < target_size:
            frame = frame / Raw(load=b"\x00" * (target_size - current))
        return frame

    @staticmethod
    def mac_to_bytes(mac: str) -> bytes:
        """Convert MAC address string to bytes."""
        return bytes(int(b, 16) for b in mac.split(":"))

    @staticmethod
    def bytes_to_mac(b: bytes) -> str:
        """Convert bytes to MAC address string."""
        return ":".join(f"{byte:02x}" for byte in b)
