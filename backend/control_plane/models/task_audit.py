from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.database.session import Base
from control_plane.models.task import utc_now


class TaskAudit(Base):
    __tablename__ = "task_audits"

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    query_type: Mapped[str] = mapped_column(String(16), nullable=False)
    group_by: Mapped[str | None] = mapped_column(String(8))
    bucket_count: Mapped[int | None] = mapped_column(Integer)
    parties_json: Mapped[str] = mapped_column(Text, nullable=False)
    epsilon: Mapped[float] = mapped_column(Float, nullable=False)
    sensitivity_json: Mapped[str | None] = mapped_column(Text)
    mechanism: Mapped[str] = mapped_column(String(48), nullable=False)
    privacy_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    calculation_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    budget_before: Mapped[float | None] = mapped_column(Float)
    budget_after: Mapped[float | None] = mapped_column(Float)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_versions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
