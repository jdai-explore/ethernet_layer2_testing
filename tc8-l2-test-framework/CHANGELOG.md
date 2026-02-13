# Changelog

All notable changes to the TC8 Layer 2 Test Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-13

### Added
- **Phase 1: Foundation**
  - Core test runner with async execution
  - Config manager for YAML-based configuration
  - Session manager with DUT state isolation
  - Result validator with TC8-compliant pass/fail logic
  - Frame builder utilities (802.1Q, 802.1ad)
  - Pydantic data models for type safety

- **Phase 2: Spec Implementation**
  - 71 TC8 specification YAML definitions
  - 7 test modules (VLAN, Address Learning, Filtering, QoS, Time Sync, Config, General)
  - Spec registry for section-specific dispatch
  - HTML report generator with Jinja2 templates
  - Test runner integration with spec handlers

- **Phase 3: Integration & Testing**
  - Database persistence (SQLAlchemy 2.0)
  - CLI tool with 4 commands (run, specs, history, report)
  - pytest integration (17/17 tests passing)
  - Enhanced web dashboard with report APIs
  - Self-validation suite

- **Phase 4: Documentation & Deployment**
  - Comprehensive user guide
  - Quick start and DUT profile tutorials
  - Cross-platform deployment (Docker, Windows, Linux)
  - Setup scripts with environment diagnostics
  - Example DUT profiles (simulation, 4-port, 8-port gateway)

### Features
- ✅ 100% TC8 Layer 2 v3.0 spec coverage (71 specifications)
- ✅ 200,000+ combinatorial test cases
- ✅ Web UI with real-time progress tracking
- ✅ Database-backed report history and trend analysis
- ✅ Cross-platform support (Windows, Linux, macOS, Docker)
- ✅ Simulation mode for testing without physical hardware

### Technical Details
- Python 3.10+ required (3.11 recommended)
- Scapy for packet crafting
- FastAPI for web backend
- SQLAlchemy for persistence
- pytest for testing
- Click for CLI

---

## [Unreleased]

### Planned
- CI/CD integration examples (Jenkins, GitLab CI, GitHub Actions)
- Performance optimizations for full-tier execution
- Advanced timing calibration tools
- Additional DUT interface plugins (USB, DoIP)
- Report export formats (PDF, CSV, JUnit XML)

---

[0.1.0]: https://github.com/your-org/tc8-l2-test-framework/releases/tag/v0.1.0
