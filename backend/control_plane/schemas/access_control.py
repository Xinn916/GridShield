from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from common.enums import (
    AccessRequestStatus,
    ApprovalDecision,
    CalculationMode,
    GrantStatus,
    GroupBy,
    OrganizationId,
    QueryType,
    TaskStatus,
    UserRole,
    DataImportStatus,
)
from common.schemas import DataValidationSummary


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: UserRole
    party_id: OrganizationId | None = None
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    role: UserRole
    organization_id: OrganizationId | None = None
    password: str = Field(min_length=8, max_length=256)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}", value):
            raise ValueError("用户名只能包含字母、数字、下划线、点或连字符，且至少 3 个字符")
        return value

    @model_validator(mode="after")
    def validate_organization(self) -> "AdminUserCreate":
        if self.role == UserRole.DATA_OWNER and self.organization_id is None:
            raise ValueError("DATA_OWNER 必须绑定园区")
        if self.role != UserRole.DATA_OWNER and self.organization_id is not None:
            raise ValueError("只有 DATA_OWNER 可以绑定园区")
        return self


class AdminUserUpdate(BaseModel):
    role: UserRole
    organization_id: OrganizationId | None = None

    @model_validator(mode="after")
    def validate_organization(self) -> "AdminUserUpdate":
        if self.role == UserRole.DATA_OWNER and self.organization_id is None:
            raise ValueError("DATA_OWNER 必须绑定园区")
        if self.role != UserRole.DATA_OWNER and self.organization_id is not None:
            raise ValueError("只有 DATA_OWNER 可以绑定园区")
        return self


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class PublicRuntimeConfigResponse(BaseModel):
    app_env: Literal["development", "testing", "production"]


class UserStatusUpdate(BaseModel):
    active: bool


class DatasetAssetResponse(BaseModel):
    asset_id: str
    name: str
    description: str
    owner_party: OrganizationId
    time_start: datetime
    time_end: datetime
    source_granularity: str
    supported_query_types: list[QueryType]
    supported_group_by: list[GroupBy]
    privacy_protection: str
    raw_download_allowed: Literal[False] = False
    status: str
    created_at: datetime
    updated_at: datetime


class SafeNodeStatusResponse(BaseModel):
    service_id: str
    name: str
    online: bool
    latency_ms: float
    version: str | None = None


class SystemPolicySummaryResponse(BaseModel):
    authorization_enforcement_enabled: bool
    raw_download_allowed: Literal[False] = False
    calculation_mode: CalculationMode
    supported_query_types: list[QueryType]
    supported_group_by: list[GroupBy]
    default_total_epsilon: float
    session_ttl_seconds: int
    audit_enabled: bool
    party_nodes: list[SafeNodeStatusResponse]
    compute_nodes: list[SafeNodeStatusResponse]


class DatabaseRuntimeStatusResponse(BaseModel):
    type: str
    connected: bool
    demo_database: bool
    note: str


class DataAssetStorageStatusResponse(BaseModel):
    type: Literal["Parquet"] = "Parquet"
    party_count: int = Field(ge=0)
    mount_mode: Literal["READ_ONLY"] = "READ_ONLY"


class AdminSecurityBaselineResponse(BaseModel):
    authorization_enforcement_enabled: bool
    raw_download_disabled: Literal[True] = True
    session_cookie_http_only: Literal[True] = True
    cookie_samesite: Literal["Lax"] = "Lax"
    session_ttl_seconds: int
    password_hash_storage: Literal[True] = True
    session_token_hash_storage: Literal[True] = True
    audit_enabled: Literal[True] = True
    calculation_mode: CalculationMode
    demo_identity_mode_enabled: bool
    did_wallet_verification: Literal[False] = False
    mfa_enabled: Literal[False] = False
    ip_allowlist_enabled: Literal[False] = False
    certificate_management: Literal["DEPLOYMENT_MANAGED"] = "DEPLOYMENT_MANAGED"
    https_forced: Literal[False] = False


class PlannedExtensionResponse(BaseModel):
    name: str
    status: Literal["PLANNED"] = "PLANNED"


class AdminSystemEventResponse(BaseModel):
    audit_id: int
    event_type: str
    actor_user_id: str | None = None
    actor_role: UserRole | None = None
    party_id: OrganizationId | None = None
    request_id: str | None = None
    grant_id: str | None = None
    task_id: str | None = None
    decision: str | None = None
    reason: str | None = None
    timestamp: datetime


class AdminSystemOverviewResponse(BaseModel):
    database: DatabaseRuntimeStatusResponse
    asset_storage: DataAssetStorageStatusResponse
    frontend_gateway: SafeNodeStatusResponse
    party_nodes: list[SafeNodeStatusResponse]
    compute_nodes: list[SafeNodeStatusResponse]
    agent_model_configured: bool
    security_baseline: AdminSecurityBaselineResponse
    planned_extensions: list[PlannedExtensionResponse]
    maintenance_records: list[str] = Field(default_factory=list)
    system_events: list[AdminSystemEventResponse] = Field(default_factory=list)
    checked_at: datetime


class AccessRequestCreate(BaseModel):
    purpose: str = Field(min_length=5, max_length=500)
    requested_parties: list[OrganizationId] = Field(min_length=1)
    requested_query_types: list[QueryType] = Field(min_length=1)
    requested_start_time: datetime
    requested_end_time: datetime
    requested_group_by: list[GroupBy] = Field(default_factory=list)
    requested_max_epsilon_per_query: float = Field(gt=0, le=5.0)
    requested_total_epsilon: float = Field(gt=0)
    requested_expires_at: datetime

    @field_validator("purpose")
    @classmethod
    def trim_purpose(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("purpose must contain at least 5 non-whitespace characters")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "AccessRequestCreate":
        if len(set(self.requested_parties)) != len(self.requested_parties):
            raise ValueError("requested_parties must not contain duplicates")
        if len(set(self.requested_query_types)) != len(self.requested_query_types):
            raise ValueError("requested_query_types must not contain duplicates")
        if self.requested_start_time >= self.requested_end_time:
            raise ValueError("requested_start_time must be earlier than requested_end_time")
        if self.requested_total_epsilon < self.requested_max_epsilon_per_query:
            raise ValueError("requested_total_epsilon must be at least the per-query limit")
        if QueryType.TIME_SERIES in self.requested_query_types and not self.requested_group_by:
            raise ValueError("requested_group_by is required when TIME_SERIES is requested")
        if QueryType.TIME_SERIES not in self.requested_query_types and self.requested_group_by:
            raise ValueError("requested_group_by is only valid when TIME_SERIES is requested")
        now = datetime.now(timezone.utc)
        expires = self.requested_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            raise ValueError("requested_expires_at must be in the future")
        return self


class AccessRequestPatch(BaseModel):
    purpose: str | None = Field(default=None, min_length=5, max_length=500)
    requested_parties: list[OrganizationId] | None = Field(default=None, min_length=1)
    requested_query_types: list[QueryType] | None = Field(default=None, min_length=1)
    requested_start_time: datetime | None = None
    requested_end_time: datetime | None = None
    requested_group_by: list[GroupBy] | None = None
    requested_max_epsilon_per_query: float | None = Field(default=None, gt=0, le=5.0)
    requested_total_epsilon: float | None = Field(default=None, gt=0)
    requested_expires_at: datetime | None = None


class ApprovalResponse(BaseModel):
    approval_id: str
    request_id: str
    party_id: OrganizationId
    approver_user_id: str | None = None
    decision: ApprovalDecision
    reason: str | None = None
    allowed_query_types: list[QueryType] | None = None
    allowed_start_time: datetime | None = None
    allowed_end_time: datetime | None = None
    allowed_group_by: list[GroupBy] | None = None
    max_epsilon_per_query: float | None = None
    total_epsilon_limit: float | None = None
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime


class AccessRequestResponse(BaseModel):
    request_id: str
    requester_user_id: str
    purpose: str
    requested_parties: list[OrganizationId]
    requested_query_types: list[QueryType]
    requested_start_time: datetime
    requested_end_time: datetime
    requested_group_by: list[GroupBy]
    requested_max_epsilon_per_query: float
    requested_total_epsilon: float
    requested_expires_at: datetime
    status: AccessRequestStatus
    created_at: datetime
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    rejection_reason: str | None = None
    approvals: list[ApprovalResponse] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal[
        ApprovalDecision.APPROVED,
        ApprovalDecision.CONDITIONALLY_APPROVED,
        ApprovalDecision.REJECTED,
    ]
    reason: str | None = Field(default=None, max_length=500)
    allowed_query_types: list[QueryType] | None = None
    allowed_start_time: datetime | None = None
    allowed_end_time: datetime | None = None
    allowed_group_by: list[GroupBy] | None = None
    max_epsilon_per_query: float | None = Field(default=None, gt=0)
    total_epsilon_limit: float | None = Field(default=None, gt=0)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "ApprovalDecisionRequest":
        if self.decision == ApprovalDecision.REJECTED and not (self.reason or "").strip():
            raise ValueError("reason is required when rejecting a request")
        return self


class GrantResponse(BaseModel):
    grant_id: str
    request_id: str
    grantee_user_id: str
    parties: list[OrganizationId]
    allowed_query_types: list[QueryType]
    allowed_start_time: datetime
    allowed_end_time: datetime
    allowed_group_by: list[GroupBy]
    max_epsilon_per_query: float
    total_epsilon_limit: float
    epsilon_consumed: float
    epsilon_reserved: float
    epsilon_remaining: float
    valid_from: datetime
    expires_at: datetime
    status: GrantStatus
    created_at: datetime
    revoked_at: datetime | None = None


class ReportTaskResponse(BaseModel):
    task_id: str
    query_type: QueryType
    parties: list[OrganizationId]
    status: TaskStatus
    epsilon: float
    created_at: datetime
    completed_at: datetime | None = None
    grant_id: str | None = None
    bucket_count: int | None = None


class GrantUsageReportResponse(BaseModel):
    task_id: str
    grant_id: str
    epsilon: float
    status: str
    remaining_before: float
    remaining_after: float | None = None
    created_at: datetime
    updated_at: datetime


class AnalystReportResponse(BaseModel):
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float
    average_task_duration_ms: float
    epsilon_consumed: float
    remaining_privacy_budget: float
    query_type_counts: dict[str, int]
    party_participation_counts: dict[str, int]
    time_series_bucket_count: int
    recent_tasks: list[ReportTaskResponse]
    recent_grant_usage: list[GrantUsageReportResponse]


class SecurityAuditResponse(BaseModel):
    audit_id: int
    event_type: str
    actor_user_id: str | None = None
    target_user_id: str | None = None
    actor_role: UserRole | None = None
    party_id: OrganizationId | None = None
    request_id: str | None = None
    grant_id: str | None = None
    task_id: str | None = None
    import_id: str | None = None
    source_sha256: str | None = None
    row_count: int | None = None
    import_status: DataImportStatus | None = None
    decision: str | None = None
    operation: str | None = None
    reason: str | None = None
    timestamp: datetime


class DataImportResponse(BaseModel):
    import_id: str
    party_id: OrganizationId
    uploader_user_id: str
    original_filename: str
    source_sha256: str | None = None
    parquet_sha256: str | None = None
    file_size_bytes: int
    row_count: int
    valid_row_count: int
    invalid_row_count: int
    duplicate_count: int
    time_start: datetime | None = None
    time_end: datetime | None = None
    schema_version: str
    import_mode: Literal["FULL_SNAPSHOT"] = "FULL_SNAPSHOT"
    status: DataImportStatus
    validation_summary: DataValidationSummary
    is_active: bool
    created_at: datetime
    validation_started_at: datetime | None = None
    validation_completed_at: datetime | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    error_message: str | None = None


class DataImportRollbackRequest(BaseModel):
    target_version: str = Field(min_length=1, max_length=64)


class ActiveDataVersionResponse(BaseModel):
    party_id: OrganizationId
    dataset_version: str
    row_count: int
    time_start: datetime | None = None
    time_end: datetime | None = None
    activated_at: datetime | None = None
    status: str
    fallback_warning: str | None = None


class DataImportConfigResponse(BaseModel):
    enabled: bool
    import_mode: Literal["FULL_SNAPSHOT"] = "FULL_SNAPSHOT"
    max_bytes: int
    max_rows: int
    allowed_extensions: list[str] = [".csv"]
    allowed_encodings: list[str] = ["UTF-8", "UTF-8-SIG"]
    expected_columns: list[str] = [
        "household_id",
        "organization_id",
        "timestamp",
        "energy_kwh",
    ]
    unique_key: list[str] = ["household_id", "timestamp"]
