import json
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.enums import (
    AccessRequestStatus,
    ApprovalDecision,
    GrantStatus,
    QueryType,
    UserRole,
)
from control_plane.models.access_control import (
    AccessApproval,
    AccessGrant,
    AccessRequest,
    DatasetAsset,
    DemoUser,
)
from control_plane.models.task import utc_now
from control_plane.services.auth_service import AuthService, hash_password
from control_plane.schemas.access_control import (
    AccessRequestCreate,
    AccessRequestPatch,
    AccessRequestResponse,
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserUpdate,
    ApprovalDecisionRequest,
    ApprovalResponse,
    DatasetAssetResponse,
    GrantResponse,
    UserResponse,
)
from control_plane.services.security_audit_service import SecurityAuditService


class AccessControlError(RuntimeError):
    pass


class AccessNotFoundError(AccessControlError):
    pass


class AccessPermissionError(AccessControlError):
    pass


class AccessConflictError(AccessControlError):
    pass


def require_role(user: DemoUser, *roles: UserRole) -> None:
    if user.role not in {role.value for role in roles}:
        raise AccessPermissionError("当前角色无权执行此操作")


class AccessControlService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = SecurityAuditService(session)

    def list_assets(self) -> list[DatasetAssetResponse]:
        assets = list(
            self.session.scalars(
                select(DatasetAsset)
                .where(DatasetAsset.status == "ACTIVE")
                .order_by(DatasetAsset.owner_party)
            )
        )
        return [self.asset_response(asset) for asset in assets]

    def get_asset(self, asset_id: str) -> DatasetAssetResponse:
        asset = self.session.get(DatasetAsset, asset_id)
        if asset is None or asset.status != "ACTIVE":
            raise AccessNotFoundError("数据资产不存在")
        return self.asset_response(asset)

    def list_owner_assets(self, user: DemoUser) -> list[DatasetAssetResponse]:
        require_role(user, UserRole.DATA_OWNER)
        assets = list(
            self.session.scalars(
                select(DatasetAsset)
                .where(
                    DatasetAsset.owner_party == user.party_id,
                    DatasetAsset.status == "ACTIVE",
                )
                .order_by(DatasetAsset.asset_id)
            )
        )
        return [self.asset_response(asset) for asset in assets]

    def create_request(self, user: DemoUser, payload: AccessRequestCreate) -> AccessRequestResponse:
        require_role(user, UserRole.ANALYST)
        self._validate_catalog_scope(payload)
        request_id = self._next_request_id()
        item = AccessRequest(
            request_id=request_id,
            requester_user_id=user.user_id,
            purpose=payload.purpose,
            requested_parties_json=self._dump(payload.requested_parties),
            requested_query_types_json=self._dump(payload.requested_query_types),
            requested_start_time=self._naive(payload.requested_start_time),
            requested_end_time=self._naive(payload.requested_end_time),
            requested_group_by_json=self._dump(payload.requested_group_by),
            requested_max_epsilon_per_query=payload.requested_max_epsilon_per_query,
            requested_total_epsilon=payload.requested_total_epsilon,
            requested_expires_at=self._naive(payload.requested_expires_at),
            status=AccessRequestStatus.DRAFT.value,
        )
        self.session.add(item)
        self.session.commit()
        self.audit.record(
            "ACCESS_REQUEST_CREATED", user, request_id=request_id, decision="DRAFT"
        )
        return self.request_response(item)

    def update_request(
        self, user: DemoUser, request_id: str, patch: AccessRequestPatch
    ) -> AccessRequestResponse:
        item = self._owned_request(user, request_id)
        if item.status != AccessRequestStatus.DRAFT.value:
            raise AccessConflictError("只有草稿申请可以修改")
        current = self._request_input(item)
        changes = patch.model_dump(exclude_unset=True)
        merged = AccessRequestCreate(**{**current, **changes})
        self._validate_catalog_scope(merged)
        item.purpose = merged.purpose
        item.requested_parties_json = self._dump(merged.requested_parties)
        item.requested_query_types_json = self._dump(merged.requested_query_types)
        item.requested_start_time = self._naive(merged.requested_start_time)
        item.requested_end_time = self._naive(merged.requested_end_time)
        item.requested_group_by_json = self._dump(merged.requested_group_by)
        item.requested_max_epsilon_per_query = merged.requested_max_epsilon_per_query
        item.requested_total_epsilon = merged.requested_total_epsilon
        item.requested_expires_at = self._naive(merged.requested_expires_at)
        self.session.commit()
        return self.request_response(item)

    def submit_request(self, user: DemoUser, request_id: str) -> AccessRequestResponse:
        item = self._owned_request(user, request_id)
        if item.status != AccessRequestStatus.DRAFT.value:
            raise AccessConflictError("只有草稿申请可以提交")
        self._validate_catalog_scope(AccessRequestCreate(**self._request_input(item)))
        for party in self._load(item.requested_parties_json):
            self.session.add(
                AccessApproval(
                    approval_id=f"APPROVAL-{item.request_id.removeprefix('REQUEST-')}-{party}",
                    request_id=item.request_id,
                    party_id=party,
                    decision=ApprovalDecision.PENDING.value,
                )
            )
        item.status = AccessRequestStatus.PENDING.value
        item.submitted_at = utc_now()
        self.session.commit()
        self.audit.record(
            "ACCESS_REQUEST_SUBMITTED", user, request_id=request_id, decision="PENDING"
        )
        return self.request_response(item)

    def withdraw_request(self, user: DemoUser, request_id: str) -> AccessRequestResponse:
        item = self._owned_request(user, request_id)
        if item.status not in {
            AccessRequestStatus.DRAFT.value,
            AccessRequestStatus.PENDING.value,
            AccessRequestStatus.PARTIALLY_APPROVED.value,
        }:
            raise AccessConflictError("当前申请状态不可撤销")
        item.status = AccessRequestStatus.REVOKED.value
        item.completed_at = utc_now()
        self.session.commit()
        self.audit.record(
            "ACCESS_REQUEST_WITHDRAWN", user, request_id=request_id, decision="REVOKED"
        )
        return self.request_response(item)

    def list_mine(self, user: DemoUser) -> list[AccessRequestResponse]:
        require_role(user, UserRole.ANALYST)
        items = list(
            self.session.scalars(
                select(AccessRequest)
                .where(AccessRequest.requester_user_id == user.user_id)
                .order_by(AccessRequest.created_at.desc())
            )
        )
        return [self.request_response(item) for item in items]

    def get_request(self, user: DemoUser, request_id: str) -> AccessRequestResponse:
        item = self.session.get(AccessRequest, request_id)
        if item is None:
            raise AccessNotFoundError("申请不存在")
        if user.role == UserRole.ANALYST.value and item.requester_user_id != user.user_id:
            raise AccessPermissionError("无权查看其他申请人的申请")
        if user.role == UserRole.DATA_OWNER.value and user.party_id not in self._load(
            item.requested_parties_json
        ):
            raise AccessPermissionError("该申请不涉及当前园区")
        return self.request_response(item)

    def pending_approvals(self, user: DemoUser) -> list[ApprovalResponse]:
        require_role(user, UserRole.DATA_OWNER)
        approvals = list(
            self.session.scalars(
                select(AccessApproval)
                .where(
                    AccessApproval.party_id == user.party_id,
                    AccessApproval.decision == ApprovalDecision.PENDING.value,
                )
                .order_by(AccessApproval.created_at)
            )
        )
        return [self.approval_response(item) for item in approvals]

    def approval_history(self, user: DemoUser) -> list[ApprovalResponse]:
        require_role(user, UserRole.DATA_OWNER)
        approvals = list(
            self.session.scalars(
                select(AccessApproval)
                .where(
                    AccessApproval.party_id == user.party_id,
                    AccessApproval.decision != ApprovalDecision.PENDING.value,
                )
                .order_by(AccessApproval.decided_at.desc())
            )
        )
        return [self.approval_response(item) for item in approvals]

    def get_approval(self, user: DemoUser, approval_id: str) -> ApprovalResponse:
        item = self.session.get(AccessApproval, approval_id)
        if item is None:
            raise AccessNotFoundError("审批记录不存在")
        if user.role == UserRole.DATA_OWNER.value and item.party_id != user.party_id:
            raise AccessPermissionError("不能查看其他园区的审批入口")
        require_role(user, UserRole.DATA_OWNER, UserRole.AUDITOR, UserRole.ADMIN)
        return self.approval_response(item)

    def decide(
        self, user: DemoUser, approval_id: str, payload: ApprovalDecisionRequest
    ) -> ApprovalResponse:
        require_role(user, UserRole.DATA_OWNER)
        approval = self.session.get(AccessApproval, approval_id)
        if approval is None:
            raise AccessNotFoundError("审批记录不存在")
        if approval.party_id != user.party_id:
            raise AccessPermissionError("只能审批所属园区的申请")
        if approval.decision != ApprovalDecision.PENDING.value:
            raise AccessConflictError("该园区审批已经完成")
        request = self.session.get(AccessRequest, approval.request_id)
        if request is None or request.status not in {
            AccessRequestStatus.PENDING.value,
            AccessRequestStatus.PARTIALLY_APPROVED.value,
        }:
            raise AccessConflictError("申请当前不可审批")

        scope = self._approval_scope(request, payload)
        approval.approver_user_id = user.user_id
        approval.decision = payload.decision.value
        approval.reason = (payload.reason or "").strip() or None
        approval.allowed_query_types_json = self._dump(scope["query_types"])
        approval.allowed_start_time = scope["start_time"]
        approval.allowed_end_time = scope["end_time"]
        approval.allowed_group_by_json = self._dump(scope["group_by"])
        approval.max_epsilon_per_query = scope["max_epsilon"]
        approval.total_epsilon_limit = scope["total_epsilon"]
        approval.expires_at = scope["expires_at"]
        approval.decided_at = utc_now()
        self.session.commit()

        event = {
            ApprovalDecision.APPROVED: "ACCESS_REQUEST_APPROVED",
            ApprovalDecision.CONDITIONALLY_APPROVED: "ACCESS_REQUEST_CONDITIONALLY_APPROVED",
            ApprovalDecision.REJECTED: "ACCESS_REQUEST_REJECTED",
        }[payload.decision]
        self.audit.record(
            event,
            user,
            request_id=request.request_id,
            decision=payload.decision.value,
            reason=approval.reason,
        )
        self._finalize_request(request)
        return self.approval_response(approval)

    def list_grants(self, user: DemoUser) -> list[GrantResponse]:
        require_role(user, UserRole.ANALYST)
        grants = list(
            self.session.scalars(
                select(AccessGrant)
                .where(AccessGrant.grantee_user_id == user.user_id)
                .order_by(AccessGrant.created_at.desc())
            )
        )
        return [self.grant_response(self._refresh_grant(item)) for item in grants]

    def owner_grants(self, user: DemoUser) -> list[GrantResponse]:
        require_role(user, UserRole.DATA_OWNER)
        grants = list(self.session.scalars(select(AccessGrant).order_by(AccessGrant.created_at.desc())))
        return [
            self.grant_response(self._refresh_grant(item))
            for item in grants
            if user.party_id in self._load(item.parties_json)
        ]

    def get_grant(self, user: DemoUser, grant_id: str) -> GrantResponse:
        grant = self.session.get(AccessGrant, grant_id)
        if grant is None:
            raise AccessNotFoundError("授权不存在")
        if user.role == UserRole.ANALYST.value and grant.grantee_user_id != user.user_id:
            raise AccessPermissionError("无权查看其他用户的授权")
        if user.role == UserRole.DATA_OWNER.value and user.party_id not in self._load(
            grant.parties_json
        ):
            raise AccessPermissionError("该授权不涉及当前园区")
        return self.grant_response(self._refresh_grant(grant))

    def revoke_grant(self, user: DemoUser, grant_id: str) -> GrantResponse:
        grant = self.session.get(AccessGrant, grant_id)
        if grant is None:
            raise AccessNotFoundError("授权不存在")
        if user.role == UserRole.ANALYST.value and grant.grantee_user_id != user.user_id:
            raise AccessPermissionError("无权撤销其他用户的授权")
        require_role(user, UserRole.ANALYST, UserRole.ADMIN)
        if grant.status == GrantStatus.ACTIVE.value:
            grant.status = GrantStatus.REVOKED.value
            grant.revoked_at = utc_now()
            self.session.commit()
            self.audit.record(
                "GRANT_REVOKED", user, grant_id=grant_id, decision="REVOKED"
            )
        return self.grant_response(grant)

    def all_requests(self, user: DemoUser) -> list[AccessRequestResponse]:
        require_role(user, UserRole.AUDITOR, UserRole.ADMIN)
        return [
            self.request_response(item)
            for item in self.session.scalars(
                select(AccessRequest).order_by(AccessRequest.created_at.desc())
            )
        ]

    def all_grants(self, user: DemoUser) -> list[GrantResponse]:
        require_role(user, UserRole.AUDITOR, UserRole.ADMIN)
        return [
            self.grant_response(self._refresh_grant(item))
            for item in self.session.scalars(
                select(AccessGrant).order_by(AccessGrant.created_at.desc())
            )
        ]

    def all_users(self, user: DemoUser) -> list[UserResponse]:
        require_role(user, UserRole.ADMIN)
        return [
            self.user_response(item)
            for item in self.session.scalars(select(DemoUser).order_by(DemoUser.username))
        ]

    def create_user(self, actor: DemoUser, payload: AdminUserCreate) -> UserResponse:
        require_role(actor, UserRole.ADMIN)
        username = payload.username.strip()
        if self.session.scalar(select(DemoUser).where(func.lower(DemoUser.username) == username.lower())):
            self.audit.record(
                "USER_CREATE_FAILED",
                actor,
                operation="CREATE_USER",
                decision="DENIED",
                reason="username already exists",
            )
            raise AccessConflictError("用户名已存在")
        salt, password_hash = self._hash_password(payload.password)
        target = DemoUser(
            user_id=f"user-{uuid.uuid4().hex}",
            username=username,
            password_salt=salt,
            password_hash=password_hash,
            role=payload.role.value,
            party_id=payload.organization_id.value if payload.organization_id else None,
            is_active=True,
        )
        self.session.add(target)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AccessConflictError("用户名已存在") from exc
        self.audit.record(
            "USER_CREATED",
            actor,
            target_user_id=target.user_id,
            operation="CREATE_USER",
            decision="ALLOWED",
        )
        return self.user_response(target)

    def update_user(self, actor: DemoUser, user_id: str, payload: AdminUserUpdate) -> UserResponse:
        require_role(actor, UserRole.ADMIN)
        target = self.session.get(DemoUser, user_id)
        if target is None:
            raise AccessNotFoundError("用户不存在")
        if target.user_id == actor.user_id and payload.role.value != UserRole.ADMIN.value:
            self._record_denied(actor, target, "USER_ROLE_UPDATED", "UPDATE_USER_ROLE", "不能修改当前登录管理员的角色")
            raise AccessConflictError("不能修改当前登录管理员的角色")
        if target.role == UserRole.ADMIN.value and payload.role.value != UserRole.ADMIN.value and target.is_active:
            self._ensure_active_admin_remains(actor, target)
        old_role, old_party = target.role, target.party_id
        target.role = payload.role.value
        target.party_id = payload.organization_id.value if payload.organization_id else None
        self.session.commit()
        if old_role != target.role:
            self.audit.record(
                "USER_ROLE_UPDATED",
                actor,
                target_user_id=target.user_id,
                operation="UPDATE_USER_ROLE",
                decision="ALLOWED",
                reason=f"{old_role} -> {target.role}",
            )
        if old_party != target.party_id:
            self.audit.record(
                "USER_ORG_UPDATED",
                actor,
                target_user_id=target.user_id,
                operation="UPDATE_USER_ORG",
                decision="ALLOWED",
                reason=f"{old_party or '—'} -> {target.party_id or '—'}",
            )
        return self.user_response(target)

    def reset_password(self, actor: DemoUser, user_id: str, payload: AdminPasswordReset) -> UserResponse:
        require_role(actor, UserRole.ADMIN)
        target = self.session.get(DemoUser, user_id)
        if target is None:
            raise AccessNotFoundError("用户不存在")
        salt, password_hash = self._hash_password(payload.password)
        target.password_salt = salt
        target.password_hash = password_hash
        self.session.commit()
        self._revoke_sessions(target.user_id)
        self.audit.record(
            "USER_PASSWORD_RESET",
            actor,
            target_user_id=target.user_id,
            operation="RESET_PASSWORD",
            decision="ALLOWED",
        )
        return self.user_response(target)

    def revoke_user_sessions(self, actor: DemoUser, user_id: str) -> UserResponse:
        require_role(actor, UserRole.ADMIN)
        target = self.session.get(DemoUser, user_id)
        if target is None:
            raise AccessNotFoundError("用户不存在")
        revoked = self._revoke_sessions(target.user_id)
        self.audit.record(
            "USER_SESSIONS_REVOKED",
            actor,
            target_user_id=target.user_id,
            operation="REVOKE_SESSIONS",
            decision="ALLOWED",
            reason=f"revoked={revoked}",
        )
        return self.user_response(target)

    def set_user_active(self, user: DemoUser, user_id: str, active: bool) -> UserResponse:
        require_role(user, UserRole.ADMIN)
        target = self.session.get(DemoUser, user_id)
        if target is None:
            raise AccessNotFoundError("用户不存在")
        if not active and target.user_id == user.user_id:
            self._record_denied(user, target, "USER_DISABLED", "DISABLE_USER", "不能停用当前登录账号")
            raise AccessConflictError("不能停用当前登录账号")
        if not active and target.role == UserRole.ADMIN.value and target.is_active:
            self._ensure_active_admin_remains(user, target)
        if target.is_active == active:
            self.audit.record(
                "USER_ENABLED" if active else "USER_DISABLED",
                user,
                target_user_id=target.user_id,
                operation="ENABLE_USER" if active else "DISABLE_USER",
                decision="ALLOWED",
                reason="already in requested state",
            )
            return self.user_response(target)
        target.is_active = active
        self.session.commit()
        if not active:
            self._revoke_sessions(target.user_id)
        self.audit.record(
            "USER_ENABLED" if active else "USER_DISABLED",
            user,
            target_user_id=target.user_id,
            operation="ENABLE_USER" if active else "DISABLE_USER",
            decision="ALLOWED",
        )
        return self.user_response(target)

    @staticmethod
    def _hash_password(password: str) -> tuple[str, str]:
        return hash_password(password)

    def _revoke_sessions(self, user_id: str) -> int:
        return AuthService(self.session).revoke_user_sessions(user_id)

    def _ensure_active_admin_remains(self, actor: DemoUser, target: DemoUser) -> None:
        count = self.session.scalar(
            select(func.count())
            .select_from(DemoUser)
            .where(
                DemoUser.role == UserRole.ADMIN.value,
                DemoUser.is_active.is_(True),
                DemoUser.user_id != target.user_id,
            )
        ) or 0
        if count < 1:
            self._record_denied(
                actor,
                target,
                "USER_ADMIN_GUARD",
                "ADMIN_ACCOUNT_GUARD",
                "系统至少需要保留一个启用的管理员账号",
            )
            raise AccessConflictError("系统至少需要保留一个启用的管理员账号")

    def _record_denied(
        self,
        actor: DemoUser | None,
        target: DemoUser,
        event_type: str,
        operation: str,
        reason: str,
    ) -> None:
        self.audit.record(
            event_type,
            actor,
            target_user_id=target.user_id,
            operation=operation,
            decision="DENIED",
            reason=reason,
        )

    def _finalize_request(self, request: AccessRequest) -> None:
        approvals = self._approvals(request.request_id)
        decisions = {item.decision for item in approvals}
        if ApprovalDecision.REJECTED.value in decisions:
            rejected = next(item for item in approvals if item.decision == ApprovalDecision.REJECTED.value)
            request.status = AccessRequestStatus.REJECTED.value
            request.rejection_reason = rejected.reason or f"{rejected.party_id} rejected the request"
            request.completed_at = utc_now()
            self.session.commit()
            return
        if ApprovalDecision.PENDING.value in decisions:
            request.status = (
                AccessRequestStatus.PARTIALLY_APPROVED.value
                if decisions - {ApprovalDecision.PENDING.value}
                else AccessRequestStatus.PENDING.value
            )
            self.session.commit()
            return
        try:
            grant = self._create_grant(request, approvals)
        except AccessConflictError as exc:
            request.status = AccessRequestStatus.REJECTED.value
            request.rejection_reason = str(exc)
            request.completed_at = utc_now()
            self.session.commit()
            return
        request.status = AccessRequestStatus.APPROVED.value
        request.completed_at = utc_now()
        self.session.commit()
        actor = self.session.get(DemoUser, request.requester_user_id)
        self.audit.record(
            "GRANT_CREATED",
            actor,
            request_id=request.request_id,
            grant_id=grant.grant_id,
            decision="ACTIVE",
        )

    def _create_grant(
        self, request: AccessRequest, approvals: list[AccessApproval]
    ) -> AccessGrant:
        existing = self.session.scalar(
            select(AccessGrant).where(AccessGrant.request_id == request.request_id)
        )
        if existing is not None:
            return existing
        query_types = set(self._load(request.requested_query_types_json))
        group_by = set(self._load(request.requested_group_by_json))
        for approval in approvals:
            query_types &= set(self._load(approval.allowed_query_types_json or "[]"))
            group_by &= set(self._load(approval.allowed_group_by_json or "[]"))
        start_time = max(
            [request.requested_start_time]
            + [item.allowed_start_time for item in approvals if item.allowed_start_time]
        )
        end_time = min(
            [request.requested_end_time]
            + [item.allowed_end_time for item in approvals if item.allowed_end_time]
        )
        expires_at = min(
            [request.requested_expires_at]
            + [item.expires_at for item in approvals if item.expires_at]
        )
        max_epsilon = min(
            [request.requested_max_epsilon_per_query]
            + [item.max_epsilon_per_query for item in approvals if item.max_epsilon_per_query]
        )
        total_epsilon = min(
            [request.requested_total_epsilon]
            + [item.total_epsilon_limit for item in approvals if item.total_epsilon_limit]
        )
        if not query_types or start_time >= end_time or expires_at <= utc_now():
            raise AccessConflictError("审批条件交集为空，无法生成有效授权")
        if QueryType.TIME_SERIES.value in query_types and not group_by:
            raise AccessConflictError("TIME_SERIES 审批粒度交集为空")
        grant = AccessGrant(
            grant_id=f"GRANT-{request.request_id.removeprefix('REQUEST-')}",
            request_id=request.request_id,
            grantee_user_id=request.requester_user_id,
            parties_json=request.requested_parties_json,
            allowed_query_types_json=json.dumps(sorted(query_types)),
            allowed_start_time=start_time,
            allowed_end_time=end_time,
            allowed_group_by_json=json.dumps(sorted(group_by)),
            max_epsilon_per_query=max_epsilon,
            total_epsilon_limit=total_epsilon,
            epsilon_consumed=0.0,
            epsilon_reserved=0.0,
            valid_from=utc_now(),
            expires_at=expires_at,
            status=GrantStatus.ACTIVE.value,
        )
        self.session.add(grant)
        self.session.commit()
        return grant

    def _approval_scope(
        self, request: AccessRequest, payload: ApprovalDecisionRequest
    ) -> dict:
        requested_query_types = self._load(request.requested_query_types_json)
        requested_group_by = self._load(request.requested_group_by_json)
        query_types = [item.value for item in payload.allowed_query_types] if payload.allowed_query_types is not None else requested_query_types
        group_by = [item.value for item in payload.allowed_group_by] if payload.allowed_group_by is not None else requested_group_by
        start_time = self._naive(payload.allowed_start_time) if payload.allowed_start_time else request.requested_start_time
        end_time = self._naive(payload.allowed_end_time) if payload.allowed_end_time else request.requested_end_time
        max_epsilon = payload.max_epsilon_per_query or request.requested_max_epsilon_per_query
        total_epsilon = payload.total_epsilon_limit or request.requested_total_epsilon
        expires_at = self._naive(payload.expires_at) if payload.expires_at else request.requested_expires_at
        if not set(query_types).issubset(requested_query_types):
            raise AccessConflictError("审批不能扩大查询类型范围")
        if not set(group_by).issubset(requested_group_by):
            raise AccessConflictError("审批不能扩大 group_by 范围")
        if start_time < request.requested_start_time or end_time > request.requested_end_time or start_time >= end_time:
            raise AccessConflictError("审批不能扩大或反转时间范围")
        if max_epsilon > request.requested_max_epsilon_per_query:
            raise AccessConflictError("审批不能提高单次 epsilon 上限")
        if total_epsilon > request.requested_total_epsilon:
            raise AccessConflictError("审批不能提高累计 epsilon 上限")
        if expires_at > request.requested_expires_at or expires_at <= utc_now():
            raise AccessConflictError("审批到期时间必须处于申请范围内且晚于当前时间")
        return {
            "query_types": query_types,
            "group_by": group_by,
            "start_time": start_time,
            "end_time": end_time,
            "max_epsilon": max_epsilon,
            "total_epsilon": total_epsilon,
            "expires_at": expires_at,
        }

    def _validate_catalog_scope(self, payload: AccessRequestCreate) -> None:
        for party in payload.requested_parties:
            asset = self.session.scalar(
                select(DatasetAsset).where(
                    DatasetAsset.owner_party == party.value,
                    DatasetAsset.status == "ACTIVE",
                )
            )
            if asset is None:
                raise AccessConflictError(f"{party.value} 没有可申请的数据资产")
            if self._naive(payload.requested_start_time) < asset.time_start or self._naive(
                payload.requested_end_time
            ) > asset.time_end:
                raise AccessConflictError(f"申请时间超出 {party.value} 数据资产范围")
            if not set(item.value for item in payload.requested_query_types).issubset(
                self._load(asset.supported_query_types_json)
            ):
                raise AccessConflictError(f"申请包含 {party.value} 不支持的查询类型")
            if not set(item.value for item in payload.requested_group_by).issubset(
                self._load(asset.supported_group_by_json)
            ):
                raise AccessConflictError(f"申请包含 {party.value} 不支持的时序粒度")

    def _owned_request(self, user: DemoUser, request_id: str) -> AccessRequest:
        require_role(user, UserRole.ANALYST)
        item = self.session.get(AccessRequest, request_id)
        if item is None:
            raise AccessNotFoundError("申请不存在")
        if item.requester_user_id != user.user_id:
            raise AccessPermissionError("无权修改其他申请人的申请")
        return item

    def _approvals(self, request_id: str) -> list[AccessApproval]:
        return list(
            self.session.scalars(
                select(AccessApproval)
                .where(AccessApproval.request_id == request_id)
                .order_by(AccessApproval.party_id)
            )
        )

    def request_response(self, item: AccessRequest) -> AccessRequestResponse:
        return AccessRequestResponse(
            request_id=item.request_id,
            requester_user_id=item.requester_user_id,
            purpose=item.purpose,
            requested_parties=self._load(item.requested_parties_json),
            requested_query_types=self._load(item.requested_query_types_json),
            requested_start_time=item.requested_start_time,
            requested_end_time=item.requested_end_time,
            requested_group_by=self._load(item.requested_group_by_json),
            requested_max_epsilon_per_query=item.requested_max_epsilon_per_query,
            requested_total_epsilon=item.requested_total_epsilon,
            requested_expires_at=item.requested_expires_at,
            status=item.status,
            created_at=item.created_at,
            submitted_at=item.submitted_at,
            completed_at=item.completed_at,
            rejection_reason=item.rejection_reason,
            approvals=[self.approval_response(value) for value in self._approvals(item.request_id)],
        )

    @staticmethod
    def approval_response(item: AccessApproval) -> ApprovalResponse:
        return ApprovalResponse(
            approval_id=item.approval_id,
            request_id=item.request_id,
            party_id=item.party_id,
            approver_user_id=item.approver_user_id,
            decision=item.decision,
            reason=item.reason,
            allowed_query_types=json.loads(item.allowed_query_types_json) if item.allowed_query_types_json else None,
            allowed_start_time=item.allowed_start_time,
            allowed_end_time=item.allowed_end_time,
            allowed_group_by=json.loads(item.allowed_group_by_json) if item.allowed_group_by_json else None,
            max_epsilon_per_query=item.max_epsilon_per_query,
            total_epsilon_limit=item.total_epsilon_limit,
            expires_at=item.expires_at,
            decided_at=item.decided_at,
            created_at=item.created_at,
        )

    @staticmethod
    def asset_response(item: DatasetAsset) -> DatasetAssetResponse:
        return DatasetAssetResponse(
            asset_id=item.asset_id,
            name=item.name,
            description=item.description,
            owner_party=item.owner_party,
            time_start=item.time_start,
            time_end=item.time_end,
            source_granularity=item.source_granularity,
            supported_query_types=json.loads(item.supported_query_types_json),
            supported_group_by=json.loads(item.supported_group_by_json),
            privacy_protection=item.privacy_protection,
            raw_download_allowed=False,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def grant_response(item: AccessGrant) -> GrantResponse:
        return GrantResponse(
            grant_id=item.grant_id,
            request_id=item.request_id,
            grantee_user_id=item.grantee_user_id,
            parties=json.loads(item.parties_json),
            allowed_query_types=json.loads(item.allowed_query_types_json),
            allowed_start_time=item.allowed_start_time,
            allowed_end_time=item.allowed_end_time,
            allowed_group_by=json.loads(item.allowed_group_by_json),
            max_epsilon_per_query=item.max_epsilon_per_query,
            total_epsilon_limit=item.total_epsilon_limit,
            epsilon_consumed=item.epsilon_consumed,
            epsilon_reserved=item.epsilon_reserved,
            epsilon_remaining=max(
                item.total_epsilon_limit - item.epsilon_consumed - item.epsilon_reserved, 0.0
            ),
            valid_from=item.valid_from,
            expires_at=item.expires_at,
            status=item.status,
            created_at=item.created_at,
            revoked_at=item.revoked_at,
        )

    @staticmethod
    def user_response(item: DemoUser) -> UserResponse:
        return UserResponse(
            user_id=item.user_id,
            username=item.username,
            role=item.role,
            party_id=item.party_id,
            is_active=item.is_active,
            created_at=item.created_at,
            last_login_at=item.last_login_at,
        )

    @staticmethod
    def _request_input(item: AccessRequest) -> dict:
        return {
            "purpose": item.purpose,
            "requested_parties": json.loads(item.requested_parties_json),
            "requested_query_types": json.loads(item.requested_query_types_json),
            "requested_start_time": item.requested_start_time,
            "requested_end_time": item.requested_end_time,
            "requested_group_by": json.loads(item.requested_group_by_json),
            "requested_max_epsilon_per_query": item.requested_max_epsilon_per_query,
            "requested_total_epsilon": item.requested_total_epsilon,
            "requested_expires_at": item.requested_expires_at,
        }

    def _refresh_grant(self, grant: AccessGrant) -> AccessGrant:
        if grant.status == GrantStatus.ACTIVE.value:
            if grant.expires_at <= utc_now():
                grant.status = GrantStatus.EXPIRED.value
                self.session.commit()
                self.audit.record(
                    "GRANT_EXPIRED",
                    self.session.get(DemoUser, grant.grantee_user_id),
                    grant_id=grant.grant_id,
                    decision="EXPIRED",
                )
            elif grant.epsilon_consumed + grant.epsilon_reserved >= grant.total_epsilon_limit:
                grant.status = GrantStatus.EXHAUSTED.value
                self.session.commit()
        return grant

    def _next_request_id(self) -> str:
        count = self.session.scalar(select(func.count()).select_from(AccessRequest)) or 0
        while True:
            request_id = f"REQUEST-{count + 1:06d}"
            if self.session.get(AccessRequest, request_id) is None:
                return request_id
            count += 1

    @staticmethod
    def _dump(values) -> str:
        return json.dumps([getattr(item, "value", item) for item in values])

    @staticmethod
    def _load(value: str) -> list[str]:
        return json.loads(value)

    @staticmethod
    def _naive(value: datetime) -> datetime:
        return value.replace(tzinfo=None) if value.tzinfo else value
