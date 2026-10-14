import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from common.enums import CalculationMode
from control_plane.config import ControlSettings
from control_plane.database.session import create_session_factory
from control_plane.main import create_app
from control_plane.models.access_control import AccessGrant
from control_plane.models.agent_conversation import AgentConversation, AgentMessage
from control_plane.models.task import Task
from control_plane.services.agent_service import AgentService, InMemoryRateLimiter


PASSWORD = "conversation-test-password"
DEMO_PASSWORDS = {
    username: PASSWORD
    for username in (
        "analyst_demo", "owner_a", "owner_b", "owner_c", "auditor_demo", "admin_demo"
    )
}


class FakeDeepSeekClient:
    model = "fake-model"

    def __init__(self):
        self.calls = []

    def chat_json(self, system_prompt, user_text):
        self.calls.append((system_prompt, user_text))
        return {
            "intent": "QUERY",
            "reply": "已识别三园区总用电量任务",
            "task_update": {
                "query_type": "SUM",
                "parties": ["ORG_A", "ORG_B", "ORG_C"],
                "start_time": "2012-11-11T00:00:00",
                "end_time": "2012-11-12T00:00:00",
                "epsilon": 1.0,
            },
            "missing_fields": [],
            "warnings": [],
            "explanation": "",
            "requires_confirmation": True,
        }


def make_client(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'conversation.db').as_posix()}"
    settings = ControlSettings(
        database_url=database_url,
        calculation_mode=CalculationMode.PLAIN,
        authorization_enforcement_enabled=True,
        demo_seed_enabled=True,
        demo_passwords=DEMO_PASSWORDS,
    )
    agent = AgentService(
        FakeDeepSeekClient(),
        rate_limiter=InMemoryRateLimiter(100, 60),
        now_provider=lambda: datetime(2026, 8, 26),
    )
    return TestClient(create_app(settings, agent_service=agent)), create_session_factory(database_url)


def login(client, username="analyst_demo"):
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


def create_conversation(client):
    response = client.post("/api/v1/agent/conversations")
    assert response.status_code == 201, response.text
    return response.json()


def test_conversation_binds_current_user_and_sqlite_tables_are_created(tmp_path):
    client, factory = make_client(tmp_path)
    assert client.get("/api/v1/agent/conversations").status_code == 401
    login(client)
    created = create_conversation(client)
    assert created["title"] == "新会话"
    assert created["messages"] == []
    assert created["current_task_snapshot"] is None
    with factory() as session:
        saved = session.get(AgentConversation, created["conversation_id"])
        assert saved.user_id == "analyst_demo"
        tables = set(inspect(session.get_bind()).get_table_names())
        assert {"agent_conversations", "agent_messages"} <= tables


def test_query_persists_messages_snapshot_and_safe_title(tmp_path):
    client, factory = make_client(tmp_path)
    login(client)
    conversation = create_conversation(client)
    response = client.post(
        "/api/v1/agent/parse-query",
        json={
            "conversation_id": conversation["conversation_id"],
            "text": "查询三个园区从2012年11月11日到2012年11月12日的总用电量，epsilon为1",
            "grant_id": "GRANT-SAMPLE",
            "has_current_task": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["conversation_id"] == conversation["conversation_id"]
    detail = client.get(
        f"/api/v1/agent/conversations/{conversation['conversation_id']}"
    ).json()
    assert [item["role"] for item in detail["messages"]] == ["USER", "ASSISTANT"]
    assert detail["messages"][1]["intent"] == "QUERY"
    assert detail["current_task_snapshot"] == {
        "grant_id": "GRANT-SAMPLE",
        "query_type": "SUM",
        "parties": ["ORG_A", "ORG_B", "ORG_C"],
        "start_time": "2012-11-11T00:00:00",
        "end_time": "2012-11-12T00:00:00",
        "group_by": None,
        "epsilon": 1.0,
    }
    assert detail["title"] == "三园区总用电量查询"
    serialized = json.dumps(detail, ensure_ascii=False).lower()
    assert "token" not in serialized
    assert "api_key" not in serialized
    assert "secret_share" not in serialized
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentMessage)) == 2


def test_greeting_keeps_task_snapshot_empty_and_new_conversation_is_isolated(tmp_path):
    client, _ = make_client(tmp_path)
    login(client)
    first = create_conversation(client)
    response = client.post(
        "/api/v1/agent/parse-query",
        json={"conversation_id": first["conversation_id"], "text": "你好"},
    )
    assert response.status_code == 200, response.text
    first_detail = client.get(
        f"/api/v1/agent/conversations/{first['conversation_id']}"
    ).json()
    assert first_detail["current_task_snapshot"] is None
    assert first_detail["last_task_id"] is None
    second = create_conversation(client)
    assert second["conversation_id"] != first["conversation_id"]
    assert second["messages"] == []
    assert second["current_task_snapshot"] is None
    assert len(client.get("/api/v1/agent/conversations").json()) == 2


def test_user_cannot_read_or_link_foreign_conversation(tmp_path):
    client, _ = make_client(tmp_path)
    login(client)
    conversation = create_conversation(client)
    client.post("/api/v1/auth/logout")
    login(client, "admin_demo")
    assert client.get(
        f"/api/v1/agent/conversations/{conversation['conversation_id']}"
    ).status_code == 404
    assert client.post(
        f"/api/v1/agent/conversations/{conversation['conversation_id']}/tasks/TASK-UNKNOWN"
    ).status_code == 404
    assert client.get("/api/v1/agent/conversations").json() == []


def test_conversation_links_owned_task_without_rerunning_or_changing_budget(tmp_path):
    client, factory = make_client(tmp_path)
    login(client)
    conversation = create_conversation(client)
    now = datetime(2026, 8, 26)
    with factory() as session:
        session.add(AccessGrant(
            grant_id="GRANT-CONVERSATION",
            request_id="REQUEST-CONVERSATION",
            grantee_user_id="analyst_demo",
            parties_json='["ORG_A"]',
            allowed_query_types_json='["SUM"]',
            allowed_start_time=now,
            allowed_end_time=now + timedelta(days=1),
            allowed_group_by_json="[]",
            max_epsilon_per_query=1.0,
            total_epsilon_limit=4.0,
            epsilon_consumed=1.0,
            epsilon_reserved=0.0,
            valid_from=now,
            expires_at=now + timedelta(days=30),
            status="ACTIVE",
        ))
        session.add(Task(
            task_id="TASK-CONVERSATION",
            grant_id="GRANT-CONVERSATION",
            status="COMPLETED",
            query_type="SUM",
            parties_json='["ORG_A"]',
            start_time=now,
            end_time=now + timedelta(hours=1),
            calculation_mode="PLAIN",
            epsilon=1.0,
            privacy_unit="household",
            mechanism="none",
            budget_status="CONSUMED",
            result_json='{"value": 12.3}',
        ))
        session.commit()
    linked = client.post(
        f"/api/v1/agent/conversations/{conversation['conversation_id']}/tasks/TASK-CONVERSATION"
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["last_task_id"] == "TASK-CONVERSATION"
    assert linked.json()["task_status"] == "COMPLETED"
    # Reopening a conversation is a read-only operation: no new task and no budget mutation.
    assert client.get(
        f"/api/v1/agent/conversations/{conversation['conversation_id']}"
    ).status_code == 200
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Task)) == 1
        grant = session.get(AccessGrant, "GRANT-CONVERSATION")
        assert grant.epsilon_consumed == 1.0
        assert grant.epsilon_reserved == 0.0
