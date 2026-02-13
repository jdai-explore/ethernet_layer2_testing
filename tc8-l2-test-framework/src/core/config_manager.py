"""
Configuration manager for TC8 L2 test framework.

Handles loading DUT profiles, test tier definitions, questionnaire responses,
and default settings from YAML files with Pydantic validation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.models.test_case import (
    DUTProfile,
    PortConfig,
    TestSection,
    TestSpecDefinition,
    TestTier,
    TimingTier,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = _PROJECT_ROOT / "config"
DATA_DIR = _PROJECT_ROOT / "data"
SPEC_DEFINITIONS_DIR = DATA_DIR / "spec_definitions"


# ---------------------------------------------------------------------------
# Tier Configuration
# ---------------------------------------------------------------------------


class TierConfig(BaseModel):
    """Configuration for a single test execution tier."""

    description: str = ""
    specs: list[str] | str = Field(default="all")
    vid_sampling: list[int] | str = Field(default="all")
    port_sampling: str = Field(default="all_combinations")
    max_duration_hours: float | None = None


class TierDefinitions(BaseModel):
    """All tier definitions."""

    smoke: TierConfig = Field(default_factory=TierConfig)
    core: TierConfig = Field(default_factory=TierConfig)
    full: TierConfig = Field(default_factory=TierConfig)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class DefaultConfig(BaseModel):
    """Framework default assumptions."""

    default_vid: int = 1
    default_payload_size: int = 64
    cleanup_wait_s: float = 5.0
    aging_wait_s: float = 30.0
    frame_timeout_s: float = 2.0
    max_retries: int = 3
    link_check_interval_s: float = 1.0
    interface_type: str = "scapy"
    log_level: str = "INFO"
    report_format: str = "html"
    parallel_execution: bool = False
    database_url: str = "sqlite:///reports/test_results.db"


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------


class ConfigManager:
    """
    Central configuration manager.

    Loads and validates all configuration from YAML files, providing
    typed access to DUT profiles, tier definitions, defaults, and
    test specification definitions.
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.config_dir = config_dir or CONFIG_DIR
        self.data_dir = data_dir or DATA_DIR
        self.spec_dir = self.data_dir / "spec_definitions"

        self._defaults: DefaultConfig | None = None
        self._tiers: TierDefinitions | None = None
        self._dut_profile: DUTProfile | None = None
        self._spec_definitions: dict[str, TestSpecDefinition] = {}

        logger.info("ConfigManager initialised — config=%s, data=%s", self.config_dir, self.data_dir)

    # ── YAML helpers ──────────────────────────────────────────────────

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        """Load a YAML file and return its contents as a dict."""
        if not path.exists():
            logger.warning("Config file not found: %s", path)
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        logger.debug("Loaded YAML: %s (%d keys)", path.name, len(data))
        return data

    # ── Defaults ──────────────────────────────────────────────────────

    @property
    def defaults(self) -> DefaultConfig:
        if self._defaults is None:
            raw = self._load_yaml(self.config_dir / "defaults.yaml")
            self._defaults = DefaultConfig(**raw)
        return self._defaults

    # ── Tiers ─────────────────────────────────────────────────────────

    @property
    def tiers(self) -> TierDefinitions:
        if self._tiers is None:
            raw = self._load_yaml(self.config_dir / "test_tiers.yaml")
            tiers_raw = raw.get("tiers", {})
            self._tiers = TierDefinitions(
                smoke=TierConfig(**tiers_raw.get("smoke", {})),
                core=TierConfig(**tiers_raw.get("core", {})),
                full=TierConfig(**tiers_raw.get("full", {})),
            )
        return self._tiers

    def get_tier_config(self, tier: TestTier) -> TierConfig:
        """Get configuration for a specific tier."""
        return getattr(self.tiers, tier.value)

    # ── DUT Profile ───────────────────────────────────────────────────

    def load_dut_profile(self, profile_path: Path | str) -> DUTProfile:
        """Load a DUT configuration profile from YAML."""
        path = Path(profile_path)
        
        # If path doesn't exist as-is and is not absolute, try relative to dut_profiles/
        if not path.is_absolute() and not path.exists():
            path = self.config_dir / "dut_profiles" / path
            
        raw = self._load_yaml(path)
        ports = [PortConfig(**p) for p in raw.pop("ports", [])]
        self._dut_profile = DUTProfile(ports=ports, **raw)
        logger.info("Loaded DUT profile: %s (%d ports)", self._dut_profile.name, self._dut_profile.port_count)
        return self._dut_profile

    @property
    def dut_profile(self) -> DUTProfile | None:
        return self._dut_profile

    # ── Spec Definitions ──────────────────────────────────────────────

    def load_spec_definitions(self) -> dict[str, TestSpecDefinition]:
        """Load all TC8 spec definitions from YAML files in spec_definitions/."""
        self._spec_definitions.clear()
        if not self.spec_dir.exists():
            logger.warning("Spec definitions directory not found: %s", self.spec_dir)
            return self._spec_definitions

        for yaml_file in sorted(self.spec_dir.glob("*.yaml")):
            # Use safe_load_all to handle multi-document YAML (--- separators)
            raw: dict[str, Any] = {}
            with open(yaml_file, "r", encoding="utf-8") as fh:
                for doc in yaml.safe_load_all(fh):
                    if doc and isinstance(doc, dict):
                        raw.update(doc)

            for spec_id, spec_data in raw.items():
                if not isinstance(spec_data, dict):
                    continue
                # Map section string to enum
                section_ref = spec_data.get("tc8_reference", "5.4")
                section_key = section_ref.rsplit(".", 1)[0] if "." in section_ref else section_ref
                section_map: dict[str, TestSection] = {
                    "5.3": TestSection.VLAN,
                    "5.4": TestSection.GENERAL,
                    "5.5": TestSection.ADDRESS_LEARNING,
                    "5.6": TestSection.FILTERING,
                    "5.7": TestSection.TIME_SYNC,
                    "5.8": TestSection.QOS,
                    "5.9": TestSection.CONFIGURATION,
                }
                section = section_map.get(section_key, TestSection.GENERAL)

                # Timing tier
                timing_str = spec_data.pop("timing_tier", "tier_a")
                timing = TimingTier(timing_str) if timing_str in [t.value for t in TimingTier] else TimingTier.TIER_A

                self._spec_definitions[spec_id] = TestSpecDefinition(
                    spec_id=spec_id,
                    section=section,
                    timing_tier=timing,
                    **{k: v for k, v in spec_data.items() if k != "timing_tier"},
                )

        logger.info("Loaded %d spec definitions from %s", len(self._spec_definitions), self.spec_dir)
        return self._spec_definitions


    @property
    def spec_definitions(self) -> dict[str, TestSpecDefinition]:
        if not self._spec_definitions:
            self.load_spec_definitions()
        return self._spec_definitions

    def get_specs_for_section(self, section: TestSection) -> list[TestSpecDefinition]:
        """Filter specs by TC8 section."""
        return [s for s in self.spec_definitions.values() if s.section == section]

    def get_specs_for_tier(self, tier: TestTier) -> list[TestSpecDefinition]:
        """Get specs applicable to the given execution tier."""
        tier_cfg = self.get_tier_config(tier)

        if tier_cfg.specs == "all":
            return list(self.spec_definitions.values())

        if isinstance(tier_cfg.specs, str):
            # Parse spec group expressions like "all_5.4 + all_5.5"
            specs: list[TestSpecDefinition] = []
            parts = [p.strip() for p in tier_cfg.specs.split("+")]
            for part in parts:
                if part.startswith("all_"):
                    section_str = part.replace("all_", "")
                    section_map: dict[str, TestSection] = {
                        "5.3": TestSection.VLAN,
                        "5.4": TestSection.GENERAL,
                        "5.5": TestSection.ADDRESS_LEARNING,
                        "5.6": TestSection.FILTERING,
                        "5.7": TestSection.TIME_SYNC,
                        "5.8": TestSection.QOS,
                        "5.9": TestSection.CONFIGURATION,
                    }
                    if section_str in section_map:
                        specs.extend(self.get_specs_for_section(section_map[section_str]))
            return specs

        # Explicit list of spec IDs
        return [
            self.spec_definitions[sid]
            for sid in tier_cfg.specs
            if sid in self.spec_definitions
        ]

    # ── Questionnaire ─────────────────────────────────────────────────

    def load_questionnaire(self) -> dict[str, Any]:
        """Load the ECU team questionnaire template."""
        return self._load_yaml(self.config_dir / "questionnaire.yaml")

    def apply_questionnaire_responses(self, responses: dict[str, Any]) -> DUTProfile:
        """
        Build a DUTProfile from questionnaire responses.

        This is the primary flow for teams without a pre-existing
        DUT profile YAML — they answer the questionnaire and the
        framework generates the profile.
        """
        port_count = responses.get("port_count", 4)
        ports = []
        for i in range(port_count):
            port_data = responses.get(f"port_{i}", {})
            ports.append(PortConfig(
                port_id=i,
                interface_name=port_data.get("interface", f"eth{i}"),
                mac_address=port_data.get("mac", f"02:00:00:00:00:{i + 1:02x}"),
                speed_mbps=port_data.get("speed", 100),
                vlan_membership=port_data.get("vlans", [1]),
                pvid=port_data.get("pvid", 1),
                is_trunk=port_data.get("trunk", False),
            ))

        self._dut_profile = DUTProfile(
            name=responses.get("dut_name", "Unknown ECU"),
            model=responses.get("model", ""),
            firmware_version=responses.get("firmware", "unknown"),
            port_count=port_count,
            ports=ports,
            max_mac_table_size=responses.get("mac_table_size", 1024),
            mac_aging_time_s=responses.get("mac_aging_time", 300),
            supports_double_tagging=responses.get("double_tagging", False),
            supports_gptp=responses.get("gptp", False),
            can_reset=responses.get("can_reset", False),
        )
        return self._dut_profile
