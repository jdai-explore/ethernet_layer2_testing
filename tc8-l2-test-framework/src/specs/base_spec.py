"""
Base test specification class.

All test spec modules (vlan_tests, general_tests, etc.) extend this
base class to provide TC8 section-specific test logic.
"""

from __future__ import annotations

import abc
import logging
from typing import Any

from src.core.config_manager import ConfigManager
from src.core.result_validator import ResultValidator
from src.models.test_case import (
    DUTProfile,
    TestCase,
    TestResult,
    TestSection,
    TestSpecDefinition,
    TestStatus,
    TestTier,
)

logger = logging.getLogger(__name__)


class BaseTestSpec(abc.ABC):
    """
    Abstract base class for a TC8 test specification section.

    Each section (5.3 VLAN, 5.4 General, etc.) subclasses this to
    provide section-specific test logic while reusing common
    setup/teardown/validation from the base.
    """

    section: TestSection
    section_name: str = "Base"

    def __init__(
        self,
        config: ConfigManager,
        validator: ResultValidator | None = None,
    ) -> None:
        self.config = config
        self.validator = validator or ResultValidator()

    def get_specs(self) -> list[TestSpecDefinition]:
        """Get all spec definitions for this section."""
        return self.config.get_specs_for_section(self.section)

    @abc.abstractmethod
    async def execute_spec(
        self,
        spec: TestSpecDefinition,
        test_case: TestCase,
        interface: Any,
    ) -> TestResult:
        """
        Execute a single test case for a specification.

        Subclasses implement section-specific test logic here.
        """
        ...

    def log_spec_info(self, spec: TestSpecDefinition) -> None:
        """Log specification details."""
        logger.info(
            "[%s] %s — %s (priority=%s)",
            spec.spec_id, spec.title, spec.tc8_reference, spec.priority,
        )
