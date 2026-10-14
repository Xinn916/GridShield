import json
from datetime import datetime

from control_plane.database.session import create_session_factory, create_tables
from control_plane.models.privacy_budget import PrivacyBudget
from control_plane.models.privacy_reservation import PrivacyReservation
from control_plane.models.task import Task
from control_plane.models.task_audit import TaskAudit
from scripts.reset_demo_budget import main


def seeded_database(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'reset.db').as_posix()}"
    factory = create_session_factory(database_url)
    create_tables(factory)
    now = datetime(2026, 1, 1)
    with factory() as session:
        session.add(
            PrivacyBudget(
                budget_id="BUDGET-demo-analyst-GLOBAL",
                subject_id="demo-analyst",
                data_scope="GLOBAL",
                total_epsilon=20.0,
                used_epsilon=7.0,
                reserved_epsilon=1.0,
            )
        )
        session.add(
            Task(
                task_id="TASK-KEEP",
                status="COMPLETED",
                query_type="SUM",
                parties_json=json.dumps(["ORG_A"]),
                start_time=now,
                end_time=now,
                calculation_mode="DISTRIBUTED_DP",
                epsilon=1.0,
                privacy_unit="household",
                mechanism="distributed_laplace",
                budget_status="CONSUMED",
            )
        )
        session.add(
            TaskAudit(
                task_id="TASK-KEEP",
                query_type="SUM",
                parties_json=json.dumps(["ORG_A"]),
                epsilon=1.0,
                mechanism="distributed_laplace",
                privacy_unit="household",
                calculation_mode="DISTRIBUTED_DP",
                status="COMPLETED",
                created_at=now,
            )
        )
        session.add(
            PrivacyReservation(
                task_id="TASK-RESERVED",
                budget_id="BUDGET-demo-analyst-GLOBAL",
                epsilon=1.0,
                status="RESERVED",
                budget_before=12.0,
            )
        )
        session.commit()
    return database_url, factory


def test_preview_does_not_modify_budget(monkeypatch, tmp_path) -> None:
    database_url, factory = seeded_database(tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert main([]) == 0
    with factory() as session:
        budget = session.get(PrivacyBudget, "BUDGET-demo-analyst-GLOBAL")
        assert (budget.total_epsilon, budget.used_epsilon, budget.reserved_epsilon) == (20.0, 7.0, 1.0)


def test_confirm_resets_budget_and_preserves_task_and_audit(monkeypatch, tmp_path) -> None:
    database_url, factory = seeded_database(tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert main(["--total-epsilon", "25", "--confirm"]) == 0
    with factory() as session:
        budget = session.get(PrivacyBudget, "BUDGET-demo-analyst-GLOBAL")
        assert (budget.total_epsilon, budget.used_epsilon, budget.reserved_epsilon) == (25.0, 0.0, 0.0)
        assert budget.total_epsilon - budget.used_epsilon - budget.reserved_epsilon == 25.0
        assert session.get(Task, "TASK-KEEP") is not None
        assert session.get(TaskAudit, "TASK-KEEP") is not None
        reservation = session.get(PrivacyReservation, "TASK-RESERVED")
        assert reservation is not None and reservation.status == "RESERVED"
