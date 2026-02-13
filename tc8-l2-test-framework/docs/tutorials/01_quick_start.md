# Quick Start Tutorial — 5-Minute Smoke Test

> **Goal**: Run your first TC8 test in under 5 minutes  
> **Prerequisites**: Python 3.10+, framework installed

## Step 1: Install Framework (2 minutes)

### Windows
```powershell
# Open PowerShell as Administrator
cd C:\path\to\tc8-l2-test-framework

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Linux
```bash
# Open terminal
cd /path/to/tc8-l2-test-framework

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Verify Installation (30 seconds)

```bash
# Run self-validation tests
python -m pytest tests/unit/ tests/self_validation/ -v

# Expected output: 17 passed
```

## Step 3: Run Simulation Smoke Test (1 minute)

The framework includes a **NullDUT** simulator for testing without physical hardware.

```bash
# List available specs
python -m src.cli specs --section 5.3

# Run smoke tier with simulated DUT
python -m src.cli run \
  --dut config/dut_profiles/examples/simulation_dut.yaml \
  --tier smoke \
  --output reports/my_first_test.html
```

**Expected output**:
```
🚀 TC8 Layer 2 Test Framework v0.1.0
📋 Loading DUT profile: simulation_dut.yaml
🔧 Test tier: smoke (10 specs, ~50 test cases)
⏱️  Estimated duration: 2-5 minutes

Running tests... ████████████████████ 100%

✅ Results:
   Total: 50
   Passed: 48 (96%)
   Failed: 2 (4%)
   Duration: 1m 23s

📊 Report saved: reports/my_first_test.html
```

## Step 4: View Report (30 seconds)

### Windows
```powershell
start reports\my_first_test.html
```

### Linux
```bash
xdg-open reports/my_first_test.html
# or: firefox reports/my_first_test.html
```

The HTML report shows:
- ✅ **Summary**: Pass/fail counts, overall compliance %
- 📊 **Section Breakdown**: Results by TC8 section (VLAN, Address Learning, etc.)
- 📝 **Detailed Results**: Every test case with expected vs. actual behavior

## Step 5: Try the Web UI (1 minute)

```bash
# Start web server
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000

# Open browser: http://localhost:8000
```

In the web UI:
1. Select **DUT Profile**: `simulation_dut.yaml`
2. Select **Test Tier**: `smoke`
3. Click **"Run Tests"**
4. Watch real-time progress
5. Click report ID to view results

## Next Steps

### With Physical DUT
Once you have a physical ECU connected:

1. **Map Ports**: Identify which test station interfaces connect to DUT ports
   ```bash
   # Windows
   ipconfig /all
   
   # Linux
   ip link show
   ```

2. **Create DUT Profile**: Copy `config/dut_profiles/examples/4port_basic_switch.yaml` and edit:
   - Update `interface_name` for each port
   - Set `mac_address` for each port
   - Configure `vlan_membership` based on DUT config

3. **Run Real Test**:
   ```bash
   python -m src.cli run --dut config/dut_profiles/my_ecu.yaml --tier smoke
   ```

### Tutorials
- [Creating Custom DUT Profiles](02_custom_dut_profile.md)
- [Interpreting Test Results](03_interpreting_results.md)
- [CI/CD Integration](04_ci_cd_integration.md)

### Troubleshooting
- **"Permission denied"** (Linux): Run with `sudo` or add capabilities
- **"Interface not found"**: Check interface names in DUT profile
- **All tests fail**: Verify DUT connectivity with `ping`

See [User Guide](../user_guide.md#troubleshooting) for more help.
