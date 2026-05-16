# Mapping Physical Connections to a DUT Profile

> **Goal**: Wire your ECU to the test station and record the port mapping  
> **Time**: 10–15 minutes  
> **Prerequisites**: ECU powered on, Ethernet cables connecting DUT ports to test station NICs

For a full explanation of every DUT profile field and what it means, see [User Guide § 5 — DUT Profile Configuration](../user_guide.md#5-dut-profile-configuration).

---

## Step 1: Gather ECU Information

Before touching YAML, collect from the ECU datasheet:

| Item | Where to find | Example |
|---|---|---|
| Number of ports | Datasheet | 4 |
| MAC address per port | Datasheet / config tool | `02:AA:BB:CC:DD:EE` |
| VLAN configuration | Config tool or default spec | VID 1 (all ports), VID 100 (ports 1–2) |
| MAC table size | Datasheet | 1024 entries |
| MAC aging time | Datasheet | 300 s |
| QoS / gPTP support | Datasheet | Yes / No |

---

## Step 2: Map Physical Connections

Connect one cable from each DUT port to a dedicated NIC on the test station. Then identify the NIC names the OS assigned to each connection.

**Linux:**
```bash
ip link show
# Unplug/replug each cable and watch which interface toggles state
```

**Windows (PowerShell):**
```powershell
ipconfig /all
# Look for Ethernet adapters — "Description" shows NIC model
```

**Via web UI (easiest):**
```bash
uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
# Open: http://localhost:8000 → DUT Configuration tab
# The Port ↔ Interface Mapping table lists all detected interfaces
# with live link status (🟢 up / 🔴 down). Select from dropdown.
```

**Example mapping table:**

| DUT Port | Test Station Interface | Cable color |
|---|---|---|
| Port 0 | `eth0` (Linux) / `Ethernet 2` (Windows) | Blue |
| Port 1 | `eth1` / `Ethernet 3` | Red |
| Port 2 | `eth2` / `Ethernet 4` | Green |
| Port 3 | `eth3` / `Ethernet 5` | Yellow |

---

## Step 3: Create the DUT Profile YAML

Create `config/dut_profiles/my_ecu.yaml` using the mapping table above. See [User Guide § 5](../user_guide.md#5-dut-profile-configuration) for the meaning of every field.

**Common configurations:**

### 4-Port Basic Switch (All Access, VLAN 1)

```yaml
name: "ECU-4Port-Basic"
model: "XC2000"
firmware_version: "v2.1.0"
port_count: 4

ports:
  - {port_id: 0, interface_name: "eth0", mac_address: "02:00:00:00:00:00", speed_mbps: 100, vlan_membership: [1], pvid: 1, is_trunk: false}
  - {port_id: 1, interface_name: "eth1", mac_address: "02:00:00:00:00:01", speed_mbps: 100, vlan_membership: [1], pvid: 1, is_trunk: false}
  - {port_id: 2, interface_name: "eth2", mac_address: "02:00:00:00:00:02", speed_mbps: 100, vlan_membership: [1], pvid: 1, is_trunk: false}
  - {port_id: 3, interface_name: "eth3", mac_address: "02:00:00:00:00:03", speed_mbps: 100, vlan_membership: [1], pvid: 1, is_trunk: false}

max_mac_table_size: 1024
mac_aging_time_s: 300
supports_double_tagging: false
supports_gptp: false
can_reset: false
```

### 8-Port Gateway (Mixed Trunk/Access, Multiple VLANs)

```yaml
name: "ECU-8Port-Gateway"
port_count: 8

ports:
  - {port_id: 0, interface_name: "eth0", mac_address: "02:00:00:00:00:00", speed_mbps: 1000, vlan_membership: [1, 100, 200, 300], pvid: 1,   is_trunk: true}   # Backbone trunk
  - {port_id: 1, interface_name: "eth1", mac_address: "02:00:00:00:00:01", speed_mbps: 100,  vlan_membership: [100],             pvid: 100, is_trunk: false}  # Sensor network
  - {port_id: 2, interface_name: "eth2", mac_address: "02:00:00:00:00:02", speed_mbps: 100,  vlan_membership: [100],             pvid: 100, is_trunk: false}
  - {port_id: 3, interface_name: "eth3", mac_address: "02:00:00:00:00:03", speed_mbps: 100,  vlan_membership: [200],             pvid: 200, is_trunk: false}  # Actuator network
  - {port_id: 4, interface_name: "eth4", mac_address: "02:00:00:00:00:04", speed_mbps: 100,  vlan_membership: [200],             pvid: 200, is_trunk: false}
  - {port_id: 5, interface_name: "eth5", mac_address: "02:00:00:00:00:05", speed_mbps: 100,  vlan_membership: [300],             pvid: 300, is_trunk: false}  # ADAS network
  - {port_id: 6, interface_name: "eth6", mac_address: "02:00:00:00:00:06", speed_mbps: 100,  vlan_membership: [300],             pvid: 300, is_trunk: false}
  - {port_id: 7, interface_name: "eth7", mac_address: "02:00:00:00:00:07", speed_mbps: 100,  vlan_membership: [1],               pvid: 1,   is_trunk: false}  # Diagnostics

max_mac_table_size: 4096
mac_aging_time_s: 300
supports_double_tagging: false
supports_gptp: true
can_reset: false
```

---

## Step 4: Validate the Profile

```bash
python -c "
from src.core.config_manager import ConfigManager
cm = ConfigManager()
p = cm.load_dut_profile('config/dut_profiles/my_ecu.yaml')
print(f'OK: {p.name}, {p.port_count} ports')
"
```

---

## Step 5: Verify Connectivity Then Run Tests

Follow [User Guide § 4](../user_guide.md#4-verifying-your-ecu-test-setup) to verify links are up and the DUT responds, then start testing per [User Guide § 6](../user_guide.md#6-running-tests).

---

## Troubleshooting

| Error | Fix |
|---|---|
| `port_count mismatch` | `port_count` must equal the number of items in the `ports` list |
| `Interface not found: eth0` | Run `ip link show` / `ipconfig /all` and use the exact name shown |
| `MAC address invalid` | Format must be `XX:XX:XX:XX:XX:XX` (hex bytes, colon-separated) |
| VLAN tests fail | Check `vlan_membership`, `pvid`, and `is_trunk` match your ECU's actual VLAN config |
| `pvid not in vlan_membership` | `pvid` must be one of the values listed in `vlan_membership` |
