"""
SQLAlchemy database models for test result persistence.

Stores historical test runs and individual results for trend analysis,
regression detection, and report retrieval.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class TestRunRecord(Base):
    """Persistent record of a complete test suite run."""

    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    dut_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    informational: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationship to individual results
    results: Mapped[list[TestResultRecord]] = relationship(
        "TestResultRecord", back_populates="run", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "dut_name": self.dut_name,
            "tier": self.tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "informational": self.informational,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration_s": self.duration_s,
            "pass_rate": self.pass_rate,
        }


class TestResultRecord(Base):
    """Persistent record of a single test case result."""

    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("test_runs.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    spec_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tc8_reference: Mapped[str] = mapped_column(String(16), nullable=False)
    section: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Frame capture & comparison data (JSON text columns)
    expected_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_frames_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_frames_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship back to run
    run: Mapped[TestRunRecord] = relationship("TestRunRecord", back_populates="results")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "case_id": self.case_id,
            "spec_id": self.spec_id,
            "tc8_reference": self.tc8_reference,
            "section": self.section,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "error_detail": self.error_detail,
        }
        # Deserialize JSON columns if present
        for key in ("expected_json", "actual_json", "sent_frames_json", "received_frames_json"):
            raw = getattr(self, key, None)
            dict_key = key.replace("_json", "")
            result[dict_key] = json.loads(raw) if raw else None
        return result


def get_engine(database_url: str = "sqlite:///reports/test_results.db") -> Engine:
    """Create a SQLAlchemy engine from a database URL."""
    engine = create_engine(database_url, echo=False)
    logger.info("Database engine created: %s", database_url)
    return engine


def create_tables(engine: Engine) -> None:
    """Create all tables in the database."""
    Base.metadata.create_all(engine)
    logger.info("Database tables created/verified")
