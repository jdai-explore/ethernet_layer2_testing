"""
CLI entry point for TC8 L2 Test Framework.

Usage::

    python -m src.cli run --dut config/dut_profiles/example_ecu.yaml --tier smoke
    python -m src.cli specs --section 5.3
    python -m src.cli history --limit 10
    python -m src.cli report <report_id>
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager
from src.core.test_runner import TestRunner
from src.models.test_case import TestSection, TestStatus, TestTier
from src.reporting.report_generator import ReportGenerator
from src.reporting.result_store import ResultStore

logger = logging.getLogger("tc8")

SECTION_MAP = {
    "5.3": TestSection.VLAN,
    "5.4": TestSection.GENERAL,
    "5.5": TestSection.ADDRESS_LEARNING,
    "5.6": TestSection.FILTERING,
    "5.7": TestSection.TIME_SYNC,
    "5.8": TestSection.QOS,
    "5.9": TestSection.CONFIGURATION,
}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """TC8 Layer 2 Automotive Ethernet ECU Test Framework."""
    _setup_logging(verbose)


@cli.command()
@click.option("--dut", required=True, type=click.Path(exists=True), help="Path to DUT profile YAML")
@click.option("--tier", default="smoke", type=click.Choice(["smoke", "core", "full"]), help="Execution tier")
@click.option("--sections", default=None, help="Comma-separated TC8 sections (e.g. 5.3,5.5)")
@click.option("--output", default=None, type=click.Path(), help="Output HTML report path")
@click.option("--db-url", default="sqlite:///reports/test_results.db", help="Database URL")
def run(dut: str, tier: str, sections: str | None, output: str | None, db_url: str) -> None:
    """Execute a test suite against a DUT."""
    config = ConfigManager()
    config.load_dut_profile(dut)
    config.load_spec_definitions()

    click.echo(f"⚡ TC8 L2 Test Framework")
    click.echo(f"   DUT:  {config.dut_profile.name}")
    click.echo(f"   Tier: {tier}")
    click.echo(f"   Specs loaded: {len(config.spec_definitions)}")

    # Parse sections filter
    section_list = None
    if sections:
        section_list = [SECTION_MAP[s.strip()] for s in sections.split(",") if s.strip() in SECTION_MAP]
        click.echo(f"   Sections: {', '.join(s.value for s in section_list)}")

    # Progress callback
    def progress(current: int, total: int, case_id: str, status: TestStatus | None) -> None:
        sym = "✓" if status == TestStatus.PASS else "✗" if status == TestStatus.FAIL else "…"
        click.echo(f"   [{current:4d}/{total}] {sym} {case_id}")

    # Build runner
    session_mgr = SessionManager(config.dut_profile)
    validator = ResultValidator()
    runner = TestRunner(config, session_mgr, validator, progress_callback=progress)

    # Run
    click.echo("\n─── Running ───")
    report = asyncio.run(runner.run_suite(TestTier(tier), section_list))

    # Summary
    click.echo(f"\n─── Results ───")
    click.echo(f"   Total:  {report.total_cases}")
    click.echo(f"   Pass:   {report.passed}")
    click.echo(f"   Fail:   {report.failed}")
    click.echo(f"   Info:   {report.informational}")
    click.echo(f"   Skip:   {report.skipped}")
    click.echo(f"   Error:  {report.errors}")
    click.echo(f"   Rate:   {report.pass_rate:.1f}%")
    click.echo(f"   Time:   {report.duration_s:.1f}s")

    # Save to database
    try:
        store = ResultStore(db_url)
        store.save_report(report)
        click.echo(f"\n   💾 Saved to database ({db_url})")
    except Exception as exc:
        click.echo(f"\n   ⚠ DB save failed: {exc}", err=True)

    # Generate HTML report
    out_path = output or f"reports/{report.report_id}.html"
    try:
        gen = ReportGenerator()
        gen.save(report, out_path)
        click.echo(f"   📄 Report: {out_path}")
    except Exception as exc:
        click.echo(f"   ⚠ Report generation failed: {exc}", err=True)


@cli.command()
@click.option("--section", default=None, help="Filter by TC8 section (e.g. 5.3)")
def specs(section: str | None) -> None:
    """List available TC8 test specifications."""
    config = ConfigManager()
    config.load_spec_definitions()

    all_specs = list(config.spec_definitions.values())
    if section and section in SECTION_MAP:
        all_specs = [s for s in all_specs if s.section == SECTION_MAP[section]]
        click.echo(f"Specs for section {section}:")
    else:
        click.echo("All TC8 specifications:")

    click.echo(f"{'ID':<24s} {'Section':<8s} {'Priority':<10s} {'Title'}")
    click.echo("─" * 80)
    for s in sorted(all_specs, key=lambda x: x.spec_id):
        click.echo(f"{s.spec_id:<24s} {s.section.value:<8s} {s.priority:<10s} {s.title}")
    click.echo(f"\nTotal: {len(all_specs)} specifications")


@cli.command()
@click.option("--limit", default=10, type=int, help="Number of recent runs to show")
@click.option("--db-url", default="sqlite:///reports/test_results.db", help="Database URL")
def history(limit: int, db_url: str) -> None:
    """Show recent test run history from database."""
    try:
        store = ResultStore(db_url)
    except Exception as exc:
        click.echo(f"Cannot open database: {exc}", err=True)
        sys.exit(1)

    runs = store.list_runs(limit=limit)
    if not runs:
        click.echo("No test runs found in database.")
        return

    click.echo(f"{'Report ID':<38s} {'DUT':<20s} {'Tier':<8s} {'Pass':<6s} {'Fail':<6s} {'Rate':<8s} {'Date'}")
    click.echo("─" * 100)
    for r in runs:
        click.echo(
            f"{r['report_id']:<38s} "
            f"{r['dut_name']:<20s} "
            f"{r['tier']:<8s} "
            f"{r['passed']:<6d} "
            f"{r['failed']:<6d} "
            f"{r['pass_rate']:<8.1f} "
            f"{r['created_at'] or ''}"
        )


@cli.command()
@click.argument("report_id")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "html"]), help="Output format")
@click.option("--output", default=None, type=click.Path(), help="Output file path")
@click.option("--db-url", default="sqlite:///reports/test_results.db", help="Database URL")
def report(report_id: str, fmt: str, output: str | None, db_url: str) -> None:
    """View or regenerate a report from stored results."""
    store = ResultStore(db_url)
    run_data = store.get_run(report_id)

    if run_data is None:
        click.echo(f"Report '{report_id}' not found in database.", err=True)
        sys.exit(1)

    if fmt == "text":
        click.echo(f"\nReport: {run_data['report_id']}")
        click.echo(f"DUT:    {run_data['dut_name']}")
        click.echo(f"Tier:   {run_data['tier']}")
        click.echo(f"Date:   {run_data['created_at']}")
        click.echo(f"Total:  {run_data['total_cases']}  Pass: {run_data['passed']}  "
                    f"Fail: {run_data['failed']}  Rate: {run_data['pass_rate']:.1f}%\n")

        results = run_data.get("results", [])
        for r in results:
            status = r["status"].upper()
            click.echo(f"  [{status:4s}] {r['case_id']}  ({r['spec_id']})")
            if r.get("message"):
                click.echo(f"         → {r['message']}")
    else:
        click.echo(f"HTML regeneration for stored reports requires full TestSuiteReport reconstruction.")
        click.echo(f"Use the web UI at /api/reports/{report_id}/html for rendered output.")


if __name__ == "__main__":
    cli()
