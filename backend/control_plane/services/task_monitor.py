import json
import threading
from dataclasses import dataclass, field
from datetime import datetime

from common.enums import OrganizationId, TaskStatus
from common.schemas import TaskMonitorResponse
from control_plane.models.task import Task


# 监控只记录阶段与计数，绝不记录秘密份额、局部明文或未加噪结果。
STAGE_ORDER = [
    TaskStatus.CREATED.value,
    TaskStatus.DISPATCHING.value,
    TaskStatus.LOCAL_COMPUTING.value,
    TaskStatus.SHARING.value,
    TaskStatus.AGGREGATING.value,
    TaskStatus.RECONSTRUCTING.value,
    TaskStatus.COMPLETED.value,
]


@dataclass
class MonitorState:
    task_id: str
    current_stage: str = TaskStatus.CREATED.value
    party_statuses: dict[str, str] = field(default_factory=dict)
    compute_node_statuses: dict[str, str] = field(default_factory=dict)
    expected_parties: list[str] = field(default_factory=list)
    submitted_share_count: int | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    execution_time_ms: int | None = None


class TaskMonitorStore:
    """进程内任务监控存储（演示阶段，重启后可通过任务状态降级重建）。"""

    def __init__(self) -> None:
        self._states: dict[str, MonitorState] = {}
        self._lock = threading.RLock()

    def create(
        self,
        task_id: str,
        expected_parties: list[str],
        started_at: datetime | None = None,
    ) -> MonitorState:
        with self._lock:
            state = MonitorState(
                task_id=task_id,
                expected_parties=list(expected_parties),
                started_at=started_at,
                updated_at=started_at,
            )
            self._states[task_id] = state
            return state

    def update(self, task_id: str, **fields) -> None:
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                return
            for key, value in fields.items():
                if hasattr(state, key):
                    setattr(state, key, value)
            state.updated_at = datetime.utcnow()

    def get(self, task_id: str) -> MonitorState | None:
        with self._lock:
            return self._states.get(task_id)


def _progress(stage: str) -> float:
    if stage in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
        return 100.0
    if stage in STAGE_ORDER:
        return round(STAGE_ORDER.index(stage) / (len(STAGE_ORDER) - 1) * 100, 1)
    return 0.0


def build_monitor_response(task: Task, state: MonitorState | None) -> TaskMonitorResponse:
    current_stage = state.current_stage if state else task.status
    expected_parties = [
        OrganizationId(party) for party in json.loads(task.parties_json)
    ]
    return TaskMonitorResponse(
        task_id=task.task_id,
        status=TaskStatus(task.status),
        current_stage=current_stage,
        progress=_progress(current_stage),
        party_statuses=dict(state.party_statuses) if state else {},
        compute_node_statuses=dict(state.compute_node_statuses) if state else {},
        expected_parties=expected_parties,
        submitted_share_count=state.submitted_share_count if state else None,
        started_at=state.started_at if state and state.started_at else task.started_at,
        updated_at=state.updated_at if state and state.updated_at else task.updated_at,
        execution_time_ms=(
            state.execution_time_ms
            if state and state.execution_time_ms is not None
            else task.duration_ms
        ),
    )
