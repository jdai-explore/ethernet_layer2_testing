"""
Shared pytest fixtures for TC8 L2 Test Framework tests.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.core.session_manager import SessionManager, NullDUTController
from src.models.test_case import DUTProfile, PortConfig


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def config_manager() -> ConfigManager:
    """Session-scoped ConfigManager with all spec definitions loaded."""
    cm = ConfigManager(config_dir=CONFIG_DIR, data_dir=DATA_DIR)
    cm.load_spec_definitions()
    return cm


@pytest.fixture(scope="session")
def dut_profile() -> DUTProfile:
    """Minimal 4-port DUT profile for testing."""
    return DUTProfile(
        name="Test-ECU-4Port",
        model="TC8-SIM",
        port_count=4,
        ports=[
            PortConfig(port_id=i, interface_name=f"eth{i}", mac_address=f"02:00:00:00:00:{i:02x}", vlan_membership=[1, 100])
            for i in range(4)
        ],
        max_mac_table_size=1024,
        mac_aging_time_s=300,
        can_reset=False,
    )


@pytest.fixture(scope="session")
def session_manager(dut_profile: DUTProfile) -> SessionManager:
    """SessionManager with NullDUTController for simulation."""
    return SessionManager(
        dut_profile=dut_profile,
        controller=NullDUTController(),
        cleanup_wait_s=0.0,
        aging_wait_s=0.0,
    )


@pytest.fixture(scope="session")
def validator() -> ResultValidator:
    """Result validator instance."""
    return ResultValidator()
