"""
FastAPI backend for TC8 L2 Test Framework web UI.

Provides REST API and WebSocket endpoints for:
- Test suite execution and monitoring
- DUT profile management
- Spec browsing
- Report access and history
- Pre-flight self-validation
- Real-time log streaming
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import traceback
from collections import deque
from pathlib import Path
from typing import Any

import psutil

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager, NullDUTController
from src.core.test_runner import TestRunner
from src.models.test_case import (
    DUTProfile,
    PortConfig,
    TestSection,
    TestStatus,
    TestTier,
)
from src.reporting.report_generator import ReportGenerator
from src.reporting.result_store import ResultStore
from src.specs.spec_registry import SpecRegistry
from src.utils.frame_builder import FrameBuilder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TC8 Layer 2 Test Framework",
    description="OPEN Alliance TC8 Automotive Ethernet ECU Conformance Testing",
    version="3.0.0",
)

# Global state
config = ConfigManager()
active_runner: TestRunner | None = None
connected_websockets: list[WebSocket] = []
log_websockets: list[WebSocket] = []
result_store = ResultStore()
report_gen = ReportGenerator()

# Log buffer for late-connecting clients
log_buffer: deque[dict] = deque(maxlen=200)


# ---------------------------------------------------------------------------
# WebSocket Log Handler
# ---------------------------------------------------------------------------


class WebSocketLogHandler(logging.Handler):
    """Forward Python log records to connected WebSocket clients."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "type": "log",
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
                "time": record.created,
            }
            log_buffer.append(entry)
            for ws in list(log_websockets):
                try:
                    asyncio.get_event_loop().create_task(ws.send_json(entry))
                except Exception:
                    pass
        except Exception:
            pass


# Install the log handler on the root logger
_ws_handler = WebSocketLogHandler()
_ws_handler.setLevel(logging.DEBUG)
_ws_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
logging.getLogger().addHandler(_ws_handler)
logging.getLogger().setLevel(logging.DEBUG)


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


class DUTProfileRequest(BaseModel):
    """Form data for creating/updating a DUT profile."""
    dut_name: str
    model: str = ""
    firmware: str = "unknown"
    port_count: int = 4
    mac_table_size: int = 1024
    mac_aging_time: int = 300
    double_tagging: bool = False
    gptp: bool = False
    can_reset: bool = False
    ports: list[dict[str, Any]] | None = None


class PreflightResult(BaseModel):
    name: str
    status: str  # "pass" or "fail"
    detail: str


# ---------------------------------------------------------------------------
# Section Map (shared)
# ---------------------------------------------------------------------------

SECTION_MAP = {
    "5.3": TestSection.VLAN,
    "5.4": TestSection.GENERAL,
    "5.5": TestSection.ADDRESS_LEARNING,
    "5.6": TestSection.FILTERING,
    "5.7": TestSection.TIME_SYNC,
    "5.8": TestSection.QOS,
    "5.9": TestSection.CONFIGURATION,
}


# ---------------------------------------------------------------------------
# REST API Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "tc8-l2-test-framework", "version": "3.0.0"}


@app.get("/api/specs", response_model=SpecListResponse)
async def list_specs(section: str | None = None) -> SpecListResponse:
    """List all available TC8 test specifications."""
    config.load_spec_definitions()
    specs = list(config.spec_definitions.values())

    if section and section in SECTION_MAP:
        specs = [s for s in specs if s.section == SECTION_MAP[section]]

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
    sections = None
    if request.sections:
        sections = [SECTION_MAP[s] for s in request.sections if s in SECTION_MAP]

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


# ---------------------------------------------------------------------------
# DUT Profile Management
# ---------------------------------------------------------------------------


@app.get("/api/dut-profiles")
async def list_dut_profiles() -> dict[str, Any]:
    """List available DUT profiles."""
    profiles_dir = config.config_dir / "dut_profiles"
    profiles = []
    if profiles_dir.exists():
        for f in sorted(profiles_dir.rglob("*.yaml")):
            profiles.append({"name": f.stem, "path": str(f.relative_to(config.config_dir / "dut_profiles"))})
    return {"profiles": profiles}


@app.get("/api/dut-profiles/{name}")
async def get_dut_profile(name: str) -> dict[str, Any]:
    """Load full details of a specific DUT profile."""
    profiles_dir = config.config_dir / "dut_profiles"
    # Search recursively
    matches = list(profiles_dir.rglob(f"{name}.yaml"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    profile_path = matches[0]
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        return {"name": name, "path": str(profile_path), "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read profile: {e}")


@app.post("/api/dut-profiles")
async def create_dut_profile(request: DUTProfileRequest) -> dict[str, Any]:
    """Create a new DUT profile from form data and save as YAML."""
    profiles_dir = config.config_dir / "dut_profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    # Build port configs
    ports_data = []
    if request.ports:
        for p in request.ports:
            ports_data.append(p)
    else:
        for i in range(request.port_count):
            ports_data.append({
                "port_id": i,
                "interface_name": f"eth{i}",
                "mac_address": f"02:00:00:00:00:{i + 1:02x}",
                "speed_mbps": 100,
                "vlan_membership": [1],
                "pvid": 1,
                "is_trunk": False,
            })

    profile_data = {
        "name": request.dut_name,
        "model": request.model,
        "firmware_version": request.firmware,
        "port_count": request.port_count,
        "ports": ports_data,
        "max_mac_table_size": request.mac_table_size,
        "mac_aging_time_s": request.mac_aging_time,
        "supports_double_tagging": request.double_tagging,
        "supports_gptp": request.gptp,
        "can_reset": request.can_reset,
    }

    # Save YAML
    safe_name = request.dut_name.lower().replace(" ", "_").replace("-", "_")
    output_path = profiles_dir / f"{safe_name}.yaml"
    output_path.write_text(yaml.dump(profile_data, default_flow_style=False, sort_keys=False), encoding="utf-8")

    logger.info("Created DUT profile: %s → %s", request.dut_name, output_path)
    return {"status": "created", "name": safe_name, "path": str(output_path)}


@app.put("/api/dut-profiles/{name}")
async def update_dut_profile(name: str, request: DUTProfileRequest) -> dict[str, Any]:
    """Update an existing DUT profile."""
    profiles_dir = config.config_dir / "dut_profiles"
    matches = list(profiles_dir.rglob(f"{name}.yaml"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    profile_path = matches[0]

    # Build updated data
    ports_data = []
    if request.ports:
        for p in request.ports:
            ports_data.append(p)
    else:
        for i in range(request.port_count):
            ports_data.append({
                "port_id": i,
                "interface_name": f"eth{i}",
                "mac_address": f"02:00:00:00:00:{i + 1:02x}",
                "speed_mbps": 100,
                "vlan_membership": [1],
                "pvid": 1,
                "is_trunk": False,
            })

    profile_data = {
        "name": request.dut_name,
        "model": request.model,
        "firmware_version": request.firmware,
        "port_count": request.port_count,
        "ports": ports_data,
        "max_mac_table_size": request.mac_table_size,
        "mac_aging_time_s": request.mac_aging_time,
        "supports_double_tagging": request.double_tagging,
        "supports_gptp": request.gptp,
        "can_reset": request.can_reset,
    }

    profile_path.write_text(yaml.dump(profile_data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    logger.info("Updated DUT profile: %s", name)
    return {"status": "updated", "name": name, "path": str(profile_path)}


# ---------------------------------------------------------------------------
# Pre-flight Checks
# ---------------------------------------------------------------------------


@app.post("/api/preflight")
async def run_preflight() -> dict[str, Any]:
    """Run framework self-validation checks."""
    checks: list[dict[str, str]] = []

    # 1. Spec Registry
    try:
        config.load_spec_definitions()
        count = len(config.spec_definitions)
        if count >= 71:
            checks.append({"name": "Spec Registry", "status": "pass", "detail": f"{count} specs loaded"})
        else:
            checks.append({"name": "Spec Registry", "status": "fail", "detail": f"Only {count}/71 specs found"})
    except Exception as e:
        checks.append({"name": "Spec Registry", "status": "fail", "detail": str(e)})

    # 2. Frame Builder
    try:
        fb = FrameBuilder()
        frame = fb.untagged_unicast(payload_size=64)
        tagged = fb.single_tagged(vid=100, payload_size=64)
        if frame is not None and tagged is not None:
            checks.append({"name": "Frame Builder", "status": "pass", "detail": f"Untagged ({len(frame)}B) + Tagged ({len(tagged)}B) OK"})
        else:
            checks.append({"name": "Frame Builder", "status": "fail", "detail": "Frame construction returned None"})
    except Exception as e:
        checks.append({"name": "Frame Builder", "status": "fail", "detail": str(e)})

    # 3. Config Validation
    try:
        test_profile = DUTProfile(
            name="Preflight-Test",
            model="SIM",
            port_count=4,
            ports=[
                PortConfig(port_id=i, interface_name=f"eth{i}", mac_address=f"02:00:00:00:00:{i:02x}", vlan_membership=[1])
                for i in range(4)
            ],
        )
        checks.append({"name": "Config Validation", "status": "pass", "detail": f"DUTProfile created: {test_profile.name}"})
    except Exception as e:
        checks.append({"name": "Config Validation", "status": "fail", "detail": str(e)})

    # 4. Database Connectivity
    try:
        count = result_store.count_runs()
        checks.append({"name": "Database", "status": "pass", "detail": f"Connected, {count} runs stored"})
    except Exception as e:
        checks.append({"name": "Database", "status": "fail", "detail": str(e)})

    # 5. Session Manager
    try:
        sm = SessionManager(
            dut_profile=test_profile,
            controller=NullDUTController(),
            cleanup_wait_s=0.0,
            aging_wait_s=0.0,
        )
        state = await sm.setup()
        if state.is_clean:
            checks.append({"name": "Session Manager", "status": "pass", "detail": f"Session {state.session_id} clean"})
        else:
            checks.append({"name": "Session Manager", "status": "fail", "detail": "Session not clean"})
    except Exception as e:
        checks.append({"name": "Session Manager", "status": "fail", "detail": str(e)})

    # 6. Report Generator
    try:
        rg = ReportGenerator()
        checks.append({"name": "Report Generator", "status": "pass", "detail": "Template engine ready"})
    except Exception as e:
        checks.append({"name": "Report Generator", "status": "fail", "detail": str(e)})

    # 7. DUT Profiles Directory
    try:
        profiles_dir = config.config_dir / "dut_profiles"
        count = len(list(profiles_dir.rglob("*.yaml"))) if profiles_dir.exists() else 0
        checks.append({"name": "DUT Profiles", "status": "pass" if count > 0 else "fail", "detail": f"{count} profiles found"})
    except Exception as e:
        checks.append({"name": "DUT Profiles", "status": "fail", "detail": str(e)})

    passed = sum(1 for c in checks if c["status"] == "pass")
    total = len(checks)
    return {"checks": checks, "passed": passed, "total": total}


# ---------------------------------------------------------------------------
# Interface Discovery & Topology
# ---------------------------------------------------------------------------


_SKIP_INTERFACE_PREFIXES = (
    "Loopback", "vEthernet", "Local Area Connection*", "isatap",
    "Teredo", "6to4", "Bluetooth", "VMware", "VirtualBox",
    "Hyper-V", "WSL", "Docker", "br-", "veth",
)


def _get_os_interfaces() -> list[dict[str, Any]]:
    """Detect physical network interfaces on the test station."""
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    results = []
    for name in sorted(stats.keys()):
        # Skip virtual / non-physical interfaces
        if any(name.startswith(p) for p in _SKIP_INTERFACE_PREFIXES):
            continue
        info = stats[name]
        mac = ""
        ipv4 = ""
        for a in addrs.get(name, []):
            if a.family == psutil.AF_LINK:
                mac = a.address.replace("-", ":")
            elif a.family == socket.AF_INET:
                ipv4 = a.address
        results.append({
            "name": name,
            "mac": mac,
            "ipv4": ipv4,
            "is_up": info.isup,
            "speed_mbps": info.speed,
            "mtu": info.mtu,
        })
    return results


@app.get("/api/interfaces")
async def list_interfaces() -> dict[str, Any]:
    """Auto-detect network interfaces on the test station."""
    ifaces = _get_os_interfaces()
    return {"interfaces": ifaces, "count": len(ifaces)}


@app.get("/api/topology")
async def get_topology() -> dict[str, Any]:
    """Return topology: DUT ports, station interfaces, mappings, and mode."""
    station_ifaces = _get_os_interfaces()
    station_names = {iface["name"] for iface in station_ifaces}
    station_up = {iface["name"] for iface in station_ifaces if iface["is_up"]}

    # Try to load the DUT profile from config
    dut_ports: list[dict[str, Any]] = []
    dut_name = "No DUT Loaded"
    mappings: list[dict[str, Any]] = []
    mode = "simulation"
    active_links = 0

    if config.dut_profile:
        dut_name = config.dut_profile.name
        for port in config.dut_profile.ports:
            iface_name = port.interface_name
            is_mapped = iface_name in station_names
            is_up = iface_name in station_up if is_mapped else False
            if is_up:
                active_links += 1
            dut_ports.append({
                "port_id": port.port_id,
                "interface_name": iface_name,
                "mac": port.mac_address,
                "speed_mbps": port.speed_mbps,
                "vlans": port.vlan_membership,
                "pvid": port.pvid,
                "is_trunk": port.is_trunk,
                "is_mapped": is_mapped,
                "is_up": is_up,
            })
            mappings.append({
                "dut_port": port.port_id,
                "station_iface": iface_name,
                "status": "up" if is_up else ("down" if is_mapped else "unmapped"),
            })

        if active_links > 0:
            mode = "actual"

    return {
        "dut_name": dut_name,
        "dut_ports": dut_ports,
        "station_interfaces": station_ifaces,
        "mappings": mappings,
        "mode": mode,
        "active_links": active_links,
        "total_ports": len(dut_ports),
    }


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


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    log_websockets.append(websocket)
    # Send buffered logs to new client
    for entry in list(log_buffer):
        try:
            await websocket.send_json(entry)
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in log_websockets:
            log_websockets.remove(websocket)


# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------

# Mount static files if directory exists
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve the main web UI dashboard with tabbed interface."""
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

    no_runs_msg = '<tr><td colspan="7" style="text-align:center;color:#64748b">No test runs yet. Use the Run Tests tab or CLI to start.</td></tr>' if not recent_runs else ""

    # Load DUT profiles for dropdowns
    profiles_dir = config.config_dir / "dut_profiles"
    profiles_json = "[]"
    if profiles_dir.exists():
        profiles = [{"name": f.stem, "path": str(f.relative_to(config.config_dir / "dut_profiles"))} for f in sorted(profiles_dir.rglob("*.yaml"))]
        profiles_json = json.dumps(profiles)

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TC8 L2 Test Framework</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Inter', system-ui, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                min-height: 100vh;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem 2rem; }}
            h1 {{
                font-size: 1.5rem; font-weight: 700;
                background: linear-gradient(135deg, #60a5fa, #a78bfa);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                margin-bottom: 0.15rem;
            }}
            .subtitle {{ color: #94a3b8; margin-bottom: 1rem; font-size: 0.82rem; }}

            /* ── Tabs ── */
            .tab-bar {{
                display: flex; gap: 0; border-bottom: 2px solid #334155;
                margin-bottom: 1.25rem;
            }}
            .tab-btn {{
                padding: 0.6rem 1.2rem; font-size: 0.8rem; font-weight: 600;
                color: #94a3b8; background: none; border: none; cursor: pointer;
                border-bottom: 2px solid transparent; margin-bottom: -2px;
                transition: color 0.2s, border-color 0.2s; white-space: nowrap;
                font-family: inherit;
            }}
            .tab-btn:hover {{ color: #e2e8f0; }}
            .tab-btn.active {{ color: #60a5fa; border-bottom-color: #60a5fa; }}
            .tab-content {{ display: none; animation: fadeIn 0.25s ease; }}
            .tab-content.active {{ display: block; }}
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: translateY(0); }} }}

            /* ── Cards ── */
            .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem; }}
            .card {{
                background: #1e293b; border: 1px solid #334155; border-radius: 10px;
                padding: 1.1rem; text-align: center;
            }}
            .card .value {{ font-size: 1.8rem; font-weight: 700; }}
            .card .label {{
                font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em;
                color: #94a3b8; margin-top: 0.2rem;
            }}
            .card.primary .value {{ color: #60a5fa; }}
            .card.green .value {{ color: #22c55e; }}
            .card.amber .value {{ color: #f59e0b; }}

            /* ── Section Chips ── */
            .section-grid {{
                display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
                gap: 0.6rem; margin-bottom: 1.25rem;
            }}
            .section-chip {{
                background: #1e293b; border: 1px solid #334155; border-radius: 8px;
                padding: 0.6rem 0.8rem; display: flex; justify-content: space-between;
                align-items: center; font-size: 0.82rem;
            }}
            .section-chip .count {{
                background: #334155; padding: 0.1rem 0.45rem; border-radius: 999px;
                font-size: 0.72rem; font-weight: 600;
            }}

            /* ── Panel ── */
            .panel {{
                background: #1e293b; border: 1px solid #334155; border-radius: 10px;
                padding: 1.25rem; margin-bottom: 1rem;
            }}
            .panel h2 {{ font-size: 0.95rem; font-weight: 600; color: #60a5fa; margin-bottom: 0.8rem; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
            th {{
                text-align: left; padding: 0.45rem 0.6rem; border-bottom: 2px solid #334155;
                color: #94a3b8; font-weight: 600; font-size: 0.68rem; text-transform: uppercase;
                letter-spacing: 0.04em;
            }}
            td {{ padding: 0.45rem 0.6rem; border-bottom: 1px solid #1e293b; }}
            tr:hover td {{ background: rgba(255,255,255,0.02); }}
            a {{ text-decoration: none; }}
            .badge {{
                display: inline-block; padding: 0.12rem 0.45rem; border-radius: 4px;
                font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
                background: #334155; color: #e2e8f0;
            }}

            /* ── Forms ── */
            .form-grid {{
                display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem;
            }}
            .form-group {{ display: flex; flex-direction: column; gap: 0.3rem; }}
            .form-group.full {{ grid-column: 1 / -1; }}
            label {{
                font-size: 0.72rem; font-weight: 600; color: #94a3b8;
                text-transform: uppercase; letter-spacing: 0.04em;
            }}
            input[type="text"], input[type="number"], select {{
                background: #0f172a; border: 1px solid #334155; border-radius: 6px;
                padding: 0.55rem 0.7rem; color: #e2e8f0; font-size: 0.82rem;
                font-family: inherit; outline: none;
                transition: border-color 0.2s;
            }}
            input:focus, select:focus {{ border-color: #60a5fa; }}
            .toggle-row {{
                display: flex; align-items: center; gap: 0.6rem;
                font-size: 0.82rem; padding: 0.2rem 0;
            }}
            input[type="checkbox"] {{
                width: 16px; height: 16px; accent-color: #60a5fa; cursor: pointer;
            }}

            /* ── Buttons ── */
            .btn {{
                display: inline-flex; align-items: center; gap: 0.4rem;
                padding: 0.55rem 1.2rem; border: none; border-radius: 8px;
                font-size: 0.82rem; font-weight: 600; cursor: pointer;
                font-family: inherit; transition: all 0.2s;
            }}
            .btn-primary {{ background: #3b82f6; color: #fff; }}
            .btn-primary:hover {{ background: #2563eb; }}
            .btn-success {{ background: #22c55e; color: #fff; }}
            .btn-success:hover {{ background: #16a34a; }}
            .btn-danger {{ background: #ef4444; color: #fff; }}
            .btn-danger:hover {{ background: #dc2626; }}
            .btn-ghost {{
                background: transparent; border: 1px solid #334155; color: #94a3b8;
            }}
            .btn-ghost:hover {{ border-color: #60a5fa; color: #60a5fa; }}
            .btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
            .btn-row {{ display: flex; gap: 0.6rem; margin-top: 0.8rem; }}

            /* ── Checklist ── */
            .check-item {{
                display: flex; align-items: center; gap: 0.6rem;
                padding: 0.55rem 0.7rem; border-bottom: 1px solid #1e293b;
                font-size: 0.82rem;
            }}
            .check-icon {{ font-size: 1.1rem; width: 1.4rem; text-align: center; }}
            .check-detail {{ color: #94a3b8; font-size: 0.75rem; margin-left: auto; }}
            .check-item.pending .check-icon {{ color: #94a3b8; }}
            .check-item.pass .check-icon {{ color: #22c55e; }}
            .check-item.fail .check-icon {{ color: #ef4444; }}

            /* ── Progress ── */
            .progress-container {{ margin: 1rem 0; }}
            .progress-bar-bg {{
                background: #0f172a; border-radius: 999px; height: 8px;
                overflow: hidden; margin-bottom: 0.3rem;
            }}
            .progress-bar-fill {{
                height: 100%; border-radius: 999px;
                background: linear-gradient(90deg, #3b82f6, #a78bfa);
                transition: width 0.3s ease; width: 0%;
            }}
            .progress-text {{ font-size: 0.75rem; color: #94a3b8; }}

            /* ── Console ── */
            .console {{
                background: #020617; border: 1px solid #1e293b; border-radius: 8px;
                padding: 0.7rem; height: 420px; overflow-y: auto;
                font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
                line-height: 1.6;
            }}
            .console .log-line {{ white-space: pre-wrap; word-break: break-all; }}
            .console .log-DEBUG {{ color: #64748b; }}
            .console .log-INFO {{ color: #94a3b8; }}
            .console .log-WARNING {{ color: #f59e0b; }}
            .console .log-ERROR {{ color: #ef4444; }}
            .console .log-CRITICAL {{ color: #ef4444; font-weight: 700; }}
            .console-toolbar {{
                display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.6rem;
            }}
            .console-toolbar select {{
                padding: 0.3rem 0.6rem; font-size: 0.75rem;
            }}
            .ws-dot {{
                width: 8px; height: 8px; border-radius: 50%;
                display: inline-block; margin-right: 0.3rem;
            }}
            .ws-dot.connected {{ background: #22c55e; }}
            .ws-dot.disconnected {{ background: #ef4444; }}

            /* ── Links ── */
            .links {{ display: flex; gap: 0.8rem; margin-top: 0.4rem; font-size: 0.82rem; }}
            .links a {{ color: #60a5fa; }}
            .links a:hover {{ text-decoration: underline; }}

            /* ── Status Badge ── */
            .status-msg {{
                padding: 0.6rem 0.8rem; border-radius: 8px; font-size: 0.8rem;
                margin-top: 0.6rem; display: none;
            }}
            .status-msg.success {{ display: block; background: rgba(34,197,94,0.1); border: 1px solid #22c55e; color: #22c55e; }}
            .status-msg.error {{ display: block; background: rgba(239,68,68,0.1); border: 1px solid #ef4444; color: #ef4444; }}

            /* ── Mode Badge ── */
            .mode-badge {{
                display: inline-flex; align-items: center; gap: 0.4rem;
                padding: 0.3rem 0.75rem; border-radius: 999px; font-size: 0.72rem;
                font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
            }}
            .mode-badge.actual {{ background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }}
            .mode-badge.simulation {{ background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }}
            .mode-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
            .mode-badge.actual .mode-dot {{ background: #22c55e; }}
            .mode-badge.simulation .mode-dot {{ background: #f59e0b; }}

            /* ── Topology Diagram ── */
            .topo-container {{
                display: flex; justify-content: center; align-items: stretch;
                gap: 2rem; padding: 1.5rem 0;
            }}
            .topo-box {{
                background: #1e293b; border: 1px solid #334155; border-radius: 12px;
                padding: 1.2rem 1.5rem; min-width: 240px;
                display: flex; flex-direction: column; gap: 0.6rem;
            }}
            .topo-box h3 {{
                font-size: 0.85rem; font-weight: 600; margin-bottom: 0.4rem;
                display: flex; align-items: center; gap: 0.5rem;
            }}
            .topo-port {{
                display: flex; align-items: center; gap: 0.5rem;
                padding: 0.35rem 0.6rem; border-radius: 6px;
                font-size: 0.78rem; font-family: 'JetBrains Mono', monospace;
                background: #0f172a; border: 1px solid #334155;
            }}
            .topo-port .port-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
            .topo-port .port-dot.up {{ background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.5); }}
            .topo-port .port-dot.down {{ background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.5); }}
            .topo-port .port-dot.unmapped {{ background: #64748b; }}
            .topo-port .port-name {{ flex: 1; }}
            .topo-port .port-speed {{ color: #64748b; font-size: 0.68rem; }}
            .topo-wires {{
                display: flex; flex-direction: column; justify-content: center;
                gap: 0.6rem; padding: 0 0.5rem;
            }}
            .topo-wire {{
                display: flex; align-items: center; gap: 0.25rem;
            }}
            .topo-wire .wire-line {{
                width: 60px; height: 2px; border-radius: 1px;
            }}
            .topo-wire .wire-line.up {{ background: #22c55e; box-shadow: 0 0 4px rgba(34,197,94,0.4); }}
            .topo-wire .wire-line.down {{ background: #ef4444; }}
            .topo-wire .wire-line.unmapped {{ background: #334155; border: 1px dashed #475569; height: 0; }}
            .topo-mode-bar {{
                text-align: center; margin-top: 0.75rem;
            }}
            .topo-summary {{
                font-size: 0.78rem; color: #94a3b8; margin-top: 0.3rem;
            }}

            /* ── Port Config Table ── */
            .port-table {{
                width: 100%; border-collapse: collapse; font-size: 0.78rem;
                margin-top: 0.8rem;
            }}
            .port-table th {{
                text-align: left; padding: 0.4rem 0.5rem; font-size: 0.7rem;
                text-transform: uppercase; letter-spacing: 0.04em; color: #64748b;
                border-bottom: 2px solid #334155;
            }}
            .port-table td {{ padding: 0.4rem 0.5rem; border-bottom: 1px solid #1e293b; }}
            .port-table input, .port-table select {{
                font-size: 0.78rem; padding: 0.25rem 0.4rem; width: 100%;
                background: #0f172a; border: 1px solid #334155; border-radius: 4px;
                color: #e2e8f0; font-family: 'JetBrains Mono', monospace;
            }}
            .port-table select {{ cursor: pointer; }}

            /* ── Simulation warning ── */
            .sim-warning {{
                background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3);
                color: #f59e0b; padding: 0.5rem 0.8rem; border-radius: 8px;
                font-size: 0.78rem; margin-bottom: 0.8rem; display: none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>TC8 Layer 2 Test Framework</h1>
            <p class="subtitle">OPEN Alliance Automotive Ethernet ECU Conformance Testing — v3.0</p>

            <!-- ═══ Tab Bar ═══ -->
            <div class="tab-bar">
                <button class="tab-btn active" data-tab="dashboard">🎛️ Dashboard</button>
                <button class="tab-btn" data-tab="topology">🗺️ Topology</button>
                <button class="tab-btn" data-tab="dut-config">🔧 DUT Configuration</button>
                <button class="tab-btn" data-tab="run-tests">🚀 Run Tests</button>
                <button class="tab-btn" data-tab="preflight">🩺 Pre-flight Checks</button>
                <button class="tab-btn" data-tab="console">📋 Console</button>
            </div>

            <!-- ═══ Tab 1: Dashboard ═══ -->
            <div class="tab-content active" id="tab-dashboard">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.8rem">
                    <div></div>
                    <span class="mode-badge simulation" id="dashboard-mode-badge">
                        <span class="mode-dot"></span> SIMULATION
                    </span>
                </div>
                <div class="cards">
                    <div class="card primary"><div class="value">{spec_count}</div><div class="label">Specifications</div></div>
                    <div class="card green"><div class="value">7</div><div class="label">TC8 Sections</div></div>
                    <div class="card amber"><div class="value">{run_count}</div><div class="label">Test Runs</div></div>
                    <div class="card primary"><div class="value">3</div><div class="label">Tiers</div></div>
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
                        <thead><tr><th>Report</th><th>DUT</th><th>Tier</th><th>Pass</th><th>Fail</th><th>Rate</th><th>Date</th></tr></thead>
                        <tbody>{run_rows}{no_runs_msg}</tbody>
                    </table>
                </div>
                <div class="panel">
                    <h2>🔗 Quick Links</h2>
                    <div class="links">
                        <a href="/docs">📖 API Docs</a>
                        <a href="/api/specs">📋 All Specs</a>
                        <a href="/api/reports">📊 All Reports</a>
                        <a href="/api/health">💚 Health</a>
                    </div>
                </div>
            </div>

            <!-- ═══ Tab 2: Topology ═══ -->
            <div class="tab-content" id="tab-topology">
                <div class="panel">
                    <h2>🗺️ Network Topology</h2>
                    <p style="font-size:0.78rem;color:#94a3b8;margin-bottom:0.4rem">
                        Live view of test station ↔ DUT connections. Auto-refreshes every 5 seconds.
                    </p>
                    <div class="topo-mode-bar">
                        <span class="mode-badge simulation" id="topo-mode-badge">
                            <span class="mode-dot"></span> <span id="topo-mode-text">SIMULATION</span>
                        </span>
                    </div>
                    <div class="topo-container" id="topo-diagram">
                        <div class="topo-box" id="topo-station-box">
                            <h3>🖥️ Test Station</h3>
                            <div id="topo-station-ports"><span style="color:#64748b;font-size:0.78rem">Detecting…</span></div>
                        </div>
                        <div class="topo-wires" id="topo-wires">
                        </div>
                        <div class="topo-box" id="topo-dut-box">
                            <h3>🔲 <span id="topo-dut-name">DUT</span></h3>
                            <div id="topo-dut-ports"><span style="color:#64748b;font-size:0.78rem">No DUT loaded</span></div>
                        </div>
                    </div>
                    <div class="topo-summary" id="topo-summary"></div>
                </div>
            </div>

            <!-- ═══ Tab 3: DUT Configuration ═══ -->
            <div class="tab-content" id="tab-dut-config">
                <div class="panel">
                    <h2>🔧 DUT Profile Configuration</h2>
                    <div class="btn-row" style="margin-bottom:1rem;margin-top:0">
                        <select id="load-profile-select" style="flex:1">
                            <option value="">— Load existing profile —</option>
                        </select>
                        <button class="btn btn-ghost" onclick="loadProfile()">Load</button>
                    </div>
                    <form id="dut-form">
                        <div class="form-grid">
                            <div class="form-group">
                                <label>DUT / ECU Name *</label>
                                <input type="text" id="dut-name" placeholder="e.g. MY_ECU_4PORT" required>
                            </div>
                            <div class="form-group">
                                <label>Model / Part Number</label>
                                <input type="text" id="dut-model" placeholder="e.g. SPC5744P">
                            </div>
                            <div class="form-group">
                                <label>Firmware Version</label>
                                <input type="text" id="dut-firmware" value="unknown">
                            </div>
                            <div class="form-group">
                                <label>Port Count</label>
                                <input type="number" id="dut-ports" value="4" min="2" max="16" onchange="rebuildPortTable()">
                            </div>
                            <div class="form-group">
                                <label>MAC Table Size</label>
                                <input type="number" id="dut-mac-table" value="1024" min="64" max="65536">
                            </div>
                            <div class="form-group">
                                <label>MAC Aging Time (sec)</label>
                                <input type="number" id="dut-aging" value="300" min="10" max="6000">
                            </div>
                            <div class="form-group full">
                                <div class="toggle-row"><input type="checkbox" id="dut-double-tag"><span>Supports Double-Tagging (802.1ad)</span></div>
                                <div class="toggle-row"><input type="checkbox" id="dut-gptp"><span>Supports gPTP (IEEE 802.1AS)</span></div>
                                <div class="toggle-row"><input type="checkbox" id="dut-reset"><span>Can power-cycle / reset between tests</span></div>
                            </div>
                        </div>
                        <!-- Per-Port Interface Mapping -->
                        <h3 style="font-size:0.88rem;margin:1rem 0 0.3rem;color:#94a3b8">Port ↔ Interface Mapping</h3>
                        <div style="overflow-x:auto">
                        <table class="port-table" id="port-config-table">
                            <thead>
                                <tr>
                                    <th>Port</th>
                                    <th>OS Interface</th>
                                    <th>MAC Address</th>
                                    <th>Speed</th>
                                    <th>VLANs</th>
                                    <th>PVID</th>
                                    <th>Trunk</th>
                                </tr>
                            </thead>
                            <tbody id="port-config-tbody"></tbody>
                        </table>
                        </div>
                        <div class="btn-row">
                            <button type="submit" class="btn btn-success">💾 Save Profile</button>
                            <button type="button" class="btn btn-ghost" onclick="clearDutForm()">Clear</button>
                        </div>
                    </form>
                    <div id="dut-status" class="status-msg"></div>
                </div>
            </div>

            <!-- ═══ Tab 4: Run Tests ═══ -->
            <div class="tab-content" id="tab-run-tests">
                <div class="sim-warning" id="run-sim-warning">
                    ⚠️ Running in <strong>SIMULATION</strong> mode — no real hardware detected. Results will not reflect actual DUT behavior.
                </div>
                <div class="panel">
                    <h2>🚀 Execute Test Suite</h2>
                    <div class="form-grid">
                        <div class="form-group">
                            <label>DUT Profile</label>
                            <select id="run-dut-select">
                                <option value="">— Select a DUT profile —</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Test Tier</label>
                            <select id="run-tier">
                                <option value="smoke">🔥 Smoke (~1 hour)</option>
                                <option value="core">⚙️ Core (~8 hours)</option>
                                <option value="full">📦 Full (40+ hours)</option>
                            </select>
                        </div>
                        <div class="form-group full">
                            <label>Sections</label>
                            <div style="display:flex;flex-wrap:wrap;gap:0.7rem;margin-top:0.3rem">
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.3" checked><span>5.3 VLAN</span></div>
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.4" checked><span>5.4 General</span></div>
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.5" checked><span>5.5 Address</span></div>
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.6" checked><span>5.6 Filter</span></div>
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.7" checked><span>5.7 Time</span></div>
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.8" checked><span>5.8 QoS</span></div>
                                <div class="toggle-row"><input type="checkbox" class="run-section" value="5.9" checked><span>5.9 Config</span></div>
                            </div>
                        </div>
                    </div>
                    <div class="btn-row">
                        <button class="btn btn-primary" id="btn-start-test" onclick="startTest()">▶ Start Test</button>
                        <button class="btn btn-danger" id="btn-cancel-test" onclick="cancelTest()" disabled>⏹ Cancel</button>
                    </div>
                </div>
                <div class="panel" id="run-progress-panel" style="display:none">
                    <h2>📈 Progress</h2>
                    <div class="progress-container">
                        <div class="progress-bar-bg"><div class="progress-bar-fill" id="run-progress-bar"></div></div>
                        <div class="progress-text" id="run-progress-text">Waiting…</div>
                    </div>
                    <div id="run-result" class="status-msg"></div>
                </div>
            </div>

            <!-- ═══ Tab 5: Pre-flight Checks ═══ -->
            <div class="tab-content" id="tab-preflight">
                <div class="panel">
                    <h2>🩺 Framework Self-Validation</h2>
                    <p style="font-size:0.82rem;color:#94a3b8;margin-bottom:0.8rem">
                        Run internal checks to verify the framework is ready for testing.
                    </p>
                    <button class="btn btn-primary" id="btn-preflight" onclick="runPreflight()">🔍 Run Checks</button>
                    <div id="preflight-list" style="margin-top:0.8rem"></div>
                    <div id="preflight-summary" class="status-msg" style="margin-top:0.6rem"></div>
                </div>
            </div>

            <!-- ═══ Tab 6: Console ═══ -->
            <div class="tab-content" id="tab-console">
                <div class="panel">
                    <h2>📋 Real-Time Console</h2>
                    <div class="console-toolbar">
                        <span><span class="ws-dot disconnected" id="log-ws-dot"></span><span id="log-ws-status" style="font-size:0.75rem;color:#94a3b8">Disconnected</span></span>
                        <select id="log-level-filter" onchange="filterLogs()">
                            <option value="DEBUG">DEBUG</option>
                            <option value="INFO" selected>INFO</option>
                            <option value="WARNING">WARNING</option>
                            <option value="ERROR">ERROR</option>
                        </select>
                        <button class="btn btn-ghost" onclick="clearConsole()" style="padding:0.3rem 0.7rem;font-size:0.72rem">Clear</button>
                        <button class="btn btn-ghost" id="btn-log-connect" onclick="connectLogs()" style="padding:0.3rem 0.7rem;font-size:0.72rem">Connect</button>
                    </div>
                    <div class="console" id="log-console"></div>
                </div>
            </div>
        </div>

        <!-- ═══ JavaScript ═══ -->
        <script>
        // ── Tab Navigation ──
        document.querySelectorAll('.tab-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
            }});
        }});

        // ── DUT Profile Data ──
        const profiles = {profiles_json};
        let detectedInterfaces = [];

        function populateProfileDropdowns() {{
            const selects = [document.getElementById('load-profile-select'), document.getElementById('run-dut-select')];
            selects.forEach(sel => {{
                while (sel.options.length > 1) sel.remove(1);
                profiles.forEach(p => {{
                    const opt = document.createElement('option');
                    opt.value = p.path;
                    opt.textContent = p.name;
                    sel.appendChild(opt);
                }});
            }});
        }}
        populateProfileDropdowns();

        // ── Fetch OS Interfaces ──
        async function fetchInterfaces() {{
            try {{
                const res = await fetch('/api/interfaces');
                const json = await res.json();
                detectedInterfaces = json.interfaces || [];
            }} catch(e) {{ console.warn('Failed to fetch interfaces', e); }}
        }}
        fetchInterfaces();

        // ── Port Config Table ──
        function rebuildPortTable(portData) {{
            const count = parseInt(document.getElementById('dut-ports').value) || 4;
            const tbody = document.getElementById('port-config-tbody');
            tbody.innerHTML = '';
            for (let i = 0; i < count; i++) {{
                const pd = portData && portData[i] ? portData[i] : null;
                const tr = document.createElement('tr');
                // Interface select options
                let ifaceOpts = '<option value="">(select)</option>';
                detectedInterfaces.forEach(iface => {{
                    const sel = (pd && pd.interface_name === iface.name) ? ' selected' : '';
                    const upIcon = iface.is_up ? '🟢' : '🔴';
                    ifaceOpts += '<option value="' + iface.name + '"' + sel + '>' + upIcon + ' ' + iface.name + '</option>';
                }});
                // If the saved interface isn't in detectedInterfaces, add it
                if (pd && pd.interface_name && !detectedInterfaces.find(x => x.name === pd.interface_name)) {{
                    ifaceOpts += '<option value="' + pd.interface_name + '" selected>⚠️ ' + pd.interface_name + '</option>';
                }}
                const mac = pd ? pd.mac_address : '02:00:00:00:00:' + (i+1).toString(16).padStart(2,'0');
                const speed = pd ? pd.speed_mbps : 100;
                const vlans = pd ? (pd.vlan_membership || [1]).join(',') : '1';
                const pvid = pd ? (pd.pvid || 1) : 1;
                const trunk = pd ? (pd.is_trunk || false) : false;
                tr.innerHTML = '<td style="font-weight:600;color:#60a5fa">' + i + '</td>'
                    + '<td><select class="port-iface">' + ifaceOpts + '</select></td>'
                    + '<td><input type="text" class="port-mac" value="' + mac + '" pattern="^([0-9A-Fa-f]{{2}}:){{5}}[0-9A-Fa-f]{{2}}$"></td>'
                    + '<td><input type="number" class="port-speed" value="' + speed + '" min="10" max="10000" style="width:70px"></td>'
                    + '<td><input type="text" class="port-vlans" value="' + vlans + '" style="width:80px"></td>'
                    + '<td><input type="number" class="port-pvid" value="' + pvid + '" min="0" max="4095" style="width:60px"></td>'
                    + '<td><input type="checkbox" class="port-trunk"' + (trunk ? ' checked' : '') + '></td>';
                tbody.appendChild(tr);
            }}
        }}
        // Build initial port table after interfaces are loaded
        fetchInterfaces().then(() => rebuildPortTable());

        function collectPortData() {{
            const rows = document.querySelectorAll('#port-config-tbody tr');
            const ports = [];
            rows.forEach((row, i) => {{
                ports.push({{
                    port_id: i,
                    interface_name: row.querySelector('.port-iface').value || ('eth' + i),
                    mac_address: row.querySelector('.port-mac').value,
                    speed_mbps: parseInt(row.querySelector('.port-speed').value) || 100,
                    vlan_membership: row.querySelector('.port-vlans').value.split(',').map(v => parseInt(v.trim())).filter(v => !isNaN(v)),
                    pvid: parseInt(row.querySelector('.port-pvid').value) || 1,
                    is_trunk: row.querySelector('.port-trunk').checked,
                }});
            }});
            return ports;
        }}

        // ── Load Profile ──
        async function loadProfile() {{
            const sel = document.getElementById('load-profile-select');
            const name = sel.options[sel.selectedIndex]?.textContent;
            if (!name || sel.value === '') return;
            try {{
                const res = await fetch('/api/dut-profiles/' + encodeURIComponent(name));
                if (!res.ok) throw new Error('Profile not found');
                const json = await res.json();
                const d = json.data;
                document.getElementById('dut-name').value = d.name || '';
                document.getElementById('dut-model').value = d.model || '';
                document.getElementById('dut-firmware').value = d.firmware_version || 'unknown';
                document.getElementById('dut-ports').value = d.port_count || 4;
                document.getElementById('dut-mac-table').value = d.max_mac_table_size || 1024;
                document.getElementById('dut-aging').value = d.mac_aging_time_s || 300;
                document.getElementById('dut-double-tag').checked = d.supports_double_tagging || false;
                document.getElementById('dut-gptp').checked = d.supports_gptp || false;
                document.getElementById('dut-reset').checked = d.can_reset || false;
                // Rebuild port table with loaded data
                await fetchInterfaces();
                rebuildPortTable(d.ports || []);
                showStatus('dut-status', 'success', 'Loaded: ' + d.name);
            }} catch (e) {{
                showStatus('dut-status', 'error', 'Failed: ' + e.message);
            }}
        }}

        // ── Save Profile ──
        document.getElementById('dut-form').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const body = {{
                dut_name: document.getElementById('dut-name').value,
                model: document.getElementById('dut-model').value,
                firmware: document.getElementById('dut-firmware').value,
                port_count: parseInt(document.getElementById('dut-ports').value),
                mac_table_size: parseInt(document.getElementById('dut-mac-table').value),
                mac_aging_time: parseInt(document.getElementById('dut-aging').value),
                double_tagging: document.getElementById('dut-double-tag').checked,
                gptp: document.getElementById('dut-gptp').checked,
                can_reset: document.getElementById('dut-reset').checked,
                ports: collectPortData(),
            }};
            try {{
                const res = await fetch('/api/dut-profiles', {{
                    method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(body),
                }});
                const json = await res.json();
                if (res.ok) {{
                    showStatus('dut-status', 'success', '✅ Profile saved: ' + json.name);
                    profiles.push({{ name: json.name, path: json.name + '.yaml' }});
                    populateProfileDropdowns();
                }} else {{
                    showStatus('dut-status', 'error', '❌ ' + (json.detail || 'Error'));
                }}
            }} catch (e) {{
                showStatus('dut-status', 'error', '❌ ' + e.message);
            }}
        }});

        function clearDutForm() {{
            document.getElementById('dut-form').reset();
            document.getElementById('dut-status').className = 'status-msg';
            rebuildPortTable();
        }}

        // ── Topology Diagram ──
        let topoInterval = null;

        async function refreshTopology() {{
            try {{
                const res = await fetch('/api/topology');
                const data = await res.json();
                renderTopology(data);
                updateModeBadges(data.mode, data.active_links, data.total_ports);
            }} catch (e) {{ console.warn('Topology refresh failed', e); }}
        }}

        function renderTopology(data) {{
            // Station ports
            const stationDiv = document.getElementById('topo-station-ports');
            stationDiv.innerHTML = '';
            data.station_interfaces.forEach(iface => {{
                const dn = document.createElement('div');
                dn.className = 'topo-port';
                dn.innerHTML = '<span class="port-dot ' + (iface.is_up ? 'up' : 'down') + '"></span>'
                    + '<span class="port-name">' + iface.name + '</span>'
                    + '<span class="port-speed">' + (iface.speed_mbps || '-') + ' Mbps</span>';
                dn.title = 'MAC: ' + (iface.mac || '-') + '\\nIP: ' + (iface.ipv4 || '-');
                stationDiv.appendChild(dn);
            }});

            // DUT ports
            document.getElementById('topo-dut-name').textContent = data.dut_name;
            const dutDiv = document.getElementById('topo-dut-ports');
            dutDiv.innerHTML = '';
            if (data.dut_ports.length === 0) {{
                dutDiv.innerHTML = '<span style="color:#64748b;font-size:0.78rem">No DUT profile loaded. Configure one in DUT Configuration tab.</span>';
            }}
            data.dut_ports.forEach(port => {{
                const dn = document.createElement('div');
                dn.className = 'topo-port';
                const status = port.is_up ? 'up' : (port.is_mapped ? 'down' : 'unmapped');
                dn.innerHTML = '<span class="port-dot ' + status + '"></span>'
                    + '<span class="port-name">Port ' + port.port_id + ' (' + port.interface_name + ')</span>'
                    + '<span class="port-speed">' + port.speed_mbps + ' Mbps</span>';
                dn.title = 'MAC: ' + port.mac + '\\nVLANs: ' + (port.vlans||[]).join(',') + '\\nPVID: ' + port.pvid + '\\nTrunk: ' + (port.is_trunk ? 'Yes' : 'No');
                dutDiv.appendChild(dn);
            }});

            // Wires
            const wiresDiv = document.getElementById('topo-wires');
            wiresDiv.innerHTML = '';
            data.mappings.forEach(m => {{
                const wire = document.createElement('div');
                wire.className = 'topo-wire';
                wire.innerHTML = '<span class="wire-line ' + m.status + '"></span>';
                wire.title = m.station_iface + ' → Port ' + m.dut_port + ' [' + m.status.toUpperCase() + ']';
                wiresDiv.appendChild(wire);
            }});

            // Summary
            const summary = document.getElementById('topo-summary');
            summary.textContent = data.active_links + '/' + data.total_ports + ' ports connected • ' + data.station_interfaces.length + ' station interfaces detected';
        }}

        function updateModeBadges(mode, activeLinks, totalPorts) {{
            const badges = ['dashboard-mode-badge', 'topo-mode-badge'];
            badges.forEach(id => {{
                const el = document.getElementById(id);
                if (!el) return;
                el.className = 'mode-badge ' + mode;
                const text = mode === 'actual'
                    ? 'ACTUAL (' + activeLinks + '/' + totalPorts + ' active)'
                    : 'SIMULATION';
                el.innerHTML = '<span class="mode-dot"></span> ' + text;
            }});
            const topoText = document.getElementById('topo-mode-text');
            if (topoText) topoText.textContent = mode === 'actual' ? 'ACTUAL' : 'SIMULATION';
            // Show/hide sim warning on Run Tests
            const warn = document.getElementById('run-sim-warning');
            if (warn) warn.style.display = mode === 'simulation' ? 'block' : 'none';
        }}

        // Start topology auto-refresh
        refreshTopology();
        topoInterval = setInterval(refreshTopology, 5000);

        // ── Run Tests ──
        let progressWs = null;

        async function startTest() {{
            const dutPath = document.getElementById('run-dut-select').value;
            if (!dutPath) {{ alert('Select a DUT profile first'); return; }}

            const tier = document.getElementById('run-tier').value;
            const sections = Array.from(document.querySelectorAll('.run-section:checked')).map(c => c.value);

            document.getElementById('btn-start-test').disabled = true;
            document.getElementById('btn-cancel-test').disabled = false;
            document.getElementById('run-progress-panel').style.display = 'block';
            document.getElementById('run-progress-bar').style.width = '0%';
            document.getElementById('run-progress-text').textContent = 'Starting…';
            document.getElementById('run-result').className = 'status-msg';

            // Connect progress WebSocket
            const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            progressWs = new WebSocket(wsProto + '//' + location.host + '/ws/progress');
            progressWs.onmessage = (ev) => {{
                const msg = JSON.parse(ev.data);
                if (msg.type === 'progress') {{
                    const pct = Math.round((msg.current / msg.total) * 100);
                    document.getElementById('run-progress-bar').style.width = pct + '%';
                    const icon = {{ pass: '✅', fail: '❌', informational: 'ℹ️', skip: '⏭️', error: '💥' }}[msg.status] || '🔄';
                    document.getElementById('run-progress-text').textContent = icon + ' [' + msg.current + '/' + msg.total + '] ' + msg.case_id;
                }}
            }};

            try {{
                const profileDir = 'config/dut_profiles/';
                const res = await fetch('/api/run', {{
                    method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ dut_profile_path: profileDir + dutPath, tier: tier, sections: sections.length ? sections : null }}),
                }});
                const json = await res.json();
                if (res.ok) {{
                    document.getElementById('run-progress-bar').style.width = '100%';
                    showStatus('run-result', 'success',
                        '✅ Complete — ' + json.passed + ' passed, ' + json.failed + ' failed, ' +
                        json.pass_rate.toFixed(1) + '% pass rate (' + json.duration_s.toFixed(1) + 's) — ' +
                        '<a href="/api/reports/' + json.report_id + '/html" style="color:#22c55e">View Report</a>'
                    );
                }} else {{
                    showStatus('run-result', 'error', '❌ ' + (json.detail || 'Error running suite'));
                }}
            }} catch (e) {{
                showStatus('run-result', 'error', '❌ ' + e.message);
            }} finally {{
                document.getElementById('btn-start-test').disabled = false;
                document.getElementById('btn-cancel-test').disabled = true;
                if (progressWs) progressWs.close();
            }}
        }}

        async function cancelTest() {{
            try {{
                await fetch('/api/cancel', {{ method: 'POST' }});
                document.getElementById('run-progress-text').textContent = '⏹ Cancellation requested…';
            }} catch (e) {{ /* ignore */ }}
        }}

        // ── Pre-flight ──
        async function runPreflight() {{
            const btn = document.getElementById('btn-preflight');
            const list = document.getElementById('preflight-list');
            const summary = document.getElementById('preflight-summary');
            btn.disabled = true;
            btn.textContent = '⏳ Running…';
            list.innerHTML = '';
            summary.className = 'status-msg';

            try {{
                const res = await fetch('/api/preflight', {{ method: 'POST' }});
                const json = await res.json();
                json.checks.forEach(c => {{
                    const div = document.createElement('div');
                    div.className = 'check-item ' + c.status;
                    div.innerHTML = '<span class="check-icon">' + (c.status === 'pass' ? '✅' : '❌') + '</span>'
                        + '<span>' + c.name + '</span>'
                        + '<span class="check-detail">' + c.detail + '</span>';
                    list.appendChild(div);
                }});
                const ok = json.passed === json.total;
                showStatus('preflight-summary', ok ? 'success' : 'error',
                    (ok ? '✅' : '⚠️') + ' ' + json.passed + '/' + json.total + ' checks passed');
            }} catch (e) {{
                showStatus('preflight-summary', 'error', '❌ ' + e.message);
            }} finally {{
                btn.disabled = false;
                btn.textContent = '🔍 Run Checks';
            }}
        }}

        // ── Console / Log Streaming ──
        let logWs = null;
        const logLines = [];
        const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

        function connectLogs() {{
            if (logWs && logWs.readyState <= 1) {{ logWs.close(); return; }}
            const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            logWs = new WebSocket(wsProto + '//' + location.host + '/ws/logs');
            logWs.onopen = () => {{
                document.getElementById('log-ws-dot').className = 'ws-dot connected';
                document.getElementById('log-ws-status').textContent = 'Connected';
                document.getElementById('btn-log-connect').textContent = 'Disconnect';
            }};
            logWs.onclose = () => {{
                document.getElementById('log-ws-dot').className = 'ws-dot disconnected';
                document.getElementById('log-ws-status').textContent = 'Disconnected';
                document.getElementById('btn-log-connect').textContent = 'Connect';
            }};
            logWs.onmessage = (ev) => {{
                const msg = JSON.parse(ev.data);
                if (msg.type === 'log') {{
                    logLines.push(msg);
                    appendLogLine(msg);
                }}
            }};
        }}

        function appendLogLine(msg) {{
            const filter = document.getElementById('log-level-filter').value;
            if (LOG_LEVELS.indexOf(msg.level) < LOG_LEVELS.indexOf(filter)) return;
            const el = document.getElementById('log-console');
            const line = document.createElement('div');
            line.className = 'log-line log-' + msg.level;
            line.textContent = msg.message;
            el.appendChild(line);
            el.scrollTop = el.scrollHeight;
        }}

        function filterLogs() {{
            const el = document.getElementById('log-console');
            el.innerHTML = '';
            logLines.forEach(msg => appendLogLine(msg));
        }}

        function clearConsole() {{
            document.getElementById('log-console').innerHTML = '';
            logLines.length = 0;
        }}

        // ── Helpers ──
        function showStatus(id, type, html) {{
            const el = document.getElementById(id);
            el.className = 'status-msg ' + type;
            el.innerHTML = html;
        }}

        // Auto-connect console when switching to that tab
        document.querySelector('[data-tab="console"]').addEventListener('click', () => {{
            if (!logWs || logWs.readyState > 1) connectLogs();
        }});
        </script>
    </body>
    </html>
    """
