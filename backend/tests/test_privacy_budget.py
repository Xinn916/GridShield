import pytest
from pydantic import ValidationError

from common.enums import OrganizationId, QueryType
from common.schemas import TaskCreateRequest
from control_plane.database.session import create_session_factory, create_tables
from control_plane.services.privacy_budget_service import (
    InsufficientPrivacyBudgetError,
    PrivacyBudgetService,
)


def budget_service(tmp_path, total=5.0):
    factory = create_session_factory(f"sqlite:///{(tmp_path / 'budget.db').as_posix()}")
    create_tables(factory)
    session = factory()
    return session, PrivacyBudgetService(session, total)


@pytest.mark.parametrize("epsilon", [0, -0.1, 5.01])
def test_invalid_epsilon_is_rejected(epsilon) -> None:
    with pytest.raises(ValidationError):
        TaskCreateRequest(
            query_type=QueryType.SUM,
            parties=[OrganizationId.ORG_A],
            start_time="2012-01-01T00:00:00",
            end_time="2012-01-02T00:00:00",
            epsilon=epsilon,
        )


def test_insufficient_budget_is_rejected(tmp_path) -> None:
    session, service = budget_service(tmp_path, total=0.5)
    try:
        with pytest.raises(InsufficientPrivacyBudgetError):
            service.reserve("TASK-BUDGET", "demo-analyst", "GLOBAL", 1.0)
    finally:
        session.close()


def test_successful_budget_is_consumed_only_once(tmp_path) -> None:
    session, service = budget_service(tmp_path)
    try:
        service.reserve("TASK-BUDGET", "demo-analyst", "GLOBAL", 1.0)
        first = service.consume("TASK-BUDGET")
        retry = service.consume("TASK-BUDGET")
        budget = service.response("demo-analyst", "GLOBAL")
        assert first.status == retry.status == "CONSUMED"
        assert budget.used_epsilon == pytest.approx(1.0)
        assert budget.reserved_epsilon == pytest.approx(0.0)
    finally:
        session.close()


def test_failed_task_releases_reserved_budget(tmp_path) -> None:
    session, service = budget_service(tmp_path)
    try:
        service.reserve("TASK-BUDGET", "demo-analyst", "GLOBAL", 1.0)
        service.release("TASK-BUDGET")
        budget = service.response("demo-analyst", "GLOBAL")
        assert budget.used_epsilon == pytest.approx(0.0)
        assert budget.reserved_epsilon == pytest.approx(0.0)
        assert budget.remaining_epsilon == pytest.approx(5.0)
    finally:
        session.close()


def test_reservation_retry_does_not_reserve_twice(tmp_path) -> None:
    session, service = budget_service(tmp_path)
    try:
        first = service.reserve("TASK-BUDGET", "demo-analyst", "GLOBAL", 1.0)
        retry = service.reserve("TASK-BUDGET", "demo-analyst", "GLOBAL", 1.0)
        budget = service.response("demo-analyst", "GLOBAL")
        assert first == retry
        assert budget.reserved_epsilon == pytest.approx(1.0)
        assert budget.remaining_epsilon == pytest.approx(4.0)
    finally:
        session.close()
