# TC8 Layer 2 Test Framework — User Guide

> **Version:** 0.1.0 | **Standard:** OPEN Alliance TC8 Layer 2 v3.0

## Table of Contents

1. [Installation](#1-installation)
2. [What the Application Does](#2-what-the-application-does)
3. [Minimum Test Setup](#3-minimum-test-setup)
4. [Verifying Your ECU Test Setup](#4-verifying-your-ecu-test-setup)
5. [DUT Profile Configuration](#5-dut-profile-configuration)
6. [Running Tests](#6-running-tests)
7. [Debugging](#7-debugging)
8. [Downloading Reports](#8-downloading-reports)
9. [Known Limitations & Incomplete Features](#9-known-limitations--incomplete-features)

---

## 1. Installation

### Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.10+ (3.11 recommended) |
| **OS** | Windows 10/11, Linux, macOS |
| **Permissions** | Windows: Run as Administrator; Linux: `sudo` or `cap_net_raw` capability |
| **Packet driver** | Required for Scapy raw Ethernet I/O (see table below) |

**Packet Capture Driver:**

| OS | Required | Install |
|----|----------|---------|
| Windows | [Npcap](https://npcap.com/) | Download installer; enable **"WinPcap API-compatible Mode"** |
| Linux (Debian/Ubuntu) | libpcap-dev | `sudo apt-get install libpcap-dev` |
| Linux (RHEL/Fedora) | libpcap-devel | `sudo dnf install libpcap-devel` |
| macOS | libpcap (pre-installed) | `brew install libpcap` only if needed |

> Without a packet capture driver, the framework starts but cannot send or receive real Ethernet frames — only simulation mode will work.

### Install Steps

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # Linux/macOS
# or: venv\Scripts\activate       # Windows PowerShell

# 2. Install dependencies
pip install -r requirements.txt
```

**Docker alternative:**
```bash
docker-compose up -d
# Web UI available at: http://localhost:8000
```

### Verify Installation

```bash
python -m pytest tests/ -v
# Expected: 52 passed
```

---

## 2. What the Application Does

The TC8 Layer 2 Test Framework validates automotive Ethernet ECU switching behavior against the **OPEN Alliance TC8 specification v3.0**. It sends and captures raw Ethernet frames via connected NICs and checks that the DUT (Device Under Test — your ECU's Ethernet switch) behaves exactly as the TC8 spec requires.

### TC8 v3.0 Conformance Tests (SWITCH_*)

| TC8 Section | Topic | Specs | Runnable on PC+DUT |
|---|---|---|---|
| 5.3 | VLAN Testing (tagging, PVID, trunks, double-tagging) | 21 | ✅ All |
| 5.4 | General Switching (unicast, broadcast, frame sizes) | 10 | ✅ (runt frames: Linux only) |
| 5.5 | Address Learning (MAC table, aging, port migration) | 21 | ✅ All |
| 5.6 | Filtering (unicast/multicast/broadcast filtering) | 11 | ⚠️ Storm control needs tgen |
| 5.7 | Time Synchronization (gPTP prerequisites) | 1 | ❌ TSN NIC required |
| 5.8 | Quality of Service (PCP priority queuing) | 4 | ⚠️ Rate accuracy needs tgen |
| 5.9 | Configuration (startup, persistence) | 3 | ✅ All |
| **TC8 Total** | | **71** | |

### Extended Automotive Tests (EXT_*)

These tests go beyond TC8 scope but are essential for automotive ECU validation programs. They use the `EXT_<CATEGORY>_NNN` ID format to be clearly distinct from TC8 compliance specs.

| Prefix | Topic | Specs | Runnable on PC+DUT |
|---|---|---|---|
| EXT_TSN | TSN / gPTP (802.1AS, Qbv, Qav, Qci) | 10 | ❌ TSN NIC required |
| EXT_PHY | Automotive PHY (100BASE-T1, 1000BASE-T1) | 8 | ⚠️ Link flap only (EXT_PHY_002) |
| EXT_MGMT | DUT management channel (DoIP/UDS) | 5 | ⚠️ DoIP not yet implemented |
| EXT_ORACLE | Golden device / virtual oracle | 4 | ✅ Linux virtual bridge |
| EXT_PERF | Performance / traffic generation | 6 | ⚠️ Basic burst only |
| **EXT_* Total** | | **33** | |
| **Grand Total** | | **104 specs → 200,000+ test cases** | |

> Tests that require unavailable hardware return **SKIP** (hardware absent) or **INFORMATIONAL** (partially observable). They never return ERROR due to a missing device. The web UI shows hardware badges per section and warns before running hardware-gated tests.
>
> For the full list of incomplete features and the path to completing them, see [docs/known_limitations.md](known_limitations.md).

### Execution Tiers

| Tier | Duration | Specs | Typical Use |
|------|----------|-------|-------------|
| **smoke** | ~1 hour | 10 | Quick validation, CI/CD gate |
| **core** | ~8 hours | 52 | Nightly regression |
| **full** | 40+ hours | 104 | Pre-release compliance (includes EXT_*) |

### Outputs

- **HTML report** — interactive, filterable results with frame-level detail and log entries
- **SQLite database** — historical results with trend analysis at `reports/test_results.db`
- **Web dashboard** — real-time progress, topology diagram, report history

---

## 3. Minimum Test Setup

### Simulation Mode (No Hardware Required)

Run a smoke test against the built-in NullDUT simulator:

```bash
python -m src.cli run \
  --dut config/dut_profiles/examples/simulation_dut.yaml \
  --tier smoke \
  --output reports/smoke_simulation.html
```

This confirms the framework is installed correctly and produces a sample report.

### Physical DUT Mode

Minimum hardware requirements:
- Test station with at least **2 NICs** connected to different DUT ports
- Npcap (Windows) or libpcap (Linux) installed
- A DUT profile YAML that maps your NIC names to DUT port IDs (see [Section 5](#5-dut-profile-configuration))

**Minimum physical wiring (2-port test):**

```
Test Station NIC 0 (eth0)  ───── DUT Port 0
Test Station NIC 1 (eth1)  ───── DUT Port 1
```

For full spec coverage, connect all DUT ports. Tests that require ports not connected will be marked SKIP automatically.

### Network Topology Diagram

The web dashboard **Topology** tab shows a live wiring diagram of your test station interfaces and DUT ports, color-coded by link state. Start the web server and open it to visually confirm your wiring before running tests:

```bash
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
# Open: http://localhost:8000 → Topology tab
```

---

## 4. Verifying Your ECU Test Setup

Before running a full test tier, confirm that the framework can communicate with the DUT.

### Step 1 — List Detected Interfaces

```bash
# Linux
ip link show

# Windows PowerShell
ipconfig /all

# Via web API (when server running)
curl http://localhost:8000/api/interfaces
```

Match the interface names shown to the ports in your DUT profile.

### Step 2 — Check Link State

Each interface connected to the DUT should show link UP. In the web dashboard, the **Topology** tab displays 🟢 (up) or 🔴 (down) for each interface. From the command line:

```bash
# Linux
ethtool eth0   # look for "Link detected: yes"

# Windows — check Device Manager or use the web UI
```

If a link shows as down, check the cable and confirm the DUT is powered on.

### Step 3 — Verify DUT Responds

Run a single unicast forwarding spec to confirm end-to-end communication:

```bash
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --spec SWITCH_GEN_001 \
  --output reports/connectivity_check.html
```

A PASS result means the DUT forwarded the frame correctly. A FAIL or timeout means a wiring or configuration problem — see [Section 7 (Debugging)](#7-debugging).

### Step 4 — Check Operating Mode

The web dashboard shows a mode badge on the Dashboard tab:

| Badge | Meaning |
|---|---|
| 🟢 ACTUAL | ≥1 mapped interface has link UP — real DUT testing |
| 🟡 SIMULATION | No active links — NullDUT mode |

A test run in SIMULATION mode exercises the framework logic but does not test the physical DUT. Ensure the mode badge shows ACTUAL before starting a compliance run.

### Common Pre-Flight Failures

| Symptom | Likely Cause | Fix |
|---|---|---|
| `OSError: No such device` | Npcap not installed or wrong interface name | Install Npcap; check interface name in DUT profile |
| `Permission denied` (Linux) | Missing raw socket capability | Run with `sudo`, or `sudo setcap cap_net_raw,cap_net_admin=eip $(which python)` |
| `No frames received (timeout)` | Link down or DUT not forwarding | Check cable, DUT power, DUT VLAN config |
| `Interface not found: eth0` | Wrong name in DUT profile | Run `ip link show` and update the profile |

---

## 5. DUT Profile Configuration

A DUT profile is a YAML file that tells the framework about your ECU: how many ports it has, which test station network interfaces are wired to each port, and what features the ECU supports.

### Why It's Needed

The framework must know:
- Which NIC to send frames from (ingress port)
- Which NICs to listen on for forwarded frames (egress ports)
- What VLANs each port belongs to (so test case generation matches ECU config)
- What optional features the ECU supports (so irrelevant test sections are skipped)

### Field Reference

```yaml
# ── Identity ───────────────────────────────────────────────────────────
name: "MyCompany-ECU-4Port"
  # Human-readable name shown in reports

model: "XC2000-4P"
  # ECU model identifier (informational, used in reports)

firmware_version: "v2.1.0"
  # Firmware version under test (informational, logged in reports)

port_count: 4
  # Total number of Ethernet ports on the ECU switch.
  # Must match the number of entries in the ports list below.

# ── Port Configuration ─────────────────────────────────────────────────
ports:
  - port_id: 0
    # Logical port number used throughout the framework (0-based).
    # Test case IDs include this: e.g. SWITCH_VLAN_001_P0_P1_VID100

    interface_name: "eth0"
    # Name of the test station NIC wired to this DUT port.
    # Linux: from `ip link show` (e.g. eth0, enp3s0, eno1)
    # Windows: adapter name from `ipconfig /all` (e.g. "Ethernet 2")

    mac_address: "02:00:00:00:00:00"
    # MAC address of this DUT port. Used to build learning frames.
    # Find this on the ECU datasheet or with a network scanner.
    # Use locally-administered MAC format (second bit of first byte = 1)
    # for test-only addresses: 02:xx:xx:xx:xx:xx

    speed_mbps: 100
    # Port link speed in Mbps. Used for timing calculations.
    # Typical values: 10, 100, 1000

    vlan_membership: [1, 100, 200]
    # List of VLAN IDs this port belongs to.
    # Must reflect the actual VLAN configuration on the ECU.
    # The framework only generates test cases for VLANs listed here.

    pvid: 1
    # Port VLAN ID (native VLAN). Untagged frames arriving on this
    # port are assigned this VLAN ID by the ECU switch.
    # Must be one of the values in vlan_membership.

    is_trunk: false
    # false = access port: sends and receives untagged frames only.
    # true  = trunk port: carries tagged frames for multiple VLANs.
    # Must match the ECU port configuration.

# ── Capabilities ───────────────────────────────────────────────────────
max_mac_table_size: 1024
  # Maximum number of MAC entries the ECU switch can learn.
  # From ECU datasheet. Used in address learning stress tests.

mac_aging_time_s: 300
  # How long (seconds) the ECU keeps an unused MAC entry before
  # removing it. From ECU datasheet. Used in aging tests.
  # Typical values: 30–300 seconds.

supports_double_tagging: false
  # true if the ECU supports Q-in-Q (802.1ad / double VLAN tagging).
  # Enables Section 5.3 double-tagging test cases.

supports_gptp: false
  # true if the ECU supports gPTP (IEEE 802.1AS time synchronization).
  # Enables Section 5.7 time sync test case.

can_reset: false
  # true if the test framework can trigger an ECU reset (power cycle
  # or software reset). Enables startup time and reset behavior tests.
  # Leave false unless you have a controlled reset mechanism.
```

### Annotated Example — 4-Port ECU

```yaml
name: "MyCompany-ECU-Gateway"
model: "XC2000-4P"
firmware_version: "v2.1.0"
port_count: 4

ports:
  - port_id: 0
    interface_name: "eth0"
    mac_address: "02:00:00:00:00:00"
    speed_mbps: 100
    vlan_membership: [1]
    pvid: 1
    is_trunk: false

  - port_id: 1
    interface_name: "eth1"
    mac_address: "02:00:00:00:00:01"
    speed_mbps: 100
    vlan_membership: [1, 100, 200]
    pvid: 1
    is_trunk: true

  - port_id: 2
    interface_name: "eth2"
    mac_address: "02:00:00:00:00:02"
    speed_mbps: 100
    vlan_membership: [100]
    pvid: 100
    is_trunk: false

  - port_id: 3
    interface_name: "eth3"
    mac_address: "02:00:00:00:00:03"
    speed_mbps: 100
    vlan_membership: [200]
    pvid: 200
    is_trunk: false

max_mac_table_size: 1024
mac_aging_time_s: 300
supports_double_tagging: false
supports_gptp: false
can_reset: false
```

Save as `config/dut_profiles/my_ecu.yaml`.

### Validate the Profile

```bash
python -c "
from src.core.config_manager import ConfigManager
cm = ConfigManager()
p = cm.load_dut_profile('config/dut_profiles/my_ecu.yaml')
print(f'OK: {p.name}, {p.port_count} ports')
"
```

### Finding Interface Names

**Linux:**
```bash
ip link show
# Look for interfaces that show "state UP" when DUT cable is connected
```

**Windows:**
```powershell
ipconfig /all
# Look for "Ethernet adapter" sections with a Default Gateway or physical address
```

**Via web UI:** Open the **DUT Configuration** tab at `http://localhost:8000`. It auto-lists all detected interfaces with live link status — click to assign an interface to each DUT port.

---

## 6. Running Tests

### CLI

```bash
# Smoke tier (~1 hour)
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier smoke

# Core tier (~8 hours)
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier core

# Full tier (40+ hours)
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier full

# Specific sections only
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier core \
  --sections 5.3,5.5

# Single spec (useful for debugging)
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --spec SWITCH_GEN_001

# Save report to specific path
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier smoke \
  --output reports/my_run.html
```

### Web Dashboard

```bash
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and use the **Run Tests** tab:

1. Select DUT profile from the dropdown (or create one in the **DUT Configuration** tab)
2. Select test tier (smoke / core / full)
3. Choose sections — each section shows a hardware badge:

   | Badge | Meaning |
   |---|---|
   | **PC+DUT** (green) | Runs reliably on any setup |
   | **Linux req.** (yellow) | Requires Linux AF_PACKET or bridge-utils |
   | **Tgen needed** (orange) | Results are indicative; accurate measurement needs dedicated traffic generator |
   | **HW required** (red) | Will always return SKIP on a basic PC+DUT setup |

4. Click **Start Test** — if any selected sections include hardware-gated tests, a **pre-run warning dialog** appears listing which specs will be SKIP/INFORMATIONAL and why. Choose **Run All**, **Skip HW-Gated Tests**, or **Cancel**.
5. Watch the progress bar and live result stream
6. Click the report link when the run completes

> **EXT_* sections are unchecked by default.** Tick them to include extended automotive tests. Be aware of their hardware requirements shown by the badge.

### Stopping a Run

Press `Ctrl+C` in the terminal (CLI) or click **Stop** in the web UI. Results collected so far are saved to the database.

---

## 7. Debugging

### Increase Log Verbosity

```bash
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier smoke \
  --log-level DEBUG
```

DEBUG output shows every frame sent and received, per-port capture counts, and session setup/teardown events.

### Reading the HTML Report

Each test case row in the report is clickable and expands to show:
- **Expected vs. Actual**: What the framework expected the DUT to do and what it observed
- **Frame details**: Hexdump of sent frames, per-port received frame counts
- **Log entries**: Session setup/teardown logs, per-case debug messages with timestamps

Log entries are color-coded by level: INFO (blue), DEBUG (gray), WARNING (orange), ERROR (red).

### Running a Single Spec

Isolate a failing spec to see detailed output:

```bash
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --spec SWITCH_VLAN_001 \
  --log-level DEBUG
```

### Scapy / Packet Capture Troubleshooting

**Symptom**: `RuntimeError: Sniffing requires Npcap` or `OSError: No such device`
```bash
# Windows: install Npcap from https://npcap.com/
# Enable "WinPcap API-compatible Mode" during install
```

**Symptom**: `PermissionError` on Linux
```bash
# Option A: run with sudo
sudo python -m src.cli run --dut my_ecu.yaml --tier smoke

# Option B: grant capabilities once (survives reboots)
sudo setcap cap_net_raw,cap_net_admin=eip $(which python)
```

**Symptom**: Frames sent but none captured on egress ports
- Confirm cables are connected and link is UP (`ethtool eth0` on Linux)
- Confirm the DUT VLAN configuration matches the profile (`vlan_membership`, `pvid`, `is_trunk`)
- Check if the DUT's NIC driver strips VLAN tags before delivery (Windows Npcap known issue — enable VLAN passthrough in Npcap settings)

### Interpreting Result Statuses

| Status | Meaning | Action |
|---|---|---|
| **PASS** | DUT behaved as TC8 requires | None |
| **FAIL** | DUT violated a TC8 requirement | Investigate DUT config or firmware |
| **INFORMATIONAL** | Observation logged, no pass/fail verdict (e.g. hardware partially observable) | Review for context; not a compliance verdict |
| **SKIP** | Test not applicable — hardware not connected, feature disabled, or hardware-gated spec on a PC+DUT setup | Acceptable when the reason is expected (see below) |
| **ERROR** | Framework exception, not a DUT fault | Check logs; may indicate misconfiguration |

**SKIP is expected (not a problem) for:**
- `SWITCH_TIME_001` — gPTP requires a TSN NIC with hardware timestamps
- `SWITCH_GEN_007` — runt frame injection requires Linux or hardware tgen
- All `EXT_TSN_*` — require TSN NIC (EXT_TSN_010 returns INFORMATIONAL instead)
- Most `EXT_PHY_*` — require media converter or PHY hardware
- `EXT_PERF_001/002/003/004/005` — require dedicated traffic generator

**SKIP is unexpected (investigate) for:**
- Any `SWITCH_VLAN_*`, `SWITCH_ADDR_*`, `SWITCH_GEN_001–006` — should always run on PC+DUT
- Any spec with a `setup_requirement: pc_only` where the DUT profile is loaded correctly

### Common FAIL Patterns

**"Expected frame on port X, got nothing"**
- DUT dropped the frame or sent it to a different port
- Check VLAN membership and port configuration

**"VLAN tag mismatch: expected VID=100, got VID=0"**
- DUT stripped or replaced the VLAN tag
- Check DUT trunk/access mode and PVID settings

**"Frame received on port X (should not forward there)"**
- DUT flooded instead of forwarding to the learned port
- May indicate MAC learning is not working — check DUT logs

---

## 8. Downloading Reports

### HTML Report

Reports are auto-saved to `reports/archives/` after every run with a timestamped filename. Open any `.html` file in a browser — no server needed, all data is embedded.

```bash
# Windows
start reports\archives\tc8_run_2026-05-16_143022.html

# Linux
xdg-open reports/archives/tc8_run_2026-05-16_143022.html
```

### Download via Web UI

In the web dashboard:
1. Open the **Reports** tab
2. Find your run in the history table
3. Click **Download** to save the HTML file

### SQLite Database

All results are stored in `reports/test_results.db`. Query with any SQLite client:

```bash
sqlite3 reports/test_results.db
> SELECT report_id, passed, failed, duration_s FROM test_runs ORDER BY created_at DESC LIMIT 10;
```

### List Recent Reports (CLI)

```bash
python -m src.cli history --limit 10

# Re-generate HTML for a specific run
python -m src.cli report <report-id>
```

---

## 9. Known Limitations & Incomplete Features

The framework is under active development. Several features are partially implemented or require hardware that may not be available in your setup.

**Key incomplete items (summary):**

| Feature | Status |
|---|---|
| Hardware traffic generator (line-rate, accurate pps) | Not built — `ScapyTrafficGen` provides burst-only at ±30% accuracy |
| TSN / gPTP hardware timestamping | Not built — all EXT_TSN_* return SKIP |
| Automotive PHY media converter control | Not built — EXT_PHY_002 (link flap via psutil) is the only runnable PHY test |
| DoIP / UDS client for ECU management | Not built — EXT_MGMT_001/002 return INFORMATIONAL |
| Virtual oracle (Linux bridge / OVS integration) | Not built — EXT_ORACLE_001–003 return INFORMATIONAL on Linux |
| PCAP capture export (`.pcap` files alongside results) | Not built |
| Traceability matrix CSV export | Not built |
| PCP / payload size parameter expansion | Partial — test cases use PCP=0 and fixed payload size |

For the full list with root causes, impact analysis, and path-to-resolution for each item, see **[docs/known_limitations.md](known_limitations.md)**.
