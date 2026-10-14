from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.database.session import Base
from control_plane.models.task import utc_now


class PerformanceTest(Base):
    __tablename__ = "performance_tests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    creator_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    benchmark_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parties_json: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    epsilon: Mapped[float | None] = mapped_column(Float)
    interval: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    phases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    participant_nodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_nodes: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    total_duration_ms: Mapped[float | None] = mapped_column(Float)
    total_communication_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_response_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PerformanceCommunicationEventModel(Base):
    __tablename__ = "performance_communication_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_id: Mapped[str] = mapped_column(ForeignKey("performance_tests.id"), index=True)
    source_node: Mapped[str] = mapped_column(String(32), nullable=False)
    target_node: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
