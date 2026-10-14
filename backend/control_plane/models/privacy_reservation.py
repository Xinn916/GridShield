from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.database.session import Base
from control_plane.models.task import utc_now


class PrivacyReservation(Base):
    __tablename__ = "privacy_reservations"

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    budget_id: Mapped[str] = mapped_column(String(96), nullable=False)
    epsilon: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    budget_before: Mapped[float] = mapped_column(Float, nullable=False)
    budget_after: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
