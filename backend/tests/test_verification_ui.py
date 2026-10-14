import json
from datetime import datetime

import httpx
from fastapi.testclient import TestClient

from common.enums import CalculationMode, QueryType, TaskStatus
from control_plane.config import ControlSettings
from control_plane.database.session import create_session_factory, create_tables
from control_plane.main import create_app
from control_plane.models.task import Task
from control_plane.models.task_audit import TaskAudit
from control_plane.services.system_health_service import SystemHealthService


class UnusedClient:
    pass


def settings_for(tmp_path) -> ControlSettings:
    return ControlSettings(
        database_url=f"sqlite:///{(tmp_path / 'verification.db').as_posix()}",
        request_timeout=0.1,
    )


def health_service(settings, offline_port=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if offline_port and request.url.port == offline_port:
            raise httpx.ConnectError("node offline", request=request)
        port = request.url.port
        return httpx.Response(
            200,
            json={"service": f"service-{port}", "status": "ok", "version": "0.4.0"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=0.1)
    return SystemHealthService(settings, client)


def test_verify_page_and_static_assets_are_available(tmp_path) -> None:
    settings = settings_for(tmp_path)
    client = TestClient(
        create_app(settings, UnusedClient(), UnusedClient(), health_service(settings))
    )
    page = client.get("/verify")
    css = client.get("/verify/assets/styles.css")
    script = client.get("/verify/assets/app.js")
    assert page.status_code == 200
    assert "分布式差分隐私后端验证台" in page.text
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]


def test_system_health_aggregate_returns_all_services(tmp_path) -> None:
    settings = settings_for(tmp_path)
    client = TestClient(
        create_app(settings, UnusedClient(), UnusedClient(), health_service(settings))
    )
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["services"]) == 7
    assert {item["service_id"] for item in payload["services"]} >= {"frontend", "control"}
    assert all(item["online"] for item in payload["services"])


def test_offline_node_does_not_fail_system_health_endpoint(tmp_path) -> None:
    settings = settings_for(tmp_path)
    client = TestClient(
        create_app(
            settings,
            UnusedClient(),
            UnusedClient(),
            health_service(settings, offline_port=8102),
        )
    )
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    services = response.json()["services"]
    party_b = next(item for item in services if item["service_id"] == "party-b")
    assert party_b["online"] is False
    assert "offline" in party_b["error"]


def seed_task_and_audit(settings: ControlSettings) -> None:
    factory = create_session_factory(settings.database_url)
    create_tables(factory)
    now = datetime(2026, 7, 28, 12, 0, 0)
    with factory() as session:
        session.add(
            Task(
                task_id="TASK-VERIFY",
                status=TaskStatus.COMPLETED.value,
                query_type=QueryType.SUM.value,
                parties_json=json.dumps(["ORG_A", "ORG_B", "ORG_C"]),
                start_time=datetime(2012, 11, 11),
                end_time=datetime(2012, 11, 12),
                calculation_mode=CalculationMode.DISTRIBUTED_DP.value,
                epsilon=1.0,
                privacy_unit="household",
                sensitivity_json="240.0",
                mechanism="distributed_laplace",
                budget_status="CONSUMED",
                result_json=json.dumps({"value": 3500.0}),
                created_at=now,
                updated_at=now,
                duration_ms=1234,
            )
        )
        session.add(
            TaskAudit(
                task_id="TASK-VERIFY",
                query_type=QueryType.SUM.value,
                parties_json=json.dumps(["ORG_A", "ORG_B", "ORG_C"]),
                epsilon=1.0,
                sensitivity_json="240.0",
                mechanism="distributed_laplace",
                privacy_unit="household",
                calculation_mode=CalculationMode.DISTRIBUTED_DP.value,
                budget_before=20.0,
                budget_after=19.0,
                execution_time_ms=1234,
                status=TaskStatus.COMPLETED.value,
                created_at=now,
            )
        )
        session.commit()


def test_recent_tasks_endpoint_returns_latest_tasks(tmp_path) -> None:
    settings = settings_for(tmp_path)
    seed_task_and_audit(settings)
    client = TestClient(
        create_app(settings, UnusedClient(), UnusedClient(), health_service(settings))
    )
    response = client.get("/api/v1/tasks?limit=10")
    assert response.status_code == 200
    assert response.json()[0]["task_id"] == "TASK-VERIFY"
    assert response.json()[0]["duration_ms"] == 1234


def test_audit_endpoint_exposes_only_safe_fields(tmp_path) -> None:
    settings = settings_for(tmp_path)
    seed_task_and_audit(settings)
    client = TestClient(
        create_app(settings, UnusedClient(), UnusedClient(), health_service(settings))
    )
    response = client.get("/api/v1/audit/events/TASK-VERIFY")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "task_id",
        "query_type",
        "parties",
        "epsilon",
        "sensitivity",
        "mechanism",
        "privacy_unit",
        "calculation_mode",
        "budget_before",
        "budget_after",
        "execution_time_ms",
        "status",
            "created_at",
            "dataset_versions",
        }
    assert payload["dataset_versions"] == {}
    forbidden = {"result", "result_json", "noise", "share_1", "share_2", "local_statistic"}
    assert forbidden.isdisjoint(payload)
