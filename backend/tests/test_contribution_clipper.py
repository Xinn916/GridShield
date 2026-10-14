from datetime import datetime

import duckdb
import pytest

from common.enums import OrganizationId, QueryType
from common.schemas import StatisticsRequest
from party_node.contribution_clipper import ContributionClipper
from party_node.data_repository import DataRepository
from party_node.query_executor import QueryExecutor


def test_daily_record_limit_and_window_cap_are_applied(tmp_path) -> None:
    file = tmp_path / "clipping.parquet"
    duckdb.connect(":memory:").execute(
        f"""COPY (SELECT * FROM (VALUES
            ('H1', 'ORG_A', TIMESTAMP '2012-01-01 00:00:00', 4.0),
            ('H1', 'ORG_A', TIMESTAMP '2012-01-01 00:30:00', 4.0),
            ('H1', 'ORG_A', TIMESTAMP '2012-01-01 01:00:00', 4.0)
        ) t(household_id, organization_id, timestamp, energy_kwh))
        TO '{file.as_posix()}' (FORMAT PARQUET)"""
    )
    executor = QueryExecutor(
        DataRepository(file),
        OrganizationId.ORG_A,
        ContributionClipper(
            record_cap=5.0,
            max_records_per_household_per_day=2,
            max_window_cap=6.0,
        ),
    )
    result = executor.execute(
        StatisticsRequest(
            task_id="TASK-CLIPPING",
            query_type=QueryType.SUM,
            start_time=datetime(2012, 1, 1),
            end_time=datetime(2012, 1, 2),
        )
    )
    assert result.value == 6.0
    assert result.count == 1


def test_time_series_vector_below_cap_is_unchanged() -> None:
    values, scaled = ContributionClipper.clip_time_series_vector([1.0, 2.0, 3.0], 10.0)
    assert values == [1.0, 2.0, 3.0]
    assert scaled is False


def test_time_series_vector_is_scaled_proportionally_to_l1_cap() -> None:
    values, scaled = ContributionClipper.clip_time_series_vector([3.0, 6.0, 1.0], 5.0)
    assert scaled is True
    assert values == pytest.approx([1.5, 3.0, 0.5])
    assert sum(abs(value) for value in values) <= 5.0 + 1e-12
