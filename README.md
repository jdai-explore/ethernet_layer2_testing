# TC8 Layer 2 Automotive Ethernet ECU Test Framework

> **OPEN Alliance TC8 v3.0 Conformance Testing — Python/Scapy**

A modular, open-architecture test framework for validating Layer 2 switching behavior of automotive Ethernet ECUs against the [OPEN Alliance TC8 Automotive Ethernet ECU Test Specification — Layer 2, v3.0](https://opensig.org/).

[![Tests](https://img.shields.io/badge/tests-17%2F17%20passing-success)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 📋 Coverage

| Section | Topic | Specs | Status |
|---------|-------|-------|--------|
| 5.3 | VLAN Testing | 21 | ✅ Complete |
| 5.4 | General | 10 | ✅ Complete |
| 5.5 | Address Learning | 21 | ✅ Complete |
| 5.6 | Filtering | 11 | ✅ Complete |
| 5.7 | Time Synchronization | 1 | ✅ Complete |
| 5.8 | Quality of Service | 4 | ✅ Complete |
| 5.9 | Configuration | 3 | ✅ Complete |
| **Total** | | **71** | **✅ 100%** |

## 🚀 Quick Start

### Installation

#### Option 1: Automated Setup (Recommended)

**Windows:**
```powershell
.\scripts\setup.ps1
```

**Linux/macOS:**
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

#### Option 2: Docker

```bash
docker-compose up -d
# Access web UI: http://localhost:8000
```

#### Option 3: Manual Install

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m pytest tests/unit/ tests/self_validation/ -v
```

### Run Your First Test

```bash
# List available specs
python -m src.cli specs

# Run smoke tests with simulation DUT
python -m src.cli run \
  --dut config/dut_profiles/examples/simulation_dut.yaml \
  --tier smoke \
  --output reports/smoke_test.html

# Start web UI
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
# Open: http://localhost:8000
```

## 📚 Documentation

- **[User Guide](docs/user_guide.md)** — Installation, configuration, running tests
- **[Quick Start Tutorial](docs/tutorials/01_quick_start.md)** — 5-minute walkthrough
- **[Creating DUT Profiles](docs/tutorials/02_custom_dut_profile.md)** — Configure your ECU
- **[API Documentation](http://localhost:8000/docs)** — Interactive API docs (when server running)

## 🏗️ Architecture

```
tc8-l2-test-framework/
├── src/
│   ├── core/           # Test runner, config manager, session manager
│   ├── specs/          # Test specification implementations (7 sections)
│   ├── reporting/      # HTML reports, DB persistence, result store
│   ├── interface/      # DUT communication (Scapy, raw socket, TCP)
│   ├── utils/          # Frame builder, timing, validators
│   └── models/         # Pydantic data models
├── web/                # FastAPI backend + Web UI
├── config/             # YAML configurations & DUT profiles
├── data/               # Data-driven spec definitions (71 YAML files)
├── tests/              # Framework self-tests (17/17 passing)
├── reports/            # Generated test reports
└── docs/               # Documentation
```

## ⚙️ Test Tiers

| Tier | Duration | Specs | Use Case |
|------|----------|-------|----------|
| **smoke** | ~1 hour | 10 | Quick validation, CI/CD |
| **core** | ~8 hours | 52 | Nightly regression |
| **full** | 40+ hours | 71 | Pre-release validation |

## 🔌 DUT Interface

The framework uses a pluggable interface layer for DUT communication:

- **Scapy** (default) — Standard packet crafting via `sendp`/`sniff`
- **Raw Socket** — Linux `AF_PACKET` for performance-sensitive tests
- **TCP Stub** — Remote DUT access over network
- **NullDUT** — Simulation mode for framework testing

## 📊 Features

- ✅ **71 TC8 Specifications** — Complete Layer 2 test coverage
- ✅ **200,000+ Test Cases** — Combinatorial test generation
- ✅ **HTML Reports** — Beautiful, interactive test reports
- ✅ **Database Persistence** — SQLAlchemy with trend analysis
- ✅ **Web Dashboard** — Real-time progress, report history
- ✅ **CLI Tool** — Headless execution for CI/CD
- ✅ **Cross-Platform** — Windows, Linux, macOS, Docker
- ✅ **Self-Validating** — 17 framework tests ensure correctness

## 🐳 Docker Deployment

```bash
# Build image
docker build -t tc8-l2-test-framework .

# Run web UI
docker-compose up -d

# Run CLI command
docker-compose exec tc8-web python -m src.cli specs

# View logs
docker-compose logs -f tc8-web
```

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# Self-validation
python -m pytest tests/self_validation/ -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
```

## 📄 License

Proprietary License


## 📧 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/tc8-l2-test-framework/issues)
- **Documentation**: [User Guide](docs/user_guide.md)
- **Email**: 

---

**Built with**: Python 3.11 • Scapy • FastAPI • SQLAlchemy • pytest  
**Standard**: OPEN Alliance TC8 Layer 2 v3.0  
**Status**: Production Ready ✅

