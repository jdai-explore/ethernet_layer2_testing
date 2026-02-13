#!/bin/bash
# TC8 Layer 2 Test Framework - Linux/macOS Setup Script
# Usage: ./scripts/setup.sh

set -e  # Exit on error

echo "🚀 TC8 Layer 2 Test Framework - Setup"
echo "======================================"
echo ""

# Check Python version
echo "📋 Checking Python version..."
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3.10 &> /dev/null; then
    PYTHON_CMD="python3.10"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$(printf '%s\n' "3.10" "$PYTHON_VERSION" | sort -V | head -n1)" = "3.10" ]; then
        PYTHON_CMD="python3"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Error: Python 3.10+ required"
    echo "   Install: sudo apt install python3.11  # Ubuntu/Debian"
    echo "           brew install python@3.11      # macOS"
    exit 1
fi

echo "✅ Found: $($PYTHON_CMD --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ -d "venv" ]; then
    echo "   Virtual environment already exists, skipping..."
else
    $PYTHON_CMD -m venv venv
    echo "✅ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --quiet --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install --quiet -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Verify Scapy installation
echo "🔍 Verifying Scapy installation..."
if python -c "from scapy.all import Ether; print('✅ Scapy OK')" 2>/dev/null; then
    echo "✅ Scapy working"
else
    echo "⚠️  Scapy import failed - may need libpcap"
    echo "   Install: sudo apt install libpcap-dev  # Ubuntu/Debian"
    echo "           brew install libpcap           # macOS"
fi
echo ""

# Create directories
echo "📁 Creating directories..."
mkdir -p config/dut_profiles/examples
mkdir -p reports
mkdir -p logs
mkdir -p data/test_results
echo "✅ Directories created"
echo ""

# Run diagnostics
echo "🔬 Running environment diagnostics..."
python -c "
import sys
import platform
print(f'Python: {sys.version}')
print(f'Platform: {platform.system()} {platform.release()}')
print(f'Architecture: {platform.machine()}')

try:
    import scapy
    print(f'Scapy: {scapy.__version__}')
except:
    print('Scapy: Not available')

try:
    import pydantic
    print(f'Pydantic: {pydantic.__version__}')
except:
    print('Pydantic: Not available')
"
echo ""

# Run self-validation tests
echo "🧪 Running self-validation tests..."
if python -m pytest tests/unit/ tests/self_validation/ -q --tb=no; then
    echo "✅ All tests passed"
else
    echo "⚠️  Some tests failed - check logs"
fi
echo ""

# Check network interfaces
echo "🌐 Available network interfaces:"
if command -v ip &> /dev/null; then
    ip link show | grep -E "^[0-9]+:" | cut -d: -f2 | sed 's/^ /   /'
elif command -v ifconfig &> /dev/null; then
    ifconfig -a | grep -E "^[a-z]" | cut -d: -f1 | sed 's/^/   /'
fi
echo ""

# Check for root/sudo (needed for raw sockets)
echo "🔐 Checking permissions..."
if [ "$EUID" -eq 0 ]; then
    echo "✅ Running as root"
else
    echo "⚠️  Not running as root"
    echo "   For raw socket access, run tests with sudo or:"
    echo "   sudo setcap cap_net_raw,cap_net_admin=eip \$(which python)"
fi
echo ""

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Activate environment:  source venv/bin/activate"
echo "  2. List specs:            python -m src.cli specs"
echo "  3. Run smoke test:        python -m src.cli run --dut config/dut_profiles/examples/simulation_dut.yaml --tier smoke"
echo "  4. Start web UI:          uvicorn web.backend.main:app --host 0.0.0.0 --port 8000"
echo ""
