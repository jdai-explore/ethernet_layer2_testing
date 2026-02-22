from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.models.test_case import TestSuiteReport
from src.reporting.db_models import (
    Base,
    TestResultRecord,
    TestRunRecord,
    create_tables,
    get_engine,
)

logger = logging.getLogger(__name__)


class ResultStore:
    """
    Persistent store for test suite reports.

    Usage::

        store = ResultStore("sqlite:///reports/test_results.db")
        store.save_report(report)
        runs = store.list_runs(limit=10)
    """

    def __init__(self, database_url: str = "sqlite:///reports/test_results.db") -> None:
        # Ensure parent directory exists for SQLite
        if database_url.startswith("sqlite:///"):
            db_path = Path(database_url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._engine = get_engine(database_url)
        create_tables(self._engine)

    def save_report(self, report: TestSuiteReport) -> TestRunRecord:
        """Persist a complete TestSuiteReport to the database."""
        run = TestRunRecord(
            report_id=report.report_id,
            dut_name=report.dut_profile.name if report.dut_profile else "Unknown",
            tier=report.tier.value,
            created_at=report.created_at,
            total_cases=report.total_cases,
            passed=report.passed,
            failed=report.failed,
            informational=report.informational,
            skipped=report.skipped,
            errors=report.errors,
            duration_s=report.duration_s,
            pass_rate=report.pass_rate,
        )

        for r in report.results:
            # Serialize frame captures as JSON lists
            sent_json = None
            received_json = None
            if r.sent_frames:
                sent_json = json.dumps(
                    [f.model_dump(exclude={"raw_bytes"}) for f in r.sent_frames],
                    default=str,
                )
            if r.received_frames:
                # received_frames is dict[int, list[FrameCapture]]
                recv_data: dict[str, list[dict]] = {}
                if isinstance(r.received_frames, dict):
                    for port_id, frames in r.received_frames.items():
                        recv_data[str(port_id)] = [
                            f.model_dump(exclude={"raw_bytes"}) if hasattr(f, "model_dump") else f
                            for f in frames
                        ]
                    received_json = json.dumps(recv_data, default=str)
                elif isinstance(r.received_frames, list):
                    received_json = json.dumps(
                        [f.model_dump(exclude={"raw_bytes"}) if hasattr(f, "model_dump") else f
                         for f in r.received_frames],
                        default=str,
                    )

            run.results.append(
                TestResultRecord(
                    case_id=r.case_id,
                    spec_id=r.spec_id,
                    tc8_reference=r.tc8_reference,
                    section=r.section.value,
                    status=r.status.value,
                    duration_ms=r.duration_ms,
                    message=r.message or None,
                    error_detail=r.error_detail,
                    expected_json=json.dumps(r.expected, default=str) if r.expected else None,
                    actual_json=json.dumps(r.actual, default=str) if r.actual else None,
                    sent_frames_json=sent_json,
                    received_frames_json=received_json,
                )
            )

        with Session(self._engine) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            logger.info(
                "Saved report %s (%d results) to database",
                report.report_id, len(report.results),
            )
            return run

    def list_runs(
        self, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List recent test runs, newest first."""
        with Session(self._engine) as session:
            stmt = (
                select(TestRunRecord)
                .order_by(desc(TestRunRecord.created_at))
                .offset(offset)
                .limit(limit)
            )
            runs = session.scalars(stmt).all()
            return [r.to_dict() for r in runs]

    def get_run(self, report_id: str) -> dict[str, Any] | None:
        """Get a full run with all results by report_id."""
        with Session(self._engine) as session:
            stmt = select(TestRunRecord).where(TestRunRecord.report_id == report_id)
            run = session.scalars(stmt).first()
            if run is None:
                return None
            data = run.to_dict()
            data["results"] = [r.to_dict() for r in run.results]
            return data

    def get_trend(
        self, spec_id: str, last_n: int = 10
    ) -> list[dict[str, Any]]:
        """
        Get pass/fail trend for a specific spec across recent runs.

        Returns a list of {report_id, created_at, status, duration_ms}
        for the most recent `last_n` runs that include the given spec.
        """
        with Session(self._engine) as session:
            stmt = (
                select(
                    TestResultRecord.status,
                    TestResultRecord.duration_ms,
                    TestRunRecord.report_id,
                    TestRunRecord.created_at,
                )
                .join(TestRunRecord, TestResultRecord.run_id == TestRunRecord.id)
                .where(TestResultRecord.spec_id == spec_id)
                .order_by(desc(TestRunRecord.created_at))
                .limit(last_n)
            )
            rows = session.execute(stmt).all()
            return [
                {
                    "report_id": row.report_id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "status": row.status,
                    "duration_ms": row.duration_ms,
                }
                for row in rows
            ]

    def count_runs(self) -> int:
        """Return total number of stored runs."""
        with Session(self._engine) as session:
            return session.scalar(select(func.count(TestRunRecord.id))) or 0
