# TC8 Layer 2 Automotive Ethernet Test Framework

Professional test framework for OPEN Alliance TC8 Layer 2 (v3.0) conformance testing. Supports VLAN membership, priority tagging, filtering, and general switching validation on real hardware using Scapy.

## 🚀 Quick Start

### 1. Prerequisites
- **Python**: 3.10 or higher.
- **Hardware Interface**: At least one Ethernet interface connected to your DUT.
- **Windows (Critical)**:
    - Install [Npcap](https://npcap.com/#download).
    - **Important**: During installation, ensure you check "Support loopback adapter" and if possible, ensure NIC drivers are configured to NOT strip VLAN tags (hardware dependent).

### 2. Installation
```bash
# Clone the repository
git clone <repo-url>
cd tc8-l2-test-framework

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Usage

#### Web UI (Recommended)
```bash
python -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8000
```
Then open http://localhost:8000 in your browser.

#### CLI
```bash
# Run the smoke suite
python -m src.cli run --tier smoke

# List all supported specifications
python -m src.cli list
```

## 🛠 Project Structure
- `src/`: Core framework logic, specs, and interfaces.
- `web/`: FastAPI backend and static frontend assets.
- `config/`: DUT profiles (YAML) define your hardware setup.
- `data/`: Spec definitions (YAML) following TC8 standards.
- `reports/`: Historical test reports in HTML format.

## 🧪 Testing Focus
- **Section 5.3**: VLAN (Membership, Tagging, Double-Tagging).
- **Section 5.4**: General (Unicast, Broadcast, Flooding).
- **Section 5.5**: Address Learning (MAC table behavior).
- **Section 5.7**: Time Sync (gPTP/TSN prerequisites).
- **Section 5.8**: Quality of Service (Priority queuing).

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
