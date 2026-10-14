from __future__ import annotations

import time
import tracemalloc
from pathlib import Path

import duckdb

from common.enums import OrganizationId, QueryType
from common.schemas import StatisticsRequest
from experiments.models import PreparedStatistics
from party_node.contribution_clipper import ContributionClipper
from party_node.data_repository import DataRepository
from party_node.query_executor import QueryExecutor


PROJECT_DIR = Path(__file__).resolve().parents[2]
PARTY_FILES = {
    OrganizationId.ORG_A: PROJECT_DIR / "data_processed" / "party_a.parquet",
    OrganizationId.ORG_B: PROJECT_DIR / "data_processed" / "party_b.parquet",
    OrganizationId.ORG_C: PROJECT_DIR / "data_processed" / "party_c.parquet",
}


class SampledDataRepository(DataRepository):
    def __init__(self, parquet_path: Path, household_limit: int | None = None):
        super().__init__(parquet_path)
        self.household_limit = household_limit

    def _connection(self) -> duckdb.DuckDBPyConnection:
        if not self.parquet_path.is_file():
            return super()._connection()
        connection = duckdb.connect(":memory:")
        connection.read_parquet(str(self.parquet_path)).create_view("source_data")
        if self.household_limit is None:
            connection.execute("CREATE VIEW party_data AS SELECT * FROM source_data")
        else:
            connection.execute(
                f"""CREATE VIEW party_data AS
                   SELECT * FROM source_data
                   WHERE household_id IN (
                       SELECT DISTINCT household_id FROM source_data
                       ORDER BY household_id LIMIT {int(self.household_limit)}
                   )"""
            )
        return connection


def allocate_households(total: int | None, party_count: int) -> list[int | None]:
    if total is None:
        return [None] * party_count
    if total <= 0:
        raise ValueError("household_count must be positive")
    total = min(total, party_count * 100)
    base, remainder = divmod(total, party_count)
    return [base + (1 if index < remainder else 0) for index in range(party_count)]


class ExperimentData:
    def __init__(self, files: dict[OrganizationId, Path] | None = None):
        self.files = files or PARTY_FILES

    def prepare(
        self,
        parties: list[OrganizationId],
        start_time,
        end_time,
        window_cap: float,
        household_count: int | None = None,
    ) -> PreparedStatistics:
        limits = allocate_households(household_count, len(parties))
        repositories = {
            party: SampledDataRepository(self.files[party], limit)
            for party, limit in zip(parties, limits)
        }
        clipper = ContributionClipper(max_window_cap=window_cap)
        local_sums: dict[OrganizationId, float] = {}
        local_counts: dict[OrganizationId, int] = {}
        unclipped_sum = 0.0
        unclipped_count = 0
        clipping_time_ms = 0.0

        tracemalloc.start()
        query_started = time.perf_counter()
        for index, (party, repository) in enumerate(repositories.items()):
            request = StatisticsRequest(
                task_id=f"TASK-EXP-PREP-{index}",
                query_type=QueryType.AVERAGE,
                start_time=start_time,
                end_time=end_time,
            )
            result = QueryExecutor(repository, party, clipper).execute(request)
            local_sums[party] = result.sum
            local_counts[party] = result.count
            raw = repository.fetch_one(
                """SELECT coalesce(sum(energy_kwh), 0), count(DISTINCT household_id)
                   FROM party_data WHERE timestamp >= ? AND timestamp < ?""",
                [start_time, end_time],
            )
            unclipped_sum += float(raw[0])
            unclipped_count += int(raw[1])

            cap = clipper.window_cap(start_time, end_time)
            cte, cap_parameters = clipper.cte(cap)
            parameters = [cap_parameters[0], start_time, end_time, cap_parameters[1], cap_parameters[2]]
            clip_started = time.perf_counter()
            repository.fetch_one(
                f"WITH {cte} SELECT coalesce(sum(clipped_energy_kwh), 0), count(*) FROM clipped",
                parameters,
            )
            clipping_time_ms += (time.perf_counter() - clip_started) * 1000
        local_query_time_ms = (time.perf_counter() - query_started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return PreparedStatistics(
            parties=parties,
            local_sums=local_sums,
            local_counts=local_counts,
            unclipped_sum=unclipped_sum,
            unclipped_count=unclipped_count,
            window_cap=clipper.window_cap(start_time, end_time),
            household_count=sum(local_counts.values()),
            local_query_time_ms=local_query_time_ms,
            clipping_time_ms=clipping_time_ms,
            peak_memory_kb=peak / 1024,
        )
