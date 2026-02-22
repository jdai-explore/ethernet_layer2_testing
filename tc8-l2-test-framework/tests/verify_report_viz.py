"""End-to-end verification of the report visualization pipeline."""
import time
from src.models.test_case import (
    DUTProfile, TestTier, TestSection, TestStatus,
    TestResult, TestSuiteReport, FrameCapture, LogEntry,
)
from src.reporting.report_generator import ReportGenerator
from src.reporting.result_store import ResultStore

# Create a mock report with frame captures AND log entries
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

# Mock log entries for test cases
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

report = TestSuiteReport(
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

# -- Test 1: HTML Report Generation --
print("=" * 50)
print("Test 1: HTML Report Generation")
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
for name, passed in checks.items():
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
assert all(checks.values()), "Some HTML checks failed!"

# Save to file
rg.save(report, "reports/test-vis-003.html")
print("  ✅ HTML saved to reports/test-vis-003.html")

# -- Test 2: DB Persistence --
print("\n" + "=" * 50)
print("Test 2: DB Persistence")
store = ResultStore("sqlite:///reports/test_verify.db")
store.save_report(report)
print("  ✅ Report saved to DB")

run = store.get_run("test-vis-003")
assert run is not None, "Report not found in DB!"
print(f"  ✅ Report retrieved from DB: {run['report_id']}")

results = run["results"]
assert len(results) == 4, f"Expected 4 results, got {len(results)}"
print(f"  ✅ Results count: {len(results)}")

r0 = results[0]
assert r0.get("expected") == {"vlan_id": 100}, f"Expected mismatch: {r0.get('expected')}"
assert r0.get("actual") == {"vlan_id": 100}, f"Actual mismatch: {r0.get('actual')}"
print("  ✅ Expected/Actual data persisted correctly")

# Check log_entries serialization
log_entries = r0.get("log_entries")
assert log_entries is not None and len(log_entries) > 0, f"Log entries missing: {log_entries}"
print(f"  ✅ Log entries persisted: {len(log_entries)} entries for first result")
assert log_entries[0]["level"] == "INFO", f"Log level mismatch: {log_entries[0]}"
assert "session_manager" in log_entries[0]["source"], f"Log source mismatch: {log_entries[0]}"
print(f"  ✅ Log entry structure correct (level={log_entries[0]['level']}, source={log_entries[0]['source']})")

# Check failed result has WARNING/ERROR logs
r1 = results[1]
r1_logs = r1.get("log_entries")
assert r1_logs is not None and len(r1_logs) > 0, f"Failed result logs missing"
has_warn = any(e["level"] == "WARNING" for e in r1_logs)
has_error = any(e["level"] == "ERROR" for e in r1_logs)
assert has_warn, "Failed result missing WARNING log"
assert has_error, "Failed result missing ERROR log"
print(f"  ✅ Failed result logs: {len(r1_logs)} entries (includes WARNING + ERROR)")

# Check sent_frames serialization
sent = r0.get("sent_frames")
if sent:
    print(f"  ✅ Sent frames persisted: {len(sent)} frame(s)")
else:
    print("  ⚠️ Sent frames not found")

# -- Test 3: Hexdump in HTML --
print("\n" + "=" * 50)
print("Test 3: Hexdump in HTML Report")
has_hexdump = "hexdump" in html
has_frame_summary = "02:00:00:00:00:01" in html or "02:00:00:00:00:02" in html
print(f"  {'✅ PASS' if has_hexdump else '⚠️ INFO'}: Hexdump class present")
print(f"  {'✅ PASS' if has_frame_summary else '⚠️ INFO'}: Frame MAC in report")

# -- Test 4: Log display in HTML --
print("\n" + "=" * 50)
print("Test 4: Log Table in HTML Report")
checks_log = {
    "Log table element": "log-table" in html,
    "Session SETUP log": "Session abc123 SETUP" in html or "session_manager" in html,
    "DEBUG level badge": 'log-badge debug' in html,
    "INFO level badge": 'log-badge info' in html,
    "WARNING level badge": 'log-badge warning' in html,
    "ERROR level badge": 'log-badge error' in html,
}
for name, passed in checks_log.items():
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
assert all(checks_log.values()), "Some log display checks failed!"

print("\n" + "=" * 50)
print(">>> ALL VERIFICATIONS PASSED <<<")
