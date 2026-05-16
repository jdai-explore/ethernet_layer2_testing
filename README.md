# TC8 Layer 2 Automotive Ethernet ECU Test Framework

> **OPEN Alliance TC8 v3.0 Conformance Testing — Python/Scapy**

A modular, open-architecture test framework for validating Layer 2 switching behavior of automotive Ethernet ECUs against the OPEN Alliance TC8 Automotive Ethernet ECU Test Specification — Layer 2, v3.0.

[![Tests](https://img.shields.io/badge/tests-52%2F52%20passing-success)](tc8-l2-test-framework/tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What It Tests

**104 specifications** — 71 TC8 v3.0 conformance specs + 33 extended automotive tests:

### TC8 v3.0 Conformance (SWITCH_*)

| Section | Topic | Specs | PC+DUT |
|---------|-------|-------|--------|
| 5.3 | VLAN Testing | 21 | ✅ |
| 5.4 | General Switching | 10 | ✅ (Linux only for runt frames) |
| 5.5 | Address Learning | 21 | ✅ |
| 5.6 | Filtering | 11 | ⚠️ storm control needs tgen |
| 5.7 | Time Synchronization | 1 | ❌ TSN NIC required |
| 5.8 | Quality of Service | 4 | ⚠️ rate accuracy needs tgen |
| 5.9 | Configuration | 3 | ✅ |

### Extended Automotive Tests (EXT_*)

| Prefix | Topic | Specs | PC+DUT |
|--------|-------|-------|--------|
| EXT_TSN | TSN / gPTP deeper support | 10 | ❌ TSN NIC required |
| EXT_PHY | Automotive PHY layer | 8 | ⚠️ link flap only |
| EXT_MGMT | DUT management / DoIP | 5 | ⚠️ DoIP not yet implemented |
| EXT_ORACLE | Golden device / virtual oracle | 4 | ✅ Linux virtual bridge |
| EXT_PERF | Performance / traffic generation | 6 | ⚠️ basic burst only |

> Tests that require unavailable hardware return `SKIP` or `INFORMATIONAL` — never `ERROR`. The web UI shows per-section hardware badges and warns before running hardware-gated sections. See [Known Limitations](tc8-l2-test-framework/docs/known_limitations.md).

Three execution tiers: **smoke** (~1 h) / **core** (~8 h) / **full** (40+ h)

## Quick Install

```bash
cd tc8-l2-test-framework
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **Windows**: Install [Npcap](https://npcap.com/) first (enable "WinPcap API-compatible Mode").  
> **Linux**: `sudo apt-get install libpcap-dev`

## Quick Smoke Run (No Hardware)

```bash
python -m src.cli run \
  --dut config/dut_profiles/examples/simulation_dut.yaml \
  --tier smoke \
  --output reports/smoke_simulation.html
```

## Documentation

- **[User Guide](tc8-l2-test-framework/docs/user_guide.md)** — Install → what the app does → minimum test setup → ECU setup verification → DUT profile config → running tests → debugging → downloading reports
- **[Known Limitations](tc8-l2-test-framework/docs/known_limitations.md)** — Incomplete features, hardware constraints, and path to resolution for each
- **[Quick Start Tutorial](tc8-l2-test-framework/docs/tutorials/01_quick_start.md)** — 5-minute simulation run
- **[DUT Profile Tutorial](tc8-l2-test-framework/docs/tutorials/02_custom_dut_profile.md)** — Physical wiring and YAML configuration

## Architecture

```
tc8-l2-test-framework/
├── src/
│   ├── core/           # Test runner, config manager, session manager, result validator
│   ├── specs/          # Spec handlers: 7 TC8 sections + 5 EXT_* extended sections
│   ├── reporting/      # HTML report generator, SQLite result store
│   ├── interface/      # DUT communication + traffic generation (Scapy, BaseTrafficGen)
│   └── models/         # Pydantic data models (TestCase, SetupRequirement, …)
├── web/                # FastAPI backend + web UI (6-tab dashboard, hardware badges)
├── config/             # DUT profile YAMLs and framework defaults
├── data/               # 104 spec definition YAML files (71 TC8 + 33 EXT_*)
├── tests/              # Self-validation suite (52 tests)
└── docs/               # User guide, tutorials, known limitations
```

## DUT Interface Options

| Interface | Use case |
|---|---|
| **Scapy** (default) | Standard NICs, Windows + Linux |
| **Raw Socket** | Linux `AF_PACKET` for high-performance |
| **TCP Stub** | Remote DUT over network |
| **NullDUT** | Simulation — no hardware needed |

## Docker

```bash
docker-compose up -d
# Web UI: http://localhost:8000
```

## License

Proprietary License
