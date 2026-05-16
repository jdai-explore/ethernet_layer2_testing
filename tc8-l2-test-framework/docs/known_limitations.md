# Known Limitations & Incomplete Features

> **Version:** 0.1.0 | Updated: 2026-05-16

This file is the authoritative record of features that are partially implemented, architecturally deferred, or require hardware not available on a basic PC + DUT setup. It is intended for engineers integrating this framework into a test program who need to know what to trust and what to treat as indicative only.

---

## 1. Traffic Generation — Rate Accuracy

**What is implemented:** `ScapyTrafficGen` (`src/interface/scapy_traffic_gen.py`) — Scapy-based burst sender. Sends frames in a loop, measures achieved pps and Mbps, returns a `BurstResult` or `ThroughputResult`.

**What is NOT implemented / not accurate:**
- **Sustained line-rate traffic** (100 Mbps) — Scapy on a standard PC NIC achieves 5–20 Mbps maximum due to Python GIL and OS scheduler overhead.
- **Accurate inter-frame gap control** — gaps below ~1 ms are not reliably achievable.
- **Hardware traffic generator integration** — `BaseTrafficGen` (`src/interface/base_traffic_gen.py`) defines the abstraction. A `HardwareTrafficGen` subclass (Ixia, Spirent, or open-source `TRex`) has not been implemented.

**Impact on test results:**
| Test | Impact |
|---|---|
| `SWITCH_FILT_008` (storm control threshold) | Results are indicative only — threshold accuracy ±30% |
| `SWITCH_QOS_*` (rate-accurate priority) | Priority order observable; rate claims not verifiable |
| `EXT_PERF_001` (sustained 100 Mbps) | Returns SKIP — cannot achieve line rate with Scapy |
| `EXT_PERF_002` (burst storm control) | Returns SKIP — same rate accuracy issue |
| `EXT_PERF_003/004/005` | Returns SKIP — require hardware tgen with HW timestamps |
| `EXT_PERF_006` (multicast burst) | Runs — single-frame Scapy burst, not sustained load |

**Path to resolution:** Implement `HardwareTrafficGen` subclass for your specific tgen hardware and register it in the runner when available.

---

## 2. TSN / gPTP Tests — Hardware Timestamping Required

**What is implemented:** All 10 `EXT_TSN_*` spec handlers exist and return `SKIP` with a descriptive message. `EXT_TSN_010` (Announce/Sync timeout) returns `INFORMATIONAL` because the state-machine transition is observable at the frame level even on a standard NIC.

**What is NOT implemented:**
- Hardware timestamping NIC integration (Intel i210 PTP socket API, Intel i225, Microchip LAN9668)
- gPTP clock offset measurement (requires sub-µs timestamp resolution)
- Qbv gate schedule verification (802.1Qbv)
- Credit-based shaper verification (802.1Qav)
- Per-stream filtering verification (802.1Qci)

**Why standard NICs are insufficient:** Standard PC NICs have ±1 ms software timestamp accuracy. gPTP residence time requirement is < 10 µs; Sync interval tolerance is ±1 ms of 125 ms — both require hardware timestamps. Using software timestamps produces meaningless results.

**Impact:** `SWITCH_TIME_001` (TC8 §5.7) also returns SKIP on a standard NIC for the same reason.

**Path to resolution:** Integrate with Linux PTP (`linuxptp` / `ptp4l`) on a NIC that exposes `SO_TIMESTAMPING`. Add a `HwTimestampInterface` in `src/interface/` and wire it into `TimeTests` and `ExtTsnTests`.

---

## 3. Automotive PHY Tests — Media Converter / PHY Hardware Required

**What is implemented:**
- `EXT_PHY_002` (link flap count) — fully runnable on any PC via `psutil`. Returns PASS/FAIL based on link stability over observation window.
- `EXT_PHY_001/004/005/006` spec handlers exist and return SKIP with a message explaining media converter requirement.
- `EXT_PHY_003/007/008` return SKIP — require PHY test equipment or PHY management API.

**What is NOT implemented:**
- 100BASE-T1 / 1000BASE-T1 (BroadR-Reach) media converter control — no driver or API abstraction.
- PHY diagnostics: cable quality, MDI error rate, loopback mode — require PHY register access via MDIO.
- 10BASE-T1S multi-drop segment behavior — requires T1S-capable NIC (not yet commercially common).

**Impact:** All EXT_PHY tests except EXT_PHY_002 return SKIP on a standard PC+DUT setup.

**Path to resolution:** Add a `PhyInterface` abstraction for MDIO register access. Media converter control depends on vendor — typically USB-serial API (e.g. PEAK PCAN, Vector VH6501).

---

## 4. DUT Management Channel — DoIP/UDS Client Not Implemented

**What is implemented:** `EXT_MGMT_001` and `EXT_MGMT_002` handlers exist and return `INFORMATIONAL` on a real DUT, explaining that DoIP is architecturally feasible on a standard NIC.

**What is NOT implemented:**
- DoIP client (ISO 13400-2) — no TCP/UDP DoIP connection manager in the framework.
- UDS session layer (ISO 14229) — no UDS service encoder/decoder.
- ECU reset via UDS 0x11 (`EXT_MGMT_001`) — no reset handshake logic.
- UDS ReadDataByIdentifier 0x22 (`EXT_MGMT_002`) — no DID map or response parser.
- `EXT_MGMT_003/004/005` — require AUTOSAR stack, SSH, or vendor proprietary API.

**Path to resolution:** Integrate [`python-uds`](https://github.com/pylessard/python-udsoncan) or [`doipclient`](https://github.com/doip/doipclient) as optional dependencies. Add `DoIpInterface` in `src/interface/` and wire into `ExtMgmtTests`.

---

## 5. Golden Device / Virtual Oracle — Platform Check Only

**What is implemented:** `EXT_ORACLE_001/002/003` handlers exist and return `INFORMATIONAL` on Linux, `SKIP` on Windows, explaining that Linux bridge or Open vSwitch is needed.

**What is NOT implemented:**
- Linux bridge / Open vSwitch provisioning — no code creates or configures the virtual bridge.
- Oracle baseline capture — no `OracleSniffer` that records expected DUT behavior from a known-good virtual switch.
- DUT-vs-oracle diff engine — no comparison logic.
- `EXT_ORACLE_004` (hardware golden device) — returns SKIP; requires a second physical ECU.

**Path to resolution:** Add a `LinuxBridgeOracle` class that calls `bridge-utils` or `ovs-vsctl` to set up a virtual topology, captures traffic, and records a behavioral baseline. The diff engine compares this to live DUT captures.

---

## 6. PCAP Capture Export — Not Implemented

**What is planned:** Save captured frames as `.pcap` files alongside each test case result. Wireshark-compatible, useful for debugging failures and as OEM audit evidence.

**What is implemented:** Nothing — `ScapyInterface.send_and_capture()` currently discards captured frames after result validation.

**Path to resolution:** In `ScapyInterface.capture_frames()`, call `wrpcap(capture_path, frames)` before returning. The `capture_path` should be derived from the report output directory + case ID. A one-day implementation task.

---

## 7. Traceability Matrix Export — Not Implemented

**What is planned:** A per-TC8-clause CSV export: `spec_id, tc8_reference, title, automated, setup_requirement, status_last_run, evidence_path`. Required for OEM audit submissions (ASPICE, ISO 26262 evidence packages).

**What is implemented:** Nothing — `ReportGenerator` produces only HTML and database entries.

**Path to resolution:** Add `export_traceability_csv(report_id, output_path)` to `ReportGenerator`. Read from the SQLite result store for the given report, join with spec definitions, write CSV. A one-to-two day implementation task.

---

## 8. Address Learning — Two-Phase Procedure Partially Implemented

**Current state:** `SWITCH_ADDR_001` (source MAC learning) does the two-phase learn-then-probe procedure. `SWITCH_ADDR_002` (learned unicast forwarding) and `SWITCH_ADDR_003` (port migration) were refactored with `model_copy` to avoid mutation but the two-phase procedure is only partially wired for all cases.

**Impact:** Address learning tests run and produce results, but the learn phase does not always use a separate session from the probe phase. In practice this means some address tests rely on the switch having learned a MAC from a previous test case rather than from an explicit learning frame sent within the same test.

---

## 9. Windows — Runt Frame Injection Not Possible

**Affected test:** `SWITCH_GEN_007` (runt frame injection).

**Issue:** Windows Ethernet drivers (including Npcap) pad frames to the minimum 64-byte Ethernet frame size before transmission. A Scapy frame with a 46-byte payload is padded to 64 bytes at the NIC driver level — the DUT never receives a runt frame.

**Current behavior:** `SWITCH_GEN_007` returns `SKIP` with a message explaining that runt frame injection requires Linux `AF_PACKET` with `ETH_P_ALL` and manual below-minimum-size framing, or a dedicated hardware traffic generator that can bypass NIC driver padding.

---

## 10. Spec Parameter Expansion — Partial

**What is expanded at test case generation time:**
- VLAN IDs (from `vid_range`)
- Frame types (untagged / single-tagged / double-tagged)
- TPID values
- Ingress/egress port combinations

**What is NOT expanded yet:**
- `pcp_values` — PCP bit patterns (0–7). Test cases are generated with PCP=0 only.
- `payload_sizes` — Frame payload sizes. Tests use a fixed size; min/max frame size boundary tests rely on spec-specific overrides.
- `inner_vid_range` for double-tagged frames — inner VLAN ID is always derived from the outer, not independently varied.
- `rates_pps` — Requires traffic generator infrastructure (see item 1).
- `mac_count` — For MAC table stress tests; requires iterative learning procedure (not yet built).

---

## 11. Hardware Badge Classification — UI Only, Not Enforced in CLI

The web UI shows per-section hardware badges and a pre-run warning dialog. The CLI (`python -m src.cli run`) does not enforce these warnings — it will run all selected specs including hardware-gated ones, which will return SKIP or INFORMATIONAL. This is intentional (CI pipelines need consistent behavior), but users running the CLI should be aware that SKIP results for `SWITCH_TIME_001`, `EXT_TSN_*`, and most `EXT_PHY_*` are expected on a PC+DUT setup and do not indicate a framework error.

---

## Summary Table

| Feature | Status | Effort to complete |
|---|---|---|
| ScapyTrafficGen burst sending | ✅ Implemented (basic) | — |
| Hardware traffic generator integration | ❌ Not built | 2–5 days |
| Hardware timestamping (gPTP/TSN) | ❌ Not built | 3–7 days |
| Automotive PHY media converter control | ❌ Not built | 2–4 days |
| DoIP/UDS client | ❌ Not built | 3–5 days |
| Virtual oracle (Linux bridge/OVS) | ❌ Not built | 2–3 days |
| PCAP capture export | ❌ Not built | 0.5 day |
| Traceability matrix CSV export | ❌ Not built | 1–2 days |
| PCP / payload size / inner-VID expansion | ❌ Partial | 1 day |
| MAC table stress (mac_count) | ❌ Not built | 2–3 days |
| CLI hardware-gate warnings | ❌ Not built | 0.5 day |
