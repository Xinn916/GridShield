import json
from datetime import datetime

from fastapi.testclient import TestClient

from control_plane.config import ControlSettings
from control_plane.database.session import create_session_factory, create_tables
from control_plane.main import create_app
from control_plane.models.task_audit import TaskAudit


def seeded_client(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'audit.db').as_posix()}"
    factory = create_session_factory(database_url)
    create_tables(factory)
    with factory() as session:
        for index, status in [(1, "COMPLETED"), (2, "FAILED")]:
            session.add(
                TaskAudit(
                    task_id=f"TASK-AUDIT-{index}",
                    query_type="SUM",
                    parties_json=json.dumps(["ORG_A", "ORG_B"]),
                    epsilon=1.0,
                    sensitivity_json=json.dumps(240.0),
                    mechanism="distributed_laplace",
                    privacy_unit="household",
                    calculation_mode="DISTRIBUTED_DP",
                    budget_before=20.0,
                    budget_after=19.0 if status == "COMPLETED" else 20.0,
                    execution_time_ms=123,
                    status=status,
                    created_at=datetime(2026, 1, 1, hour=index),
                )
            )
        session.commit()
    settings = ControlSettings(database_url=database_url)
    return TestClient(create_app(settings))


def test_audit_events_list_returns_safe_fields_in_descending_order(tmp_path) -> None:
    client = seeded_client(tmp_path)
    response = client.get("/api/v1/audit/events")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["task_id"] == "TASK-AUDIT-2"
    assert payload[1]["task_id"] == "TASK-AUDIT-1"
    assert payload[0]["query_type"] == "SUM"
    assert payload[0]["parties"] == ["ORG_A", "ORG_B"]
    assert payload[0]["epsilon"] == 1.0
    assert payload[0]["mechanism"] == "distributed_laplace"
    assert payload[0]["calculation_mode"] == "DISTRIBUTED_DP"
    assert payload[0]["budget_before"] == 20.0
    assert payload[0]["budget_after"] == 20.0
    assert "result" not in payload[0]


def test_audit_events_list_respects_limit(tmp_path) -> None:
    client = seeded_client(tmp_path)
    response = client.get("/api/v1/audit/events?limit=1")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_audit_event_single_endpoint_still_works(tmp_path) -> None:
    client = seeded_client(tmp_path)
    response = client.get("/api/v1/audit/events/TASK-AUDIT-1")
    assert response.status_code == 200
    assert response.json()["task_id"] == "TASK-AUDIT-1"
