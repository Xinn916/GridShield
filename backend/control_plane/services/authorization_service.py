import json
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.orm import Session

from common.enums import GrantStatus, QueryType, UserRole
from common.schemas import TaskCreateRequest
from control_plane.models.access_control import (
    AccessGrant,
    DemoUser,
    GrantReservation,
)
from control_plane.models.task import utc_now
from control_plane.services.security_audit_service import SecurityAuditService


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GrantBudgetOperation:
    status: str
    remaining_before: float
    remaining_after: float | None


class AuthorizationService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = SecurityAuditService(session)

    def authorize_and_reserve(
        self,
        task_id: str,
        user: DemoUser | None,
        request: TaskCreateRequest,
        *,
        reserve_budget: bool = True,
    ) -> GrantBudgetOperation:
        try:
            if user is None:
                raise AuthorizationError("请先登录")
            if user.role != UserRole.ANALYST.value:
                raise AuthorizationError("当前角色不能创建查询任务")
            if not request.grant_id:
                raise AuthorizationError("启用授权控制后必须提供 grant_id")
            grant = self.session.get(AccessGrant, request.grant_id)
            if grant is None:
                raise AuthorizationError("授权不存在")
            # A retry for the same task must be idempotent even when a read
            # of a fully reserved Grant has already refreshed its status to
            # EXHAUSTED. Return the existing reservation before re-running
            # status/scope checks.
            existing = self.session.get(GrantReservation, task_id) if reserve_budget else None
            if existing is not None:
                if grant.grantee_user_id != user.user_id:
                    raise AuthorizationError("授权不属于当前用户")
                if existing.grant_id != grant.grant_id or abs(existing.epsilon - request.epsilon) > 1e-12:
                    raise AuthorizationError("task_id 已绑定不同的授权额度预留")
                return GrantBudgetOperation(
                    existing.status, existing.remaining_before, existing.remaining_after
                )
            self._validate_scope(grant, user, request, require_budget=reserve_budget)
            if not reserve_budget:
                # Non-DP modes still require Grant scope authorization but do
                # not reserve or consume the DP privacy budget.
                remaining = max(
                    grant.total_epsilon_limit
                    - grant.epsilon_consumed
                    - grant.epsilon_reserved,
                    0.0,
                )
                self.session.commit()
                self.audit.record(
                    "AUTHORIZATION_CHECK_PASSED",
                    user,
                    grant_id=grant.grant_id,
                    task_id=task_id,
                    decision="ALLOWED",
                )
                return GrantBudgetOperation("NOT_REQUIRED", remaining, remaining)
            remaining = grant.total_epsilon_limit - grant.epsilon_consumed - grant.epsilon_reserved
            result = self.session.execute(
                update(AccessGrant)
                .where(
                    AccessGrant.grant_id == grant.grant_id,
                    AccessGrant.status == GrantStatus.ACTIVE.value,
                    AccessGrant.total_epsilon_limit
                    - AccessGrant.epsilon_consumed
                    - AccessGrant.epsilon_reserved
                    >= request.epsilon,
                )
                .values(epsilon_reserved=AccessGrant.epsilon_reserved + request.epsilon)
            )
            if result.rowcount != 1:
                self.session.rollback()
                raise AuthorizationError("授权累计 epsilon 剩余额度不足")
            self.session.add(
                GrantReservation(
                    task_id=task_id,
                    grant_id=grant.grant_id,
                    epsilon=request.epsilon,
                    status="RESERVED",
                    remaining_before=remaining,
                )
            )
            self.session.commit()
            self.audit.record(
                "AUTHORIZATION_CHECK_PASSED",
                user,
                grant_id=grant.grant_id,
                task_id=task_id,
                decision="ALLOWED",
            )
            return GrantBudgetOperation("RESERVED", remaining, None)
        except AuthorizationError as exc:
            self.audit.record(
                "AUTHORIZATION_CHECK_FAILED",
                user,
                grant_id=request.grant_id,
                task_id=task_id,
                decision="DENIED",
                reason=str(exc),
            )
            raise

    def consume(self, task_id: str) -> GrantBudgetOperation:
        reservation = self._reservation(task_id)
        if reservation.status == "CONSUMED":
            return GrantBudgetOperation(
                reservation.status, reservation.remaining_before, reservation.remaining_after
            )
        if reservation.status != "RESERVED":
            raise AuthorizationError(f"cannot consume a {reservation.status} grant reservation")
        grant = self.session.get(AccessGrant, reservation.grant_id)
        transition = self.session.execute(
            update(GrantReservation)
            .where(
                GrantReservation.task_id == task_id,
                GrantReservation.status == "RESERVED",
            )
            .values(status="CONSUMED")
        )
        if transition.rowcount != 1:
            self.session.rollback()
            return self._operation(self._reservation(task_id))
        self.session.execute(
            update(AccessGrant)
            .where(AccessGrant.grant_id == reservation.grant_id)
            .values(
                epsilon_reserved=AccessGrant.epsilon_reserved - reservation.epsilon,
                epsilon_consumed=AccessGrant.epsilon_consumed + reservation.epsilon,
            )
        )
        self.session.flush()
        self.session.refresh(grant)
        remaining = grant.total_epsilon_limit - grant.epsilon_consumed - grant.epsilon_reserved
        if remaining <= 1e-12:
            grant.status = GrantStatus.EXHAUSTED.value
        reservation.remaining_after = max(remaining, 0.0)
        self.session.commit()
        return self._operation(reservation)

    def release(self, task_id: str) -> GrantBudgetOperation:
        reservation = self._reservation(task_id)
        if reservation.status in {"RELEASED", "CONSUMED"}:
            return self._operation(reservation)
        transition = self.session.execute(
            update(GrantReservation)
            .where(
                GrantReservation.task_id == task_id,
                GrantReservation.status == "RESERVED",
            )
            .values(status="RELEASED")
        )
        if transition.rowcount != 1:
            self.session.rollback()
            return self._operation(self._reservation(task_id))
        grant = self.session.get(AccessGrant, reservation.grant_id)
        self.session.execute(
            update(AccessGrant)
            .where(AccessGrant.grant_id == reservation.grant_id)
            .values(epsilon_reserved=AccessGrant.epsilon_reserved - reservation.epsilon)
        )
        self.session.flush()
        self.session.refresh(grant)
        # A read-side refresh may have marked a fully reserved Grant as
        # EXHAUSTED.  If the task failed and the reservation is now released,
        # restore ACTIVE so the recovered balance can be used again.
        if (
            grant.status == GrantStatus.EXHAUSTED.value
            and grant.epsilon_consumed + grant.epsilon_reserved < grant.total_epsilon_limit
        ):
            grant.status = GrantStatus.ACTIVE.value
        reservation.remaining_after = max(
            grant.total_epsilon_limit - grant.epsilon_consumed - grant.epsilon_reserved, 0.0
        )
        self.session.commit()
        return self._operation(reservation)

    def _validate_scope(
        self,
        grant: AccessGrant,
        user: DemoUser,
        request: TaskCreateRequest,
        *,
        require_budget: bool = True,
    ) -> None:
        now = utc_now()
        if grant.grantee_user_id != user.user_id:
            raise AuthorizationError("授权不属于当前用户")
        # Budget exhaustion only blocks budgeted DP releases. PLAIN and
        # SECRET_SHARE still require the Grant's scope and expiry checks, but
        # must not be denied merely because the independent DP allowance is
        # exhausted.
        if grant.status != GrantStatus.ACTIVE.value and not (
            not require_budget and grant.status == GrantStatus.EXHAUSTED.value
        ):
            raise AuthorizationError(f"授权状态为 {grant.status}")
        if grant.valid_from > now or grant.expires_at <= now:
            if grant.expires_at <= now:
                grant.status = GrantStatus.EXPIRED.value
                self.session.commit()
                self.audit.record(
                    "GRANT_EXPIRED",
                    user,
                    grant_id=grant.grant_id,
                    decision="EXPIRED",
                )
            raise AuthorizationError("授权不在有效期内")
        allowed_parties = set(json.loads(grant.parties_json))
        if not {party.value for party in request.parties}.issubset(allowed_parties):
            raise AuthorizationError("查询园区超出授权范围")
        if request.query_type.value not in json.loads(grant.allowed_query_types_json):
            raise AuthorizationError("查询类型超出授权范围")
        start_time = self._naive(request.start_time)
        end_time = self._naive(request.end_time)
        if start_time < grant.allowed_start_time or end_time > grant.allowed_end_time:
            raise AuthorizationError("查询时间超出授权范围")
        if request.query_type == QueryType.TIME_SERIES:
            if request.group_by is None or request.group_by.value not in json.loads(
                grant.allowed_group_by_json
            ):
                raise AuthorizationError("group_by 超出授权范围")
        if request.epsilon > grant.max_epsilon_per_query:
            raise AuthorizationError("单次 epsilon 超出授权上限")
        remaining = grant.total_epsilon_limit - grant.epsilon_consumed - grant.epsilon_reserved
        if require_budget and remaining + 1e-12 < request.epsilon:
            raise AuthorizationError("授权累计 epsilon 剩余额度不足")

    def _reservation(self, task_id: str) -> GrantReservation:
        reservation = self.session.get(GrantReservation, task_id)
        if reservation is None:
            raise AuthorizationError("授权额度预留不存在")
        return reservation

    @staticmethod
    def _operation(reservation: GrantReservation) -> GrantBudgetOperation:
        return GrantBudgetOperation(
            reservation.status, reservation.remaining_before, reservation.remaining_after
        )

    @staticmethod
    def _naive(value):
        return value.replace(tzinfo=None) if value.tzinfo else value
