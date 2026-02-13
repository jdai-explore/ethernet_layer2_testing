"""
FastAPI backend for TC8 L2 Test Framework web UI.

Provides REST API and WebSocket endpoints for:
- Test suite execution and monitoring
- DUT profile management
- Spec browsing
- Report access and history
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager
from src.core.test_runner import TestRunner
from src.models.test_case import TestSection, TestStatus, TestTier
from src.reporting.report_generator import ReportGenerator
from src.reporting.result_store import ResultStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TC8 Layer 2 Test Framework",
    description="OPEN Alliance TC8 Automotive Ethernet ECU Conformance Testing",
    version="2.0.0",
)

# Global state
config = ConfigManager()
active_runner: TestRunner | None = None
connected_websockets: list[WebSocket] = []
result_store = ResultStore()
report_gen = ReportGenerator()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class RunSuiteRequest(BaseModel):
    dut_profile_path: str
    tier: str = "smoke"
    sections: list[str] | None = None
    spec_ids: list[str] | None = None


class RunSuiteResponse(BaseModel):
    report_id: str
    total_cases: int
    passed: int
    failed: int
    informational: int
    skipped: int
    errors: int
    duration_s: float
    pass_rate: float


class SpecListResponse(BaseModel):
    specs: list[dict[str, Any]]
    total: int


# ---------------------------------------------------------------------------
# REST API Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "tc8-l2-test-framework", "version": "2.0.0"}


@app.get("/api/specs", response_model=SpecListResponse)
async def list_specs(section: str | None = None) -> SpecListResponse:
    """List all available TC8 test specifications."""
    config.load_spec_definitions()
    specs = list(config.spec_definitions.values())

    section_map = {
        "5.3": TestSection.VLAN,
        "5.4": TestSection.GENERAL,
        "5.5": TestSection.ADDRESS_LEARNING,
        "5.6": TestSection.FILTERING,
        "5.7": TestSection.TIME_SYNC,
        "5.8": TestSection.QOS,
        "5.9": TestSection.CONFIGURATION,
    }

    if section and section in section_map:
        specs = [s for s in specs if s.section == section_map[section]]

    spec_dicts = [
        {
            "spec_id": s.spec_id,
            "tc8_reference": s.tc8_reference,
            "section": s.section.value,
            "title": s.title,
            "description": s.description,
            "priority": s.priority,
        }
        for s in specs
    ]

    return SpecListResponse(specs=spec_dicts, total=len(spec_dicts))


@app.post("/api/run", response_model=RunSuiteResponse)
async def run_suite(request: RunSuiteRequest) -> RunSuiteResponse:
    """Execute a test suite."""
    global active_runner

    # Load DUT profile
    try:
        dut_profile = config.load_dut_profile(request.dut_profile_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid DUT profile: {e}")

    config.load_spec_definitions()

    # Parse sections
    section_map = {
        "5.3": TestSection.VLAN,
        "5.4": TestSection.GENERAL,
        "5.5": TestSection.ADDRESS_LEARNING,
        "5.6": TestSection.FILTERING,
        "5.7": TestSection.TIME_SYNC,
        "5.8": TestSection.QOS,
        "5.9": TestSection.CONFIGURATION,
    }
    sections = None
    if request.sections:
        sections = [section_map[s] for s in request.sections if s in section_map]

    # Setup runner
    session_mgr = SessionManager(dut_profile)
    validator = ResultValidator()

    async def ws_progress(current: int, total: int, case_id: str, status: TestStatus | None) -> None:
        msg = {
            "type": "progress",
            "current": current,
            "total": total,
            "case_id": case_id,
            "status": status.value if status else "running",
        }
        for ws in connected_websockets:
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    active_runner = TestRunner(config, session_mgr, validator)
    tier = TestTier(request.tier)
    report = await active_runner.run_suite(tier, sections, request.spec_ids)
    active_runner = None

    # Persist to database
    try:
        result_store.save_report(report)
    except Exception as exc:
        logger.warning("Failed to persist report: %s", exc)

    # Generate HTML report file
    try:
        report_gen.save(report, f"reports/{report.report_id}.html")
    except Exception as exc:
        logger.warning("Failed to generate HTML report: %s", exc)

    return RunSuiteResponse(
        report_id=report.report_id,
        total_cases=report.total_cases,
        passed=report.passed,
        failed=report.failed,
        informational=report.informational,
        skipped=report.skipped,
        errors=report.errors,
        duration_s=report.duration_s,
        pass_rate=report.pass_rate,
    )


@app.post("/api/cancel")
async def cancel_run() -> dict[str, str]:
    """Cancel the currently running test suite."""
    if active_runner and active_runner.is_running:
        active_runner.cancel()
        return {"status": "cancellation_requested"}
    return {"status": "no_active_run"}


@app.get("/api/dut-profiles")
async def list_dut_profiles() -> dict[str, Any]:
    """List available DUT profiles."""
    profiles_dir = config.config_dir / "dut_profiles"
    profiles = []
    if profiles_dir.exists():
        for f in profiles_dir.glob("*.yaml"):
            profiles.append({"name": f.stem, "path": str(f)})
    return {"profiles": profiles}


# ---------------------------------------------------------------------------
# Report History & Detail Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/reports")
async def list_reports(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """List stored test reports, newest first."""
    runs = result_store.list_runs(limit=limit, offset=offset)
    total = result_store.count_runs()
    return {"reports": runs, "total": total, "limit": limit, "offset": offset}


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str) -> dict[str, Any]:
    """Get full report detail with all results."""
    run = result_store.get_run(report_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    return run


@app.get("/api/reports/{report_id}/html", response_class=HTMLResponse)
async def get_report_html(report_id: str) -> str:
    """Serve the rendered HTML report."""
    html_path = Path(f"reports/{report_id}.html")
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail=f"HTML report for '{report_id}' not found")


@app.get("/api/trend/{spec_id}")
async def get_trend(spec_id: str, last_n: int = 10) -> dict[str, Any]:
    """Get pass/fail trend for a specific spec across recent runs."""
    trend = result_store.get_trend(spec_id, last_n=last_n)
    return {"spec_id": spec_id, "trend": trend}


# ---------------------------------------------------------------------------
# WebSocket for real-time progress
# ---------------------------------------------------------------------------


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time test progress updates."""
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)


# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------

# Mount static files if directory exists
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve the main web UI dashboard."""
    # Load dynamic data
    config.load_spec_definitions()
    spec_count = len(config.spec_definitions)
    run_count = result_store.count_runs()
    recent_runs = result_store.list_runs(limit=5)

    # Build run history rows
    run_rows = ""
    for r in recent_runs:
        rate_color = "#22c55e" if r["pass_rate"] >= 80 else "#f59e0b" if r["pass_rate"] >= 50 else "#ef4444"
        run_rows += f"""
        <tr>
            <td><a href="/api/reports/{r['report_id']}/html" style="color:#60a5fa">{r['report_id'][:12]}…</a></td>
            <td>{r['dut_name']}</td>
            <td><span class="badge">{r['tier']}</span></td>
            <td>{r['passed']}</td>
            <td>{r['failed']}</td>
            <td style="color:{rate_color};font-weight:600">{r['pass_rate']:.1f}%</td>
            <td>{r['created_at'][:19] if r['created_at'] else '—'}</td>
        </tr>"""

    no_runs_msg = '<tr><td colspan="7" style="text-align:center;color:#64748b">No test runs yet. Use the CLI or API to run tests.</td></tr>' if not recent_runs else ""

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TC8 L2 Test Framework</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Inter', system-ui, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                min-height: 100vh;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
            h1 {{
                font-size: 1.75rem; font-weight: 700;
                background: linear-gradient(135deg, #60a5fa, #a78bfa);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                margin-bottom: 0.25rem;
            }}
            .subtitle {{ color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }}

            /* Cards */
            .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; margin-bottom: 1.5rem; }}
            .card {{
                background: #1e293b; border: 1px solid #334155; border-radius: 10px;
                padding: 1.25rem; text-align: center;
            }}
            .card .value {{ font-size: 2rem; font-weight: 700; }}
            .card .label {{
                font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
                color: #94a3b8; margin-top: 0.25rem;
            }}
            .card.primary .value {{ color: #60a5fa; }}
            .card.green .value {{ color: #22c55e; }}
            .card.amber .value {{ color: #f59e0b; }}

            /* Sections */
            .section-grid {{
                display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 0.75rem; margin-bottom: 1.5rem;
            }}
            .section-chip {{
                background: #1e293b; border: 1px solid #334155; border-radius: 8px;
                padding: 0.75rem 1rem; display: flex; justify-content: space-between;
                align-items: center; font-size: 0.85rem;
            }}
            .section-chip .count {{
                background: #334155; padding: 0.15rem 0.5rem; border-radius: 999px;
                font-size: 0.75rem; font-weight: 600;
            }}

            /* Table */
            .panel {{
                background: #1e293b; border: 1px solid #334155; border-radius: 10px;
                padding: 1.25rem; margin-bottom: 1.5rem;
            }}
            .panel h2 {{ font-size: 1rem; font-weight: 600; color: #60a5fa; margin-bottom: 1rem; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
            th {{
                text-align: left; padding: 0.5rem 0.75rem; border-bottom: 2px solid #334155;
                color: #94a3b8; font-weight: 600; font-size: 0.7rem; text-transform: uppercase;
                letter-spacing: 0.04em;
            }}
            td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b; }}
            tr:hover td {{ background: rgba(255,255,255,0.02); }}
            a {{ text-decoration: none; }}
            .badge {{
                display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
                font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
                background: #334155; color: #e2e8f0;
            }}

            /* Links */
            .links {{ display: flex; gap: 1rem; margin-top: 0.5rem; font-size: 0.85rem; }}
            .links a {{ color: #60a5fa; }}
            .links a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ TC8 Layer 2 Test Framework</h1>
            <p class="subtitle">OPEN Alliance Automotive Ethernet ECU Conformance Testing — v2.0</p>

            <div class="cards">
                <div class="card primary">
                    <div class="value">{spec_count}</div>
                    <div class="label">Specifications</div>
                </div>
                <div class="card green">
                    <div class="value">7</div>
                    <div class="label">TC8 Sections</div>
                </div>
                <div class="card amber">
                    <div class="value">{run_count}</div>
                    <div class="label">Test Runs</div>
                </div>
                <div class="card primary">
                    <div class="value">3</div>
                    <div class="label">Tiers</div>
                </div>
            </div>

            <div class="section-grid">
                <div class="section-chip">5.3 VLAN Testing <span class="count">21</span></div>
                <div class="section-chip">5.4 General <span class="count">10</span></div>
                <div class="section-chip">5.5 Address Learning <span class="count">21</span></div>
                <div class="section-chip">5.6 Filtering <span class="count">11</span></div>
                <div class="section-chip">5.7 Time Sync <span class="count">1</span></div>
                <div class="section-chip">5.8 QoS <span class="count">4</span></div>
                <div class="section-chip">5.9 Configuration <span class="count">3</span></div>
            </div>

            <div class="panel">
                <h2>📊 Recent Test Runs</h2>
                <table>
                    <thead>
                        <tr><th>Report</th><th>DUT</th><th>Tier</th><th>Pass</th><th>Fail</th><th>Rate</th><th>Date</th></tr>
                    </thead>
                    <tbody>
                        {run_rows}{no_runs_msg}
                    </tbody>
                </table>
            </div>

            <div class="panel">
                <h2>🔧 Quick Start</h2>
                <ol style="padding-left:1.5rem;line-height:2;font-size:0.85rem">
                    <li>Create a DUT profile in <code style="color:#a78bfa">config/dut_profiles/</code></li>
                    <li>Run: <code style="color:#a78bfa">python -m src.cli run --dut path/to/profile.yaml --tier smoke</code></li>
                    <li>View reports in <code style="color:#a78bfa">reports/</code> or at <code style="color:#a78bfa">/api/reports</code></li>
                </ol>
                <div class="links">
                    <a href="/docs">📖 API Docs</a>
                    <a href="/api/specs">📋 All Specs</a>
                    <a href="/api/reports">📊 All Reports</a>
                    <a href="/api/health">💚 Health Check</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
