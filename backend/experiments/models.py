from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from common.enums import OrganizationId, QueryType


class ExperimentMode(StrEnum):
    PLAIN = "PLAIN"
    SECRET_SHARE = "SECRET_SHARE"
    CENTRAL_DP = "CENTRAL_DP"
    LOCAL_DP = "LOCAL_DP"
    DISTRIBUTED_DP = "DISTRIBUTED_DP"


@dataclass(frozen=True)
class BenchmarkConfig:
    query_types: list[QueryType]
    trials: int = 100
    epsilons: list[float] = field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0, 4.0])
    window_caps: list[float] = field(default_factory=lambda: [20, 30, 50, 100, 240])
    party_counts: list[int] = field(default_factory=lambda: [1, 2, 3])
    household_counts: list[int] = field(default_factory=lambda: [50, 100, 200, 300])
    seed: int | None = None
    output_dir: Path = Path("backend/reports/experiments")
    start_time: datetime = datetime(2012, 11, 11)
    end_time: datetime = datetime(2012, 11, 12)
    epsilon_sum_ratio: float = 0.7
    epsilon_count_ratio: float = 0.3
    minimum_denominator: float = 10.0


@dataclass(frozen=True)
class PreparedStatistics:
    parties: list[OrganizationId]
    local_sums: dict[OrganizationId, float]
    local_counts: dict[OrganizationId, int]
    unclipped_sum: float
    unclipped_count: int
    window_cap: float
    household_count: int
    local_query_time_ms: float
    clipping_time_ms: float
    peak_memory_kb: float

    def true_value(self, query_type: QueryType, clipped: bool = True) -> float:
        total_sum = sum(self.local_sums.values()) if clipped else self.unclipped_sum
        total_count = sum(self.local_counts.values()) if clipped else self.unclipped_count
        if query_type == QueryType.SUM:
            return float(total_sum)
        if query_type == QueryType.COUNT:
            return float(total_count)
        return float(total_sum / total_count) if total_count else float("nan")


@dataclass(frozen=True)
class TrialResult:
    value: float | None
    execution_time_ms: float
    local_query_time_ms: float
    clipping_time_ms: float
    noise_time_ms: float
    secret_sharing_time_ms: float
    aggregation_time_ms: float
    peak_memory_kb: float
    party_to_s1_bytes: int
    party_to_s2_bytes: int
    compute_to_control_bytes: int
    direct_to_control_bytes: int

    @property
    def total_communication_bytes(self) -> int:
        return (
            self.party_to_s1_bytes
            + self.party_to_s2_bytes
            + self.compute_to_control_bytes
            + self.direct_to_control_bytes
        )
