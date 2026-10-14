import logging
from datetime import datetime
from typing import Any

from common.enums import GroupBy, OrganizationId, QueryType
from common.schemas import StatisticsRequest, StatisticsResponse
from common.time_buckets import generate_time_buckets
from party_node.contribution_clipper import ClippingStats, ContributionClipper
from party_node.data_repository import DataRepository


logger = logging.getLogger(__name__)

BUCKET_EXPRESSIONS = {
    GroupBy.HALF_HOUR: "date_trunc('hour', timestamp) + INTERVAL '30 minutes' * floor(date_part('minute', timestamp) / 30)",
    GroupBy.HOUR: "date_trunc('hour', timestamp)",
    GroupBy.DAY: "date_trunc('day', timestamp)",
}
class QueryExecutor:
    def __init__(
        self,
        repository: DataRepository,
        organization_id: OrganizationId,
        clipper: ContributionClipper | None = None,
    ):
        self.repository = repository
        self.organization_id = organization_id
        self.clipper = clipper or ContributionClipper()

    def execute(self, request: StatisticsRequest) -> StatisticsResponse:
        with self.repository.snapshot() as dataset_version:
            return self._execute_snapshot(request, dataset_version)

    def _execute_snapshot(self, request: StatisticsRequest, dataset_version: str) -> StatisticsResponse:
        start_time = self._naive(request.start_time)
        end_time = self._naive(request.end_time)
        window_cap = self.clipper.window_cap(start_time, end_time)
        cte, cap_parameters = self.clipper.cte(window_cap)
        parameters = [cap_parameters[0], start_time, end_time, cap_parameters[1], cap_parameters[2]]
        stats = self._clipping_stats(cte, parameters, start_time, end_time, window_cap)
        logger.info(
            "%s %s local computing completed records_before=%d records_after=%d clipped_records=%d clipped_energy_kwh=%.6f",
            request.task_id,
            self.organization_id.value,
            stats.records_before,
            stats.records_after,
            stats.clipped_records,
            stats.clipped_energy_kwh,
        )
        if request.query_type == QueryType.TIME_SERIES:
            return self._time_series(request, cte, parameters, start_time, end_time, dataset_version)

        total, household_count = self.repository.fetch_one(
            f"WITH {cte} SELECT coalesce(sum(clipped_energy_kwh), 0), count(DISTINCT household_id) FROM clipped",
            parameters,
        )
        total = float(total)
        household_count = int(household_count)
        if request.query_type == QueryType.SUM:
            value: float | int | None = total
        elif request.query_type == QueryType.COUNT:
            value = household_count
        else:
            value = total / household_count if household_count else None
        return StatisticsResponse(
            task_id=request.task_id,
            organization_id=self.organization_id,
            query_type=request.query_type,
            sum=total,
            count=household_count,
            value=value,
            dataset_version=dataset_version,
            dataset_fallback_warning=self.repository.snapshot_warning(),
        )

    def _clipping_stats(
        self,
        cte: str,
        parameters: list[Any],
        start_time: datetime,
        end_time: datetime,
        window_cap: float,
    ) -> ClippingStats:
        row = self.repository.fetch_one(
            f"""
            WITH {cte}, before_stats AS (
                SELECT count(*) AS records, coalesce(sum(energy_kwh), 0) AS energy
                FROM party_data WHERE timestamp >= ? AND timestamp < ?
            ), after_stats AS (
                SELECT count(*) AS records, coalesce(sum(clipped_energy_kwh), 0) AS energy,
                       count(*) FILTER (
                           WHERE original_energy_kwh <> record_value OR household_total > ?
                       ) AS modified_records
                FROM clipped
            )
            SELECT before_stats.records, after_stats.records,
                   after_stats.modified_records + (before_stats.records - after_stats.records),
                   greatest(before_stats.energy - after_stats.energy, 0)
            FROM before_stats, after_stats
            """,
            [*parameters, start_time, end_time, window_cap],
        )
        return ClippingStats(int(row[0]), int(row[1]), int(row[2]), float(row[3]), window_cap)

    def _time_series(
        self,
        request: StatisticsRequest,
        cte: str,
        parameters: list[Any],
        start_time: datetime,
        end_time: datetime,
        dataset_version: str,
    ) -> StatisticsResponse:
        bucket_expression = BUCKET_EXPRESSIONS[request.group_by]
        rows = self.repository.fetch_all(
            f"""WITH {cte}
                SELECT {bucket_expression} AS bucket, coalesce(sum(clipped_energy_kwh), 0),
                       count(DISTINCT household_id)
                FROM clipped GROUP BY bucket ORDER BY bucket""",
            parameters,
        )
        values = {row[0]: (float(row[1]), int(row[2])) for row in rows}
        buckets = generate_time_buckets(start_time, end_time, request.group_by)
        series: list[dict[str, Any]] = [
            {
                "timestamp": bucket.isoformat(),
                "sum": values.get(bucket, (0.0, 0))[0],
                "count": values.get(bucket, (0.0, 0))[1],
            }
            for bucket in buckets
        ]
        household_count = self.repository.fetch_one(
            f"WITH {cte} SELECT count(DISTINCT household_id) FROM clipped", parameters
        )[0]
        return StatisticsResponse(
            task_id=request.task_id,
            organization_id=self.organization_id,
            query_type=request.query_type,
            sum=sum(item["sum"] for item in series),
            count=int(household_count),
            series=series,
            dataset_version=dataset_version,
            dataset_fallback_warning=self.repository.snapshot_warning(),
        )

    @staticmethod
    def _naive(value: datetime) -> datetime:
        return value.replace(tzinfo=None) if value.tzinfo else value
