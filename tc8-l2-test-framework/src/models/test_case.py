"""
Data models for test cases, results, and DUT profiles.

Pydantic models providing strict validation for all test framework data structures.
Aligned with OPEN Alliance TC8 Layer 2 v3.0 specification terminology.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FrameType(str, enum.Enum):
    """Ethernet frame tagging classification per TC8."""

    UNTAGGED = "untagged"
    SINGLE_TAGGED = "single_tagged"
    DOUBLE_TAGGED = "double_tagged"


class TPIDValue(int, enum.Enum):
    """Tag Protocol Identifier values used in automotive Ethernet."""

    CVLAN = 0x8100      # IEEE 802.1Q Customer VLAN
    SVLAN = 0x88A8      # IEEE 802.1ad Service VLAN
    LEGACY = 0x9100     # Legacy / vendor-specific double-tag


class ProtocolType(str, enum.Enum):
    """Protocol types used in TC8 Layer 2 tests."""

    ICMP = "icmp"
    ARP = "arp"


class TestTier(str, enum.Enum):
    """Tiered test execution levels."""

    SMOKE = "smoke"         # Quick validation — ~1 hour
    CORE = "core"           # Core functionality — ~8 hours
    FULL = "full"           # Full regression — 40+ hours


class TestStatus(str, enum.Enum):
    """Outcome classification for a single test case."""

    PASS = "pass"
    FAIL = "fail"
    INFORMATIONAL = "informational"   # Subject to known limitation
    SKIP = "skip"                     # Not applicable to DUT config
    ERROR = "error"                   # Framework error, not DUT bug


class TestSection(str, enum.Enum):
    """TC8 Layer 2 specification sections."""

    VLAN = "5.3"
    GENERAL = "5.4"
    ADDRESS_LEARNING = "5.5"
    FILTERING = "5.6"
    TIME_SYNC = "5.7"
    QOS = "5.8"
    CONFIGURATION = "5.9"


class TimingTier(str, enum.Enum):
    """Timing accuracy tiers."""

    TIER_A = "tier_a"   # ±1 ms  — Python perf_counter
    TIER_B = "tier_b"   # ±100 µs — NIC hardware timestamps
    TIER_C = "tier_c"   # ±1 µs  — External hardware (PPS/GPS)


class InterfaceType(str, enum.Enum):
    """DUT communication interface types."""

    SCAPY = "scapy"
    RAW_SOCKET = "raw_socket"
    TCP = "tcp"
    USB = "usb"


# ---------------------------------------------------------------------------
# Port & Network Models
# ---------------------------------------------------------------------------


class PortConfig(BaseModel):
    """Configuration for a single DUT / test-station port."""

    port_id: int = Field(ge=0, description="Logical port index (0-based)")
    interface_name: str = Field(description="OS network interface name, e.g. eth0")
    mac_address: str = Field(pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
    speed_mbps: int = Field(default=100, description="Link speed in Mbps")
    vlan_membership: list[int] = Field(default_factory=list)
    pvid: int = Field(default=1, ge=0, le=4095, description="Port VLAN ID")
    is_trunk: bool = Field(default=False, description="Whether port carries tagged traffic")


class DUTProfile(BaseModel):
    """
    Complete DUT configuration profile.

    Populated from the ECU-team questionnaire or config YAML.
    """

    name: str = Field(description="Human-readable DUT identifier")
    model: str = Field(default="", description="ECU model/part number")
    firmware_version: str = Field(default="unknown")
    port_count: int = Field(ge=2, le=16, description="Number of Ethernet ports on DUT")
    ports: list[PortConfig] = Field(default_factory=list)
    supported_features: list[str] = Field(
        default_factory=lambda: [
            "vlan", "address_learning", "filtering", "qos", "configuration"
        ]
    )
    max_mac_table_size: int = Field(default=1024, description="MAC address table capacity")
    mac_aging_time_s: int = Field(default=300, description="MAC aging timeout in seconds")
    supports_double_tagging: bool = Field(default=False)
    supports_gptp: bool = Field(default=False)
    can_reset: bool = Field(default=False, description="Whether DUT can be power-cycled between tests")
    reset_command: str | None = Field(default=None, description="Command to reset DUT")
    notes: str = Field(default="")

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, v: list[PortConfig], info: Any) -> list[PortConfig]:
        port_count = info.data.get("port_count")
        if port_count and len(v) > port_count:
            raise ValueError(f"More ports defined ({len(v)}) than port_count ({port_count})")
        return v


# ---------------------------------------------------------------------------
# Test Specification Model
# ---------------------------------------------------------------------------


class TestSpecDefinition(BaseModel):
    """
    A single TC8 test specification definition (data-driven from YAML).

    Maps 1:1 to a row in the TC8 spec document.
    """

    spec_id: str = Field(description="Unique ID, e.g. SWITCH_VLAN_001")
    tc8_reference: str = Field(description="Section reference, e.g. 5.3.1")
    section: TestSection
    title: str
    description: str
    priority: str = Field(default="medium")  # high / medium / low
    timing_tier: TimingTier = Field(default=TimingTier.TIER_A)
    parameters: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    test_procedure: list[str] = Field(default_factory=list)
    expected_result: dict[str, Any] = Field(default_factory=dict)
    timing_tolerance_ms: float = Field(default=100.0)
    applicable_frame_types: list[FrameType] = Field(
        default_factory=lambda: list(FrameType)
    )
    applicable_tpids: list[int] = Field(
        default_factory=lambda: [0x8100, 0x88A8, 0x9100]
    )


# ---------------------------------------------------------------------------
# Test Case & Result Models
# ---------------------------------------------------------------------------


class TestCaseParameters(BaseModel):
    """Concrete parameters for a single test case execution."""

    ingress_port: int
    egress_ports: list[int] = Field(default_factory=list)
    vid: int = Field(default=1, ge=0, le=4095)
    frame_type: FrameType = Field(default=FrameType.UNTAGGED)
    tpid: int = Field(default=0x8100)
    protocol: ProtocolType = Field(default=ProtocolType.ICMP)
    src_mac: str = Field(default="02:00:00:00:00:01")
    dst_mac: str = Field(default="02:00:00:00:00:02")
    payload_size: int = Field(default=64, ge=46, le=9216)
    custom: dict[str, Any] = Field(default_factory=dict)


class TestCase(BaseModel):
    """
    A fully-parameterized, executable test case.

    Generated by expanding a TestSpecDefinition across all parameter
    combinations (ports × VIDs × frame types × …).
    """

    case_id: str = Field(description="Unique case ID, e.g. SWITCH_VLAN_001_P1_P2_VID100_ST")
    spec_id: str = Field(description="Parent specification ID")
    tc8_reference: str
    section: TestSection
    tier: TestTier = Field(default=TestTier.FULL)
    parameters: TestCaseParameters
    description: str = Field(default="")


class FrameCapture(BaseModel):
    """Captured Ethernet frame data from a port."""

    port_id: int
    timestamp: float = Field(description="Capture timestamp (epoch seconds)")
    raw_bytes: bytes | None = Field(default=None, exclude=True, repr=False)
    raw_hex: str = Field(default="", description="Hex-encoded frame bytes for JSON/DB storage")
    src_mac: str = Field(default="")
    dst_mac: str = Field(default="")
    ethertype: int = Field(default=0)
    vlan_tags: list[dict[str, Any]] = Field(default_factory=list)
    payload_size: int = Field(default=0)



class TestResult(BaseModel):
    """Result of executing a single test case."""

    case_id: str
    spec_id: str
    tc8_reference: str
    section: TestSection
    status: TestStatus
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None
    duration_ms: float = Field(default=0.0)
    timing_tier: TimingTier = Field(default=TimingTier.TIER_A)

    # What we expected vs what happened
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)

    # Frame captures
    sent_frames: list[FrameCapture] = Field(default_factory=list)
    received_frames: list[FrameCapture] = Field(default_factory=list)

    # Diagnostics
    message: str = Field(default="")
    error_detail: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Report & Session Models
# ---------------------------------------------------------------------------


class TestSuiteReport(BaseModel):
    """Aggregate report for a test run."""

    report_id: str
    dut_profile: DUTProfile
    tier: TestTier
    created_at: datetime = Field(default_factory=datetime.now)
    total_cases: int = Field(default=0)
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    informational: int = Field(default=0)
    skipped: int = Field(default=0)
    errors: int = Field(default=0)
    duration_s: float = Field(default=0.0)
    results: list[TestResult] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        """Percentage of passed tests (excluding skips and informational)."""
        evaluated = self.passed + self.failed
        return (self.passed / evaluated * 100) if evaluated > 0 else 0.0

    @property
    def sections_summary(self) -> dict[str, dict[str, int]]:
        """Per-section pass/fail summary."""
        summary: dict[str, dict[str, int]] = {}
        for r in self.results:
            sec = r.section.value
            if sec not in summary:
                summary[sec] = {"pass": 0, "fail": 0, "skip": 0, "error": 0, "info": 0}
            match r.status:
                case TestStatus.PASS:
                    summary[sec]["pass"] += 1
                case TestStatus.FAIL:
                    summary[sec]["fail"] += 1
                case TestStatus.SKIP:
                    summary[sec]["skip"] += 1
                case TestStatus.ERROR:
                    summary[sec]["error"] += 1
                case TestStatus.INFORMATIONAL:
                    summary[sec]["info"] += 1
        return summary


class SessionState(BaseModel):
    """Tracks DUT state within a test session for isolation."""

    session_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    dut_profile: DUTProfile
    mac_table_cleared: bool = Field(default=False)
    statistics_cleared: bool = Field(default=False)
    links_verified: bool = Field(default=False)
    vlan_config_verified: bool = Field(default=False)
    cleanup_wait_s: float = Field(default=0.0)
    is_clean: bool = Field(default=False)
