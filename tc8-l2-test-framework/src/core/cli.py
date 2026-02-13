"""
CLI entry point for the TC8 L2 Test Framework.

Provides command-line interface for running tests, managing
configurations, and generating reports.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager
from src.core.test_runner import TestRunner
from src.models.test_case import TestSection, TestStatus, TestTier

console = Console()


def setup_logging(level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """TC8 Layer 2 Automotive Ethernet ECU Test Framework."""
    setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["config"] = ConfigManager()


@cli.command()
@click.option("--dut", required=True, help="Path to DUT profile YAML")
@click.option("--tier", default="smoke", type=click.Choice(["smoke", "core", "full"]))
@click.option("--section", multiple=True, help="Limit to specific sections (e.g., 5.3, 5.4)")
@click.pass_context
def run(ctx: click.Context, dut: str, tier: str, section: tuple[str, ...]) -> None:
    """Run TC8 Layer 2 test suite."""
    config: ConfigManager = ctx.obj["config"]

    # Load DUT profile
    console.print(f"\n[bold blue]TC8 Layer 2 Test Framework[/bold blue]")
    console.print(f"Loading DUT profile: [cyan]{dut}[/cyan]")
    dut_profile = config.load_dut_profile(dut)
    console.print(f"  DUT: [green]{dut_profile.name}[/green] ({dut_profile.port_count} ports)")

    # Load specs
    config.load_spec_definitions()
    console.print(f"  Loaded [yellow]{len(config.spec_definitions)}[/yellow] spec definitions")

    # Resolve sections
    section_map = {
        "5.3": TestSection.VLAN,
        "5.4": TestSection.GENERAL,
        "5.5": TestSection.ADDRESS_LEARNING,
        "5.6": TestSection.FILTERING,
        "5.7": TestSection.TIME_SYNC,
        "5.8": TestSection.QOS,
        "5.9": TestSection.CONFIGURATION,
    }
    sections = [section_map[s] for s in section if s in section_map] if section else None

    # Setup and run
    test_tier = TestTier(tier)
    session_mgr = SessionManager(dut_profile)
    validator = ResultValidator()

    def progress_cb(current: int, total: int, case_id: str, status: TestStatus | None) -> None:
        icon = {"pass": "✅", "fail": "❌", "informational": "ℹ️", "skip": "⏭️", "error": "💥"}
        s = icon.get(status.value, "❓") if status else "🔄"
        console.print(f"  [{current}/{total}] {s} {case_id}")

    runner = TestRunner(config, session_mgr, validator, progress_callback=progress_cb)

    console.print(f"\n[bold]Running [yellow]{tier}[/yellow] suite...[/bold]\n")
    report = asyncio.run(runner.run_suite(test_tier, sections))

    # Print summary
    console.print(f"\n[bold]{'═' * 60}[/bold]")
    console.print(f"[bold blue]Test Suite Results[/bold blue]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total Cases", str(report.total_cases))
    table.add_row("Passed", f"[green]{report.passed}[/green]")
    table.add_row("Failed", f"[red]{report.failed}[/red]")
    table.add_row("Informational", f"[yellow]{report.informational}[/yellow]")
    table.add_row("Skipped", str(report.skipped))
    table.add_row("Errors", f"[red]{report.errors}[/red]")
    table.add_row("Duration", f"{report.duration_s:.1f}s")
    table.add_row("Pass Rate", f"{report.pass_rate:.1f}%")
    console.print(table)


@cli.command()
@click.pass_context
def list_specs(ctx: click.Context) -> None:
    """List all available TC8 test specifications."""
    config: ConfigManager = ctx.obj["config"]
    config.load_spec_definitions()

    table = Table(title="TC8 Layer 2 Test Specifications", show_header=True)
    table.add_column("Spec ID", style="cyan")
    table.add_column("Section")
    table.add_column("Title")
    table.add_column("Priority")

    for spec in config.spec_definitions.values():
        priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(spec.priority, "white")
        table.add_row(
            spec.spec_id,
            spec.section.value,
            spec.title,
            f"[{priority_color}]{spec.priority}[/{priority_color}]",
        )

    console.print(table)
    console.print(f"\nTotal: [bold]{len(config.spec_definitions)}[/bold] specifications")


@cli.command()
@click.option("--output", default="config/dut_profiles/new_dut.yaml", help="Output file")
@click.pass_context
def questionnaire(ctx: click.Context, output: str) -> None:
    """Interactive ECU questionnaire to generate a DUT profile."""
    console.print("[bold blue]ECU Configuration Questionnaire[/bold blue]\n")
    console.print("[yellow]Answer the following questions about your ECU switch.[/yellow]\n")

    responses: dict = {}
    responses["dut_name"] = click.prompt("ECU / DUT name")
    responses["model"] = click.prompt("ECU model / part number", default="")
    responses["firmware"] = click.prompt("Firmware version")
    responses["port_count"] = click.prompt("Number of Ethernet ports", type=int, default=4)
    responses["mac_table_size"] = click.prompt("MAC table capacity", type=int, default=1024)
    responses["mac_aging_time"] = click.prompt("MAC aging time (seconds)", type=int, default=300)
    responses["double_tagging"] = click.confirm("Supports double-tagging (802.1ad)?", default=False)
    responses["gptp"] = click.confirm("Supports gPTP (IEEE 802.1AS)?", default=False)
    responses["can_reset"] = click.confirm("Can DUT be power-cycled between tests?", default=False)

    config: ConfigManager = ctx.obj["config"]
    profile = config.apply_questionnaire_responses(responses)

    console.print(f"\n[green]DUT Profile generated: {profile.name}[/green]")
    console.print(f"Output: [cyan]{output}[/cyan]")


def main() -> None:
    """CLI entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
