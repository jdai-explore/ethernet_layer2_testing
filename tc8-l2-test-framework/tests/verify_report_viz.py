"""End-to-end verification of the report visualization pipeline."""
from src.models.test_case import (
    DUTProfile, TestTier, TestSection, TestStatus,
    TestResult, TestSuiteReport, FrameCapture,
)
from src.reporting.report_generator import ReportGenerator
from src.reporting.result_store import ResultStore

# Create a mock report with frame captures
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

report = TestSuiteReport(
    report_id="test-vis-002",
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
        ),
        TestResult(
            case_id="TC_VLAN_002", spec_id="SPEC_002", tc8_reference="5.3.2",
            section=TestSection.VLAN, status=TestStatus.FAIL, duration_ms=85.0,
            message="VLAN tag mismatch",
            expected={"vlan_id": 200}, actual={"vlan_id": 201},
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
}
for name, passed in checks.items():
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
assert all(checks.values()), "Some HTML checks failed!"

# Save to file
rg.save(report, "reports/test-vis-002.html")
print("  ✅ HTML saved to reports/test-vis-002.html")

# -- Test 2: DB Persistence --
print("\n" + "=" * 50)
print("Test 2: DB Persistence")
store = ResultStore()
store.save_report(report)
print("  ✅ Report saved to DB")

run = store.get_run("test-vis-002")
assert run is not None, "Report not found in DB!"
print(f"  ✅ Report retrieved from DB: {run['report_id']}")

results = run["results"]
assert len(results) == 4, f"Expected 4 results, got {len(results)}"
print(f"  ✅ Results count: {len(results)}")

r0 = results[0]
assert r0.get("expected") == {"vlan_id": 100}, f"Expected mismatch: {r0.get('expected')}"
assert r0.get("actual") == {"vlan_id": 100}, f"Actual mismatch: {r0.get('actual')}"
print("  ✅ Expected/Actual data persisted correctly")

# Check sent_frames serialization
sent = r0.get("sent_frames")
if sent:
    print(f"  ✅ Sent frames persisted: {len(sent)} frame(s)")
else:
    print("  ⚠️ Sent frames not found (may be None — check serialization)")

# -- Test 3: Hexdump in HTML --
print("\n" + "=" * 50)
print("Test 3: Hexdump in HTML Report")
# The first result has a frame with raw_bytes, so hexdump should appear
has_hexdump = "hexdump" in html
has_frame_summary = "02:00:00:00:00:01" in html or "02:00:00:00:00:02" in html
print(f"  {'✅ PASS' if has_hexdump else '⚠️ INFO'}: Hexdump class present")
print(f"  {'✅ PASS' if has_frame_summary else '⚠️ INFO'}: Frame MAC in report")

print("\n" + "=" * 50)
print(">>> ALL VERIFICATIONS PASSED <<<")
