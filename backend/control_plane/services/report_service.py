import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.enums import OrganizationId, QueryType, TaskStatus, UserRole
from control_plane.models.access_control import AccessGrant, DemoUser, GrantReservation
from control_plane.models.privacy_budget import PrivacyBudget
from control_plane.models.task import Task
from control_plane.models.task_audit import TaskAudit
from control_plane.schemas.access_control import (
    AnalystReportResponse,
    GrantUsageReportResponse,
    ReportTaskResponse,
)


class ReportPermissionError(RuntimeError):
    pass


class AnalystReportService:
    def __init__(self, session: Session, default_total_epsilon: float = 20.0):
        self.session = session
        self.default_total_epsilon = default_total_epsilon

    def build(self, user: DemoUser, limit: int = 20) -> AnalystReportResponse:
        if user.role != UserRole.ANALYST.value:
            raise ReportPermissionError("仅分析员可以查看个人任务报表")

        tasks = list(
            self.session.scalars(
                select(Task)
                .join(AccessGrant, Task.grant_id == AccessGrant.grant_id)
                .where(AccessGrant.grantee_user_id == user.user_id)
                .order_by(Task.created_at.desc())
            )
        )
        task_ids = [task.task_id for task in tasks]
        audits = (
            list(self.session.scalars(select(TaskAudit).where(TaskAudit.task_id.in_(task_ids))))
            if task_ids
            else []
        )
        audits_by_task = {audit.task_id: audit for audit in audits}
        usages = list(
            self.session.scalars(
                select(GrantReservation)
                .join(AccessGrant, GrantReservation.grant_id == AccessGrant.grant_id)
                .where(AccessGrant.grantee_user_id == user.user_id)
                .order_by(GrantReservation.updated_at.desc())
            )
        )
        grants = list(
            self.session.scalars(
                select(AccessGrant).where(AccessGrant.grantee_user_id == user.user_id)
            )
        )

        completed = sum(task.status == TaskStatus.COMPLETED.value for task in tasks)
        failed = sum(task.status == TaskStatus.FAILED.value for task in tasks)
        durations = [
            max((task.completed_at - task.created_at).total_seconds() * 1000, 0.0)
            for task in tasks
            if task.completed_at is not None
        ]
        query_counts = Counter(task.query_type for task in tasks)
        party_counts: Counter[str] = Counter()
        for task in tasks:
            party_counts.update(json.loads(task.parties_json))

        if grants:
            # A report may contain multiple independent Grants.  Never merge
            # them through a user/dataset GLOBAL ledger; sum each Grant's
            # authoritative remaining balance instead.
            remaining_budget = sum(
                max(
                    float(grant.total_epsilon_limit)
                    - float(grant.epsilon_consumed)
                    - float(grant.epsilon_reserved),
                    0.0,
                )
                for grant in grants
            )
        else:
            # Keep the unauthenticated/legacy report fallback for existing
            # deployments that have not created a Grant yet.
            budget = self.session.scalar(
                select(PrivacyBudget).where(
                    PrivacyBudget.subject_id == user.user_id,
                    PrivacyBudget.data_scope == "GLOBAL",
                )
            )
            remaining_budget = (
                budget.total_epsilon - budget.used_epsilon - budget.reserved_epsilon
                if budget is not None
                else self.default_total_epsilon
            )

        return AnalystReportResponse(
            total_tasks=len(tasks),
            completed_tasks=completed,
            failed_tasks=failed,
            success_rate=round((completed / len(tasks) * 100) if tasks else 0.0, 2),
            average_task_duration_ms=round(sum(durations) / len(durations), 2) if durations else 0.0,
            epsilon_consumed=round(
                sum(item.epsilon for item in usages if item.status == "CONSUMED"), 12
            ),
            remaining_privacy_budget=max(round(remaining_budget, 12), 0.0),
            query_type_counts={query_type.value: query_counts.get(query_type.value, 0) for query_type in QueryType},
            party_participation_counts={
                party.value: party_counts.get(party.value, 0) for party in OrganizationId
            },
            time_series_bucket_count=sum(
                audit.bucket_count or 0
                for audit in audits
                if audit.query_type == QueryType.TIME_SERIES.value
            ),
            recent_tasks=[
                ReportTaskResponse(
                    task_id=task.task_id,
                    query_type=task.query_type,
                    parties=json.loads(task.parties_json),
                    status=task.status,
                    epsilon=task.epsilon,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                    grant_id=task.grant_id,
                    bucket_count=(audits_by_task[task.task_id].bucket_count if task.task_id in audits_by_task else None),
                )
                for task in tasks[:limit]
            ],
            recent_grant_usage=[
                GrantUsageReportResponse(
                    task_id=item.task_id,
                    grant_id=item.grant_id,
                    epsilon=item.epsilon,
                    status=item.status,
                    remaining_before=item.remaining_before,
                    remaining_after=item.remaining_after,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in usages[:limit]
            ],
        )
