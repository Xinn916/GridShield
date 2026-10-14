import json
from datetime import datetime

import duckdb
import pytest

from common.enums import CalculationMode, GroupBy, OrganizationId, QueryType, TaskStatus
from common.fixed_point import encode
from common.schemas import ComputeTaskRegistration, SecretTaskRequest, StatisticsRequest, TaskCreateRequest
from common.time_buckets import generate_time_buckets
from compute_node.share_store import ShareStore
from control_plane.database.session import create_session_factory, create_tables
from control_plane.models.task import Task
from control_plane.models.task_audit import TaskAudit
from control_plane.services.aggregation import aggregate_results
from control_plane.services.task_service import TaskService
from party_node.contribution_clipper import ContributionClipper
from party_node.data_repository import DataRepository
from party_node.query_executor import QueryExecutor
from party_node.share_service import ShareService


@pytest.fixture()
def network(tmp_path):
    rows = {
        OrganizationId.ORG_A: [
            ("A1", "2012-01-01 00:00:00", 10.0),
            ("A1", "2012-01-01 00:30:00", 1.0),
            ("A2", "2012-01-01 01:00:00", 2.0),
        ],
        OrganizationId.ORG_B: [
            ("B1", "2012-01-01 00:00:00", 4.0),
            ("B1", "2012-01-01 00:30:00", 6.0),
            ("B2", "2012-01-01 01:00:00", 3.0),
        ],
        OrganizationId.ORG_C: [
            ("C1", "2012-01-01 00:00:00", 1.0),
            ("C2", "2012-01-01 00:30:00", 2.0),
        ],
    }
    executors = {}
    for party, party_rows in rows.items():
        file = tmp_path / f"{party.value}.parquet"
        values = ",".join(
            f"('{household}', '{party.value}', TIMESTAMP '{timestamp}', {energy})"
            for household, timestamp, energy in party_rows
        )
        duckdb.connect(":memory:").execute(
            f"""COPY (SELECT * FROM (VALUES {values})
                t(household_id, organization_id, timestamp, energy_kwh))
                TO '{file.as_posix()}' (FORMAT PARQUET)"""
        )
        executors[party] = QueryExecutor(
            DataRepository(file),
            party,
            ContributionClipper(record_cap=5.0, max_records_per_household_per_day=48, max_window_cap=240.0),
        )
    return executors


def run_both_modes(executors, query_type: QueryType, group_by: GroupBy | None = None):
    task_id = f"TASK-{query_type.value}"
    parties = list(OrganizationId)
    start = datetime(2012, 1, 1)
    end = datetime(2012, 1, 2)
    plain_responses = [
        executors[party].execute(
            StatisticsRequest(
                task_id=task_id,
                query_type=query_type,
                start_time=start,
                end_time=end,
                group_by=group_by,
            )
        )
        for party in parties
    ]
    plain = aggregate_results(query_type, plain_responses)

    stores = {1: ShareStore("S1", 1), 2: ShareStore("S2", 2)}
    registration = ComputeTaskRegistration(
        task_id=task_id,
        expected_parties=parties,
        query_type=query_type,
        group_by=group_by,
        bucket_count=len(generate_time_buckets(start, end, group_by))
        if query_type == QueryType.TIME_SERIES
        else None,
    )
    for store in stores.values():
        store.register(registration)
    for party in parties:
        service = ShareService(
            executors[party],
            {1: "memory://s1", 2: "memory://s2"},
            submitter=lambda index, submission: stores[index].submit(submission),
        )
        service.process(
            SecretTaskRequest(
                task_id=task_id,
                query_type=query_type,
                start_time=start,
                end_time=end,
                group_by=group_by,
                expected_parties=parties,
            )
        )
    secret = TaskService._reconstruct(stores[1].aggregate(task_id), stores[2].aggregate(task_id))
    return plain, secret


def test_secret_sum_matches_plain_after_clipping(network) -> None:
    plain, secret = run_both_modes(network, QueryType.SUM)
    assert plain["value"] == pytest.approx(23.0)
    assert secret["value"] == pytest.approx(plain["value"], abs=1e-6)


def test_secret_count_matches_plain(network) -> None:
    plain, secret = run_both_modes(network, QueryType.COUNT)
    assert plain["value"] == 6
    assert secret["value"] == plain["value"]


def test_secret_average_matches_plain(network) -> None:
    plain, secret = run_both_modes(network, QueryType.AVERAGE)
    assert secret["sum"] == pytest.approx(plain["sum"], abs=1e-6)
    assert secret["count"] == plain["count"]
    assert secret["value"] == pytest.approx(plain["value"], abs=1e-6)


def test_secret_time_series_matches_plain_per_bucket(network) -> None:
    plain, secret = run_both_modes(network, QueryType.TIME_SERIES, GroupBy.HOUR)
    plain_values = {item["timestamp"]: item["sum"] for item in plain["series"]}
    secret_values = {item["timestamp"]: item["sum"] for item in secret["series"]}
    assert secret_values.keys() == plain_values.keys()
    for timestamp in plain_values:
        assert secret_values[timestamp] == pytest.approx(plain_values[timestamp], abs=1e-6)


class InMemoryComputeClient:
    def __init__(self):
        self.stores = {1: ShareStore("S1", 1), 2: ShareStore("S2", 2)}

    def register(self, index, request):
        return self.stores[index].register(request)

    def aggregate(self, index, task_id):
        return self.stores[index].aggregate(task_id)


class InMemoryPartyClient:
    def __init__(self, executors, compute_client, noise_generator=None):
        self.executors = executors
        self.services = {
            party: ShareService(
                executor,
                {1: "memory://s1", 2: "memory://s2"},
                submitter=lambda index, submission: compute_client.stores[index].submit(submission),
                noise_generator=noise_generator,
            )
            for party, executor in executors.items()
        }

    def dispatch_secret(self, party, request):
        return self.services[party].process(request)

    def statistics(self, party, request):
        return self.executors[party].execute(request)


def test_control_database_contains_no_party_plaintext_results(network, tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}")
    create_tables(factory)
    compute_client = InMemoryComputeClient()
    party_client = InMemoryPartyClient(network, compute_client)
    with factory() as session:
        task = TaskService(
            session,
            party_client,
            compute_client,
            CalculationMode.SECRET_SHARE,
            poll_interval=0,
            poll_attempts=2,
        ).create_and_run(
            TaskCreateRequest(
                query_type=QueryType.SUM,
                parties=list(OrganizationId),
                start_time=datetime(2012, 1, 1),
                end_time=datetime(2012, 1, 2),
                epsilon=1.0,
            )
        )
        assert task.status == TaskStatus.COMPLETED
        stored_result = json.loads(task.result_json)
        assert set(stored_result) == {"sum", "value", "parties", "dataset_versions"}
        assert stored_result["dataset_versions"] == {party.value: "BASELINE" for party in OrganizationId}
        assert json.loads(session.get(TaskAudit, task.task_id).dataset_versions_json) == stored_result["dataset_versions"]
        assert task.calculation_mode == CalculationMode.SECRET_SHARE
        column_names = {column.name for column in Task.__table__.columns}
        assert not any("local" in name or "party_result" in name for name in column_names)


def test_plain_task_mode_remains_available_for_backend_configuration(network, tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{(tmp_path / 'plain.db').as_posix()}")
    create_tables(factory)
    compute_client = InMemoryComputeClient()
    party_client = InMemoryPartyClient(network, compute_client)
    with factory() as session:
        task = TaskService(
            session,
            party_client,
            compute_client,
            CalculationMode.PLAIN,
        ).create_and_run(
            TaskCreateRequest(
                query_type=QueryType.SUM,
                parties=list(OrganizationId),
                start_time=datetime(2012, 1, 1),
                end_time=datetime(2012, 1, 2),
                epsilon=1.0,
            )
        )
        assert task.status == TaskStatus.COMPLETED
        assert task.calculation_mode == CalculationMode.PLAIN
        assert json.loads(task.result_json)["value"] == pytest.approx(23.0)


class RecordingNoise:
    def __init__(self, value=0.25):
        self.value = value
        self.calls = []

    def partial_noise(self, sensitivity, epsilon, participants):
        self.calls.append((sensitivity, epsilon, participants))
        return self.value


def run_dp_task(
    network, tmp_path, query_type, epsilon=1.0, noise=None, total_budget=20.0, group_by=None
):
    factory = create_session_factory(f"sqlite:///{(tmp_path / f'{query_type.value}.db').as_posix()}")
    create_tables(factory)
    session = factory()
    compute_client = InMemoryComputeClient()
    noise = noise or RecordingNoise()
    party_client = InMemoryPartyClient(network, compute_client, noise)
    service = TaskService(
        session,
        party_client,
        compute_client,
        CalculationMode.DISTRIBUTED_DP,
        poll_interval=0,
        poll_attempts=2,
        default_total_epsilon=total_budget,
        minimum_denominator=1.0,
        max_window_cap=240.0,
    )
    task = service.create_and_run(
        TaskCreateRequest(
            query_type=query_type,
            parties=list(OrganizationId),
            start_time=datetime(2012, 1, 1),
            end_time=datetime(2012, 1, 2),
            group_by=group_by,
            epsilon=epsilon,
        )
    )
    return session, task, service, compute_client, noise


def test_distributed_dp_sum_completes(network, tmp_path) -> None:
    session, task, service, _, _ = run_dp_task(network, tmp_path, QueryType.SUM)
    try:
        assert task.status == TaskStatus.COMPLETED
        result = json.loads(task.result_json)
        assert result["value"] == pytest.approx(23.75)
        assert result["dataset_versions"] == {party.value: "BASELINE" for party in OrganizationId}
        response = service.to_response(task)
        assert response.sensitivity == 240.0
        assert response.budget_status == "CONSUMED"
    finally:
        session.close()


def test_distributed_dp_count_completes_with_sensitivity_one(network, tmp_path) -> None:
    session, task, service, _, _ = run_dp_task(network, tmp_path, QueryType.COUNT)
    try:
        assert task.status == TaskStatus.COMPLETED
        assert json.loads(task.result_json)["value"] == pytest.approx(6.75, abs=1e-6)
        assert service.to_response(task).sensitivity == 1.0
    finally:
        session.close()


def test_distributed_dp_average_splits_sum_and_count_epsilon(network, tmp_path) -> None:
    noise = RecordingNoise()
    session, task, _, _, noise = run_dp_task(
        network, tmp_path, QueryType.AVERAGE, epsilon=1.0, noise=noise
    )
    try:
        expected = (23.0 + 0.75) / (6.0 + 0.75)
        assert json.loads(task.result_json)["value"] == pytest.approx(expected, abs=1e-6)
        epsilons = [call[1] for call in noise.calls]
        assert epsilons.count(pytest.approx(0.7)) == 3
        assert epsilons.count(pytest.approx(0.3)) == 3
    finally:
        session.close()


def test_dp_failure_releases_task_reservation(network, tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{(tmp_path / 'failed.db').as_posix()}")
    create_tables(factory)
    compute_client = InMemoryComputeClient()

    class FailingPartyClient(InMemoryPartyClient):
        def dispatch_secret(self, party, request):
            raise RuntimeError("injected party failure")

    with factory() as session:
        service = TaskService(
            session,
            FailingPartyClient(network, compute_client, RecordingNoise()),
            compute_client,
            CalculationMode.DISTRIBUTED_DP,
            default_total_epsilon=5.0,
            minimum_denominator=1.0,
            max_window_cap=240.0,
        )
        task = service.create_and_run(
            TaskCreateRequest(
                query_type=QueryType.SUM,
                parties=list(OrganizationId),
                start_time=datetime(2012, 1, 1),
                end_time=datetime(2012, 1, 2),
                epsilon=1.0,
            )
        )
        budget = service.budget_service.response("demo-analyst", "GLOBAL")
        assert task.status == TaskStatus.FAILED
        assert task.budget_status == "RELEASED"
        assert budget.used_epsilon == 0
        assert budget.reserved_epsilon == 0


def test_compute_nodes_see_only_combined_random_shares(network, tmp_path) -> None:
    session, task, _, compute_client, _ = run_dp_task(network, tmp_path, QueryType.SUM)
    try:
        final_encoded = encode(json.loads(task.result_json)["value"])
        first = compute_client.stores[1].aggregate(task.task_id)
        second = compute_client.stores[2].aggregate(task.task_id)
        assert first.payload.value != final_encoded
        assert second.payload.value != final_encoded
        assert not any(
            "noise" in name or "statistic" in name
            for name in type(first.payload).model_fields
        )
    finally:
        session.close()


def test_dp_sqlite_stores_no_true_result_or_partial_noise(network, tmp_path) -> None:
    session, task, _, _, _ = run_dp_task(network, tmp_path, QueryType.SUM)
    try:
        assert set(json.loads(task.result_json)) == {"value", "dataset_versions"}
        audit = session.get(TaskAudit, task.task_id)
        assert audit.mechanism == "distributed_laplace"
        assert not hasattr(audit, "result")
        columns = {column.name for column in Task.__table__.columns}
        assert not any("noise" in name or "true_result" in name or "local" in name for name in columns)
    finally:
        session.close()


def test_distributed_dp_time_series_completes_with_one_budget_charge(network, tmp_path) -> None:
    session, task, service, _, noise = run_dp_task(
        network, tmp_path, QueryType.TIME_SERIES, group_by=GroupBy.HOUR
    )
    try:
        result = json.loads(task.result_json)
        budget = service.budget_service.response("demo-analyst", "GLOBAL")
        assert task.status == TaskStatus.COMPLETED
        assert task.mechanism == "distributed_vector_laplace"
        assert result["group_by"] == "1h"
        assert result["bucket_count"] == 24
        assert len(result["buckets"]) == 24
        assert result["buckets"][0]["value"] == pytest.approx(18.75, abs=1e-6)
        assert result["buckets"][1]["value"] == pytest.approx(5.75, abs=1e-6)
        assert all(item["value"] >= 0 for item in result["buckets"])
        assert budget.used_epsilon == pytest.approx(1.0)
        assert len(noise.calls) == 3 * 24
        assert all(call == (240.0, 1.0, 3) for call in noise.calls)
        audit = session.get(TaskAudit, task.task_id)
        assert audit.group_by == "1h"
        assert audit.bucket_count == 24
        assert not hasattr(audit, "result_json")
        response = service.to_result(task)
        assert response.privacy["sensitivity"] == 240.0
        assert response.privacy["post_processing"] == ["non_negative_clamp", "load_metrics"]
    finally:
        session.close()


def test_time_series_metrics_are_computed_only_from_published_values() -> None:
    buckets = [
        {"timestamp": "2012-01-01T00:00:00", "value": 0.0},
        {"timestamp": "2012-01-01T01:00:00", "value": 8.0},
        {"timestamp": "2012-01-01T02:00:00", "value": 4.0},
    ]
    metrics = TaskService._load_metrics(buckets)
    assert metrics == {
        "peak_value": 8.0,
        "peak_timestamp": "2012-01-01T01:00:00",
        "valley_value": 0.0,
        "valley_timestamp": "2012-01-01T00:00:00",
        "peak_valley_difference": 8.0,
        "average_load": 4.0,
        "load_factor": 0.5,
    }
