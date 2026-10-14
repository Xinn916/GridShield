from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.models.access_control import DemoUser, SecurityAudit


class SecurityAuditService:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        event_type: str,
        actor: DemoUser | None = None,
        *,
        target_user_id: str | None = None,
        operation: str | None = None,
        request_id: str | None = None,
        grant_id: str | None = None,
        task_id: str | None = None,
        import_id: str | None = None,
        source_sha256: str | None = None,
        row_count: int | None = None,
        import_status: str | None = None,
        party_id: str | None = None,
        decision: str | None = None,
        reason: str | None = None,
    ) -> SecurityAudit:
        event = SecurityAudit(
            event_type=event_type,
            actor_user_id=actor.user_id if actor else None,
            target_user_id=target_user_id,
            actor_role=actor.role if actor else None,
            party_id=party_id if party_id is not None else actor.party_id if actor else None,
            request_id=request_id,
            grant_id=grant_id,
            task_id=task_id,
            import_id=import_id,
            source_sha256=source_sha256,
            row_count=row_count,
            import_status=import_status,
            decision=decision,
            operation=operation,
            reason=reason,
        )
        self.session.add(event)
        self.session.commit()
        return event

    def list_recent(self, limit: int = 100) -> list[SecurityAudit]:
        return list(
            self.session.scalars(
                select(SecurityAudit).order_by(SecurityAudit.timestamp.desc()).limit(limit)
            )
        )
