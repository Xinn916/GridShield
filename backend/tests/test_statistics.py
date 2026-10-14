from datetime import datetime

import duckdb
import pytest
from pydantic import ValidationError

from common.enums import GroupBy, OrganizationId, QueryType
from common.schemas import StatisticsRequest
from control_plane.services.aggregation import aggregate_results
from party_node.data_repository import DataRepository
from party_node.query_executor import QueryExecutor


@pytest.fixture()
def executor(tmp_path):
    path = tmp_path / "party.parquet"
    connection = duckdb.connect(":memory:")
    connection.execute(
        f"""COPY (SELECT * FROM (VALUES
            ('H1', 'ORG_A', TIMESTAMP '2012-01-01 00:00:00', 1.0),
            ('H1', 'ORG_A', TIMESTAMP '2012-01-01 00:30:00', 2.0),
            ('H2', 'ORG_A', TIMESTAMP '2012-01-01 01:00:00', 3.0)
        ) t(household_id, organization_id, timestamp, energy_kwh))
        TO '{path.as_posix()}' (FORMAT PARQUET)"""
    )
    return QueryExecutor(DataRepository(path), OrganizationId.ORG_A)


def request(query_type: QueryType, group_by: GroupBy | None = None) -> StatisticsRequest:
    return StatisticsRequest(
        task_id="TASK-TEST",
        query_type=query_type,
        start_time=datetime(2012, 1, 1),
        end_time=datetime(2012, 1, 2),
        group_by=group_by,
    )


def test_sum_query(executor) -> None:
    result = executor.execute(request(QueryType.SUM))
    assert result.value == 6.0


def test_count_query(executor) -> None:
    result = executor.execute(request(QueryType.COUNT))
    assert result.value == 2


def test_average_uses_total_sum_divided_by_total_count(executor) -> None:
    local = executor.execute(request(QueryType.AVERAGE))
    other = local.model_copy(update={"sum": 18.0, "count": 4, "value": 4.5, "organization_id": OrganizationId.ORG_B})
    result = aggregate_results(QueryType.AVERAGE, [local, other])
    assert result["value"] == 4.0


def test_time_series_groups_by_hour(executor) -> None:
    result = executor.execute(request(QueryType.TIME_SERIES, GroupBy.HOUR))
    assert len(result.series) == 24
    assert result.series[:2] == [
        {"timestamp": "2012-01-01T00:00:00", "sum": 3.0, "count": 1},
        {"timestamp": "2012-01-01T01:00:00", "sum": 3.0, "count": 1},
    ]
    assert all(point["sum"] == 0 for point in result.series[2:])


@pytest.mark.parametrize(
    ("group_by", "expected_count"),
    [(GroupBy.HALF_HOUR, 48), (GroupBy.HOUR, 24), (GroupBy.DAY, 1)],
)
def test_time_series_uses_complete_left_closed_window(executor, group_by, expected_count) -> None:
    result = executor.execute(request(QueryType.TIME_SERIES, group_by))
    assert len(result.series) == expected_count
    assert result.series[0]["timestamp"] == "2012-01-01T00:00:00"
    assert all(point["timestamp"] < "2012-01-02T00:00:00" for point in result.series)


def test_invalid_query_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StatisticsRequest(
            task_id="TASK-TEST",
            query_type="DROP TABLE party_data",
            start_time=datetime(2012, 1, 1),
            end_time=datetime(2012, 1, 2),
        )


def test_invalid_time_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StatisticsRequest(
            task_id="TASK-TEST",
            query_type=QueryType.SUM,
            start_time=datetime(2012, 1, 2),
            end_time=datetime(2012, 1, 1),
        )
