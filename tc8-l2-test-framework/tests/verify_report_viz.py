"""End-to-end verification of the report visualization pipeline."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.models.test_case import (
    DUTProfile,
    FrameCapture,
    LogEntry,
    TestResult,
    TestSection,
    TestStatus,
    TestSuiteReport,
    TestTier,
)
from src.reporting.report_generator import ReportGenerator
from src.reporting.result_store import ResultStore


def _build_report() -> TestSuiteReport:
    """Build a representative mock report for visualization tests."""
    profile = DUTProfile(name="Test ECU", mac_address="02:00:00:00:00:01", port_count=3)

    frame_sent = FrameCapture(
        port_id=1,
        timestamp=1234567890.0,
        raw_bytes=b"\x02\x00\x00\x00\x00\x01\x02\x00\x00\x00\x00\x02\x08\x00" + b"\x00" * 46,
        raw_hex="020000000001020000000002080000" + "00" * 46,
        src_mac="02:00:00:00:00:02",
        dst_mac="02:00:00:00:00:01",
        ethertype=0x0800,
        payload_size=46,
    )

    now = time.time()
    vlan_logs = [
        LogEntry(timestamp=now, level="INFO", source="session_manager", message="═══ Session abc123 SETUP ═══"),
        LogEntry(timestamp=now + 0.01, level="INFO", source="session_manager", message="Session abc123 ready (0.5s setup)"),
        LogEntry(timestamp=now + 0.02, level="INFO", source="vlan_tests", message="[SWITCH_VLAN_001] VLAN Tag Relay — TC8 §5.3.1 (priority=high)"),
        LogEntry(timestamp=now + 0.05, level="DEBUG", source="test_runner", message="Executing: TC_VLAN_001"),
        LogEntry(timestamp=now + 0.08, level="INFO", source="result_validator", message="Frame forwarding check: PASS on port 2"),
        LogEntry(timestamp=now + 0.10, level="INFO", source="session_manager", message="═══ Session abc123 TEARDOWN ═══"),
    ]
    fail_logs = [
        LogEntry(timestamp=now, level="INFO", source="session_manager", message="═══ Session def456 SETUP ═══"),
        LogEntry(timestamp=now + 0.01, level="DEBUG", source="test_runner", message="Executing: TC_VLAN_002"),
        LogEntry(timestamp=now + 0.05, level="WARNING", source="result_validator", message="VLAN tag mismatch: expected VID=200, got VID=201"),
        LogEntry(timestamp=now + 0.06, level="ERROR", source="result_validator", message="Frame validation FAILED on port 3"),
    ]

    return TestSuiteReport(
        report_id="test-vis-003",
        dut_profile=profile,
        tier=TestTier.SMOKE,
        total_cases=10, passed=6, failed=2, informational=1, skipped=0, errors=1,
        duration_s=5.3,
        results=[
            TestResult(
                case_id="TC_VLAN_001", spec_id="SPEC_001", tc8_reference="5.3.1",
                section=TestSection.VLAN, status=TestStatus.PASS, duration_ms=120.0,
                expected={"vlan_id": 100}, actual={"vlan_id": 100},
                sent_frames=[frame_sent],
                log_entries=vlan_logs,
            ),
            TestResult(
                case_id="TC_VLAN_002", spec_id="SPEC_002", tc8_reference="5.3.2",
                section=TestSection.VLAN, status=TestStatus.FAIL, duration_ms=85.0,
                message="VLAN tag mismatch",
                expected={"vlan_id": 200}, actual={"vlan_id": 201},
                log_entries=fail_logs,
            ),
            TestResult(
                case_id="TC_GEN_001", spec_id="SPEC_010", tc8_reference="5.4.1",
                section=TestSection.GENERAL, status=TestStatus.PASS, duration_ms=45.0,
            ),
            TestResult(
                case_id="TC_GEN_002", spec_id="SPEC_011", tc8_reference="5.4.2",
                section=TestSection.GENERAL, status=TestStatus.INFORMATIONAL, duration_ms=30.0,
                message="Frame forwarded correctly (informational)",
            ),
        ],
    )


def test_html_report_generation(tmp_path: Path) -> None:
    """HTML report renders all expected UI elements."""
    report = _build_report()
    rg = ReportGenerator()
    html = rg.render(report)

    checks = {
        "Doughnut canvas": "doughnutChart" in html,
        "Section bar canvas": "sectionChart" in html,
        "Chart.js CDN": "chart.umd" in html,
        "Filter buttons": "filter-btn" in html,
        "Click-to-expand": "detail-row" in html,
        "Hexdump CSS": "hx-dst" in html,
        "Chart data JSON": "chart_data" in html.lower() or "chartData" in html,
        "Log table": "log-table" in html,
        "Log badge": "log-badge" in html,
        "Log entries present": "session_manager" in html,
    }
    failed = [name for name, ok in checks.items() if not ok]
    assert not failed, f"HTML checks failed: {failed}"

    out_file = tmp_path / "test-vis-003.html"
    rg.save(report, str(out_file))
    assert out_file.exists(), "HTML file was not written"


def test_log_display_in_html() -> None:
    """Log-level badges and session markers appear in the HTML report."""
    report = _build_report()
    html = ReportGenerator().render(report)

    checks = {
        "Log table element": "log-table" in html,
        "Session SETUP log": "Session abc123 SETUP" in html or "session_manager" in html,
        "DEBUG level badge": "log-badge debug" in html,
        "INFO level badge": "log-badge info" in html,
        "WARNING level badge": "log-badge warning" in html,
        "ERROR level badge": "log-badge error" in html,
    }
    failed = [name for name, ok in checks.items() if not ok]
    assert not failed, f"Log display checks failed: {failed}"


def test_db_persistence() -> None:
    """Report round-trips through SQLite with all fields intact."""
    report = _build_report()
    store = ResultStore("sqlite:///:memory:")
    store.save_report(report)

    run = store.get_run("test-vis-003")
    assert run is not None, "Report not found in DB after save"
    assert run["report_id"] == "test-vis-003"

    results = run["results"]
    assert len(results) == 4, f"Expected 4 results, got {len(results)}"

    r0 = results[0]
    assert r0.get("expected") == {"vlan_id": 100}
    assert r0.get("actual") == {"vlan_id": 100}

    log_entries = r0.get("log_entries")
    assert log_entries and len(log_entries) > 0, "Log entries missing from first result"
    assert log_entries[0]["level"] == "INFO"
    assert "session_manager" in log_entries[0]["source"]

    r1 = results[1]
    r1_logs = r1.get("log_entries", [])
    assert any(e["level"] == "WARNING" for e in r1_logs), "Failed result missing WARNING log"
    assert any(e["level"] == "ERROR" for e in r1_logs), "Failed result missing ERROR log"
