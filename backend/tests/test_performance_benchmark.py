from datetime import datetime

import duckdb
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from common.enums import CalculationMode, ComputeTaskStatus, OrganizationId, QueryType
from common.performance import (
    BenchmarkPlainResponse,
    BenchmarkSharedResponse,
    BenchmarkTestCreate,
    PerformanceCommunicationEvent,
)
from common.schemas import ComputeTaskRegistration, StatisticsRequest
from compute_node.share_store import ShareStore
from control_plane.config import ControlSettings
from control_plane.database.session import create_session_factory, create_tables
from control_plane.main import create_app
from control_plane.models.performance import PerformanceCommunicationEventModel
from control_plane.models.privacy_budget import PrivacyBudget
from control_plane.services.performance_service import PerformanceService
from party_node.contribution_clipper import ContributionClipper
from party_node.data_repository import DataRepository
from party_node.query_executor import QueryExecutor
from party_node.share_service import ShareService


def event(test_id, source, target, operation, request_bytes=11, response_bytes=7):
    now = datetime.utcnow()
    return PerformanceCommunicationEvent(
        test_id=test_id,
        source_node=source,
        target_node=target,
        operation=operation,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        total_bytes=request_bytes + response_bytes,
        duration_ms=1.0,
        started_at=now,
        completed_at=now,
    )


@pytest.fixture()
def benchmark_network(tmp_path):
    executors = {}
    for party in OrganizationId:
        file = tmp_path / f"{party.value.lower()}_benchmark.parquet"
        prefix = party.value.replace("ORG_", "SYNTHETIC_")
        duckdb.connect(":memory:").execute(
            f"""COPY (
                SELECT '{prefix}_001' AS household_id,
                       '{party.value}' AS organization_id,
                       TIMESTAMP '2026-01-01 00:00:00'
                           + (row_number() OVER () - 1) * INTERVAL '30 minutes' AS timestamp,
                       1.25::DOUBLE AS energy_kwh
                FROM range(48)
            ) TO '{file.as_posix()}' (FORMAT PARQUET)"""
        )
        executors[party] = QueryExecutor(
            DataRepository(file),
            party,
            ContributionClipper(
                record_cap=5.0,
                max_records_per_household_per_day=48,
                max_window_cap=7440.0,
            ),
        )
    return executors


class BenchmarkComputeClient:
    def __init__(self):
        self.stores = {1: ShareStore("S1", 1), 2: ShareStore("S2", 2)}
        self.calls = []

    def benchmark_register(self, index, request: ComputeTaskRegistration, test_id):
        self.calls.append((test_id, "register", index))
        result = self.stores[index].register(request)
        return result, event(test_id, "control", f"compute-s{index}", "register")

    def benchmark_aggregate(self, index, task_id, test_id):
        self.calls.append((test_id, "aggregate", index))
        result = self.stores[index].aggregate(task_id)
        return result, event(test_id, "control", f"compute-s{index}", "aggregate", 0, 13)


class BenchmarkPartyClient:
    def __init__(self, executors, compute):
        self.executors = executors
        self.calls = []
        self.services = {
            party: ShareService(
                executor,
                {1: "memory://s1", 2: "memory://s2"},
                submitter=lambda index, submission: compute.stores[index].submit(submission),
            )
            for party, executor in executors.items()
        }

    def benchmark_plain(self, party, request):
        self.calls.append((request.test_id, party, "plain"))
        started = datetime.utcnow()
        result = self.executors[party].execute(
            StatisticsRequest(
                task_id=request.task_id,
                query_type=request.query_type,
                start_time=request.start_time,
                end_time=request.end_time,
                group_by=request.interval,
            )
        )
        response = BenchmarkPlainResponse(statistics=result, local_duration_ms=0.1)
        body_bytes = len(response.model_dump_json().encode("utf-8"))
        return response, event(
            request.test_id, "control", f"party-{party.value[-1].lower()}",
            "statistics", 17, body_bytes,
        )

    def benchmark_shared(self, party, request):
        self.calls.append((request.test_id, party, "shared"))
        ack, local_ms, share_ms, events = self.services[party].process_measured(
            request=self._secret_request(request), test_id=request.test_id, internal_token="test-token"
        )
        response = BenchmarkSharedResponse(
            acknowledgement=ack,
            local_duration_ms=local_ms,
            share_generation_duration_ms=share_ms,
            performance_events=events,
        )
        return response, event(
            request.test_id, "control", f"party-{party.value[-1].lower()}",
            "tasks", 19, len(response.model_dump_json().encode("utf-8")),
        )

    @staticmethod
    def _secret_request(request):
        from common.schemas import SecretTaskRequest

        return SecretTaskRequest(
            task_id=request.task_id,
            query_type=request.query_type,
            start_time=request.start_time,
            end_time=request.end_time,
            group_by=request.interval,
            expected_parties=request.parties,
            calculation_mode=request.mode,
            dp_parameters=request.dp_parameters,
        )


@pytest.fixture()
def benchmark_service(tmp_path, benchmark_network):
    factory = create_session_factory(f"sqlite:///{(tmp_path / 'performance.db').as_posix()}")
    create_tables(factory)
    compute = BenchmarkComputeClient()
    party = BenchmarkPartyClient(benchmark_network, compute)
    session = factory()
    service = PerformanceService(session, party, compute, poll_interval=0, poll_attempts=2)
    try:
        yield session, service, party, compute
    finally:
        session.close()


def request(mode=CalculationMode.PLAIN, parties=None, epsilon=None):
    return BenchmarkTestCreate(
        parties=parties or [OrganizationId.ORG_A],
        query_type=QueryType.SUM,
        mode=mode,
        epsilon=epsilon,
    )


def test_plain_uses_only_control_and_selected_party_and_returns_no_result(benchmark_service):
    session, service, party, compute = benchmark_service
    item = service.create_and_run(request(), "analyst_demo")
    response = service.to_response(item)
    assert response.status == "COMPLETED"
    assert compute.calls == []
    assert response.summary.participant_nodes == 2
    assert response.summary.communication_bytes > 0
    assert {link.target_node for link in response.links} == {"party-a"}
    assert "local_statistics" not in {phase.key for phase in response.phases}
    assert "result" not in response.model_dump()
    assert "statistics" not in response.model_dump()
    assert party.calls[0][2] == "plain"
    assert session.scalar(select(func.count()).select_from(PrivacyBudget)) == 0


def test_secret_share_returns_real_party_to_compute_events(benchmark_service):
    _, service, _, compute = benchmark_service
    item = service.create_and_run(
        request(CalculationMode.SECRET_SHARE, list(OrganizationId)), "analyst_demo"
    )
    response = service.to_response(item)
    assert response.status == "COMPLETED"
    assert "local_statistics" not in {phase.key for phase in response.phases}
    assert {link.operation for link in response.links} >= {"register", "submit_share", "aggregate"}
    assert {link.target_node for link in response.links} >= {"compute-s1", "compute-s2"}
    assert any(call[1] == "aggregate" for call in compute.calls)


def test_distributed_dp_completes_without_business_budget_consumption(benchmark_service):
    session, service, _, _ = benchmark_service
    item = service.create_and_run(
        request(CalculationMode.DISTRIBUTED_DP, list(OrganizationId), 1.0), "analyst_demo"
    )
    response = service.to_response(item)
    assert response.status == "COMPLETED"
    assert response.epsilon == 1.0
    assert session.scalar(select(func.count()).select_from(PrivacyBudget)) == 0
    assert "result" not in response.model_dump()


def test_time_series_requires_and_executes_with_real_interval(benchmark_service):
    from common.enums import GroupBy

    _, service, _, _ = benchmark_service
    item = service.create_and_run(
        BenchmarkTestCreate(
            parties=[OrganizationId.ORG_A],
            query_type=QueryType.TIME_SERIES,
            mode=CalculationMode.SECRET_SHARE,
            interval=GroupBy.HOUR,
        ),
        "analyst_demo",
    )
    response = service.to_response(item)
    assert response.status == "COMPLETED"
    assert response.interval == GroupBy.HOUR
    assert "result" not in response.model_dump()


def test_separate_test_ids_never_mix_persisted_events(benchmark_service):
    session, service, _, _ = benchmark_service
    first = service.create_and_run(request(), "analyst_demo")
    second = service.create_and_run(request(), "analyst_demo")
    assert first.id != second.id
    first_ids = set(session.scalars(
        select(PerformanceCommunicationEventModel.test_id)
        .where(PerformanceCommunicationEventModel.test_id == first.id)
    ))
    second_ids = set(session.scalars(
        select(PerformanceCommunicationEventModel.test_id)
        .where(PerformanceCommunicationEventModel.test_id == second.id)
    ))
    assert first_ids == {first.id}
    assert second_ids == {second.id}


def test_performance_api_requires_session_and_allows_analyst(tmp_path, benchmark_network):
    database_url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    settings = ControlSettings(
        database_url=database_url,
        calculation_mode=CalculationMode.PLAIN,
        demo_seed_enabled=True,
        demo_passwords={
            "analyst_demo": "benchmark-password",
            "owner_a": "benchmark-password",
            "owner_b": "benchmark-password",
            "owner_c": "benchmark-password",
            "auditor_demo": "benchmark-password",
            "admin_demo": "benchmark-password",
        },
    )
    compute = BenchmarkComputeClient()
    party = BenchmarkPartyClient(benchmark_network, compute)
    client = TestClient(create_app(settings, party_client=party, compute_client=compute))
    payload = {
        "benchmark_id": "ENERGY_BENCHMARK_V1",
        "parties": ["ORG_A"],
        "query_type": "SUM",
        "mode": "PLAIN",
        "epsilon": None,
        "interval": None,
    }
    assert client.post("/api/v1/performance-tests", json=payload).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "analyst_demo", "password": "benchmark-password"},
    ).status_code == 200
    response = client.post("/api/v1/performance-tests", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert "result" not in body
    assert client.get("/api/v1/performance-tests").status_code == 200


def test_byte_count_uses_serialized_utf8_lengths(monkeypatch):
    from control_plane.services.party_client import PartyClient

    captured = {}

    class Response:
        content = "响应完成".encode("utf-8")

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "statistics": {
                    "task_id": "TASK-UTF8",
                    "organization_id": "ORG_A",
                    "query_type": "SUM",
                    "sum": 1.0,
                    "count": 1,
                    "value": 1.0,
                },
                "local_duration_ms": 1.0,
            }

    def fake_post(url, content, headers, timeout):
        captured["content"] = content
        return Response()

    monkeypatch.setattr("control_plane.services.party_client.httpx.post", fake_post)
    payload = request().model_dump()
    from common.performance import BenchmarkPartyRequest

    benchmark_request = BenchmarkPartyRequest(
        **payload,
        test_id="PERF-UTF8",
        task_id="TASK-UTF8",
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 2),
    )
    _, measured = PartyClient(
        {OrganizationId.ORG_A: "http://party-a"}, internal_token="token"
    ).benchmark_plain(OrganizationId.ORG_A, benchmark_request)
    assert measured.request_bytes == len(captured["content"])
    assert measured.response_bytes == len("响应完成".encode("utf-8"))
    assert measured.total_bytes == measured.request_bytes + measured.response_bytes


def test_party_benchmark_endpoint_requires_internal_identity_and_uses_its_configured_file(
    tmp_path, benchmark_network
):
    from party_node.config import PartySettings
    from party_node.main import create_app as create_party_app

    business_file = tmp_path / "business.parquet"
    duckdb.connect(":memory:").execute(
        f"""COPY (SELECT 'BUSINESS_001' household_id, 'ORG_A' organization_id,
                   CAST('2026-01-01' AS TIMESTAMP) AS timestamp, 999.0 energy_kwh)
            TO '{business_file.as_posix()}' (FORMAT PARQUET)"""
    )
    settings = PartySettings(
        OrganizationId.ORG_A,
        "party-a",
        8101,
        business_file,
        benchmark_data_path=benchmark_network[OrganizationId.ORG_A].repository.parquet_path,
        internal_service_token="internal-only",
    )
    client = TestClient(create_party_app(settings))
    payload = {
        "benchmark_id": "ENERGY_BENCHMARK_V1",
        "parties": ["ORG_A"],
        "query_type": "SUM",
        "mode": "PLAIN",
        "epsilon": None,
        "interval": None,
        "test_id": "PERF-PARTY-A",
        "task_id": "TASK-PARTY-A",
        "start_time": "2026-01-01T00:00:00",
        "end_time": "2026-01-02T00:00:00",
        "dp_parameters": None,
    }
    assert client.post("/internal/benchmark/statistics", json=payload).status_code == 401
    mismatch = client.post(
        "/internal/benchmark/statistics",
        json=payload,
        headers={"X-Internal-Token": "internal-only", "X-PrivGrid-Performance-Test-ID": "OTHER"},
    )
    assert mismatch.status_code == 400
    response = client.post(
        "/internal/benchmark/statistics",
        json=payload,
        headers={
            "X-Internal-Token": "internal-only",
            "X-PrivGrid-Performance-Test-ID": "PERF-PARTY-A",
        },
    )
    assert response.status_code == 200, response.text
    # The configured synthetic file contains 48 clipped 1.25 kWh rows; the
    # business file's 999 value must never enter the Benchmark repository.
    assert response.json()["statistics"]["sum"] == pytest.approx(60.0)
