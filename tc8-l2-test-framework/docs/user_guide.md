# TC8 Layer 2 Test Framework — User Guide

> **Version:** 0.1.0  
> **Last Updated:** 2026-02-13

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [DUT Configuration](#dut-configuration)
5. [Running Tests](#running-tests)
6. [Web Dashboard](#web-dashboard)
7. [Topology & Mode Detection](#topology--mode-detection)
8. [Understanding Reports](#understanding-reports)
9. [Troubleshooting](#troubleshooting)

---

## Introduction

The TC8 Layer 2 Test Framework validates automotive Ethernet ECU switching behavior against the OPEN Alliance TC8 specification v3.0. It covers:

- **VLAN Testing** (21 specs) — 802.1Q tagging, PVID, trunk ports
- **Address Learning** (21 specs) — MAC table, aging, forwarding
- **Filtering** (11 specs) — Unicast, multicast, broadcast filtering
- **QoS** (4 specs) — Priority code point (PCP) handling
- **Time Sync** (1 spec) — gPTP support validation
- **Configuration** (3 specs) — Startup modes, persistence
- **General** (10 specs) — Frame forwarding, port isolation

**Total: 71 specifications → 200,000+ test cases**

---

## Installation

### Prerequisites

- **Python 3.10+** (3.11 recommended)
- **Operating System**: Linux (recommended), Windows, or macOS
- **Network Access**: Direct Ethernet connection to DUT ports
- **Permissions**: Root/admin for raw socket access (Linux: `sudo`, Windows: Run as Administrator)
- **Packet Capture Driver** (required for Scapy):
  - **Windows**: [Npcap](https://npcap.com/) — download and install with **"WinPcap API-compatible Mode"** enabled
  - **Linux**: `sudo apt-get install libpcap-dev` (Debian/Ubuntu) or `sudo dnf install libpcap-devel` (RHEL/Fedora)
  - **macOS**: Pre-installed; if issues, run `brew install libpcap`

> ⚠️ **Without a packet capture driver, Scapy cannot send or sniff raw Ethernet frames.** The framework will start in simulation mode but real DUT testing requires this driver.

### Option 1: From Source

```bash
# Clone repository
git clone https://github.com/your-org/tc8-l2-test-framework.git
cd tc8-l2-test-framework

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m pytest tests/unit/ tests/self_validation/ -v
```

### Option 2: Docker

```bash
# Pull image
docker pull your-org/tc8-l2-test-framework:latest

# Run smoke tests
docker run --rm --network host \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/reports:/app/reports \
  tc8-l2-test-framework tc8 run --dut /app/config/dut_profiles/example_ecu.yaml --tier smoke
```

### Verify Installation

```bash
# Check framework version
python -m src.cli --version

# Run diagnostics
python -c "from src.utils.diagnostics import check_environment; check_environment()"

# List available specs
python -m src.cli specs
```

---

## Quick Start

### 1. Create a DUT Profile

Create `config/dut_profiles/my_ecu.yaml`:

```yaml
name: "My-ECU-4Port"
model: "XC2000"
firmware_version: "v2.1.0"
port_count: 4

ports:
  - port_id: 0
    interface_name: "eth0"  # Your test station interface
    mac_address: "02:00:00:00:00:00"
    speed_mbps: 100
    vlan_membership: [1, 100, 200]
    pvid: 1
    is_trunk: false
    
  - port_id: 1
    interface_name: "eth1"
    mac_address: "02:00:00:00:00:01"
    speed_mbps: 100
    vlan_membership: [1, 100, 200]
    pvid: 1
    is_trunk: true

# ... ports 2-3 ...

supported_features:
  - vlan
  - address_learning
  - filtering
  - qos

max_mac_table_size: 1024
mac_aging_time_s: 300
supports_double_tagging: false
can_reset: false
```

### 2. Run Smoke Tests (CLI)

```bash
# Execute smoke tier (~1 hour)
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier smoke \
  --output reports/smoke_run.html

# View results
open reports/smoke_run.html  # or: start reports/smoke_run.html (Windows)
```

### 3. Run Tests (Web UI)

```bash
# Start web server
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000

# Open browser: http://localhost:8000
# Select DUT profile, tier, click "Run Tests"
```

---

## DUT Configuration

### Port Mapping

Map DUT physical ports to test station network interfaces:

| DUT Port | Test Station Interface | How to Find |
|----------|------------------------|-------------|
| Port 0 | `eth0` | Linux: `ip link show` |
| Port 1 | `eth1` | Windows: `ipconfig /all` |
| Port 2 | `eth2` | Look for interface connected to DUT |

### VLAN Configuration

```yaml
ports:
  - port_id: 0
    vlan_membership: [1, 100, 200]  # VLANs this port belongs to
    pvid: 1                          # Default VLAN for untagged frames
    is_trunk: false                  # Access port (untagged)
    
  - port_id: 1
    vlan_membership: [1, 100, 200, 300, 400]
    pvid: 1
    is_trunk: true                   # Trunk port (tagged)
```

### Feature Flags

Enable/disable test sections based on DUT capabilities:

```yaml
supported_features:
  - vlan                # Section 5.3
  - address_learning    # Section 5.5
  - filtering           # Section 5.6
  - qos                 # Section 5.8
  # - time_sync         # Omit if gPTP not supported
  # - configuration     # Omit if config persistence not supported
```

---

## Running Tests

### Test Tiers

| Tier | Duration | Specs | Use Case |
|------|----------|-------|----------|
| **smoke** | ~1 hour | 10 | Quick validation, CI/CD |
| **core** | ~8 hours | 52 | Nightly regression |
| **full** | 40+ hours | 71 | Pre-release validation |

### CLI Commands

```bash
# List available specs
python -m src.cli specs

# Filter by section
python -m src.cli specs --section 5.3  # VLAN specs only

# Run specific tier
python -m src.cli run --dut my_ecu.yaml --tier smoke

# Run specific sections
python -m src.cli run --dut my_ecu.yaml --tier core --sections 5.3,5.5

# View test history
python -m src.cli history --limit 10

# Regenerate report
python -m src.cli report <report-id>
```

### Web Dashboard

```bash
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
# Open: http://localhost:8000
```

The web UI has **6 tabs**:

| Tab | Purpose |
|-----|--------|
| 🎛️ **Dashboard** | Spec coverage, recent test runs, mode badge |
| 🗺️ **Topology** | Live station ↔ DUT wiring diagram, connection status |
| 🔧 **DUT Configuration** | Create/load profiles, per-port interface mapping |
| 🚀 **Run Tests** | Select DUT + tier, execute with real-time progress |
| 🩺 **Pre-flight Checks** | Validate framework environment |
| 📋 **Console** | Real-time log streaming via WebSocket |

**DUT Configuration Tab**:
1. Select an existing profile from the dropdown, or create a new one
2. Fill in ECU name, model, firmware, port count, and feature flags
3. Map each DUT port to a test station OS interface using the **Port ↔ Interface Mapping** table — detected interfaces are auto-populated with link status (🟢 up / 🔴 down)
4. Click **Save Profile** to create the YAML file

**Run Tests Tab**:
1. Select a DUT profile and test tier (smoke/core/full)
2. Choose TC8 sections to include
3. Click **Start Test** — progress bar and live results appear
4. Click the report link when complete

---

## Topology & Mode Detection

The framework automatically detects your test station's network interfaces and determines whether you have real DUT hardware connected.

### Operating Modes

| Mode | Meaning | How Triggered |
|------|---------|---------------|
| 🟢 **ACTUAL** | Real DUT hardware detected | ≥1 mapped interface is link-UP |
| 🟡 **SIMULATION** | No hardware / all interfaces down | Default when no links active |

Mode badges appear on the **Dashboard** and **Topology** tabs. A warning banner appears on the **Run Tests** tab when in simulation mode.

### Interface Detection API

```
GET /api/interfaces
```

Returns all detected OS network interfaces with link status, MAC address, IP, speed, and MTU. Virtual/loopback interfaces are filtered out.

### Topology API

```
GET /api/topology
```

Returns the DUT ↔ station mapping, including per-port connection status (up / down / unmapped), the current operating mode, and active link count.

### Topology Diagram

The 🗺️ **Topology** tab shows a live wiring diagram:
- **Left box**: Test station interfaces with link status dots
- **Right box**: DUT ports (from loaded profile)
- **Wires**: Color-coded connections (🟢 active, 🔴 link down, gray dashed = unmapped)
- **Auto-refresh**: Updates every 5 seconds using OS-level interface status checks (`psutil`). **No packets are sent to the DUT** — the polling only reads the host NIC driver's link state, so it has zero impact on simulation or test execution.
- **Hover tooltips**: Show MAC address, IP, VLAN membership, PVID

---

## Understanding Reports

### Summary Section

```
Total Cases: 5,234
Passed: 5,102 (97.5%)
Failed: 98 (1.9%)
Informational: 34 (0.6%)
```

- **Pass**: DUT behaved as expected per TC8 spec
- **Fail**: DUT violated TC8 requirement (compliance issue)
- **Informational**: Observation only, not pass/fail
- **Skip**: Test not applicable to this DUT
- **Error**: Framework issue (not DUT fault)

### Section Breakdown

Each TC8 section shows pass rate:

| Section | Passed | Failed | Pass Rate |
|---------|--------|--------|-----------|
| 5.3 VLAN | 1,234 | 12 | 99.0% |
| 5.5 Address Learning | 987 | 45 | 95.6% |

### Detailed Results

Each test case shows:
- **Case ID**: `SWITCH_VLAN_001_P0_P1_VID100`
- **TC8 Reference**: `5.3.1` (links to spec clause)
- **Status**: PASS/FAIL
- **Message**: Human-readable explanation
- **Duration**: Execution time
- **Frames**: Sent/received counts

### Debugging Failures

**Example Failure**:
```
[FAIL] SWITCH_VLAN_001_P0_P1_VID100
Message: Expected frame on port 1, got drop
Expected: Forward tagged frame with VID=100
Actual: No frame received (timeout 500ms)
```

**Troubleshooting Steps**:
1. Check DUT VLAN configuration — is VID 100 configured?
2. Check port membership — is port 1 in VLAN 100?
3. Check trunk mode — is port 1 configured as trunk?
4. Review DUT logs for errors

---

## Troubleshooting

### Common Issues

#### Packet capture driver not installed

Scapy requires a packet capture driver for raw Ethernet I/O:

```bash
# Windows — install Npcap from https://npcap.com/
# Enable "WinPcap API-compatible Mode" during install

# Linux (Debian/Ubuntu)
sudo apt-get install libpcap-dev

# Linux (RHEL/Fedora)
sudo dnf install libpcap-devel

# macOS (if needed)
brew install libpcap
```

**Symptoms**: `OSError: No such device`, Scapy import errors, or `RuntimeError: Sniffing requires Npcap`.

#### "No module named 'scapy'"
```bash
pip install scapy>=2.5.0
```

#### "Permission denied" (Linux)
```bash
# Run with sudo for raw socket access
sudo python -m src.cli run --dut my_ecu.yaml --tier smoke

# Or: Add capabilities to Python binary
sudo setcap cap_net_raw,cap_net_admin=eip $(which python)
```

#### "Interface not found: eth0"
```bash
# List available interfaces
ip link show  # Linux
ipconfig /all  # Windows

# Update DUT profile with correct interface names
```

#### "Timing tests fail with ±50ms variance"
```bash
# Calibrate timing
python -c "from src.utils.diagnostics import calibrate_timing; calibrate_timing()"

# For <±10ms precision, use Linux with real-time kernel
```

#### "All tests timeout"
```bash
# Check DUT connectivity
ping <DUT_IP>

# Verify link status
ethtool eth0  # Linux
```

### Getting Help

- **GitHub Issues**: https://github.com/your-org/tc8-l2-test-framework/issues
- **Documentation**: https://tc8-l2-docs.readthedocs.io
- **Email**: tc8-support@your-org.com

---

## Next Steps

- **Tutorial**: [Quick Start Walkthrough](tutorials/01_quick_start.md)
- **Advanced**: [Creating Custom DUT Profiles](tutorials/02_custom_dut_profile.md)
- **CI/CD**: [Jenkins/GitLab Integration](tutorials/04_ci_cd_integration.md)
- **Developer Guide**: [Extending the Framework](developer_guide.md)
