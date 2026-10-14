from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.database.session import Base
from control_plane.models.task import utc_now


class PrivacyBudget(Base):
    __tablename__ = "privacy_budgets"
    __table_args__ = (UniqueConstraint("subject_id", "data_scope"),)

    budget_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    total_epsilon: Mapped[float] = mapped_column(Float, nullable=False)
    used_epsilon: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reserved_epsilon: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
