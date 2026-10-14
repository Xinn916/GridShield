import json
from datetime import datetime, timedelta

import pytest

from common.enums import OrganizationId, QueryType, UserRole
from common.schemas import TaskCreateRequest
from control_plane.database.session import create_session_factory, create_tables
from control_plane.models.access_control import AccessGrant, DemoUser, GrantReservation
from control_plane.services.access_control_service import AccessControlService
from control_plane.services.authorization_service import AuthorizationService
from control_plane.services.report_service import AnalystReportService


def make_request(grant_id: str, *, epsilon: float = 1.0) -> TaskCreateRequest:
    return TaskCreateRequest(
        grant_id=grant_id,
        query_type=QueryType.SUM,
        parties=[OrganizationId.ORG_A, OrganizationId.ORG_B, OrganizationId.ORG_C],
        start_time=datetime(2012, 11, 11),
        end_time=datetime(2012, 11, 12),
        epsilon=epsilon,
    )


def make_grant(grant_id: str, user_id: str, *, total: float = 20.0) -> AccessGrant:
    return AccessGrant(
        grant_id=grant_id,
        request_id=f"REQUEST-{grant_id}",
        grantee_user_id=user_id,
        parties_json=json.dumps([party.value for party in OrganizationId]),
        allowed_query_types_json=json.dumps([QueryType.SUM.value]),
        allowed_start_time=datetime(2012, 1, 1),
        allowed_end_time=datetime(2013, 1, 1),
        allowed_group_by_json="[]",
        max_epsilon_per_query=5.0,
        total_epsilon_limit=total,
        epsilon_consumed=0.0,
        epsilon_reserved=0.0,
        valid_from=datetime(2012, 1, 1),
        expires_at=datetime.utcnow() + timedelta(days=30),
        status="ACTIVE",
    )


def setup_session(tmp_path):
    url = f"sqlite:///{(tmp_path / 'grant-budget.db').as_posix()}"
    factory = create_session_factory(url)
    create_tables(factory)
    session = factory()
    user = DemoUser(
        user_id="analyst_demo",
        username="analyst_demo",
        password_salt="salt",
        password_hash="hash",
        role=UserRole.ANALYST.value,
        is_active=True,
    )
    session.add_all([user, make_grant("GRANT-A", user.user_id), make_grant("GRANT-B", user.user_id)])
    session.commit()
    return session, user


def test_grants_are_isolated_and_consume_once(tmp_path):
    session, user = setup_session(tmp_path)
    try:
        auth = AuthorizationService(session)
        auth.authorize_and_reserve("TASK-A-1", user, make_request("GRANT-A"))
        auth.consume("TASK-A-1")
        auth.consume("TASK-A-1")
        grant_a = session.get(AccessGrant, "GRANT-A")
        grant_b = session.get(AccessGrant, "GRANT-B")
        assert grant_a.epsilon_consumed == pytest.approx(1.0)
        assert grant_a.epsilon_reserved == pytest.approx(0.0)
        assert grant_b.epsilon_consumed == pytest.approx(0.0)
        assert grant_b.epsilon_reserved == pytest.approx(0.0)
        assert grant_a.total_epsilon_limit - grant_a.epsilon_consumed - grant_a.epsilon_reserved == pytest.approx(19.0)
        assert grant_b.total_epsilon_limit - grant_b.epsilon_consumed - grant_b.epsilon_reserved == pytest.approx(20.0)
    finally:
        session.close()


def test_failed_task_releases_grant_reservation_and_non_dp_does_not_reserve(tmp_path):
    session, user = setup_session(tmp_path)
    try:
        auth = AuthorizationService(session)
        auth.authorize_and_reserve("TASK-FAIL", user, make_request("GRANT-A"))
        grant = session.get(AccessGrant, "GRANT-A")
        assert grant.epsilon_reserved == pytest.approx(1.0)
        auth.release("TASK-FAIL")
        auth.release("TASK-FAIL")
        assert grant.epsilon_consumed == pytest.approx(0.0)
        assert grant.epsilon_reserved == pytest.approx(0.0)
        assert session.get(GrantReservation, "TASK-FAIL").status == "RELEASED"

        operation = auth.authorize_and_reserve(
            "TASK-PLAIN",
            user,
            make_request("GRANT-A"),
            reserve_budget=False,
        )
        assert operation.status == "NOT_REQUIRED"
        assert session.get(GrantReservation, "TASK-PLAIN") is None
        assert grant.epsilon_consumed == pytest.approx(0.0)
        assert grant.epsilon_reserved == pytest.approx(0.0)
    finally:
        session.close()


def test_full_reserved_grant_recovers_after_release(tmp_path):
    session, user = setup_session(tmp_path)
    try:
        grant = session.get(AccessGrant, "GRANT-A")
        grant.total_epsilon_limit = 1.0
        session.commit()
        auth = AuthorizationService(session)
        auth.authorize_and_reserve("TASK-FULL", user, make_request("GRANT-A"))
        AccessControlService(session)._refresh_grant(grant)
        assert grant.status == "EXHAUSTED"
        retry = auth.authorize_and_reserve("TASK-FULL", user, make_request("GRANT-A"))
        assert retry.status == "RESERVED"
        auth.release("TASK-FULL")
        assert grant.status == "ACTIVE"
        assert grant.epsilon_consumed == pytest.approx(0.0)
        assert grant.epsilon_reserved == pytest.approx(0.0)
    finally:
        session.close()


def test_non_dp_scope_check_does_not_consume_or_block_exhausted_budget(tmp_path):
    session, user = setup_session(tmp_path)
    try:
        grant = session.get(AccessGrant, "GRANT-A")
        grant.total_epsilon_limit = 1.0
        session.commit()
        auth = AuthorizationService(session)
        auth.authorize_and_reserve("TASK-DP", user, make_request("GRANT-A"))
        auth.consume("TASK-DP")
        assert grant.status == "EXHAUSTED"

        operation = auth.authorize_and_reserve(
            "TASK-PLAIN-AFTER-DP",
            user,
            make_request("GRANT-A"),
            reserve_budget=False,
        )
        assert operation.status == "NOT_REQUIRED"
        assert grant.epsilon_consumed == pytest.approx(1.0)
        assert grant.epsilon_reserved == pytest.approx(0.0)
        assert session.get(GrantReservation, "TASK-PLAIN-AFTER-DP") is None
    finally:
        session.close()


def test_report_sums_independent_grant_balances(tmp_path):
    session, user = setup_session(tmp_path)
    try:
        grant_a = session.get(AccessGrant, "GRANT-A")
        grant_b = session.get(AccessGrant, "GRANT-B")
        grant_a.epsilon_consumed = 4.0
        grant_b.epsilon_reserved = 2.0
        session.commit()
        report = AnalystReportService(session).build(user)
        assert report.remaining_privacy_budget == pytest.approx(34.0)
    finally:
        session.close()
