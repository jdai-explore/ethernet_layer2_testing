"""
Hexdump utility for Ethernet frame visualization.

Provides classic hex+ASCII dump output, HTML-rendered variants with
color-highlighted regions, and quick frame header parsing.

Usage::

    from src.utils.hexdump import hexdump, hexdump_html, frame_summary

    raw = b'\\x02\\x00...'
    print(hexdump(raw))          # terminal-friendly text
    html = hexdump_html(raw)     # embeddable HTML fragment
    info = frame_summary(raw)    # parsed header dict
"""

from __future__ import annotations

import struct
from typing import Any


# ---------------------------------------------------------------------------
# Text hexdump
# ---------------------------------------------------------------------------


def hexdump(data: bytes, columns: int = 16) -> str:
    """Classic hexdump: offset | hex pairs | ASCII.

    Example output (columns=16)::

        0000  02 00 00 00 00 01 02 00  00 00 00 02 08 00 45 00  |..............E.|
        0010  00 2e 00 01 00 00 40 01  f9 76 c0 a8 01 01 c0 a8  |......@..v......|
    """
    if not data:
        return "(empty)"

    lines: list[str] = []
    for offset in range(0, len(data), columns):
        chunk = data[offset : offset + columns]

        # Hex part — split into two groups for readability
        hex_parts: list[str] = []
        for i, byte in enumerate(chunk):
            if i == columns // 2:
                hex_parts.append("")  # extra space at midpoint
            hex_parts.append(f"{byte:02x}")
        hex_str = " ".join(hex_parts)

        # Pad hex string to fixed width so ASCII column aligns
        # Full line: columns * 3 chars + 1 for mid-gap - 1 trailing space
        full_hex_width = columns * 3 + 1 - 1
        hex_str = hex_str.ljust(full_hex_width)

        # ASCII part
        ascii_str = "".join(
            chr(b) if 0x20 <= b < 0x7F else "." for b in chunk
        )

        lines.append(f"{offset:04x}  {hex_str}  |{ascii_str}|")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML hexdump with color highlighting
# ---------------------------------------------------------------------------

# CSS classes for frame regions
_REGION_CLASSES = {
    "dst_mac":   "hx-dst",
    "src_mac":   "hx-src",
    "ethertype": "hx-etype",
    "vlan_tag":  "hx-vlan",
    "payload":   "hx-payload",
}


def _classify_byte(index: int, data: bytes) -> str:
    """Return a CSS class for the byte at *index* based on Ethernet regions."""
    if index < 6:
        return "hx-dst"
    if index < 12:
        return "hx-src"
    # Check for VLAN tag (0x8100 or 0x88A8)
    if len(data) >= 14:
        ethertype_raw = struct.unpack("!H", data[12:14])[0]
        if ethertype_raw in (0x8100, 0x88A8, 0x9100):
            # VLAN tag present: bytes 12-15 are outer tag, 16-17 real ethertype
            if index < 16:
                return "hx-vlan"
            if index < 18:
                return "hx-etype"
            # Check for double tagging (Q-in-Q)
            if len(data) >= 18:
                inner_etype = struct.unpack("!H", data[16:18])[0]
                if inner_etype in (0x8100, 0x88A8, 0x9100):
                    if index < 20:
                        return "hx-vlan"
                    if index < 22:
                        return "hx-etype"
                    return "hx-payload"
            return "hx-payload"
        # No VLAN
        if index < 14:
            return "hx-etype"
    return "hx-payload"


def hexdump_html(data: bytes, columns: int = 16) -> str:
    """Hex dump wrapped in ``<pre class="hexdump">`` with color spans.

    Regions: destination MAC, source MAC, EtherType, VLAN tag, payload.
    Include the companion CSS (see ``hexdump_css()``) in your page.
    """
    if not data:
        return '<pre class="hexdump">(empty)</pre>'

    lines: list[str] = []
    for offset in range(0, len(data), columns):
        chunk = data[offset : offset + columns]

        # Build hex spans
        hex_parts: list[str] = []
        for i, byte in enumerate(chunk):
            abs_idx = offset + i
            cls = _classify_byte(abs_idx, data)
            if i == columns // 2:
                hex_parts.append(" ")
            hex_parts.append(f'<span class="{cls}">{byte:02x}</span>')

        hex_str = " ".join(hex_parts)

        # ASCII column (no coloring — keep it simple)
        ascii_str = "".join(
            chr(b) if 0x20 <= b < 0x7F else "." for b in chunk
        )

        lines.append(
            f'<span class="hx-offset">{offset:04x}</span>  {hex_str}  '
            f'<span class="hx-ascii">|{ascii_str}|</span>'
        )

    body = "\n".join(lines)
    return f'<pre class="hexdump">{body}</pre>'


def hexdump_css() -> str:
    """Return minimal CSS for hexdump HTML rendering."""
    return """\
.hexdump { font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 0.8rem; line-height: 1.5; background: #0d1117;
  color: #c9d1d9; padding: 1rem; border-radius: 6px; overflow-x: auto; }
.hx-offset { color: #6e7681; }
.hx-dst    { color: #79c0ff; }
.hx-src    { color: #a5d6ff; }
.hx-etype  { color: #ffa657; font-weight: 600; }
.hx-vlan   { color: #d2a8ff; }
.hx-payload{ color: #8b949e; }
.hx-ascii  { color: #7ee787; }
"""


# ---------------------------------------------------------------------------
# Frame summary parser
# ---------------------------------------------------------------------------


def frame_summary(data: bytes) -> dict[str, Any]:
    """Parse Ethernet header to extract key fields.

    Returns dict with keys: dst_mac, src_mac, ethertype, ethertype_name,
    vlan_tags (list of {vid, pcp, dei, tpid}), payload_len, total_len.
    """
    result: dict[str, Any] = {
        "dst_mac": "",
        "src_mac": "",
        "ethertype": 0,
        "ethertype_name": "",
        "vlan_tags": [],
        "payload_len": 0,
        "total_len": len(data),
    }

    if len(data) < 14:
        return result

    result["dst_mac"] = ":".join(f"{b:02x}" for b in data[0:6])
    result["src_mac"] = ":".join(f"{b:02x}" for b in data[6:12])

    pos = 12
    # Parse VLAN tags (can be stacked)
    while pos + 2 <= len(data):
        tpid = struct.unpack("!H", data[pos : pos + 2])[0]
        if tpid not in (0x8100, 0x88A8, 0x9100):
            break
        if pos + 4 > len(data):
            break
        tci = struct.unpack("!H", data[pos + 2 : pos + 4])[0]
        result["vlan_tags"].append({
            "tpid": f"0x{tpid:04x}",
            "vid": tci & 0x0FFF,
            "pcp": (tci >> 13) & 0x07,
            "dei": (tci >> 12) & 0x01,
        })
        pos += 4

    # EtherType / Length field
    if pos + 2 <= len(data):
        etype = struct.unpack("!H", data[pos : pos + 2])[0]
        result["ethertype"] = etype
        result["ethertype_name"] = _ETHERTYPE_NAMES.get(etype, f"0x{etype:04x}")
        pos += 2

    result["payload_len"] = len(data) - pos

    return result


_ETHERTYPE_NAMES: dict[int, str] = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x86DD: "IPv6",
    0x8100: "802.1Q",
    0x88A8: "802.1ad (S-VLAN)",
    0x9100: "Legacy Q-in-Q",
    0x88F7: "PTP (IEEE 1588)",
    0x8902: "802.1ag (CFM)",
    0x88CC: "LLDP",
    0x88E1: "HomePlug AV",
    0x22F0: "AVB (IEEE 1722)",
    0x22EA: "SRP (IEEE 1722.1)",
}
