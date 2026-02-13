"""
Integration tests — smoke suite execution and report generation.

Runs the test framework in simulation mode (NullDUTController) and validates
that the full pipeline works: spec loading → case generation → execution →
result validation → report generation.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager
from src.core.test_runner import TestRunner
from src.models.test_case import DUTProfile, TestSection, TestTier
from src.reporting.report_generator import ReportGenerator
from src.specs.spec_registry import SpecRegistry


class TestSpecHandlers:
    """Verify every spec has a registered handler."""

    @pytest.mark.parametrize("section", list(TestSection))
    def test_spec_handler_exists(
        self,
        section: TestSection,
        config_manager: ConfigManager,
        validator: ResultValidator,
    ) -> None:
        """Each TestSection must have a registered handler in SpecRegistry."""
        registry = SpecRegistry(config_manager, validator)
        assert registry.has_handler(section), (
            f"No handler registered for section {section.value}"
        )


class TestSmokeRun:
    """Run a smoke-tier suite in simulation mode."""

    @pytest.fixture
    def runner(
        self,
        config_manager: ConfigManager,
        session_manager: SessionManager,
        validator: ResultValidator,
    ) -> TestRunner:
        return TestRunner(config_manager, session_manager, validator)

    @pytest.mark.asyncio
    async def test_smoke_run_produces_report(
        self,
        runner: TestRunner,
    ) -> None:
        """Smoke run should produce a valid report with results."""
        report = await runner.run_suite(tier=TestTier.SMOKE)

        assert report is not None
        assert report.report_id
        assert report.tier == TestTier.SMOKE
        assert report.total_cases >= 0
        assert report.duration_s >= 0


class TestReportGeneration:
    """Validate HTML report rendering."""

    @pytest.mark.asyncio
    async def test_html_report_renders(
        self,
        config_manager: ConfigManager,
        session_manager: SessionManager,
        validator: ResultValidator,
    ) -> None:
        """HTML report should render from a smoke run without errors."""
        runner = TestRunner(config_manager, session_manager, validator)
        report = await runner.run_suite(tier=TestTier.SMOKE)

        gen = ReportGenerator()
        html = gen.render(report)

        assert html
        assert "TC8" in html
        assert report.report_id in html

    @pytest.mark.asyncio
    async def test_html_report_saves_to_file(
        self,
        config_manager: ConfigManager,
        session_manager: SessionManager,
        validator: ResultValidator,
    ) -> None:
        """Report should save to disk as an HTML file."""
        runner = TestRunner(config_manager, session_manager, validator)
        report = await runner.run_suite(tier=TestTier.SMOKE)

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test_report.html"
            gen = ReportGenerator()
            result_path = gen.save(report, out)

            assert result_path.exists()
            assert result_path.stat().st_size > 100
            content = result_path.read_text(encoding="utf-8")
            assert "TC8" in content
