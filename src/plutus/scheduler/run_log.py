from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from plutus.db.models import Base

RunStatus = Literal["OK", "FAILED", "ABORTED"]


class RunLogRow(Base):
    __tablename__ = "run_log"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_name: Mapped[str] = mapped_column(String(48), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str | None] = mapped_column(String(8), nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


@dataclass
class RunLog:
    session: Session

    def start(self, job_name: str, now: datetime, run_id: str) -> str:
        self.session.add(RunLogRow(run_id=run_id, job_name=job_name, started_at=now))
        self.session.flush()
        return run_id

    def end(
        self, run_id: str, status: RunStatus, details: dict[str, Any], now: datetime
    ) -> None:
        row = self.session.get(RunLogRow, run_id)
        if row is None:
            raise ValueError(f"unknown run_id {run_id}")
        row.ended_at = now
        row.status = status
        row.details_json = details

    def history(self, job_name: str, limit: int = 20) -> list[RunLogRow]:
        return (
            self.session.query(RunLogRow)
            .filter(RunLogRow.job_name == job_name)
            .order_by(RunLogRow.started_at.desc())
            .limit(limit)
            .all()
        )
