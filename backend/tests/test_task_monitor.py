import json
from datetime import datetime

from fastapi.testclient import TestClient

from common.enums import OrganizationId, TaskStatus
from control_plane.config import ControlSettings
from control_plane.database.session import create_session_factory, create_tables
from control_plane.main import create_app
from control_plane.models.task import Task
from control_plane.services.task_monitor import (
    MonitorState,
    TaskMonitorStore,
    build_monitor_response,
)


def test_monitor_store_tracks_stage_and_counts_only() -> None:
    store = TaskMonitorStore()
    store.create("TASK-MON-1", ["ORG_A", "ORG_B"], datetime(2026, 1, 1))
    store.update(
        "TASK-MON-1",
        current_stage="COMPLETED",
        party_statuses={"ORG_A": "SHARED", "ORG_B": "SHARED"},
        compute_node_statuses={"S1": "READY", "S2": "READY"},
        submitted_share_count=2,
        execution_time_ms=120,
    )
    state = store.get("TASK-MON-1")
    assert state is not None
    assert state.current_stage == "COMPLETED"
    assert state.submitted_share_count == 2
    assert state.execution_time_ms == 120


def test_monitor_response_never_contains_secret_or_plaintext_fields() -> None:
    task = Task(
        task_id="TASK-MON-2",
        status=TaskStatus.COMPLETED.value,
        query_type="SUM",
        parties_json=json.dumps(["ORG_A", "ORG_B", "ORG_C"]),
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 2),
        calculation_mode="DISTRIBUTED_DP",
        epsilon=1.0,
        privacy_unit="household",
        mechanism="distributed_laplace",
        result_json=json.dumps({"value": 123.0}),
    )
    state = MonitorState(
        task_id=task.task_id,
        current_stage="COMPLETED",
        party_statuses={"ORG_A": "SHARED", "ORG_B": "SHARED", "ORG_C": "SHARED"},
        compute_node_statuses={"S1": "READY", "S2": "READY"},
        expected_parties=["ORG_A", "ORG_B", "ORG_C"],
        submitted_share_count=3,
        execution_time_ms=88,
    )
    response = build_monitor_response(task, state)
    payload = response.model_dump(mode="json")
    assert payload["task_id"] == "TASK-MON-2"
    assert payload["progress"] == 100.0
    assert payload["submitted_share_count"] == 3
    allowed_keys = {
        "task_id",
        "status",
        "current_stage",
        "progress",
        "party_statuses",
        "compute_node_statuses",
        "expected_parties",
        "submitted_share_count",
        "started_at",
        "updated_at",
        "execution_time_ms",
    }
    assert set(payload) == allowed_keys


def test_monitor_endpoint_returns_safe_fields_for_existing_task(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'monitor.db').as_posix()}"
    factory = create_session_factory(database_url)
    create_tables(factory)
    settings = ControlSettings(database_url=database_url)
    client = TestClient(create_app(settings))
    with factory() as session:
        session.add(
            Task(
                task_id="TASK-MON-3",
                status=TaskStatus.RECONSTRUCTING.value,
                query_type="TIME_SERIES",
                parties_json=json.dumps(["ORG_A", "ORG_B", "ORG_C"]),
                start_time=datetime(2026, 1, 1),
                end_time=datetime(2026, 1, 2),
                group_by="1h",
                calculation_mode="DISTRIBUTED_DP",
                epsilon=1.0,
                privacy_unit="household",
                mechanism="distributed_vector_laplace",
                result_json=json.dumps({"series": [{"timestamp": "2026-01-01T00:00:00", "sum": 1.0}]}),
            )
        )
        session.commit()
    response = client.get("/api/v1/tasks/TASK-MON-3/monitor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "TASK-MON-3"
    assert payload["current_stage"] == "RECONSTRUCTING"
    assert payload["expected_parties"] == ["ORG_A", "ORG_B", "ORG_C"]
    assert payload["submitted_share_count"] is None
    assert "series" not in payload
    assert "result" not in payload


def test_monitor_endpoint_404_for_unknown_task(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'monitor-404.db').as_posix()}"
    factory = create_session_factory(database_url)
    create_tables(factory)
    settings = ControlSettings(database_url=database_url)
    client = TestClient(create_app(settings))
    response = client.get("/api/v1/tasks/TASK-NOT-EXIST/monitor")
    assert response.status_code == 404
