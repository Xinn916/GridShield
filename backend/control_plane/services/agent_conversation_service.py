import json
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.schemas import AgentParseRequest, AgentParseResponse, TaskDraft
from control_plane.models.access_control import AccessGrant, DemoUser
from control_plane.models.agent_conversation import AgentConversation, AgentMessage
from control_plane.models.task import Task, utc_now
from control_plane.schemas.agent_conversation import (
    AgentConversationDetail,
    AgentConversationSummary,
    AgentMessageResponse,
    AgentTaskSnapshot,
)


class AgentConversationNotFoundError(Exception):
    pass


class AgentConversationPermissionError(Exception):
    pass


class AgentConversationService:
    """Persist only user-visible chat and an allow-listed task snapshot."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, user: DemoUser) -> AgentConversationDetail:
        conversation = AgentConversation(
            conversation_id=str(uuid4()),
            user_id=user.user_id,
            title="新会话",
        )
        self.session.add(conversation)
        self.session.commit()
        return self.detail(user, conversation.conversation_id)

    def list(self, user: DemoUser, limit: int = 50) -> list[AgentConversationSummary]:
        conversations = list(
            self.session.scalars(
                select(AgentConversation)
                .where(AgentConversation.user_id == user.user_id)
                .order_by(AgentConversation.updated_at.desc())
                .limit(limit)
            )
        )
        return [self._summary(item) for item in conversations]

    def detail(self, user: DemoUser, conversation_id: str) -> AgentConversationDetail:
        conversation = self._owned(user, conversation_id)
        messages = list(
            self.session.scalars(
                select(AgentMessage)
                .where(AgentMessage.conversation_id == conversation_id)
                .order_by(AgentMessage.created_at.asc(), AgentMessage.message_id.asc())
            )
        )
        summary = self._summary(conversation)
        return AgentConversationDetail(
            **summary.model_dump(),
            current_task_snapshot=self._snapshot(conversation),
            messages=[self._message_response(message) for message in messages],
        )

    def save_user_message(
        self, user: DemoUser, conversation_id: str, content: str
    ) -> AgentConversation:
        conversation = self._owned(user, conversation_id)
        message = AgentMessage(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            role="USER",
            content=content,
        )
        self.session.add(message)
        if conversation.title == "新会话":
            conversation.title = self._chat_title(content)
        conversation.updated_at = utc_now()
        self.session.commit()
        return conversation

    def save_assistant_message(
        self,
        user: DemoUser,
        conversation_id: str,
        request: AgentParseRequest,
        response: AgentParseResponse,
    ) -> AgentConversationDetail:
        conversation = self._owned(user, conversation_id)
        task_update = self._draft_dict(response.task_draft, request.grant_id)
        message = AgentMessage(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            role="ASSISTANT",
            content=(response.reply or response.explanation or "")[:10000],
            intent=response.intent,
            task_update_json=json.dumps(task_update, ensure_ascii=False) if task_update else None,
        )
        self.session.add(message)
        if response.intent in {"QUERY", "CREATE_PRIVACY_QUERY"} and task_update:
            conversation.current_task_snapshot_json = json.dumps(task_update, ensure_ascii=False)
            conversation.title = self._task_title(task_update)
        elif response.intent == "TASK_UPDATE" and task_update:
            merged = self._snapshot_dict(conversation)
            merged.update({key: value for key, value in task_update.items() if value not in (None, [])})
            conversation.current_task_snapshot_json = json.dumps(merged, ensure_ascii=False)
            conversation.title = self._task_title(merged)
        conversation.updated_at = utc_now()
        self.session.commit()
        return self.detail(user, conversation_id)

    def link_task(
        self, user: DemoUser, conversation_id: str, task_id: str
    ) -> AgentConversationDetail:
        conversation = self._owned(user, conversation_id)
        task = self.session.get(Task, task_id)
        if task is None:
            raise AgentConversationNotFoundError("Task not found")
        grant = self.session.get(AccessGrant, task.grant_id) if task.grant_id else None
        if grant is None or grant.grantee_user_id != user.user_id:
            raise AgentConversationPermissionError("Current user cannot link this task")
        snapshot = {
            "grant_id": task.grant_id,
            "query_type": task.query_type,
            "parties": json.loads(task.parties_json),
            "start_time": task.start_time.isoformat(),
            "end_time": task.end_time.isoformat(),
            "group_by": task.group_by,
            "epsilon": task.epsilon,
        }
        conversation.last_task_id = task.task_id
        conversation.current_task_snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        conversation.title = self._task_title(snapshot)
        conversation.updated_at = utc_now()
        self.session.commit()
        return self.detail(user, conversation_id)

    def _owned(self, user: DemoUser, conversation_id: str) -> AgentConversation:
        conversation = self.session.get(AgentConversation, conversation_id)
        # Return the same not-found result for missing and foreign IDs to avoid enumeration.
        if conversation is None or conversation.user_id != user.user_id:
            raise AgentConversationNotFoundError("Conversation not found")
        return conversation

    def _summary(self, conversation: AgentConversation) -> AgentConversationSummary:
        snapshot = self._snapshot(conversation)
        task = self.session.get(Task, conversation.last_task_id) if conversation.last_task_id else None
        return AgentConversationSummary(
            conversation_id=conversation.conversation_id,
            title=conversation.title,
            query_type=snapshot.query_type if snapshot else None,
            parties=snapshot.parties if snapshot else [],
            task_status=task.status if task else None,
            last_task_id=conversation.last_task_id,
            has_current_task=snapshot is not None,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @staticmethod
    def _message_response(message: AgentMessage) -> AgentMessageResponse:
        task_update = None
        if message.task_update_json:
            try:
                task_update = AgentTaskSnapshot.model_validate(json.loads(message.task_update_json))
            except (TypeError, ValueError):
                task_update = None
        return AgentMessageResponse(
            message_id=message.message_id,
            role=message.role,
            content=message.content,
            intent=message.intent,
            task_update=task_update,
            created_at=message.created_at,
        )

    @staticmethod
    def _snapshot(conversation: AgentConversation) -> AgentTaskSnapshot | None:
        if not conversation.current_task_snapshot_json:
            return None
        try:
            return AgentTaskSnapshot.model_validate(json.loads(conversation.current_task_snapshot_json))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _snapshot_dict(conversation: AgentConversation) -> dict:
        snapshot = AgentConversationService._snapshot(conversation)
        return snapshot.model_dump(mode="json") if snapshot else {}

    @staticmethod
    def _draft_dict(draft: TaskDraft | None, grant_id: str | None) -> dict:
        if draft is None:
            return {}
        data = draft.model_dump(mode="json", exclude_none=True)
        if grant_id:
            data["grant_id"] = grant_id
        return data

    @staticmethod
    def _chat_title(content: str) -> str:
        compact = re.sub(r"\s+", " ", content).strip()
        return compact[:36] or "新会话"

    @staticmethod
    def _task_title(snapshot: dict) -> str:
        parties = snapshot.get("parties") or []
        if set(parties) == {"ORG_A", "ORG_B", "ORG_C"}:
            scope = "三园区"
        else:
            scope = "/".join(str(item).replace("ORG_", "") for item in parties)
            scope = f"{scope}园区" if scope else "园区"
        query_type = snapshot.get("query_type")
        group_by = snapshot.get("group_by")
        labels = {
            "SUM": "总用电量查询",
            "COUNT": "用电记录计数",
            "AVERAGE": "平均负荷查询",
            "TIME_SERIES": "小时负荷趋势" if group_by == "1h" else "负荷趋势查询",
        }
        return f"{scope}{labels.get(query_type, '隐私查询')}"[:120]
