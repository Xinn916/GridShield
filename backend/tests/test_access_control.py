from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from common.enums import CalculationMode, OrganizationId
from common.schemas import ServiceHealthResponse, StatisticsResponse, SystemHealthResponse
from control_plane.config import ControlSettings
from control_plane.database.session import create_session_factory
from control_plane.main import create_app
from control_plane.models.access_control import (
    AccessGrant,
    GrantReservation,
    SecurityAudit,
)
from control_plane.models.privacy_budget import PrivacyBudget
from control_plane.models.task import Task
from control_plane.models.task_audit import TaskAudit


PASSWORD = "demo-test-password"
DEMO_PASSWORDS = {
    username: PASSWORD
    for username in (
        "analyst_demo",
        "owner_a",
        "owner_b",
        "owner_c",
        "auditor_demo",
        "admin_demo",
    )
}


class RecordingPartyClient:
    def __init__(self):
        self.calls = []
        self.fail = False

    def statistics(self, party, request):
        self.calls.append((party, request))
        if self.fail:
            raise RuntimeError("injected party failure")
        return StatisticsResponse(
            task_id=request.task_id,
            organization_id=party,
            query_type=request.query_type,
            sum=10.0,
            count=2,
            value=10.0,
        )

    def dispatch_secret(self, party, request):  # pragma: no cover - PLAIN tests must not call this
        raise AssertionError("secret dispatch must not run in PLAIN tests")

    def describe(self, party):
        return {"organization_id": party.value, "status": "ok"}


class NoComputeClient:
    def register(self, index, request):  # pragma: no cover - PLAIN tests must not call this
        raise AssertionError("compute register must not run in PLAIN tests")

    def aggregate(self, index, task_id):  # pragma: no cover - PLAIN tests must not call this
        raise AssertionError("compute aggregate must not run in PLAIN tests")


class StaticHealthService:
    def check_all(self):
        return SystemHealthResponse(
            services=[
                ServiceHealthResponse(service_id="control", name="总控", endpoint="internal://control", online=True, latency_ms=1),
                ServiceHealthResponse(service_id="frontend", name="前端网关 Nginx", endpoint="internal://frontend", online=True, latency_ms=1),
                ServiceHealthResponse(service_id="party-a", name="园区 A", endpoint="internal://party-a", online=True, latency_ms=2),
                ServiceHealthResponse(service_id="party-b", name="园区 B", endpoint="internal://party-b", online=False, latency_ms=3),
                ServiceHealthResponse(service_id="party-c", name="园区 C", endpoint="internal://party-c", online=True, latency_ms=2),
                ServiceHealthResponse(service_id="compute-s1", name="计算节点 S1", endpoint="internal://s1", online=True, latency_ms=2),
                ServiceHealthResponse(service_id="compute-s2", name="计算节点 S2", endpoint="internal://s2", online=True, latency_ms=2),
            ],
            checked_at=datetime.utcnow(),
        )


def make_client(tmp_path, name="access", *, enforcement=True):
    database_url = f"sqlite:///{(tmp_path / f'{name}.db').as_posix()}"
    settings = ControlSettings(
        database_url=database_url,
        calculation_mode=CalculationMode.PLAIN,
        authorization_enforcement_enabled=enforcement,
        demo_seed_enabled=True,
        demo_passwords=DEMO_PASSWORDS,
    )
    party = RecordingPartyClient()
    client = TestClient(
        create_app(
            settings,
            party_client=party,
            compute_client=NoComputeClient(),
            health_service=StaticHealthService(),
        )
    )
    return client, party, create_session_factory(database_url)


def login(client, username):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response


def logout(client):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204, response.text


def request_payload(*, parties=None, query_types=None, group_by=None, total_epsilon=4.0):
    query_types = query_types or ["SUM", "TIME_SERIES"]
    if group_by is None:
        group_by = ["30m", "1h"] if "TIME_SERIES" in query_types else []
    return {
        "purpose": "跨园区用电趋势分析演示",
        "requested_parties": parties or ["ORG_A", "ORG_B"],
        "requested_query_types": query_types,
        "requested_start_time": "2012-11-11T00:00:00Z",
        "requested_end_time": "2012-11-13T00:00:00Z",
        "requested_group_by": group_by,
        "requested_max_epsilon_per_query": 2.0,
        "requested_total_epsilon": total_epsilon,
        "requested_expires_at": "2099-01-01T00:00:00Z",
    }


def submit_request(client, payload=None):
    created = client.post("/api/v1/access-requests", json=payload or request_payload())
    assert created.status_code == 201, created.text
    request_id = created.json()["request_id"]
    submitted = client.post(f"/api/v1/access-requests/{request_id}/submit")
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


def approve(client, approval_id, username, payload=None):
    logout(client)
    login(client, username)
    response = client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json=payload or {"decision": "APPROVED"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_grant(client, *, conditional=False, total_epsilon=4.0):
    login(client, "analyst_demo")
    submitted = submit_request(client, request_payload(total_epsilon=total_epsilon))
    approvals = {item["party_id"]: item["approval_id"] for item in submitted["approvals"]}
    a_payload = None
    if conditional:
        a_payload = {
            "decision": "CONDITIONALLY_APPROVED",
            "reason": "仅允许小时粒度并收紧额度",
            "allowed_query_types": ["SUM", "TIME_SERIES"],
            "allowed_start_time": "2012-11-11T06:00:00Z",
            "allowed_end_time": "2012-11-12T18:00:00Z",
            "allowed_group_by": ["1h"],
            "max_epsilon_per_query": 1.0,
            "total_epsilon_limit": min(total_epsilon, 2.5),
            "expires_at": "2098-01-01T00:00:00Z",
        }
    approve(client, approvals["ORG_A"], "owner_a", a_payload)
    approve(client, approvals["ORG_B"], "owner_b")
    logout(client)
    login(client, "analyst_demo")
    grants = client.get("/api/v1/grants/mine")
    assert grants.status_code == 200, grants.text
    assert len(grants.json()) == 1
    return submitted, grants.json()[0]


def create_single_party_grant(client, party):
    login(client, "analyst_demo")
    submitted = submit_request(
        client,
        request_payload(parties=[party], query_types=["SUM"], group_by=[]),
    )
    approval_id = submitted["approvals"][0]["approval_id"]
    approve(client, approval_id, f"owner_{party[-1].lower()}")
    logout(client)
    login(client, "analyst_demo")
    grants = client.get("/api/v1/grants/mine").json()
    grant = next(item for item in grants if item["request_id"] == submitted["request_id"])
    logout(client)
    return grant


def task_payload(grant_id=None, **changes):
    payload = {
        "grant_id": grant_id,
        "query_type": "SUM",
        "parties": ["ORG_A", "ORG_B"],
        "start_time": "2012-11-11T06:00:00Z",
        "end_time": "2012-11-12T00:00:00Z",
        "epsilon": 1.0,
    }
    payload.update(changes)
    if payload.get("grant_id") is None:
        payload.pop("grant_id", None)
    return payload


def test_authentication_catalog_and_logout(tmp_path):
    client, _, factory = make_client(tmp_path, "auth")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.get("/api/v1/audit/events").status_code == 401
    wrong = client.post(
        "/api/v1/auth/login",
        json={"username": "analyst_demo", "password": "wrong-password"},
    )
    assert wrong.status_code == 401

    response = login(client, "analyst_demo")
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["role"] == "ANALYST"

    catalog = client.get("/api/v1/catalog/assets")
    assert catalog.status_code == 200
    assert {item["asset_id"] for item in catalog.json()} == {
        "ENERGY_ORG_A",
        "ENERGY_ORG_B",
        "ENERGY_ORG_C",
    }
    forbidden = {"household_id", "parquet_path", "download_url", "raw_records"}
    assert all(not forbidden.intersection(item) for item in catalog.json())
    assert all(item["raw_download_allowed"] is False for item in catalog.json())

    logout(client)
    assert client.get("/api/v1/auth/me").status_code == 401
    with factory() as session:
        events = set(session.scalars(select(SecurityAudit.event_type)))
        assert {"LOGIN_FAILED", "LOGIN_SUCCESS", "LOGOUT"}.issubset(events)


def test_owner_assets_are_derived_from_session_party_and_are_safe(tmp_path):
    client, _, _ = make_client(tmp_path, "owner-assets")
    login(client, "owner_a")
    response = client.get("/api/v1/catalog/assets/owner")
    assert response.status_code == 200
    assert [item["asset_id"] for item in response.json()] == ["ENERGY_ORG_A"]
    assert {item["owner_party"] for item in response.json()} == {"ORG_A"}
    switched = client.get("/api/v1/catalog/assets/owner?party_id=ORG_B")
    assert [item["asset_id"] for item in switched.json()] == ["ENERGY_ORG_A"]
    forbidden = {"parquet_path", "household_id", "raw_records", "download_url"}
    assert all(not forbidden.intersection(item) for item in response.json())

    logout(client)
    login(client, "analyst_demo")
    assert client.get("/api/v1/catalog/assets/owner").status_code == 403


def test_owner_grants_cannot_be_switched_to_another_party(tmp_path):
    client, _, _ = make_client(tmp_path, "owner-grants")
    grant_a = create_single_party_grant(client, "ORG_A")
    grant_b = create_single_party_grant(client, "ORG_B")

    login(client, "owner_a")
    response = client.get("/api/v1/grants/owner")
    assert response.status_code == 200
    assert [item["grant_id"] for item in response.json()] == [grant_a["grant_id"]]
    switched = client.get("/api/v1/grants/owner?party_id=ORG_B")
    assert [item["grant_id"] for item in switched.json()] == [grant_a["grant_id"]]
    assert client.get(f"/api/v1/grants/{grant_b['grant_id']}").status_code == 403


def test_owner_policy_summary_contains_only_safe_effective_values(tmp_path):
    client, _, _ = make_client(tmp_path, "policy-summary")
    login(client, "owner_b")
    response = client.get("/api/v1/system/policy-summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["authorization_enforcement_enabled"] is True
    assert payload["raw_download_allowed"] is False
    assert payload["calculation_mode"] == "PLAIN"
    assert payload["supported_query_types"] == ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"]
    assert payload["supported_group_by"] == ["30m", "1h", "1d"]
    assert len(payload["party_nodes"]) == 3
    assert len(payload["compute_nodes"]) == 2
    serialized = response.text.lower()
    for forbidden in ("endpoint", "database", "parquet", "password", "token", "deepseek"):
        assert forbidden not in serialized


def test_admin_system_overview_is_real_read_only_and_safe(tmp_path):
    client, _, _ = make_client(tmp_path, "admin-system-overview")
    login(client, "admin_demo")
    response = client.get("/api/v1/admin/system-overview")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["database"] == {
        "type": "SQLite",
        "connected": True,
        "demo_database": True,
        "note": "当前为 SQLite 单机开发数据库，适用于本地开发和低并发运行；生产环境建议使用 PostgreSQL。",
    }
    assert payload["asset_storage"] == {
        "type": "Parquet",
        "party_count": 3,
        "mount_mode": "READ_ONLY",
    }
    assert payload["frontend_gateway"]["service_id"] == "frontend"
    assert {item["service_id"] for item in payload["party_nodes"]} == {
        "party-a", "party-b", "party-c"
    }
    assert {item["service_id"] for item in payload["compute_nodes"]} == {
        "compute-s1", "compute-s2"
    }
    assert payload["agent_model_configured"] is False
    assert payload["maintenance_records"] == []
    assert payload["system_events"][0]["event_type"] == "LOGIN_SUCCESS"

    baseline = payload["security_baseline"]
    assert baseline["authorization_enforcement_enabled"] is True
    assert baseline["raw_download_disabled"] is True
    assert baseline["session_cookie_http_only"] is True
    assert baseline["cookie_samesite"] == "Lax"
    assert baseline["password_hash_storage"] is True
    assert baseline["session_token_hash_storage"] is True
    assert baseline["did_wallet_verification"] is False
    assert baseline["mfa_enabled"] is False
    assert baseline["ip_allowlist_enabled"] is False
    assert baseline["https_forced"] is False
    assert {item["name"] for item in payload["planned_extensions"]} == {
        "PostgreSQL", "Redis", "MQTT", "对象存储", "通知服务"
    }
    assert all(item["status"] == "PLANNED" for item in payload["planned_extensions"])

    serialized = response.text.lower()
    for forbidden in (
        "database_url", "sqlite:///", "postgresql://", "127.0.0.1",
        "internal://", "password_salt", '"password_hash":', '"token_hash":',
        "deepseek_api_key", "parquet_path", "/app/data",
    ):
        assert forbidden not in serialized

    logout(client)
    login(client, "auditor_demo")
    assert client.get("/api/v1/admin/system-overview").status_code == 403


def test_request_validation_ownership_submission_and_withdrawal(tmp_path):
    client, _, _ = make_client(tmp_path, "requests")
    login(client, "analyst_demo")

    invalid_time = request_payload()
    invalid_time["requested_end_time"] = invalid_time["requested_start_time"]
    assert client.post("/api/v1/access-requests", json=invalid_time).status_code == 422
    invalid_epsilon = request_payload()
    invalid_epsilon["requested_max_epsilon_per_query"] = 6.0
    assert client.post("/api/v1/access-requests", json=invalid_epsilon).status_code == 422

    created = client.post("/api/v1/access-requests", json=request_payload())
    assert created.status_code == 201
    request_id = created.json()["request_id"]
    logout(client)
    login(client, "owner_a")
    assert (
        client.patch(
            f"/api/v1/access-requests/{request_id}", json={"purpose": "越权修改申请"}
        ).status_code
        == 403
    )

    logout(client)
    login(client, "analyst_demo")
    submitted = client.post(f"/api/v1/access-requests/{request_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "PENDING"
    assert len(submitted.json()["approvals"]) == 2
    assert (
        client.patch(
            f"/api/v1/access-requests/{request_id}", json={"purpose": "提交后禁止修改"}
        ).status_code
        == 409
    )
    withdrawn = client.post(f"/api/v1/access-requests/{request_id}/withdraw")
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "REVOKED"


def test_party_scoped_approval_rejection_and_role_permissions(tmp_path):
    client, _, _ = make_client(tmp_path, "approval-roles")
    login(client, "analyst_demo")
    submitted = submit_request(client)
    approvals = {item["party_id"]: item["approval_id"] for item in submitted["approvals"]}
    assert client.get("/api/v1/approvals/pending").status_code == 403

    logout(client)
    login(client, "owner_b")
    assert client.get(f"/api/v1/approvals/{approvals['ORG_A']}").status_code == 403
    assert (
        client.post(
            f"/api/v1/approvals/{approvals['ORG_A']}/decision",
            json={"decision": "APPROVED"},
        ).status_code
        == 403
    )
    rejected = client.post(
        f"/api/v1/approvals/{approvals['ORG_B']}/decision",
        json={"decision": "REJECTED", "reason": "本园区暂不开放"},
    )
    assert rejected.status_code == 200
    logout(client)
    login(client, "analyst_demo")
    detail = client.get(f"/api/v1/access-requests/{submitted['request_id']}")
    assert detail.json()["status"] == "REJECTED"
    assert client.get("/api/v1/grants/mine").json() == []

    logout(client)
    login(client, "auditor_demo")
    assert client.post("/api/v1/access-requests", json=request_payload()).status_code == 403
    assert client.post("/api/v1/tasks", json=task_payload()).status_code == 403


def test_task_audit_is_filtered_by_session_role_and_security_audit_is_global_only(tmp_path):
    client, _, _ = make_client(tmp_path, "audit-role-scope")
    _, grant = create_grant(client)
    created = client.post("/api/v1/tasks", json=task_payload(grant["grant_id"]))
    assert created.status_code == 201, created.text
    task_id = created.json()["task_id"]

    analyst_events = client.get("/api/v1/audit/events")
    assert analyst_events.status_code == 200
    assert task_id in {item["task_id"] for item in analyst_events.json()}
    assert client.get("/api/v1/admin/security-audit").status_code == 403

    logout(client)
    login(client, "owner_a")
    assert task_id in {item["task_id"] for item in client.get("/api/v1/audit/events").json()}

    logout(client)
    login(client, "owner_c")
    assert task_id not in {item["task_id"] for item in client.get("/api/v1/audit/events").json()}
    assert client.get(f"/api/v1/audit/events/{task_id}").status_code == 403
    assert client.get("/api/v1/admin/security-audit").status_code == 403

    for username in ("auditor_demo", "admin_demo"):
        logout(client)
        login(client, username)
        global_events = client.get("/api/v1/audit/events")
        assert global_events.status_code == 200
        assert task_id in {item["task_id"] for item in global_events.json()}
        assert client.get("/api/v1/admin/security-audit").status_code == 200


def test_analyst_report_uses_real_scoped_tasks_budget_and_audits(tmp_path):
    client, _, factory = make_client(tmp_path, "analyst-report")
    _, grant_payload = create_grant(client)
    grant_id = grant_payload["grant_id"]
    created_at = datetime(2026, 8, 1, 10, 0, 0)

    with factory() as session:
        session.add_all([
            Task(
                task_id="TASK-REPORT-1", grant_id=grant_id, status="COMPLETED",
                query_type="TIME_SERIES", parties_json='["ORG_A", "ORG_B"]',
                start_time=created_at, end_time=created_at + timedelta(days=1), group_by="1h",
                calculation_mode="DISTRIBUTED_DP", epsilon=1.0, privacy_unit="household",
                mechanism="distributed_vector_laplace", budget_status="CONSUMED",
                created_at=created_at, updated_at=created_at + timedelta(seconds=2),
                started_at=created_at, completed_at=created_at + timedelta(seconds=2), duration_ms=2000,
            ),
            Task(
                task_id="TASK-REPORT-2", grant_id=grant_id, status="FAILED",
                query_type="SUM", parties_json='["ORG_B"]', start_time=created_at,
                end_time=created_at + timedelta(days=1), group_by=None,
                calculation_mode="DISTRIBUTED_DP", epsilon=0.5, privacy_unit="household",
                mechanism="distributed_laplace", budget_status="RELEASED",
                created_at=created_at + timedelta(minutes=1),
                updated_at=created_at + timedelta(minutes=1, seconds=4),
                started_at=created_at + timedelta(minutes=1),
                completed_at=created_at + timedelta(minutes=1, seconds=4), duration_ms=4000,
            ),
            TaskAudit(
                task_id="TASK-REPORT-1", query_type="TIME_SERIES", group_by="1h",
                bucket_count=24, parties_json='["ORG_A", "ORG_B"]', epsilon=1.0,
                sensitivity_json="1.0", mechanism="distributed_vector_laplace",
                privacy_unit="household", calculation_mode="DISTRIBUTED_DP",
                budget_before=20.0, budget_after=19.0, execution_time_ms=2000,
                status="COMPLETED", created_at=created_at,
            ),
            TaskAudit(
                task_id="TASK-REPORT-2", query_type="SUM", group_by=None,
                bucket_count=None, parties_json='["ORG_B"]', epsilon=0.5,
                sensitivity_json="1.0", mechanism="distributed_laplace",
                privacy_unit="household", calculation_mode="DISTRIBUTED_DP",
                budget_before=19.0, budget_after=19.0, execution_time_ms=4000,
                status="FAILED", created_at=created_at + timedelta(minutes=1),
            ),
            GrantReservation(
                task_id="TASK-REPORT-1", grant_id=grant_id, epsilon=1.0,
                status="CONSUMED", remaining_before=4.0, remaining_after=3.0,
                created_at=created_at, updated_at=created_at + timedelta(seconds=2),
            ),
            GrantReservation(
                task_id="TASK-REPORT-2", grant_id=grant_id, epsilon=0.5,
                status="RELEASED", remaining_before=3.0, remaining_after=3.0,
                created_at=created_at + timedelta(minutes=1),
                updated_at=created_at + timedelta(minutes=1, seconds=4),
            ),
            PrivacyBudget(
                budget_id="BUDGET-analyst_demo-GLOBAL", subject_id="analyst_demo",
                data_scope="GLOBAL", total_epsilon=20.0, used_epsilon=1.0,
                reserved_epsilon=0.0,
            ),
        ])
        session.commit()

    response = client.get("/api/v1/reports/me")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_tasks"] == 2
    assert payload["completed_tasks"] == 1
    assert payload["failed_tasks"] == 1
    assert payload["success_rate"] == pytest.approx(50.0)
    assert payload["average_task_duration_ms"] == pytest.approx(3000.0)
    assert payload["epsilon_consumed"] == pytest.approx(1.0)
    # Reports now aggregate each user's independent Grant balances instead of
    # reading the legacy subject/GLOBAL ledger.
    assert payload["remaining_privacy_budget"] == pytest.approx(4.0)
    assert payload["query_type_counts"]["TIME_SERIES"] == 1
    assert payload["query_type_counts"]["SUM"] == 1
    assert payload["party_participation_counts"] == {"ORG_A": 1, "ORG_B": 2, "ORG_C": 0}
    assert payload["time_series_bucket_count"] == 24
    assert {item["task_id"] for item in payload["recent_tasks"]} == {
        "TASK-REPORT-1", "TASK-REPORT-2"
    }
    time_series = next(item for item in payload["recent_tasks"] if item["task_id"] == "TASK-REPORT-1")
    assert time_series["bucket_count"] == 24
    assert len(payload["recent_grant_usage"]) == 2

    logout(client)
    login(client, "owner_b")
    assert client.get("/api/v1/reports/me").status_code == 403


def test_analyst_report_empty_state_is_zero_and_finite(tmp_path):
    client, _, _ = make_client(tmp_path, "analyst-report-empty")
    login(client, "analyst_demo")
    payload = client.get("/api/v1/reports/me").json()
    assert payload["total_tasks"] == 0
    assert payload["completed_tasks"] == 0
    assert payload["failed_tasks"] == 0
    assert payload["success_rate"] == 0
    assert payload["average_task_duration_ms"] == 0
    assert payload["epsilon_consumed"] == 0
    assert payload["remaining_privacy_budget"] == pytest.approx(20.0)
    assert payload["recent_tasks"] == []
    assert payload["recent_grant_usage"] == []


def test_conditional_approval_intersection_and_grant_idempotence(tmp_path):
    client, _, factory = make_client(tmp_path, "intersection")
    login(client, "analyst_demo")
    submitted = submit_request(client)
    approvals = {item["party_id"]: item["approval_id"] for item in submitted["approvals"]}
    logout(client)
    login(client, "owner_a")
    expanded = client.post(
        f"/api/v1/approvals/{approvals['ORG_A']}/decision",
        json={
            "decision": "CONDITIONALLY_APPROVED",
            "reason": "非法扩大额度",
            "max_epsilon_per_query": 3.0,
        },
    )
    assert expanded.status_code == 409

    narrowed = client.post(
        f"/api/v1/approvals/{approvals['ORG_A']}/decision",
        json={
            "decision": "CONDITIONALLY_APPROVED",
            "reason": "收紧时间、粒度和额度",
            "allowed_query_types": ["SUM", "TIME_SERIES"],
            "allowed_start_time": "2012-11-11T06:00:00Z",
            "allowed_end_time": "2012-11-12T18:00:00Z",
            "allowed_group_by": ["1h"],
            "max_epsilon_per_query": 1.0,
            "total_epsilon_limit": 2.5,
            "expires_at": "2098-01-01T00:00:00Z",
        },
    )
    assert narrowed.status_code == 200
    assert narrowed.json()["decision"] == "CONDITIONALLY_APPROVED"
    approve(client, approvals["ORG_B"], "owner_b")

    logout(client)
    login(client, "analyst_demo")
    grants = client.get("/api/v1/grants/mine").json()
    assert len(grants) == 1
    grant = grants[0]
    assert grant["allowed_start_time"].startswith("2012-11-11T06:00:00")
    assert grant["allowed_end_time"].startswith("2012-11-12T18:00:00")
    assert grant["allowed_group_by"] == ["1h"]
    assert grant["max_epsilon_per_query"] == pytest.approx(1.0)
    assert grant["total_epsilon_limit"] == pytest.approx(2.5)

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AccessGrant)) == 1
        events = set(session.scalars(select(SecurityAudit.event_type)))
        assert {
            "ACCESS_REQUEST_CREATED",
            "ACCESS_REQUEST_SUBMITTED",
            "ACCESS_REQUEST_CONDITIONALLY_APPROVED",
            "ACCESS_REQUEST_APPROVED",
            "GRANT_CREATED",
        }.issubset(events)


def test_task_authorization_scope_budget_and_failure_release(tmp_path):
    client, party, factory = make_client(tmp_path, "task-auth")
    _, grant = create_grant(client, conditional=True)
    grant_id = grant["grant_id"]

    forbidden_payloads = [
        task_payload(),
        task_payload(grant_id, parties=["ORG_C"]),
        task_payload(grant_id, query_type="COUNT"),
        task_payload(grant_id, start_time="2012-11-11T00:00:00Z"),
        task_payload(
            grant_id,
            query_type="TIME_SERIES",
            group_by="30m",
        ),
        task_payload(grant_id, epsilon=1.1),
    ]
    for payload in forbidden_payloads:
        response = client.post("/api/v1/tasks", json=payload)
        assert response.status_code == 403, response.text
    assert party.calls == []
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PrivacyBudget)) == 0
        assert session.scalar(select(func.count()).select_from(GrantReservation)) == 0

    completed = client.post("/api/v1/tasks", json=task_payload(grant_id))
    assert completed.status_code == 201, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert len(party.calls) == 2
    current = client.get(f"/api/v1/grants/{grant_id}").json()
    # PLAIN authorization validates the Grant scope but does not consume DP
    # epsilon.
    assert current["epsilon_consumed"] == pytest.approx(0.0)
    assert current["epsilon_reserved"] == pytest.approx(0.0)

    party.fail = True
    failed = client.post("/api/v1/tasks", json=task_payload(grant_id, epsilon=0.5))
    assert failed.status_code == 201
    assert failed.json()["status"] == "FAILED"
    after_failure = client.get(f"/api/v1/grants/{grant_id}").json()
    assert after_failure["epsilon_consumed"] == pytest.approx(0.0)
    assert after_failure["epsilon_reserved"] == pytest.approx(0.0)

    calls_before = len(party.calls)
    insufficient = client.post("/api/v1/tasks", json=task_payload(grant_id, epsilon=2.0))
    assert insufficient.status_code == 403
    assert len(party.calls) == calls_before

    revoked = client.post(f"/api/v1/grants/{grant_id}/revoke")
    assert revoked.status_code == 200
    assert client.post("/api/v1/tasks", json=task_payload(grant_id)).status_code == 403

    with factory() as session:
        grant_row = session.get(AccessGrant, grant_id)
        grant_row.status = "ACTIVE"
        grant_row.expires_at = datetime.utcnow() - timedelta(days=1)
        session.commit()
    assert client.post("/api/v1/tasks", json=task_payload(grant_id)).status_code == 403
    with factory() as session:
        events = set(session.scalars(select(SecurityAudit.event_type)))
        assert {
            "AUTHORIZATION_CHECK_FAILED",
            "AUTHORIZATION_CHECK_PASSED",
            "TASK_CREATED_WITH_GRANT",
            "GRANT_REVOKED",
            "GRANT_EXPIRED",
        }.issubset(events)


def test_authorization_disabled_preserves_existing_task_behavior(tmp_path):
    client, party, _ = make_client(tmp_path, "compatibility", enforcement=False)
    response = client.post(
        "/api/v1/tasks",
        json=task_payload(parties=[OrganizationId.ORG_A.value]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "COMPLETED"
    assert len(party.calls) == 1
