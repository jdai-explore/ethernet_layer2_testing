# Quick Start — 5-Minute Simulation Run

> **Goal**: Confirm the framework is installed and produces a report  
> **Hardware required**: None (uses built-in NullDUT simulator)

## 1. Install (if not already done)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Verify
python -m pytest tests/ -v      # Expected: 47 passed
```

## 2. Run Smoke Test in Simulation Mode

```bash
python -m src.cli run \
  --dut config/dut_profiles/examples/simulation_dut.yaml \
  --tier smoke \
  --output reports/first_run.html
```

Expected output:
```
TC8 Layer 2 Test Framework v0.1.0
Loading DUT profile: simulation_dut.yaml
Test tier: smoke (10 specs)
Running tests...
Results: 48 passed, 2 informational
Report saved: reports/first_run.html
```

## 3. Open the Report

```bash
# Windows
start reports\first_run.html

# Linux
xdg-open reports/first_run.html
```

## 4. Try the Web UI

```bash
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
# Open: http://localhost:8000
```

Select `simulation_dut.yaml`, choose the `smoke` tier, click **Start Test**, and watch real-time progress.

## Next Step: Physical DUT

Once the simulation run passes, connect your ECU and follow the [User Guide](../user_guide.md) starting at **Section 4 (Verifying Your ECU Test Setup)** and **Section 5 (DUT Profile Configuration)**.
