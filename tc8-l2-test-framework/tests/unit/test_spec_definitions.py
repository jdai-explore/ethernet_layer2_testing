"""
Unit tests for TC8 YAML spec definitions.

Validates that all 71 spec definitions load correctly, have unique IDs,
reference valid sections, and contain required fields.
"""

from __future__ import annotations

import pytest

from src.core.config_manager import ConfigManager
from src.models.test_case import TestSection


class TestSpecDefinitions:
    """Validate YAML spec definitions integrity."""

    def test_all_71_specs_loaded(self, config_manager: ConfigManager) -> None:
        """All 71 TC8 specifications must be loaded."""
        assert len(config_manager.spec_definitions) == 71

    def test_spec_ids_unique(self, config_manager: ConfigManager) -> None:
        """Every spec ID must be unique."""
        ids = [s.spec_id for s in config_manager.spec_definitions.values()]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_spec_sections_valid(self, config_manager: ConfigManager) -> None:
        """All specs must reference a valid TestSection."""
        valid_sections = {s for s in TestSection}
        for spec in config_manager.spec_definitions.values():
            assert spec.section in valid_sections, (
                f"{spec.spec_id} has invalid section: {spec.section}"
            )

    def test_spec_fields_complete(self, config_manager: ConfigManager) -> None:
        """All specs must have required fields populated."""
        for spec in config_manager.spec_definitions.values():
            assert spec.spec_id, f"Spec missing spec_id"
            assert spec.tc8_reference, f"{spec.spec_id} missing tc8_reference"
            assert spec.title, f"{spec.spec_id} missing title"
            assert spec.section, f"{spec.spec_id} missing section"

    def test_section_counts(self, config_manager: ConfigManager) -> None:
        """Validate expected spec counts per section."""
        expected = {
            TestSection.VLAN: 21,
            TestSection.GENERAL: 10,
            TestSection.ADDRESS_LEARNING: 21,
            TestSection.FILTERING: 11,
            TestSection.TIME_SYNC: 1,
            TestSection.QOS: 4,
            TestSection.CONFIGURATION: 3,
        }
        for section, count in expected.items():
            actual = len(config_manager.get_specs_for_section(section))
            assert actual == count, (
                f"Section {section.value}: expected {count}, got {actual}"
            )

    def test_vlan_spec_ids_sequential(self, config_manager: ConfigManager) -> None:
        """VLAN specs should be numbered 001–021."""
        vlan_specs = config_manager.get_specs_for_section(TestSection.VLAN)
        ids = sorted(s.spec_id for s in vlan_specs)
        for i, sid in enumerate(ids, start=1):
            assert sid == f"SWITCH_VLAN_{i:03d}", f"Expected SWITCH_VLAN_{i:03d}, got {sid}"

    def test_address_spec_ids_sequential(self, config_manager: ConfigManager) -> None:
        """Address specs should be numbered 001–021."""
        addr_specs = config_manager.get_specs_for_section(TestSection.ADDRESS_LEARNING)
        ids = sorted(s.spec_id for s in addr_specs)
        for i, sid in enumerate(ids, start=1):
            assert sid == f"SWITCH_ADDR_{i:03d}", f"Expected SWITCH_ADDR_{i:03d}, got {sid}"
