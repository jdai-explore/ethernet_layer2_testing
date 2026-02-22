"""Unit tests for src/utils/hexdump module."""

from __future__ import annotations

import struct

import pytest

from src.utils.hexdump import hexdump, hexdump_html, hexdump_css, frame_summary


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _build_ethernet_frame(
    dst: str = "02:00:00:00:00:01",
    src: str = "02:00:00:00:00:02",
    ethertype: int = 0x0800,
    vlan_tags: list[tuple[int, int, int]] | None = None,
    payload: bytes = b"\x00" * 46,
) -> bytes:
    """Build a minimal Ethernet frame for testing."""
    dst_bytes = bytes(int(x, 16) for x in dst.split(":"))
    src_bytes = bytes(int(x, 16) for x in src.split(":"))
    frame = dst_bytes + src_bytes
    if vlan_tags:
        for tpid, vid, pcp in vlan_tags:
            tci = (pcp << 13) | vid
            frame += struct.pack("!HH", tpid, tci)
    frame += struct.pack("!H", ethertype)
    frame += payload
    return frame


# ---------------------------------------------------------------------------
# hexdump() tests
# ---------------------------------------------------------------------------


class TestHexdump:
    def test_empty_bytes(self) -> None:
        assert hexdump(b"") == "(empty)"

    def test_single_byte(self) -> None:
        result = hexdump(b"\xab")
        assert "00ab" in result.lower() or "ab" in result.lower()
        assert "0000" in result  # offset

    def test_alignment_16_columns(self) -> None:
        data = bytes(range(32))
        result = hexdump(data, columns=16)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("0000")
        assert lines[1].startswith("0010")

    def test_ascii_printable(self) -> None:
        data = b"Hello, World!\x00\x01\x02"
        result = hexdump(data)
        assert "Hello, World!..." in result

    def test_full_ethernet_frame(self) -> None:
        frame = _build_ethernet_frame()
        result = hexdump(frame)
        # Should have offset column and hex values
        assert "0000" in result
        assert "02 00 00 00 00 01" in result  # dst MAC


# ---------------------------------------------------------------------------
# hexdump_html() tests
# ---------------------------------------------------------------------------


class TestHexdumpHtml:
    def test_empty(self) -> None:
        result = hexdump_html(b"")
        assert "(empty)" in result
        assert "<pre" in result

    def test_has_pre_wrapper(self) -> None:
        result = hexdump_html(b"\x00" * 16)
        assert result.startswith('<pre class="hexdump">')
        assert result.endswith("</pre>")

    def test_dst_mac_highlighted(self) -> None:
        frame = _build_ethernet_frame()
        result = hexdump_html(frame)
        assert 'class="hx-dst"' in result

    def test_src_mac_highlighted(self) -> None:
        frame = _build_ethernet_frame()
        result = hexdump_html(frame)
        assert 'class="hx-src"' in result

    def test_ethertype_highlighted(self) -> None:
        frame = _build_ethernet_frame()
        result = hexdump_html(frame)
        assert 'class="hx-etype"' in result

    def test_vlan_highlighted(self) -> None:
        frame = _build_ethernet_frame(
            vlan_tags=[(0x8100, 100, 5)]
        )
        result = hexdump_html(frame)
        assert 'class="hx-vlan"' in result

    def test_css_not_empty(self) -> None:
        css = hexdump_css()
        assert ".hexdump" in css
        assert ".hx-dst" in css


# ---------------------------------------------------------------------------
# frame_summary() tests
# ---------------------------------------------------------------------------


class TestFrameSummary:
    def test_empty_data(self) -> None:
        info = frame_summary(b"")
        assert info["total_len"] == 0
        assert info["dst_mac"] == ""

    def test_too_short(self) -> None:
        info = frame_summary(b"\x00" * 10)
        assert info["total_len"] == 10
        assert info["dst_mac"] == ""

    def test_untagged_ipv4(self) -> None:
        frame = _build_ethernet_frame(ethertype=0x0800)
        info = frame_summary(frame)
        assert info["dst_mac"] == "02:00:00:00:00:01"
        assert info["src_mac"] == "02:00:00:00:00:02"
        assert info["ethertype"] == 0x0800
        assert info["ethertype_name"] == "IPv4"
        assert info["vlan_tags"] == []
        assert info["payload_len"] == 46

    def test_untagged_arp(self) -> None:
        frame = _build_ethernet_frame(ethertype=0x0806)
        info = frame_summary(frame)
        assert info["ethertype_name"] == "ARP"

    def test_single_vlan_tagged(self) -> None:
        frame = _build_ethernet_frame(
            vlan_tags=[(0x8100, 200, 3)],
            ethertype=0x0800,
        )
        info = frame_summary(frame)
        assert len(info["vlan_tags"]) == 1
        tag = info["vlan_tags"][0]
        assert tag["vid"] == 200
        assert tag["pcp"] == 3
        assert tag["tpid"] == "0x8100"

    def test_double_tagged_qinq(self) -> None:
        frame = _build_ethernet_frame(
            vlan_tags=[(0x88A8, 100, 7), (0x8100, 200, 3)],
            ethertype=0x0800,
        )
        info = frame_summary(frame)
        assert len(info["vlan_tags"]) == 2
        assert info["vlan_tags"][0]["vid"] == 100
        assert info["vlan_tags"][0]["tpid"] == "0x88a8"
        assert info["vlan_tags"][1]["vid"] == 200

    def test_unknown_ethertype(self) -> None:
        frame = _build_ethernet_frame(ethertype=0xBEEF)
        info = frame_summary(frame)
        assert info["ethertype"] == 0xBEEF
        assert info["ethertype_name"] == "0xbeef"

    def test_payload_length_accuracy(self) -> None:
        payload = b"\xaa" * 100
        frame = _build_ethernet_frame(payload=payload)
        info = frame_summary(frame)
        assert info["payload_len"] == 100
        assert info["total_len"] == 6 + 6 + 2 + 100  # dst + src + etype + payload
