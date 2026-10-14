from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from common.enums import GroupBy, OrganizationId, QueryType


class AgentTaskSnapshot(BaseModel):
    grant_id: str | None = Field(default=None, max_length=40)
    query_type: QueryType | None = None
    parties: list[OrganizationId] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    group_by: GroupBy | None = None
    epsilon: float | None = Field(default=None, gt=0, le=5)


class AgentMessageResponse(BaseModel):
    message_id: str
    role: Literal["USER", "ASSISTANT"]
    content: str
    intent: str | None = None
    task_update: AgentTaskSnapshot | None = None
    created_at: datetime


class AgentConversationSummary(BaseModel):
    conversation_id: str
    title: str
    query_type: QueryType | None = None
    parties: list[OrganizationId] = Field(default_factory=list)
    task_status: str | None = None
    last_task_id: str | None = None
    has_current_task: bool = False
    created_at: datetime
    updated_at: datetime


class AgentConversationDetail(AgentConversationSummary):
    current_task_snapshot: AgentTaskSnapshot | None = None
    messages: list[AgentMessageResponse] = Field(default_factory=list)
