# Creating Custom DUT Profiles

> **Goal**: Create a DUT profile for your automotive ECU  
> **Time**: 10-15 minutes  
> **Prerequisites**: ECU datasheet, network interface names

## Overview

A DUT profile tells the framework:
- How many ports your ECU has
- Which test station interfaces connect to each port
- What features your ECU supports (VLAN, QoS, etc.)
- MAC table size, aging time, and other capabilities

## Step 1: Gather ECU Information

You'll need:

| Information | Where to Find | Example |
|-------------|---------------|---------|
| **Port count** | ECU datasheet | 4 ports |
| **MAC table size** | Datasheet / config tool | 1024 entries |
| **MAC aging time** | Datasheet / default config | 300 seconds |
| **Supported VLANs** | Config tool / spec | VID 1-4094 |
| **QoS support** | Datasheet | Yes/No |
| **gPTP support** | Datasheet | Yes/No |

## Step 2: Map Physical Connections

Connect your test station to the ECU and identify interface names:

### Windows
```powershell
ipconfig /all
```
Look for adapters connected to ECU (e.g., `Ethernet 2`, `Ethernet 3`)

### Linux
```bash
ip link show
```
Look for interfaces connected to ECU (e.g., `eth0`, `eth1`, `enp0s3`)

**Example mapping**:
| DUT Port | Test Station Interface | Cable |
|----------|------------------------|-------|
| Port 0 | `eth0` (Linux) or `Ethernet 2` (Windows) | Blue cable |
| Port 1 | `eth1` or `Ethernet 3` | Red cable |
| Port 2 | `eth2` or `Ethernet 4` | Green cable |
| Port 3 | `eth3` or `Ethernet 5` | Yellow cable |

> **💡 Tip: Auto-Detection via Web UI**
>
> Instead of running `ipconfig` / `ip link` manually, you can use the Web Dashboard:
> 1. Start the server: `uvicorn web.backend.main:app --port 8000`
> 2. Open http://localhost:8000 → **🔧 DUT Configuration** tab
> 3. The **Port ↔ Interface Mapping** table auto-detects your OS interfaces with live link status (🟢 up / 🔴 down)
> 4. Select interfaces from the dropdown for each DUT port
>
> You can also call `GET /api/interfaces` to list all detected interfaces programmatically.

## Step 3: Create DUT Profile YAML

Create `config/dut_profiles/my_ecu.yaml`:

```yaml
# Basic Information
name: "MyCompany-ECU-Gateway"
model: "XC2000-4P"
firmware_version: "v2.1.0"
port_count: 4

# Port Configuration
ports:
  # Port 0 - Access port, VLAN 1
  - port_id: 0
    interface_name: "eth0"              # ← Change to your interface
    mac_address: "02:00:00:00:00:00"    # ← Port's MAC address
    speed_mbps: 100
    vlan_membership: [1]                # VLANs this port belongs to
    pvid: 1                             # Default VLAN for untagged frames
    is_trunk: false                     # Access port (untagged only)
    
  # Port 1 - Trunk port, VLANs 1, 100, 200
  - port_id: 1
    interface_name: "eth1"
    mac_address: "02:00:00:00:00:01"
    speed_mbps: 100
    vlan_membership: [1, 100, 200]
    pvid: 1
    is_trunk: true                      # Trunk port (tagged frames)
    
  # Port 2 - Access port, VLAN 100
  - port_id: 2
    interface_name: "eth2"
    mac_address: "02:00:00:00:00:02"
    speed_mbps: 100
    vlan_membership: [100]
    pvid: 100
    is_trunk: false
    
  # Port 3 - Access port, VLAN 200
  - port_id: 3
    interface_name: "eth3"
    mac_address: "02:00:00:00:00:03"
    speed_mbps: 100
    vlan_membership: [200]
    pvid: 200
    is_trunk: false

# Feature Support (enable sections to test)
supported_features:
  - vlan                # Section 5.3 - VLAN Testing
  - address_learning    # Section 5.5 - Address Learning
  - filtering           # Section 5.6 - Filtering
  - qos                 # Section 5.8 - QoS
  # - time_sync         # Section 5.7 - Uncomment if gPTP supported
  # - configuration     # Section 5.9 - Uncomment if config persistence supported

# Capabilities
max_mac_table_size: 1024        # From datasheet
mac_aging_time_s: 300           # From datasheet (5 minutes)
supports_double_tagging: false  # Q-in-Q / 802.1ad support
supports_gptp: false            # gPTP / 802.1AS support
can_reset: false                # Can DUT be power-cycled between tests?

# Notes
notes: |
  XC2000 gateway ECU with 4 100BASE-T1 ports.
  Port 0: Diagnostic interface (VLAN 1)
  Port 1: Backbone trunk (VLANs 1, 100, 200)
  Port 2: Sensor network (VLAN 100)
  Port 3: Actuator network (VLAN 200)
```

## Step 4: Validate Profile

```bash
# Check if profile parses correctly
python -c "
from src.core.config_manager import ConfigManager
cm = ConfigManager()
profile = cm.load_dut_profile('config/dut_profiles/my_ecu.yaml')
print(f'✅ Profile valid: {profile.name}')
print(f'   Ports: {profile.port_count}')
print(f'   Features: {profile.supported_features}')
"
```

Expected output:
```
✅ Profile valid: MyCompany-ECU-Gateway
   Ports: 4
   Features: ['vlan', 'address_learning', 'filtering', 'qos']
```

## Step 5: Run Tests

```bash
# Start with smoke tier
python -m src.cli run \
  --dut config/dut_profiles/my_ecu.yaml \
  --tier smoke \
  --output reports/my_ecu_smoke.html
```

## Common Configurations

### 4-Port Basic Switch (All Access Ports)
```yaml
port_count: 4
ports:
  - {port_id: 0, interface_name: "eth0", mac_address: "02:00:00:00:00:00", vlan_membership: [1], pvid: 1, is_trunk: false}
  - {port_id: 1, interface_name: "eth1", mac_address: "02:00:00:00:00:01", vlan_membership: [1], pvid: 1, is_trunk: false}
  - {port_id: 2, interface_name: "eth2", mac_address: "02:00:00:00:00:02", vlan_membership: [1], pvid: 1, is_trunk: false}
  - {port_id: 3, interface_name: "eth3", mac_address: "02:00:00:00:00:03", vlan_membership: [1], pvid: 1, is_trunk: false}
```

### 8-Port Gateway (Mixed Trunk/Access)
```yaml
port_count: 8
ports:
  - {port_id: 0, interface_name: "eth0", mac_address: "02:00:00:00:00:00", vlan_membership: [1, 100, 200, 300], pvid: 1, is_trunk: true}   # Backbone
  - {port_id: 1, interface_name: "eth1", mac_address: "02:00:00:00:00:01", vlan_membership: [100], pvid: 100, is_trunk: false}  # Sensor 1
  - {port_id: 2, interface_name: "eth2", mac_address: "02:00:00:00:00:02", vlan_membership: [100], pvid: 100, is_trunk: false}  # Sensor 2
  # ... etc
```

## Troubleshooting

### "Port count mismatch"
Ensure `port_count` matches the number of items in `ports` list.

### "Interface not found: eth0"
- **Linux**: Run `ip link show` and use exact interface name
- **Windows**: Run `ipconfig /all` and use adapter name (may have spaces)

### "MAC address invalid"
Format must be `XX:XX:XX:XX:XX:XX` (colon-separated hex bytes).

### "VLAN tests fail"
1. Check `vlan_membership` — does it match ECU config?
2. Check `is_trunk` — trunk ports carry tagged frames, access ports don't
3. Check `pvid` — must be in `vlan_membership` list

## Next Steps

- [Interpreting Test Results](03_interpreting_results.md)
- [CI/CD Integration](04_ci_cd_integration.md)
- [User Guide](../user_guide.md)
