# TC8 Layer 2 Test Framework

This directory contains the framework package. For full setup and usage instructions, see:

- **[Root PRD](docs/PRD.md)** — Project overview, quick install, architecture
- **[User Guide](docs/user_guide.md)** — Complete operational guide (install → run → debug → reports)
- **[Quick Start Tutorial](docs/tutorials/01_quick_start.md)** — 5-minute simulation run
- **[DUT Profile Tutorial](docs/tutorials/02_custom_dut_profile.md)** — Wiring and YAML configuration

## Package Structure

| Directory | Contents |
|---|---|
| `src/` | Core framework: test runner, config manager, session manager, spec handlers, DUT interface layer, reporting |
| `web/` | FastAPI backend and static web UI |
| `config/` | YAML configurations and DUT profile examples |
| `data/` | Data-driven spec definitions (71 YAML files, one per TC8 spec) |
| `tests/` | Framework self-validation suite (47 tests) |
| `reports/` | Generated HTML reports and SQLite database |
| `docs/` | User guide and tutorials |
