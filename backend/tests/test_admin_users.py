from fastapi.testclient import TestClient

from test_access_control import login, make_client


def test_admin_can_list_create_and_update_users(tmp_path):
    client, _, _ = make_client(tmp_path, "admin-users-lifecycle")
    login(client, "admin_demo")

    response = client.get("/api/v1/admin/users")
    assert response.status_code == 200
    users = response.json()
    assert users
    assert {"password_hash", "password_salt"}.isdisjoint(users[0])
    assert "created_at" in users[0]
    assert "last_login_at" in users[0]

    created = client.post(
        "/api/v1/admin/users",
        json={
            "username": "report_viewer",
            "role": "ANALYST",
            "password": "report-viewer-password",
        },
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["username"] == "report_viewer"
    assert user["party_id"] is None

    owner = client.post(
        "/api/v1/admin/users",
        json={
            "username": "owner_extra",
            "role": "DATA_OWNER",
            "organization_id": "ORG_B",
            "password": "owner-extra-password",
        },
    )
    assert owner.status_code == 201, owner.text
    owner_id = owner.json()["user_id"]
    updated = client.patch(
        f"/api/v1/admin/users/{owner_id}",
        json={"role": "ANALYST", "organization_id": None},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["party_id"] is None

    assert client.post(
        "/api/v1/admin/users",
        json={"username": "report_viewer", "role": "AUDITOR", "password": "another-password"},
    ).status_code == 409


def test_admin_user_role_binding_and_rbac_are_enforced(tmp_path):
    client, _, _ = make_client(tmp_path, "admin-users-validation")
    login(client, "admin_demo")

    assert client.post(
        "/api/v1/admin/users",
        json={"username": "missing_org", "role": "DATA_OWNER", "password": "valid-password"},
    ).status_code == 422
    assert client.post(
        "/api/v1/admin/users",
        json={"username": "analyst_org", "role": "ANALYST", "organization_id": "ORG_A", "password": "valid-password"},
    ).status_code == 422

    client.post("/api/v1/auth/logout")
    login(client, "analyst_demo")
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.post(
        "/api/v1/admin/users",
        json={"username": "not_allowed", "role": "ANALYST", "password": "valid-password"},
    ).status_code == 403


def test_admin_cannot_disable_self_or_last_active_admin(tmp_path):
    client, _, _ = make_client(tmp_path, "admin-users-guards")
    login(client, "admin_demo")
    users = client.get("/api/v1/admin/users").json()
    admin = next(item for item in users if item["username"] == "admin_demo")

    self_disable = client.post(f"/api/v1/admin/users/{admin['user_id']}/disable")
    assert self_disable.status_code == 409

    create_admin = client.post(
        "/api/v1/admin/users",
        json={"username": "second_admin", "role": "ADMIN", "password": "second-admin-password"},
    )
    assert create_admin.status_code == 201
    second_id = create_admin.json()["user_id"]
    assert client.post(f"/api/v1/admin/users/{second_id}/disable").status_code == 200
    assert client.post(f"/api/v1/admin/users/{admin['user_id']}/disable").status_code == 409


def test_disable_and_reset_password_revoke_sessions_and_are_audited(tmp_path):
    client, _, _ = make_client(tmp_path, "admin-users-sessions")
    app = client.app
    subject_client = TestClient(app)
    login(client, "admin_demo")
    created = client.post(
        "/api/v1/admin/users",
        json={"username": "session_user", "role": "ANALYST", "password": "old-password"},
    )
    assert created.status_code == 201
    user_id = created.json()["user_id"]

    assert subject_client.post(
        "/api/v1/auth/login",
        json={"username": "session_user", "password": "old-password"},
    ).status_code == 200
    assert subject_client.get("/api/v1/auth/me").status_code == 200
    assert client.post(f"/api/v1/admin/users/{user_id}/revoke-sessions").status_code == 200
    assert subject_client.get("/api/v1/auth/me").status_code == 401

    reset = client.post(
        f"/api/v1/admin/users/{user_id}/reset-password",
        json={"password": "new-password"},
    )
    assert reset.status_code == 200
    assert client.get("/api/v1/admin/security-audit").status_code == 200
    events = [item["event_type"] for item in client.get("/api/v1/admin/security-audit").json()]
    assert "USER_PASSWORD_RESET" in events
    assert "USER_SESSIONS_REVOKED" in events

    subject_client = TestClient(app)
    assert subject_client.post("/api/v1/auth/login", json={"username": "session_user", "password": "old-password"}).status_code == 401
    assert subject_client.post("/api/v1/auth/login", json={"username": "session_user", "password": "new-password"}).status_code == 200
    assert client.post(f"/api/v1/admin/users/{user_id}/disable").status_code == 200
    assert subject_client.get("/api/v1/auth/me").status_code == 401
