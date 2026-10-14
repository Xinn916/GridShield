from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from common.enums import (
    CalculationMode,
    ComputeTaskStatus,
    GroupBy,
    OrganizationId,
    QueryType,
    TaskStatus,
    DataImportStatus,
)
from common.fixed_point import SCALE
from common.secret_sharing import PRIME

TASK_ID_PATTERN = r"^TASK-[A-Za-z0-9_-]+$"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HealthResponse(BaseModel):
    service: str
    status: str = "ok"
    timestamp: datetime = Field(default_factory=utc_now)
    version: str = "0.1.0"


class StatisticsRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=64, pattern=TASK_ID_PATTERN)
    query_type: QueryType
    start_time: datetime
    end_time: datetime
    group_by: GroupBy | None = None

    @model_validator(mode="after")
    def validate_query(self) -> "StatisticsRequest":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time")
        if self.query_type == QueryType.TIME_SERIES and self.group_by is None:
            raise ValueError("group_by is required for TIME_SERIES")
        if self.query_type != QueryType.TIME_SERIES and self.group_by is not None:
            raise ValueError("group_by is only valid for TIME_SERIES")
        return self


class StatisticsResponse(BaseModel):
    task_id: str
    organization_id: OrganizationId
    query_type: QueryType
    sum: float
    count: int
    value: float | int | None = None
    series: list[dict[str, Any]] | None = None
    dataset_version: str = "BASELINE"
    dataset_fallback_warning: str | None = None


class DistributedDPParameters(BaseModel):
    epsilon: float = Field(gt=0, le=5)
    sum_epsilon: float | None = Field(default=None, gt=0)
    count_epsilon: float | None = Field(default=None, gt=0)
    sum_sensitivity: float | None = Field(default=None, gt=0)
    count_sensitivity: float = Field(default=1.0, gt=0)
    minimum_denominator: float = Field(default=10.0, gt=0)
    participants: int = Field(gt=0)


class SecretTaskRequest(StatisticsRequest):
    expected_parties: list[OrganizationId] = Field(min_length=1)
    calculation_mode: CalculationMode = CalculationMode.SECRET_SHARE
    dp_parameters: DistributedDPParameters | None = None

    @model_validator(mode="after")
    def validate_expected_parties(self) -> "SecretTaskRequest":
        if len(set(self.expected_parties)) != len(self.expected_parties):
            raise ValueError("expected_parties must not contain duplicates")
        if self.calculation_mode == CalculationMode.DISTRIBUTED_DP:
            if self.dp_parameters is None:
                raise ValueError("dp_parameters are required for DISTRIBUTED_DP")
            if self.dp_parameters.participants != len(self.expected_parties):
                raise ValueError("participants must match expected_parties")
            if self.query_type in (QueryType.SUM, QueryType.AVERAGE, QueryType.TIME_SERIES) and self.dp_parameters.sum_sensitivity is None:
                raise ValueError("sum_sensitivity is required")
            if self.query_type == QueryType.AVERAGE and (
                self.dp_parameters.sum_epsilon is None or self.dp_parameters.count_epsilon is None
            ):
                raise ValueError("AVERAGE requires split epsilon values")
        elif self.dp_parameters is not None:
            raise ValueError("dp_parameters are only valid for DISTRIBUTED_DP")
        return self


class ShareBucket(BaseModel):
    timestamp: datetime
    value: int = Field(ge=0, lt=PRIME)


class SharePayload(BaseModel):
    value: int | None = Field(default=None, ge=0, lt=PRIME)
    sum: int | None = Field(default=None, ge=0, lt=PRIME)
    count: int | None = Field(default=None, ge=0, lt=PRIME)
    buckets: list[ShareBucket] | None = None

    @model_validator(mode="after")
    def validate_buckets(self) -> "SharePayload":
        if self.buckets is not None:
            timestamps = [bucket.timestamp for bucket in self.buckets]
            if len(set(timestamps)) != len(timestamps):
                raise ValueError("bucket timestamps must be unique")
        return self


class ShareSubmission(BaseModel):
    task_id: str = Field(min_length=1, max_length=64, pattern=TASK_ID_PATTERN)
    party_id: OrganizationId
    expected_parties: list[OrganizationId] = Field(min_length=1)
    query_type: QueryType
    group_by: GroupBy | None = None
    bucket_count: int | None = Field(default=None, ge=1)
    share_index: Literal[1, 2]
    scale: int = Field(default=SCALE, gt=0)
    count_scale: int = Field(default=1, gt=0)
    payload: SharePayload

    @model_validator(mode="after")
    def validate_share(self) -> "ShareSubmission":
        if len(set(self.expected_parties)) != len(self.expected_parties):
            raise ValueError("expected_parties must not contain duplicates")
        if self.party_id not in self.expected_parties:
            raise ValueError("party_id is not an expected party")
        if self.query_type == QueryType.TIME_SERIES:
            if self.group_by is None or self.bucket_count is None:
                raise ValueError("TIME_SERIES shares require group_by and bucket_count")
        elif self.group_by is not None or self.bucket_count is not None:
            raise ValueError("group_by and bucket_count are only valid for TIME_SERIES")
        if self.query_type in (QueryType.SUM, QueryType.COUNT):
            if self.payload.value is None or any(
                item is not None for item in (self.payload.sum, self.payload.count, self.payload.buckets)
            ):
                raise ValueError("SUM and COUNT require only payload.value")
        elif self.query_type == QueryType.AVERAGE:
            if self.payload.sum is None or self.payload.count is None or any(
                item is not None for item in (self.payload.value, self.payload.buckets)
            ):
                raise ValueError("AVERAGE requires only payload.sum and payload.count")
        elif self.payload.buckets is None or any(
            item is not None for item in (self.payload.value, self.payload.sum, self.payload.count)
        ):
            raise ValueError("TIME_SERIES requires only payload.buckets")
        return self


class ComputeTaskRegistration(BaseModel):
    task_id: str = Field(min_length=1, max_length=64, pattern=TASK_ID_PATTERN)
    expected_parties: list[OrganizationId] = Field(min_length=1)
    query_type: QueryType
    group_by: GroupBy | None = None
    bucket_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_parties(self) -> "ComputeTaskRegistration":
        if len(set(self.expected_parties)) != len(self.expected_parties):
            raise ValueError("expected_parties must not contain duplicates")
        if self.query_type == QueryType.TIME_SERIES:
            if self.group_by is None or self.bucket_count is None:
                raise ValueError("TIME_SERIES registration requires group_by and bucket_count")
        elif self.group_by is not None or self.bucket_count is not None:
            raise ValueError("group_by and bucket_count are only valid for TIME_SERIES")
        return self


class ShareReceipt(BaseModel):
    task_id: str
    party_id: OrganizationId
    share_index: Literal[1, 2]
    status: ComputeTaskStatus
    received_parties: int
    expected_parties: int
    idempotent: bool = False


class ShareAggregateResponse(BaseModel):
    task_id: str
    share_index: Literal[1, 2]
    query_type: QueryType | None = None
    status: ComputeTaskStatus
    scale: int | None = None
    count_scale: int = Field(default=1, gt=0)
    received_parties: int
    expected_parties: int
    payload: SharePayload | None = None
    error: str | None = None


class PartyTaskAck(BaseModel):
    task_id: str
    party_id: OrganizationId
    status: Literal["SHARED"]
    bucket_count: int | None = None
    secure_execution: Literal["COMPLETED"] = "COMPLETED"
    dataset_version: str = "BASELINE"
    dataset_fallback_warning: str | None = None


class TaskCreateRequest(BaseModel):
    grant_id: str | None = Field(default=None, min_length=1, max_length=40)
    query_type: QueryType
    parties: list[OrganizationId] = Field(min_length=1)
    start_time: datetime
    end_time: datetime
    group_by: GroupBy | None = None
    epsilon: float = Field(gt=0, le=5.0)

    @model_validator(mode="after")
    def validate_task(self) -> "TaskCreateRequest":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time")
        if len(set(self.parties)) != len(self.parties):
            raise ValueError("parties must not contain duplicates")
        if self.query_type == QueryType.TIME_SERIES and self.group_by is None:
            raise ValueError("group_by is required for TIME_SERIES")
        if self.query_type != QueryType.TIME_SERIES and self.group_by is not None:
            raise ValueError("group_by is only valid for TIME_SERIES")
        return self


class TaskResponse(BaseModel):
    task_id: str
    grant_id: str | None = None
    status: TaskStatus
    query_type: QueryType
    parties: list[OrganizationId]
    start_time: datetime
    end_time: datetime
    group_by: GroupBy | None
    calculation_mode: CalculationMode
    epsilon: float
    privacy_unit: str
    sensitivity: float | dict[str, float] | None = None
    budget_status: str
    created_at: datetime
    updated_at: datetime
    duration_ms: int | None = None
    error: str | None = None


class TaskResultResponse(BaseModel):
    task_id: str
    status: TaskStatus
    query_type: QueryType
    calculation_mode: CalculationMode
    privacy: dict[str, Any] | None = None
    result: dict[str, Any]


class PrivacyBudgetResponse(BaseModel):
    budget_id: str
    subject_id: str
    data_scope: str
    total_epsilon: float
    used_epsilon: float
    reserved_epsilon: float
    remaining_epsilon: float
    created_at: datetime
    updated_at: datetime


class ServiceHealthResponse(BaseModel):
    service_id: str
    name: str
    endpoint: str
    online: bool
    latency_ms: float
    service: str | None = None
    version: str | None = None
    error: str | None = None


class SystemHealthResponse(BaseModel):
    services: list[ServiceHealthResponse]
    checked_at: datetime


class TaskMonitorResponse(BaseModel):
    task_id: str
    status: TaskStatus
    current_stage: str
    progress: float
    party_statuses: dict[str, str]
    compute_node_statuses: dict[str, str]
    expected_parties: list[OrganizationId]
    submitted_share_count: int | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    execution_time_ms: int | None = None


class AuditEventResponse(BaseModel):
    task_id: str
    query_type: QueryType
    group_by: GroupBy | None = None
    bucket_count: int | None = None
    parties: list[OrganizationId]
    epsilon: float
    sensitivity: float | dict[str, float] | None = None
    mechanism: str
    privacy_unit: str
    calculation_mode: CalculationMode
    budget_before: float | None = None
    budget_after: float | None = None
    execution_time_ms: int | None = None
    status: TaskStatus
    created_at: datetime
    dataset_versions: dict[str, str] = Field(default_factory=dict)


class DataValidationIssue(BaseModel):
    error_type: str
    row_number: int | None = None
    field: str | None = None
    message: str


class DataValidationSummary(BaseModel):
    schema_matches: bool = False
    error_count: int = 0
    errors: list[DataValidationIssue] = Field(default_factory=list)
    errors_truncated: bool = False


class PartyDataImportResponse(BaseModel):
    import_id: str
    party_id: OrganizationId
    source_filename: str
    source_sha256: str | None = None
    parquet_sha256: str | None = None
    file_size_bytes: int = 0
    row_count: int = 0
    valid_row_count: int = 0
    invalid_row_count: int = 0
    duplicate_count: int = 0
    time_start: datetime | None = None
    time_end: datetime | None = None
    schema_version: str = "energy-v1"
    status: DataImportStatus
    validation_summary: DataValidationSummary = Field(default_factory=DataValidationSummary)
    created_at: datetime
    validation_started_at: datetime | None = None
    validation_completed_at: datetime | None = None
    activated_at: datetime | None = None
    archived_at: datetime | None = None
    error_message: str | None = None
    idempotent: bool = False


class PartyActiveDatasetResponse(BaseModel):
    party_id: OrganizationId
    dataset_version: str
    row_count: int
    time_start: datetime | None = None
    time_end: datetime | None = None
    activated_at: datetime | None = None
    status: str
    fallback_warning: str | None = None


class PartyRollbackRequest(BaseModel):
    target_version: str = Field(min_length=1, max_length=64)


class TaskDraft(BaseModel):
    """Agent 生成的查询参数草案：只允许受控字段。"""

    query_type: QueryType | None = None
    parties: list[OrganizationId] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    epsilon: float | None = Field(default=None, gt=0, le=5)
    group_by: GroupBy | None = None


class AgentParseRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)
    current_form: TaskDraft | None = None
    grant_id: str | None = Field(default=None, min_length=1, max_length=40)
    has_current_task: bool = False
    timezone: str = "Asia/Shanghai"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if len(text) < 2:
            raise ValueError("text 至少需要 2 个字符")
        # 拒绝二进制/控制字符（保留 \n \r \t）
        for char in text:
            code = ord(char)
            if code == 0 or (code < 32 and code not in (9, 10, 13)):
                raise ValueError("text 包含不允许的二进制或控制字符")
        return text


class AgentParseResponse(BaseModel):
    conversation_id: str | None = None
    intent: Literal[
        "QUERY",
        "TASK_UPDATE",
        "GREETING",
        "IDENTITY",
        "HELP",
        "PRIVACY_EXPLAIN",
        "BUDGET_QUERY",
        "TASK_CONFIRM",
        "OTHER",
        "REFUSED",
    ]
    reply: str = ""
    task_draft: TaskDraft | None = None
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: str = ""
    requires_confirmation: bool = True


class AgentExplainRequest(BaseModel):
    """结果解释只允许接收已发布的带噪结果摘要。"""

    query_type: QueryType
    noisy_value: float | None = None
    bucket_count: int | None = None
    peak_value: float | None = None
    peak_timestamp: datetime | None = None
    valley_value: float | None = None
    valley_timestamp: datetime | None = None
    peak_valley_difference: float | None = None
    average_load: float | None = None
    load_factor: float | None = None
    epsilon: float | None = None
    sensitivity: float | dict[str, float] | None = None
    parties: list[OrganizationId] = Field(default_factory=list)
    execution_time_ms: int | None = None


class AgentExplainResponse(BaseModel):
    explanation: str


class GovernanceAdviceRequest(BaseModel):
    """Request a governance review for an already completed task.

    The API intentionally accepts only the task identifier.  The control plane
    loads the task, grant and budget state after checking the caller's access,
    so a browser cannot forge the context sent to the model.
    """

    task_id: str = Field(min_length=1, max_length=40)


class GovernanceAdviceContext(BaseModel):
    """Allow-listed, non-row context passed from the control plane to AgentService."""

    task_id: str
    task_status: TaskStatus
    query_type: QueryType
    parties: list[OrganizationId] = Field(default_factory=list)
    calculation_mode: CalculationMode
    epsilon: float = Field(gt=0, le=5)
    group_by: GroupBy | None = None
    start_time: datetime
    end_time: datetime
    window_minutes: int = Field(ge=1)
    grant_status: str | None = None
    budget_status: str | None = None
    grant_epsilon_limit: float | None = Field(default=None, ge=0)
    grant_epsilon_remaining: float | None = Field(default=None, ge=0)
    budget_total: float = Field(ge=0)
    budget_used: float = Field(ge=0)
    budget_reserved: float = Field(ge=0)
    budget_remaining: float = Field(ge=0)
    budget_before: float | None = Field(default=None, ge=0)
    budget_after: float | None = Field(default=None, ge=0)
    result_bucket_count: int | None = Field(default=None, ge=0)


class GovernanceAdviceResponse(BaseModel):
    task_id: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    summary: str = Field(min_length=1, max_length=1000)
    suggestions: list[str] = Field(default_factory=list, max_length=4)
