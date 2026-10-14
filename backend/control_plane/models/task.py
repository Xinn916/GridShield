from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.database.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    grant_id: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    query_type: Mapped[str] = mapped_column(String(16), nullable=False)
    parties_json: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    group_by: Mapped[str | None] = mapped_column(String(8))
    calculation_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="SECRET_SHARE")
    epsilon: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    privacy_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="household")
    sensitivity_json: Mapped[str | None] = mapped_column(Text)
    mechanism: Mapped[str] = mapped_column(String(48), nullable=False, default="none")
    budget_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NOT_REQUIRED")
    budget_before: Mapped[float | None] = mapped_column(Float)
    budget_after: Mapped[float | None] = mapped_column(Float)
    result_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
