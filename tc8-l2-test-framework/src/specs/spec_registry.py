"""
Spec registry — maps TestSection → BaseTestSpec subclass.

Provides automatic dispatch of test execution to the correct
section handler based on the test case's section field.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.models.test_case import TestSection
from src.specs.base_spec import BaseTestSpec

# Section test modules (lazy import to avoid circular dependencies)

logger = logging.getLogger(__name__)


def _build_registry() -> dict[TestSection, type[BaseTestSpec]]:
    """Build the section → spec class mapping."""
    from src.specs.general_tests import GeneralTests
    from src.specs.vlan_tests import VLANTests
    from src.specs.address_tests import AddressTests
    from src.specs.filtering_tests import FilteringTests
    from src.specs.time_tests import TimeTests
    from src.specs.qos_tests import QoSTests
    from src.specs.config_tests import ConfigTests

    return {
        TestSection.GENERAL: GeneralTests,
        TestSection.VLAN: VLANTests,
        TestSection.ADDRESS_LEARNING: AddressTests,
        TestSection.FILTERING: FilteringTests,
        TestSection.TIME_SYNC: TimeTests,
        TestSection.QOS: QoSTests,
        TestSection.CONFIGURATION: ConfigTests,
    }


class SpecRegistry:
    """
    Central registry that instantiates and caches section test handlers.

    Usage::

        registry = SpecRegistry(config, validator)
        handler = registry.get_handler(TestSection.VLAN)
        result = await handler.execute_spec(spec, test_case, interface)
    """

    def __init__(
        self,
        config: ConfigManager,
        validator: ResultValidator | None = None,
    ) -> None:
        self.config = config
        self.validator = validator or ResultValidator()
        self._registry = _build_registry()
        self._instances: dict[TestSection, BaseTestSpec] = {}

    def get_handler(self, section: TestSection) -> BaseTestSpec:
        """Get (or create) the handler for a given TC8 section."""
        if section not in self._instances:
            spec_cls = self._registry.get(section)
            if spec_cls is None:
                raise ValueError(f"No handler registered for section {section.value}")
            self._instances[section] = spec_cls(self.config, self.validator)
            logger.debug("Instantiated handler %s for section %s", spec_cls.__name__, section.value)
        return self._instances[section]

    @property
    def supported_sections(self) -> list[TestSection]:
        """Return all sections that have registered handlers."""
        return list(self._registry.keys())

    def has_handler(self, section: TestSection) -> bool:
        """Check if a handler is registered for the given section."""
        return section in self._registry
