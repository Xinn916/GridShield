from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from common.enums import CalculationMode, GroupBy, OrganizationId, QueryType
from common.schemas import DistributedDPParameters, PartyTaskAck, StatisticsResponse


BENCHMARK_ID = "ENERGY_BENCHMARK_V1"
PERFORMANCE_HEADER = "X-PrivGrid-Performance-Test-ID"
CORE_NODE_COUNT = 6


class PerformanceCommunicationEvent(BaseModel):
    test_id: str
    source_node: str
    target_node: str
    operation: str
    request_bytes: int = Field(ge=0)
    response_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    started_at: datetime
    completed_at: datetime


class BenchmarkTestCreate(BaseModel):
    benchmark_id: Literal["ENERGY_BENCHMARK_V1"] = BENCHMARK_ID
    parties: list[OrganizationId] = Field(min_length=1)
    query_type: QueryType
    mode: CalculationMode
    epsilon: float | None = Field(default=None, gt=0, le=5)
    interval: GroupBy | None = None

    @model_validator(mode="after")
    def validate_benchmark(self) -> "BenchmarkTestCreate":
        if len(set(self.parties)) != len(self.parties):
            raise ValueError("parties must not contain duplicates")
        if self.mode == CalculationMode.DISTRIBUTED_DP and self.epsilon is None:
            raise ValueError("epsilon is required for DISTRIBUTED_DP")
        if self.mode != CalculationMode.DISTRIBUTED_DP and self.epsilon is not None:
            raise ValueError("epsilon is only valid for DISTRIBUTED_DP")
        if self.query_type == QueryType.TIME_SERIES and self.interval is None:
            raise ValueError("interval is required for TIME_SERIES")
        if self.query_type != QueryType.TIME_SERIES and self.interval is not None:
            raise ValueError("interval is only valid for TIME_SERIES")
        return self


class BenchmarkPartyRequest(BenchmarkTestCreate):
    test_id: str = Field(min_length=1, max_length=64)
    task_id: str = Field(min_length=1, max_length=64, pattern=r"^TASK-[A-Za-z0-9_-]+$")
    start_time: datetime
    end_time: datetime
    dp_parameters: DistributedDPParameters | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "BenchmarkPartyRequest":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time")
        if self.mode == CalculationMode.DISTRIBUTED_DP and self.dp_parameters is None:
            raise ValueError("dp_parameters are required for DISTRIBUTED_DP")
        if self.mode != CalculationMode.DISTRIBUTED_DP and self.dp_parameters is not None:
            raise ValueError("dp_parameters are only valid for DISTRIBUTED_DP")
        return self


class BenchmarkPlainResponse(BaseModel):
    statistics: StatisticsResponse
    local_duration_ms: float = Field(ge=0)


class BenchmarkSharedResponse(BaseModel):
    acknowledgement: PartyTaskAck
    local_duration_ms: float = Field(ge=0)
    share_generation_duration_ms: float = Field(ge=0)
    performance_events: list[PerformanceCommunicationEvent] = Field(default_factory=list)


class PerformancePhase(BaseModel):
    key: str
    label: str
    duration_ms: float | None = None


class PerformanceSummary(BaseModel):
    total_duration_ms: float | None = None
    communication_bytes: int = 0
    participant_nodes: int = 0
    total_nodes: int = CORE_NODE_COUNT
    average_response_ms: float | None = None


class PerformanceTestResponse(BaseModel):
    id: str
    benchmark_id: str
    parties: list[OrganizationId]
    query_type: QueryType
    mode: CalculationMode
    epsilon: float | None = None
    interval: GroupBy | None = None
    status: Literal["RUNNING", "COMPLETED", "FAILED"]
    summary: PerformanceSummary
    phases: list[PerformancePhase] = Field(default_factory=list)
    links: list[PerformanceCommunicationEvent] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PerformanceTestList(BaseModel):
    items: list[PerformanceTestResponse]
    total: int
    limit: int
    offset: int
