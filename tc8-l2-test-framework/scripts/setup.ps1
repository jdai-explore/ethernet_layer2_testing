# TC8 Layer 2 Test Framework - Windows Setup Script
# Usage: .\scripts\setup.ps1

Write-Host "🚀 TC8 Layer 2 Test Framework - Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️  Warning: Not running as Administrator" -ForegroundColor Yellow
    Write-Host "   Some features may require elevated privileges" -ForegroundColor Yellow
    Write-Host ""
}

# Check Python version
Write-Host "📋 Checking Python version..." -ForegroundColor Cyan
$pythonCmd = $null
$pythonVersions = @("python3.11", "python3.10", "python3", "python")

foreach ($cmd in $pythonVersions) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python 3\.(1[0-9]|[2-9][0-9])") {
            $pythonCmd = $cmd
            break
        }
    } catch {
        continue
    }
}

if ($null -eq $pythonCmd) {
    Write-Host "❌ Error: Python 3.10+ required" -ForegroundColor Red
    Write-Host "   Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

$pythonVersion = & $pythonCmd --version
Write-Host "✅ Found: $pythonVersion" -ForegroundColor Green
Write-Host ""

# Create virtual environment
Write-Host "📦 Creating virtual environment..." -ForegroundColor Cyan
if (Test-Path "venv") {
    Write-Host "   Virtual environment already exists, skipping..." -ForegroundColor Yellow
} else {
    & $pythonCmd -m venv venv
    Write-Host "✅ Virtual environment created" -ForegroundColor Green
}
Write-Host ""

# Activate virtual environment
Write-Host "🔧 Activating virtual environment..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "⬆️  Upgrading pip..." -ForegroundColor Cyan
python -m pip install --quiet --upgrade pip

# Install dependencies
Write-Host "📥 Installing dependencies..." -ForegroundColor Cyan
pip install --quiet -r requirements.txt
Write-Host "✅ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Verify Scapy installation
Write-Host "🔍 Verifying Scapy installation..." -ForegroundColor Cyan
try {
    python -c "from scapy.all import Ether; print('✅ Scapy OK')" 2>$null
    Write-Host "✅ Scapy working" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Scapy import failed" -ForegroundColor Yellow
    Write-Host "   May need Npcap: https://npcap.com/#download" -ForegroundColor Yellow
}
Write-Host ""

# Create directories
Write-Host "📁 Creating directories..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "config\dut_profiles\examples" | Out-Null
New-Item -ItemType Directory -Force -Path "reports" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
New-Item -ItemType Directory -Force -Path "data\test_results" | Out-Null
Write-Host "✅ Directories created" -ForegroundColor Green
Write-Host ""

# Run diagnostics
Write-Host "🔬 Running environment diagnostics..." -ForegroundColor Cyan
python -c @"
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
"@
Write-Host ""

# Run self-validation tests
Write-Host "🧪 Running self-validation tests..." -ForegroundColor Cyan
$testResult = python -m pytest tests/unit/ tests/self_validation/ -q --tb=no
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ All tests passed" -ForegroundColor Green
} else {
    Write-Host "⚠️  Some tests failed - check logs" -ForegroundColor Yellow
}
Write-Host ""

# Check network interfaces
Write-Host "🌐 Available network interfaces:" -ForegroundColor Cyan
Get-NetAdapter | Select-Object Name, InterfaceDescription, Status | Format-Table -AutoSize
Write-Host ""

Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Activate environment:  .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  2. List specs:            python -m src.cli specs" -ForegroundColor White
Write-Host "  3. Run smoke test:        python -m src.cli run --dut config\dut_profiles\examples\simulation_dut.yaml --tier smoke" -ForegroundColor White
Write-Host "  4. Start web UI:          uvicorn web.backend.main:app --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host ""
