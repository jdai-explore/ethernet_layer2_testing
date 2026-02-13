"""
FastAPI backend for TC8 L2 Test Framework web UI.

Provides REST API and WebSocket endpoints for:
- Test suite execution and monitoring
- DUT profile management
- Spec browsing
- Report access
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TC8 Layer 2 Test Framework",
    description="OPEN Alliance TC8 Automotive Ethernet ECU Conformance Testing",
    version="0.1.0",
)

# Global state
config = ConfigManager()
active_runner: TestRunner | None = None
connected_websockets: list[WebSocket] = []


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
    return {"status": "ok", "service": "tc8-l2-test-framework"}


@app.get("/api/specs", response_model=SpecListResponse)
async def list_specs(section: str | None = None) -> SpecListResponse:
    """List all available TC8 test specifications."""
    config.load_spec_definitions()
    specs = list(config.spec_definitions.values())

    if section:
        section_map = {
            "5.3": TestSection.VLAN,
            "5.4": TestSection.GENERAL,
            "5.5": TestSection.ADDRESS_LEARNING,
            "5.6": TestSection.FILTERING,
            "5.7": TestSection.TIME_SYNC,
            "5.8": TestSection.QOS,
            "5.9": TestSection.CONFIGURATION,
        }
        if section in section_map:
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
    """Serve the main web UI page."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TC8 L2 Test Framework</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Inter', system-ui, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                min-height: 100vh;
            }
            .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
            h1 { 
                font-size: 2rem;
                background: linear-gradient(135deg, #60a5fa, #a78bfa);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
            }
            .subtitle { color: #94a3b8; margin-bottom: 2rem; }
            .card {
                background: #1e293b;
                border-radius: 12px;
                padding: 1.5rem;
                margin-bottom: 1rem;
                border: 1px solid #334155;
            }
            .card h2 { font-size: 1.2rem; color: #60a5fa; margin-bottom: 1rem; }
            .status { padding: 0.5rem 1rem; border-radius: 8px; background: #334155; }
            .badge {
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 999px;
                font-size: 0.875rem;
                font-weight: 500;
            }
            .badge-pass { background: #065f46; color: #34d399; }
            .badge-fail { background: #7f1d1d; color: #fca5a5; }
            .badge-info { background: #713f12; color: #fde68a; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ TC8 Layer 2 Test Framework</h1>
            <p class="subtitle">OPEN Alliance Automotive Ethernet ECU Conformance Testing</p>
            
            <div class="card">
                <h2>📊 Dashboard</h2>
                <p>API available at <code>/docs</code> for interactive testing.</p>
                <p style="margin-top: 0.5rem;">
                    <a href="/docs" style="color: #60a5fa;">Open API Documentation →</a>
                </p>
            </div>
            
            <div class="card">
                <h2>🔧 Quick Start</h2>
                <ol style="padding-left: 1.5rem; line-height: 2;">
                    <li>Create a DUT profile in <code>config/dut_profiles/</code></li>
                    <li>Run: <code>tc8-run run --dut path/to/profile.yaml --tier smoke</code></li>
                    <li>View results in <code>reports/</code></li>
                </ol>
            </div>
            
            <div class="card">
                <h2>📋 Test Sections</h2>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; margin-top: 0.5rem;">
                    <div class="status">5.3 VLAN Testing (21)</div>
                    <div class="status">5.4 General (10)</div>
                    <div class="status">5.5 Address Learning (21)</div>
                    <div class="status">5.6 Filtering (11)</div>
                    <div class="status">5.7 Time Sync (1)</div>
                    <div class="status">5.8 QoS (4)</div>
                    <div class="status">5.9 Configuration (3)</div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
