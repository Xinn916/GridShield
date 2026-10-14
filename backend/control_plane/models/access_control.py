from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.database.session import Base
from control_plane.models.task import utc_now


class DemoUser(Base):
    __tablename__ = "demo_users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    party_id: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class DatasetAsset(Base):
    __tablename__ = "dataset_assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_party: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    time_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    time_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_granularity: Mapped[str] = mapped_column(String(32), nullable=False)
    supported_query_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    supported_group_by_json: Mapped[str] = mapped_column(Text, nullable=False)
    privacy_protection: Mapped[str] = mapped_column(Text, nullable=False)
    raw_download_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )


class AccessRequest(Base):
    __tablename__ = "access_requests"

    request_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    requester_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_parties_json: Mapped[str] = mapped_column(Text, nullable=False)
    requested_query_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    requested_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    requested_end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    requested_group_by_json: Mapped[str] = mapped_column(Text, nullable=False)
    requested_max_epsilon_per_query: Mapped[float] = mapped_column(Float, nullable=False)
    requested_total_epsilon: Mapped[float] = mapped_column(Float, nullable=False)
    requested_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class AccessApproval(Base):
    __tablename__ = "access_approvals"
    __table_args__ = (UniqueConstraint("request_id", "party_id"),)

    approval_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    party_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    approver_user_id: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    reason: Mapped[str | None] = mapped_column(Text)
    allowed_query_types_json: Mapped[str | None] = mapped_column(Text)
    allowed_start_time: Mapped[datetime | None] = mapped_column(DateTime)
    allowed_end_time: Mapped[datetime | None] = mapped_column(DateTime)
    allowed_group_by_json: Mapped[str | None] = mapped_column(Text)
    max_epsilon_per_query: Mapped[float | None] = mapped_column(Float)
    total_epsilon_limit: Mapped[float | None] = mapped_column(Float)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class AccessGrant(Base):
    __tablename__ = "access_grants"
    __table_args__ = (UniqueConstraint("request_id"),)

    grant_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grantee_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parties_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_query_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    allowed_end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    allowed_group_by_json: Mapped[str] = mapped_column(Text, nullable=False)
    max_epsilon_per_query: Mapped[float] = mapped_column(Float, nullable=False)
    total_epsilon_limit: Mapped[float] = mapped_column(Float, nullable=False)
    epsilon_consumed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    epsilon_reserved: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class GrantReservation(Base):
    __tablename__ = "grant_reservations"

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    epsilon: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    remaining_before: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_after: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )


class SecurityAudit(Base):
    __tablename__ = "security_audits"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    target_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(24))
    party_id: Mapped[str | None] = mapped_column(String(16))
    request_id: Mapped[str | None] = mapped_column(String(32), index=True)
    grant_id: Mapped[str | None] = mapped_column(String(40), index=True)
    task_id: Mapped[str | None] = mapped_column(String(32), index=True)
    import_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int | None] = mapped_column(Integer)
    import_status: Mapped[str | None] = mapped_column(String(16))
    decision: Mapped[str | None] = mapped_column(String(32))
    operation: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, index=True)


class DataImport(Base):
    __tablename__ = "data_imports"
    __table_args__ = (UniqueConstraint("party_id", "source_sha256"),)

    import_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    party_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    uploader_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    parquet_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_start: Mapped[datetime | None] = mapped_column(DateTime)
    time_end: Mapped[datetime | None] = mapped_column(DateTime)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="energy-v1")
    import_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="FULL_SNAPSHOT")
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    validation_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    validation_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    validation_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
