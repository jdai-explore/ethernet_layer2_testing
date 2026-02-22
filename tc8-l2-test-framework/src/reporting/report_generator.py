"""
HTML report generator — produces test suite reports.

Uses Jinja2 templates to render professional HTML reports
containing test results, statistics, and TC8 compliance status.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:  # pragma: no cover
    Environment = None  # type: ignore[misc,assignment]
    FileSystemLoader = None  # type: ignore[misc,assignment]
    select_autoescape = None  # type: ignore[misc,assignment]

from src.models.test_case import (
    TestResult,
    TestSection,
    TestStatus,
    TestSuiteReport,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "data" / "templates"


class ReportGenerator:
    """
    Generate HTML reports from TestSuiteReport data.

    Usage::

        gen = ReportGenerator()
        html = gen.render(report)
        gen.save(report, "output/report.html")
    """

    def __init__(self, template_dir: Path | str | None = None) -> None:
        tdir = Path(template_dir) if template_dir else TEMPLATE_DIR
        if Environment is None:
            logger.warning("Jinja2 not installed — report rendering unavailable")
            self._env = None
        else:
            self._env = Environment(
                loader=FileSystemLoader(str(tdir)),
                autoescape=select_autoescape(["html"]),
            )

    def render(self, report: TestSuiteReport) -> str:
        """Render an HTML report from the suite report data."""
        if self._env is None:
            return self._render_fallback(report)

        template = self._env.get_template("report_template.html")
        context = self._build_context(report)
        return template.render(**context)

    def save(self, report: TestSuiteReport, output_path: str | Path) -> Path:
        """Render and save report to file."""
        html = self.render(report)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        logger.info("Report saved to %s", out)
        return out

    def _build_context(self, report: TestSuiteReport) -> dict[str, Any]:
        """Build the template rendering context from a report."""
        from src.utils.hexdump import hexdump_html, hexdump_css, frame_summary

        # Section breakdown
        section_stats: dict[str, dict[str, int]] = {}
        section_labels = {
            "5.3": "5.3 VLAN", "5.4": "5.4 General", "5.5": "5.5 Address Learning",
            "5.6": "5.6 Filtering", "5.7": "5.7 Time Sync", "5.8": "5.8 QoS",
            "5.9": "5.9 Configuration",
        }

        for result in report.results:
            sec = result.section.value if result.section else "unknown"
            label = section_labels.get(sec, sec)
            if label not in section_stats:
                section_stats[label] = {"pass": 0, "fail": 0, "info": 0, "skip": 0, "error": 0}
            match result.status:
                case TestStatus.PASS:
                    section_stats[label]["pass"] += 1
                case TestStatus.FAIL:
                    section_stats[label]["fail"] += 1
                case TestStatus.INFORMATIONAL:
                    section_stats[label]["info"] += 1
                case TestStatus.SKIP:
                    section_stats[label]["skip"] += 1
                case TestStatus.ERROR:
                    section_stats[label]["error"] += 1

        # Failures only
        failures = [r for r in report.results if r.status == TestStatus.FAIL]
        errors = [r for r in report.results if r.status == TestStatus.ERROR]

        # Pass rate
        total_non_skip = report.total_cases - report.skipped
        pass_rate = (report.passed / total_non_skip * 100) if total_non_skip > 0 else 0.0

        # Chart data (JSON-serializable for Chart.js)
        chart_data = {
            "summary": {
                "pass": report.passed,
                "fail": report.failed,
                "info": report.informational,
                "skip": report.skipped,
                "error": report.errors,
            },
            "sections": list(section_stats.keys()),
            "section_pass": [s["pass"] for s in section_stats.values()],
            "section_fail": [s["fail"] for s in section_stats.values()],
            "section_info": [s["info"] for s in section_stats.values()],
            "section_skip": [s["skip"] for s in section_stats.values()],
            "section_error": [s["error"] for s in section_stats.values()],
        }

        # Frame hexdumps per result
        result_details: dict[str, dict[str, Any]] = {}
        for r in report.results:
            detail: dict[str, Any] = {
                "expected": r.expected,
                "actual": r.actual,
                "sent_hexdumps": [],
                "received_hexdumps": [],
                "log_entries": [],
            }
            # Format log entries with readable timestamps
            for entry in r.log_entries:
                from datetime import datetime as dt
                detail["log_entries"].append({
                    "time": dt.fromtimestamp(entry.timestamp).strftime("%H:%M:%S.%f")[:-3],
                    "level": entry.level,
                    "source": entry.source,
                    "message": entry.message,
                })
            for frame in r.sent_frames:
                if frame.raw_bytes:
                    detail["sent_hexdumps"].append({
                        "port": frame.port_id,
                        "summary": frame_summary(frame.raw_bytes),
                        "hex_html": hexdump_html(frame.raw_bytes),
                    })
                elif frame.raw_hex:
                    try:
                        raw = bytes.fromhex(frame.raw_hex)
                        detail["sent_hexdumps"].append({
                            "port": frame.port_id,
                            "summary": frame_summary(raw),
                            "hex_html": hexdump_html(raw),
                        })
                    except ValueError:
                        pass
            result_details[r.case_id] = detail

        import json

        return {
            "report": report,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "section_stats": section_stats,
            "failures": failures,
            "errors": errors,
            "pass_rate": round(pass_rate, 1),
            "tc8_version": "3.0",
            "framework_version": "2.0.0",
            "chart_data_json": json.dumps(chart_data),
            "result_details": result_details,
            "hexdump_css": hexdump_css(),
        }

    @staticmethod
    def _render_fallback(report: TestSuiteReport) -> str:
        """Minimal text-based fallback when Jinja2 is unavailable."""
        lines = [
            "=" * 72,
            "TC8 Layer 2 Test Report (text fallback)",
            f"Report ID: {report.report_id}",
            f"DUT: {report.dut_profile.name if report.dut_profile else 'N/A'}",
            f"Tier: {report.tier.value}",
            f"Duration: {report.duration_s:.1f}s",
            "-" * 72,
            f"Total: {report.total_cases}  |  "
            f"Pass: {report.passed}  |  Fail: {report.failed}  |  "
            f"Info: {report.informational}  |  Skip: {report.skipped}  |  Error: {report.errors}",
            "=" * 72,
        ]

        for r in report.results:
            status = r.status.value.upper()
            lines.append(f"  [{status:4s}] {r.case_id}")
            if r.message:
                lines.append(f"         → {r.message}")

        return "\n".join(lines)
