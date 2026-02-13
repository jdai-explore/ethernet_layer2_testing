"""
Validation helper utilities.

Common validation functions shared across test specifications:
MAC address validation, VLAN tag checks, frame integrity, etc.
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MAC Address Validation
# ---------------------------------------------------------------------------

_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def is_valid_mac(mac: str) -> bool:
    """Check if a MAC address string is valid."""
    return bool(_MAC_PATTERN.match(mac))


def is_unicast_mac(mac: str) -> bool:
    """Check if MAC is a unicast address (bit 0 of first octet = 0)."""
    if not is_valid_mac(mac):
        return False
    first_byte = int(mac.split(":")[0], 16)
    return (first_byte & 0x01) == 0


def is_multicast_mac(mac: str) -> bool:
    """Check if MAC is a multicast address (bit 0 of first octet = 1)."""
    if not is_valid_mac(mac):
        return False
    first_byte = int(mac.split(":")[0], 16)
    return (first_byte & 0x01) == 1


def is_broadcast_mac(mac: str) -> bool:
    """Check if MAC is the broadcast address."""
    return mac.lower() == "ff:ff:ff:ff:ff:ff"


def is_locally_administered(mac: str) -> bool:
    """Check if MAC is locally administered (bit 1 of first octet = 1)."""
    if not is_valid_mac(mac):
        return False
    first_byte = int(mac.split(":")[0], 16)
    return (first_byte & 0x02) != 0


# ---------------------------------------------------------------------------
# VLAN Validation
# ---------------------------------------------------------------------------


def is_valid_vid(vid: int) -> bool:
    """Check if VLAN ID is in valid range (0-4095)."""
    return 0 <= vid <= 4095


def is_reserved_vid(vid: int) -> bool:
    """Check if VID is reserved (0 = priority-tagged, 4095 = reserved)."""
    return vid in (0, 4095)


def is_valid_pcp(pcp: int) -> bool:
    """Check if Priority Code Point is valid (0-7)."""
    return 0 <= pcp <= 7


def is_valid_tpid(tpid: int) -> bool:
    """Check if TPID is a recognized value."""
    return tpid in (0x8100, 0x88A8, 0x9100)


# ---------------------------------------------------------------------------
# Frame Validation
# ---------------------------------------------------------------------------


def validate_frame_size(size: int, allow_jumbo: bool = False) -> bool:
    """Check if frame size is valid."""
    min_size = 64
    max_size = 9216 if allow_jumbo else 1518
    return min_size <= size <= max_size


def validate_vlan_tag(
    tag: dict[str, Any],
    expected_vid: int | None = None,
    expected_pcp: int | None = None,
    expected_tpid: int | None = None,
) -> tuple[bool, list[str]]:
    """
    Validate a VLAN tag dictionary against expected values.

    Returns (is_valid, list_of_issues).
    """
    issues: list[str] = []

    vid = tag.get("vid")
    if vid is not None and not is_valid_vid(vid):
        issues.append(f"Invalid VID: {vid}")
    if expected_vid is not None and vid != expected_vid:
        issues.append(f"VID mismatch: expected={expected_vid}, actual={vid}")

    pcp = tag.get("pcp")
    if pcp is not None and not is_valid_pcp(pcp):
        issues.append(f"Invalid PCP: {pcp}")
    if expected_pcp is not None and pcp != expected_pcp:
        issues.append(f"PCP mismatch: expected={expected_pcp}, actual={pcp}")

    tpid = tag.get("tpid")
    if expected_tpid is not None and tpid != expected_tpid:
        issues.append(f"TPID mismatch: expected=0x{expected_tpid:04X}, actual=0x{tpid or 0:04X}")

    return len(issues) == 0, issues


# ---------------------------------------------------------------------------
# Port Validation
# ---------------------------------------------------------------------------


def validate_port_membership(
    port_vlans: list[int],
    required_vid: int,
) -> bool:
    """Check if a port is a member of the required VLAN."""
    return required_vid in port_vlans


def get_member_ports(
    ports: list[dict[str, Any]],
    vid: int,
    exclude_port: int | None = None,
) -> list[int]:
    """Get all ports that are members of the given VLAN."""
    members = []
    for port in ports:
        if vid in port.get("vlan_membership", []):
            pid = port.get("port_id")
            if pid != exclude_port:
                members.append(pid)
    return members
