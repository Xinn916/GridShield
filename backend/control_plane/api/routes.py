import json
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from common.enums import GroupBy, OrganizationId, QueryType, TaskStatus, UserRole
from common.schemas import (
    AgentExplainRequest,
    AgentExplainResponse,
    AgentParseRequest,
    AgentParseResponse,
    AuditEventResponse,
    GovernanceAdviceContext,
    GovernanceAdviceRequest,
    GovernanceAdviceResponse,
    PrivacyBudgetResponse,
    SystemHealthResponse,
    TaskCreateRequest,
    TaskMonitorResponse,
    TaskResponse,
    TaskResultResponse,
)
from common.performance import BenchmarkTestCreate, PerformanceTestList, PerformanceTestResponse
from control_plane.config import ControlSettings
from control_plane.services.compute_client import ComputeClient
from control_plane.services.party_client import PartyClient
from control_plane.services.privacy_budget_service import (
    InsufficientPrivacyBudgetError,
    PrivacyBudgetService,
)
from control_plane.services.system_health_service import SystemHealthService
from control_plane.services.task_service import TaskService
from control_plane.models.task_audit import TaskAudit
from control_plane.services.task_monitor import TaskMonitorStore, build_monitor_response
from control_plane.services.agent_service import AgentRateLimitError, AgentService
from control_plane.models.access_control import AccessGrant, DatasetAsset, DemoUser
from control_plane.models.task import Task
from control_plane.models.privacy_budget import PrivacyBudget
from control_plane.database.session import database_type_from_url
from control_plane.schemas.access_control import (
    AccessRequestCreate,
    AccessRequestPatch,
    AccessRequestResponse,
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserUpdate,
    AnalystReportResponse,
    AdminSecurityBaselineResponse,
    AdminSystemEventResponse,
    AdminSystemOverviewResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    DatasetAssetResponse,
    DatabaseRuntimeStatusResponse,
    DataAssetStorageStatusResponse,
    GrantResponse,
    LoginRequest,
    PlannedExtensionResponse,
    PublicRuntimeConfigResponse,
    SecurityAuditResponse,
    SafeNodeStatusResponse,
    SystemPolicySummaryResponse,
    UserStatusUpdate,
    UserResponse,
    ActiveDataVersionResponse,
    DataImportConfigResponse,
    DataImportResponse,
    DataImportRollbackRequest,
)
from control_plane.services.access_control_service import (
    AccessControlError,
    AccessControlService,
    AccessNotFoundError,
    AccessPermissionError,
)
from control_plane.services.auth_service import (
    AuthService,
    AuthenticationError,
    InactiveUserError,
)
from control_plane.services.security_audit_service import SecurityAuditService
from control_plane.services.report_service import AnalystReportService, ReportPermissionError
from control_plane.services.authorization_service import AuthorizationError
from control_plane.services.deepseek_client import (
    DeepSeekAuthError,
    DeepSeekError,
    DeepSeekInvalidResponseError,
    DeepSeekNotConfiguredError,
    DeepSeekRateLimitError,
    DeepSeekServerError,
    DeepSeekTimeoutError,
)
from control_plane.services.party_import_client import PartyImportClient, PartyImportError
from control_plane.services.data_import_service import (
    DataImportNotFoundError,
    DataImportPermissionError,
    DataImportService,
    DataImportStateError,
)
from control_plane.services.performance_service import PerformanceNotFoundError, PerformanceService
from control_plane.schemas.agent_conversation import (
    AgentConversationDetail,
    AgentConversationSummary,
)
from control_plane.services.agent_conversation_service import (
    AgentConversationNotFoundError,
    AgentConversationPermissionError,
    AgentConversationService,
)


def create_router(
    get_session,
    party_client: PartyClient,
    compute_client: ComputeClient,
    settings: ControlSettings,
    health_service: SystemHealthService,
    monitor_store: TaskMonitorStore | None = None,
    agent_service: AgentService | None = None,
    party_import_client: PartyImportClient | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    monitor_store = monitor_store or TaskMonitorStore()
    party_import_client = party_import_client or PartyImportClient(
        settings.party_urls, settings.internal_service_token, settings.request_timeout
    )

    @router.get("/public/config", response_model=PublicRuntimeConfigResponse)
    def public_runtime_config() -> PublicRuntimeConfigResponse:
        return PublicRuntimeConfigResponse(app_env=settings.app_env)

    def task_service(session: Session) -> TaskService:
        return TaskService(
            session,
            party_client,
            compute_client,
            settings.calculation_mode,
            settings.aggregate_poll_interval,
            settings.aggregate_poll_attempts,
            settings.default_total_epsilon,
            settings.subject_id,
            settings.epsilon_sum_ratio,
            settings.epsilon_count_ratio,
            settings.minimum_denominator,
            settings.record_cap,
            settings.max_records_per_household_per_day,
            settings.max_window_cap,
            monitor_store,
            settings.authorization_enforcement_enabled,
        )

    def current_user(session: Session, request: Request, required: bool = True) -> DemoUser | None:
        user = AuthService(session, settings.session_ttl_seconds).current_user(
            request.cookies.get(settings.session_cookie_name)
        )
        if required and user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return user

    def performance_service(session: Session) -> PerformanceService:
        return PerformanceService(
            session, party_client, compute_client,
            poll_interval=settings.aggregate_poll_interval,
            poll_attempts=settings.aggregate_poll_attempts,
            record_cap=settings.record_cap,
            max_records_per_household_per_day=settings.max_records_per_household_per_day,
            max_window_cap=settings.max_window_cap,
            minimum_denominator=settings.minimum_denominator,
            epsilon_sum_ratio=settings.epsilon_sum_ratio,
            epsilon_count_ratio=settings.epsilon_count_ratio,
        )

    def performance_user(session: Session, request: Request) -> DemoUser:
        user = current_user(session, request)
        if user.role not in {UserRole.ANALYST.value, UserRole.ADMIN.value}:
            raise HTTPException(status_code=403, detail="Current role cannot run performance benchmarks")
        return user

    def can_view_task_audit(session: Session, user: DemoUser, audit: TaskAudit) -> bool:
        if user.role in {UserRole.AUDITOR.value, UserRole.ADMIN.value}:
            return True
        task = session.get(Task, audit.task_id)
        if task is None:
            return False
        if user.role == UserRole.ANALYST.value:
            grant = session.get(AccessGrant, task.grant_id) if task.grant_id else None
            return grant is not None and grant.grantee_user_id == user.user_id
        if user.role == UserRole.DATA_OWNER.value and user.party_id:
            try:
                return user.party_id in json.loads(task.parties_json)
            except (TypeError, ValueError):
                return False
        return False

    def can_view_task_agent_context(session: Session, user: DemoUser, task: Task) -> bool:
        """Keep governance advice subject to the same task ownership boundary."""
        if user.role in {UserRole.ADMIN.value, UserRole.AUDITOR.value}:
            return True
        if user.role == UserRole.ANALYST.value:
            grant = session.get(AccessGrant, task.grant_id) if task.grant_id else None
            return grant is not None and grant.grantee_user_id == user.user_id
        if user.role == UserRole.DATA_OWNER.value and user.party_id:
            try:
                return user.party_id in json.loads(task.parties_json)
            except (TypeError, ValueError):
                return False
        return False

    def governance_context(session: Session, task: Task, actor: DemoUser | None) -> GovernanceAdviceContext:
        try:
            parties = json.loads(task.parties_json)
        except (TypeError, ValueError):
            parties = []
        grant = session.get(AccessGrant, task.grant_id) if task.grant_id else None
        subject_id = grant.grantee_user_id if grant else (actor.user_id if actor else settings.subject_id)
        # Authorized tasks are budgeted by their own Grant.  The legacy
        # subject/GLOBAL ledger remains only for compatibility tasks created
        # while authorization enforcement is disabled.
        if grant is not None:
            total = float(grant.total_epsilon_limit)
            used = float(grant.epsilon_consumed)
            reserved = float(grant.epsilon_reserved)
        else:
            budget = session.scalar(
                select(PrivacyBudget).where(
                    PrivacyBudget.subject_id == subject_id,
                    PrivacyBudget.data_scope == "GLOBAL",
                )
            )
            total = float(budget.total_epsilon if budget else settings.default_total_epsilon)
            used = float(budget.used_epsilon if budget else 0.0)
            reserved = float(budget.reserved_epsilon if budget else 0.0)
        remaining = max(total - used - reserved, 0.0)
        grant_remaining = None
        if grant is not None:
            grant_remaining = max(
                float(grant.total_epsilon_limit) - float(grant.epsilon_consumed) - float(grant.epsilon_reserved),
                0.0,
            )
        bucket_count = None
        if task.result_json and task.query_type == QueryType.TIME_SERIES:
            try:
                result = json.loads(task.result_json)
                bucket_count = int(result.get("bucket_count", 0))
            except (TypeError, ValueError, json.JSONDecodeError):
                bucket_count = None
        window_minutes = max(int((task.end_time - task.start_time).total_seconds() // 60), 1)
        return GovernanceAdviceContext(
            task_id=task.task_id,
            task_status=task.status,
            query_type=task.query_type,
            parties=parties,
            calculation_mode=task.calculation_mode,
            epsilon=float(task.epsilon),
            group_by=task.group_by,
            start_time=task.start_time,
            end_time=task.end_time,
            window_minutes=window_minutes,
            grant_status=grant.status if grant else None,
            budget_status=task.budget_status,
            grant_epsilon_limit=float(grant.max_epsilon_per_query) if grant else None,
            grant_epsilon_remaining=grant_remaining,
            budget_total=total,
            budget_used=used,
            budget_reserved=reserved,
            budget_remaining=remaining,
            budget_before=float(task.budget_before) if task.budget_before is not None else None,
            budget_after=float(task.budget_after) if task.budget_after is not None else None,
            result_bucket_count=bucket_count,
        )

    def access_error(exc: Exception) -> HTTPException:
        if isinstance(exc, AccessNotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, AccessPermissionError):
            return HTTPException(status_code=403, detail=str(exc))
        return HTTPException(status_code=409, detail=str(exc))

    def import_error(exc: Exception) -> HTTPException:
        if isinstance(exc, DataImportNotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, DataImportPermissionError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, PartyImportError):
            return HTTPException(status_code=exc.status_code, detail=str(exc))
        return HTTPException(status_code=409, detail=str(exc))

    @router.post("/auth/login", response_model=UserResponse)
    def login(payload: LoginRequest, response: Response, session: Session = Depends(get_session)) -> UserResponse:
        try:
            user, token = AuthService(session, settings.session_ttl_seconds).login(
                payload.username, payload.password
            )
        except (AuthenticationError, InactiveUserError) as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        response.set_cookie(
            settings.session_cookie_name,
            token,
            max_age=settings.session_ttl_seconds,
            httponly=True,
            samesite="lax",
            secure=settings.session_cookie_secure,
        )
        return AccessControlService.user_response(user)

    @router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request, response: Response, session: Session = Depends(get_session)) -> None:
        AuthService(session, settings.session_ttl_seconds).logout(
            request.cookies.get(settings.session_cookie_name)
        )
        response.delete_cookie(settings.session_cookie_name)

    @router.get("/auth/me", response_model=UserResponse)
    def me(request: Request, session: Session = Depends(get_session)) -> UserResponse:
        return AccessControlService.user_response(current_user(session, request))

    @router.post("/performance-tests", response_model=PerformanceTestResponse, status_code=status.HTTP_201_CREATED)
    def create_performance_test(
        payload: BenchmarkTestCreate,
        request: Request,
        session: Session = Depends(get_session),
    ) -> PerformanceTestResponse:
        actor = performance_user(session, request)
        item = performance_service(session).create_and_run(payload, actor.user_id)
        return performance_service(session).to_response(item)

    @router.get("/performance-tests", response_model=PerformanceTestList)
    def list_performance_tests(
        request: Request,
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ) -> PerformanceTestList:
        actor = performance_user(session, request)
        creator_scope = None if actor.role == UserRole.ADMIN.value else actor.user_id
        return performance_service(session).list(limit, offset, creator_scope)

    @router.get("/performance-tests/{test_id}", response_model=PerformanceTestResponse)
    def get_performance_test(
        test_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> PerformanceTestResponse:
        actor = performance_user(session, request)
        service = performance_service(session)
        try:
            creator_scope = None if actor.role == UserRole.ADMIN.value else actor.user_id
            return service.to_response(service.get(test_id, creator_scope))
        except PerformanceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/catalog/assets", response_model=list[DatasetAssetResponse])
    def catalog_assets(request: Request, session: Session = Depends(get_session)) -> list[DatasetAssetResponse]:
        current_user(session, request)
        return AccessControlService(session).list_assets()

    @router.get("/catalog/assets/owner", response_model=list[DatasetAssetResponse])
    def owner_catalog_assets(request: Request, session: Session = Depends(get_session)) -> list[DatasetAssetResponse]:
        try:
            return AccessControlService(session).list_owner_assets(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/catalog/assets/{asset_id}", response_model=DatasetAssetResponse)
    def catalog_asset(asset_id: str, request: Request, session: Session = Depends(get_session)) -> DatasetAssetResponse:
        current_user(session, request)
        try:
            return AccessControlService(session).get_asset(asset_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/data-imports/config", response_model=DataImportConfigResponse)
    def data_import_config(request: Request, session: Session = Depends(get_session)) -> DataImportConfigResponse:
        user = current_user(session, request)
        if user.role != UserRole.DATA_OWNER.value or not user.party_id:
            raise HTTPException(status_code=403, detail="only a bound DATA_OWNER can import data")
        return DataImportConfigResponse(
            enabled=settings.csv_import_enabled,
            max_bytes=settings.csv_import_max_bytes,
            max_rows=settings.csv_import_max_rows,
        )

    @router.post("/data-imports", response_model=DataImportResponse, status_code=status.HTTP_201_CREATED)
    def create_data_import(
        request: Request,
        file: UploadFile = File(...),
        session: Session = Depends(get_session),
    ) -> DataImportResponse:
        user = current_user(session, request)
        try:
            if not settings.csv_import_enabled:
                raise DataImportStateError("CSV import is disabled")
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
            if size > settings.csv_import_max_bytes:
                raise HTTPException(status_code=413, detail="CSV exceeds configured size limit")
            return DataImportService(session, party_import_client).upload(
                user, file.filename or "", file.file
            )
        except (DataImportNotFoundError, DataImportPermissionError, DataImportStateError, PartyImportError) as exc:
            raise import_error(exc) from exc

    @router.get("/data-imports/mine", response_model=list[DataImportResponse])
    def my_data_imports(request: Request, session: Session = Depends(get_session)) -> list[DataImportResponse]:
        try:
            return DataImportService(session, party_import_client).list_mine(current_user(session, request))
        except (DataImportPermissionError, DataImportStateError) as exc:
            raise import_error(exc) from exc

    @router.get("/data-imports/active", response_model=ActiveDataVersionResponse)
    def active_data_import(request: Request, session: Session = Depends(get_session)) -> ActiveDataVersionResponse:
        try:
            result = DataImportService(session, party_import_client).active(current_user(session, request))
            return ActiveDataVersionResponse.model_validate(result.model_dump())
        except (DataImportPermissionError, PartyImportError) as exc:
            raise import_error(exc) from exc

    @router.get("/admin/data-imports", response_model=list[DataImportResponse])
    def all_data_imports(request: Request, session: Session = Depends(get_session)) -> list[DataImportResponse]:
        try:
            return DataImportService(session, party_import_client).list_all(current_user(session, request))
        except DataImportPermissionError as exc:
            raise import_error(exc) from exc

    @router.get("/data-imports/{import_id}", response_model=DataImportResponse)
    def data_import_detail(import_id: str, request: Request, session: Session = Depends(get_session)) -> DataImportResponse:
        try:
            return DataImportService(session, party_import_client).get(current_user(session, request), import_id)
        except (DataImportNotFoundError, DataImportPermissionError) as exc:
            raise import_error(exc) from exc

    @router.post("/data-imports/{import_id}/activate", response_model=DataImportResponse)
    def activate_data_import(import_id: str, request: Request, session: Session = Depends(get_session)) -> DataImportResponse:
        try:
            return DataImportService(session, party_import_client).activate(current_user(session, request), import_id)
        except (DataImportNotFoundError, DataImportPermissionError, DataImportStateError, PartyImportError) as exc:
            raise import_error(exc) from exc

    @router.post("/data-imports/{import_id}/rollback", response_model=ActiveDataVersionResponse)
    def rollback_data_import(
        import_id: str,
        payload: DataImportRollbackRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> ActiveDataVersionResponse:
        if payload.target_version != import_id:
            raise HTTPException(status_code=400, detail="rollback target does not match route")
        try:
            result = DataImportService(session, party_import_client).rollback(
                current_user(session, request), payload.target_version
            )
            return ActiveDataVersionResponse.model_validate(result.model_dump())
        except (DataImportNotFoundError, DataImportPermissionError, DataImportStateError, PartyImportError) as exc:
            raise import_error(exc) from exc

    @router.post("/access-requests", response_model=AccessRequestResponse, status_code=status.HTTP_201_CREATED)
    def create_access_request(payload: AccessRequestCreate, request: Request, session: Session = Depends(get_session)) -> AccessRequestResponse:
        try:
            return AccessControlService(session).create_request(current_user(session, request), payload)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/access-requests/mine", response_model=list[AccessRequestResponse])
    def my_access_requests(request: Request, session: Session = Depends(get_session)) -> list[AccessRequestResponse]:
        try:
            return AccessControlService(session).list_mine(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/access-requests/{request_id}", response_model=AccessRequestResponse)
    def access_request_detail(request_id: str, request: Request, session: Session = Depends(get_session)) -> AccessRequestResponse:
        try:
            return AccessControlService(session).get_request(current_user(session, request), request_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.patch("/access-requests/{request_id}", response_model=AccessRequestResponse)
    def update_access_request(request_id: str, payload: AccessRequestPatch, request: Request, session: Session = Depends(get_session)) -> AccessRequestResponse:
        try:
            return AccessControlService(session).update_request(current_user(session, request), request_id, payload)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/access-requests/{request_id}/submit", response_model=AccessRequestResponse)
    def submit_access_request(request_id: str, request: Request, session: Session = Depends(get_session)) -> AccessRequestResponse:
        try:
            return AccessControlService(session).submit_request(current_user(session, request), request_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/access-requests/{request_id}/withdraw", response_model=AccessRequestResponse)
    def withdraw_access_request(request_id: str, request: Request, session: Session = Depends(get_session)) -> AccessRequestResponse:
        try:
            return AccessControlService(session).withdraw_request(current_user(session, request), request_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/approvals/pending", response_model=list[ApprovalResponse])
    def pending_approvals(request: Request, session: Session = Depends(get_session)) -> list[ApprovalResponse]:
        try:
            return AccessControlService(session).pending_approvals(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/approvals/history", response_model=list[ApprovalResponse])
    def approval_history(request: Request, session: Session = Depends(get_session)) -> list[ApprovalResponse]:
        try:
            return AccessControlService(session).approval_history(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/approvals/{approval_id}", response_model=ApprovalResponse)
    def approval_detail(approval_id: str, request: Request, session: Session = Depends(get_session)) -> ApprovalResponse:
        try:
            return AccessControlService(session).get_approval(current_user(session, request), approval_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/approvals/{approval_id}/decision", response_model=ApprovalResponse)
    def approval_decision(approval_id: str, payload: ApprovalDecisionRequest, request: Request, session: Session = Depends(get_session)) -> ApprovalResponse:
        try:
            return AccessControlService(session).decide(current_user(session, request), approval_id, payload)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/grants/mine", response_model=list[GrantResponse])
    def my_grants(request: Request, session: Session = Depends(get_session)) -> list[GrantResponse]:
        try:
            return AccessControlService(session).list_grants(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/grants/owner", response_model=list[GrantResponse])
    def grants_for_owner(request: Request, session: Session = Depends(get_session)) -> list[GrantResponse]:
        try:
            return AccessControlService(session).owner_grants(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/grants/{grant_id}", response_model=GrantResponse)
    def grant_detail(grant_id: str, request: Request, session: Session = Depends(get_session)) -> GrantResponse:
        try:
            return AccessControlService(session).get_grant(current_user(session, request), grant_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/grants/{grant_id}/revoke", response_model=GrantResponse)
    def revoke_grant(grant_id: str, request: Request, session: Session = Depends(get_session)) -> GrantResponse:
        try:
            return AccessControlService(session).revoke_grant(current_user(session, request), grant_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/admin/access-requests", response_model=list[AccessRequestResponse])
    def all_access_requests(request: Request, session: Session = Depends(get_session)) -> list[AccessRequestResponse]:
        try:
            return AccessControlService(session).all_requests(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/admin/grants", response_model=list[GrantResponse])
    def all_grants(request: Request, session: Session = Depends(get_session)) -> list[GrantResponse]:
        try:
            return AccessControlService(session).all_grants(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/admin/users", response_model=list[UserResponse])
    def all_users(request: Request, session: Session = Depends(get_session)) -> list[UserResponse]:
        try:
            return AccessControlService(session).all_users(current_user(session, request))
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
    def create_admin_user(payload: AdminUserCreate, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).create_user(current_user(session, request), payload)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.patch("/admin/users/{user_id}", response_model=UserResponse)
    def update_admin_user(user_id: str, payload: AdminUserUpdate, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).update_user(current_user(session, request), user_id, payload)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.patch("/admin/users/{user_id}/status", response_model=UserResponse)
    def set_user_status(user_id: str, payload: UserStatusUpdate, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).set_user_active(
                current_user(session, request), user_id, payload.active
            )
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/admin/users/{user_id}/disable", response_model=UserResponse)
    def disable_admin_user(user_id: str, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).set_user_active(current_user(session, request), user_id, False)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/admin/users/{user_id}/enable", response_model=UserResponse)
    def enable_admin_user(user_id: str, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).set_user_active(current_user(session, request), user_id, True)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/admin/users/{user_id}/reset-password", response_model=UserResponse)
    def reset_admin_user_password(user_id: str, payload: AdminPasswordReset, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).reset_password(current_user(session, request), user_id, payload)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.post("/admin/users/{user_id}/revoke-sessions", response_model=UserResponse)
    def revoke_admin_user_sessions(user_id: str, request: Request, session: Session = Depends(get_session)) -> UserResponse:
        try:
            return AccessControlService(session).revoke_user_sessions(current_user(session, request), user_id)
        except AccessControlError as exc:
            raise access_error(exc) from exc

    @router.get("/admin/security-audit", response_model=list[SecurityAuditResponse])
    def security_audit(request: Request, session: Session = Depends(get_session)) -> list[SecurityAuditResponse]:
        user = current_user(session, request)
        if user.role not in {UserRole.AUDITOR.value, UserRole.ADMIN.value}:
            raise HTTPException(status_code=403, detail="当前角色无权查看安全审计")
        return [
            SecurityAuditResponse(
                audit_id=item.audit_id,
                event_type=item.event_type,
                actor_user_id=item.actor_user_id,
                target_user_id=item.target_user_id,
                actor_role=item.actor_role,
                party_id=item.party_id,
                request_id=item.request_id,
                grant_id=item.grant_id,
                task_id=item.task_id,
                import_id=item.import_id,
                source_sha256=item.source_sha256,
                row_count=item.row_count,
                import_status=item.import_status,
                decision=item.decision,
                operation=item.operation,
                reason=item.reason,
                timestamp=item.timestamp,
            )
            for item in SecurityAuditService(session).list_recent()
        ]

    @router.get("/admin/system-overview", response_model=AdminSystemOverviewResponse)
    def admin_system_overview(
        request: Request, session: Session = Depends(get_session)
    ) -> AdminSystemOverviewResponse:
        user = current_user(session, request)
        if user.role != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="仅系统管理员可以查看系统运行摘要")

        database_type = database_type_from_url(settings.database_url)
        database_connected = True
        try:
            session.execute(text("SELECT 1"))
        except Exception:
            session.rollback()
            database_connected = False

        health = health_service.check_all()

        def safe_node(service_id: str, fallback_name: str) -> SafeNodeStatusResponse:
            item = next((node for node in health.services if node.service_id == service_id), None)
            if item is None:
                return SafeNodeStatusResponse(
                    service_id=service_id,
                    name=fallback_name,
                    online=False,
                    latency_ms=0,
                )
            return SafeNodeStatusResponse(
                service_id=item.service_id,
                name=item.name,
                online=item.online,
                latency_ms=item.latency_ms,
                version=item.version,
            )

        party_count = session.scalar(
            select(func.count(func.distinct(DatasetAsset.owner_party)))
        ) or 0
        event_rows = SecurityAuditService(session).list_recent(limit=50)
        database_note = (
            "当前为 SQLite 单机开发数据库，适用于本地开发和低并发运行；生产环境建议使用 PostgreSQL。"
            if database_type == "SQLite"
            else "控制平面元数据数据库；能源原始数据仍由各园区 Parquet 资产保存。"
        )

        return AdminSystemOverviewResponse(
            database=DatabaseRuntimeStatusResponse(
                type=database_type,
                connected=database_connected,
                demo_database=database_type == "SQLite",
                note=database_note,
            ),
            asset_storage=DataAssetStorageStatusResponse(party_count=party_count),
            frontend_gateway=safe_node("frontend", "前端网关 Nginx"),
            party_nodes=[safe_node(f"party-{suffix}", f"园区 {suffix.upper()}") for suffix in "abc"],
            compute_nodes=[safe_node(f"compute-s{index}", f"计算节点 S{index}") for index in (1, 2)],
            agent_model_configured=bool(settings.deepseek_api_key.strip()),
            security_baseline=AdminSecurityBaselineResponse(
                authorization_enforcement_enabled=settings.authorization_enforcement_enabled,
                session_ttl_seconds=settings.session_ttl_seconds,
                calculation_mode=settings.calculation_mode,
                demo_identity_mode_enabled=settings.demo_seed_enabled,
            ),
            planned_extensions=[
                PlannedExtensionResponse(name=name)
                for name in ("PostgreSQL", "Redis", "MQTT", "对象存储", "通知服务")
            ],
            maintenance_records=[],
            system_events=[
                AdminSystemEventResponse(
                    audit_id=item.audit_id,
                    event_type=item.event_type,
                    actor_user_id=item.actor_user_id,
                    actor_role=item.actor_role,
                    party_id=item.party_id,
                    request_id=item.request_id,
                    grant_id=item.grant_id,
                    task_id=item.task_id,
                    decision=item.decision,
                    reason=item.reason,
                    timestamp=item.timestamp,
                )
                for item in event_rows
            ],
            checked_at=health.checked_at,
        )

    @router.get("/parties")
    def parties() -> list[dict]:
        return [party_client.describe(party) for party in OrganizationId]

    @router.get("/system/health", response_model=SystemHealthResponse)
    def system_health() -> SystemHealthResponse:
        return health_service.check_all()

    @router.get("/system/policy-summary", response_model=SystemPolicySummaryResponse)
    def system_policy_summary(request: Request, session: Session = Depends(get_session)) -> SystemPolicySummaryResponse:
        user = current_user(session, request)
        if user.role != UserRole.DATA_OWNER.value:
            raise HTTPException(status_code=403, detail="仅园区管理员可以查看本园区生效策略摘要")
        health = health_service.check_all()
        safe_nodes = [
            SafeNodeStatusResponse(
                service_id=item.service_id,
                name=item.name,
                online=item.online,
                latency_ms=item.latency_ms,
                version=item.version,
            )
            for item in health.services
        ]
        return SystemPolicySummaryResponse(
            authorization_enforcement_enabled=settings.authorization_enforcement_enabled,
            raw_download_allowed=False,
            calculation_mode=settings.calculation_mode,
            supported_query_types=list(QueryType),
            supported_group_by=list(GroupBy),
            default_total_epsilon=settings.default_total_epsilon,
            session_ttl_seconds=settings.session_ttl_seconds,
            audit_enabled=True,
            party_nodes=[item for item in safe_nodes if item.service_id.startswith("party-")],
            compute_nodes=[item for item in safe_nodes if item.service_id.startswith("compute-")],
        )

    @router.get("/reports/me", response_model=AnalystReportResponse)
    def analyst_report(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        session: Session = Depends(get_session),
    ) -> AnalystReportResponse:
        try:
            return AnalystReportService(
                session, settings.default_total_epsilon
            ).build(current_user(session, request), limit)
        except ReportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.get("/tasks", response_model=list[TaskResponse])
    def recent_tasks(
        http_request: Request,
        limit: int = Query(default=10, ge=1, le=100),
        session: Session = Depends(get_session),
    ) -> list[TaskResponse]:
        if settings.authorization_enforcement_enabled:
            current_user(session, http_request)
        return [TaskService.to_response(task) for task in task_service(session).list_recent(limit)]

    @router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
    def create_task(
        payload: TaskCreateRequest,
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> TaskResponse:
        try:
            actor = current_user(session, http_request) if settings.authorization_enforcement_enabled else None
            task = task_service(session).create_and_run(payload, actor)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InsufficientPrivacyBudgetError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TaskService.to_response(task)

    @router.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str, http_request: Request, session: Session = Depends(get_session)) -> TaskResponse:
        if settings.authorization_enforcement_enabled:
            current_user(session, http_request)
        task = task_service(session).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskService.to_response(task)

    @router.get("/tasks/{task_id}/result", response_model=TaskResultResponse)
    def get_result(task_id: str, http_request: Request, session: Session = Depends(get_session)) -> TaskResultResponse:
        if settings.authorization_enforcement_enabled:
            current_user(session, http_request)
        task = task_service(session).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status != TaskStatus.COMPLETED.value:
            raise HTTPException(status_code=409, detail=f"Task is {task.status}")
        return TaskService.to_result(task)

    @router.get("/privacy/budgets", response_model=PrivacyBudgetResponse)
    def privacy_budget(
        http_request: Request,
        subject_id: str = "demo-analyst",
        data_scope: Literal["GLOBAL", "ORG_A", "ORG_B", "ORG_C"] = "GLOBAL",
        session: Session = Depends(get_session),
    ) -> PrivacyBudgetResponse:
        if settings.authorization_enforcement_enabled:
            actor = current_user(session, http_request)
            subject_id = actor.user_id
        return PrivacyBudgetService(session, settings.default_total_epsilon).response(
            subject_id, data_scope
        )

    @router.get(
        "/audit/events/{task_id}",
        response_model=AuditEventResponse,
        response_model_exclude_none=True,
    )
    def audit_event(
        task_id: str, http_request: Request, session: Session = Depends(get_session)
    ) -> AuditEventResponse:
        actor = current_user(session, http_request) if settings.authorization_enforcement_enabled else None
        audit = session.get(TaskAudit, task_id)
        if audit is None:
            raise HTTPException(status_code=404, detail="Audit event not found")
        if actor is not None and not can_view_task_audit(session, actor, audit):
            raise HTTPException(status_code=403, detail="Current role cannot view this audit event")
        return _audit_to_response(audit)

    @router.get(
        "/audit/events",
        response_model=list[AuditEventResponse],
        response_model_exclude_none=True,
    )
    def audit_events(
        http_request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        session: Session = Depends(get_session),
    ) -> list[AuditEventResponse]:
        actor = current_user(session, http_request) if settings.authorization_enforcement_enabled else None
        audits = list(
            session.scalars(
                select(TaskAudit).order_by(TaskAudit.created_at.desc())
            )
        )
        if actor is not None:
            audits = [audit for audit in audits if can_view_task_audit(session, actor, audit)]
        audits = audits[:limit]
        return [_audit_to_response(audit) for audit in audits]

    @router.get("/tasks/{task_id}/monitor", response_model=TaskMonitorResponse)
    def task_monitor(
        task_id: str, http_request: Request, session: Session = Depends(get_session)
    ) -> TaskMonitorResponse:
        if settings.authorization_enforcement_enabled:
            current_user(session, http_request)
        task = task_service(session).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return build_monitor_response(task, monitor_store.get(task_id))

    @router.post("/agent/parse-query", response_model=AgentParseResponse)
    def agent_parse_query(
        request: AgentParseRequest,
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> AgentParseResponse:
        actor = current_user(session, http_request) if (
            settings.authorization_enforcement_enabled or request.conversation_id
        ) else None
        conversations = AgentConversationService(session)
        if request.conversation_id and actor is not None:
            try:
                conversations.save_user_message(actor, request.conversation_id, request.text)
            except AgentConversationNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        budget_context = None
        if request.grant_id:
            grant = session.get(AccessGrant, request.grant_id)
            can_read_grant = grant is not None and (
                actor is None or grant.grantee_user_id == actor.user_id
            )
            if can_read_grant:
                budget_context = {
                    "grant_id": grant.grant_id,
                    "total_epsilon": float(grant.total_epsilon_limit),
                    "used_epsilon": float(grant.epsilon_consumed),
                    "reserved_epsilon": float(grant.epsilon_reserved),
                    "remaining_epsilon": max(
                        float(grant.total_epsilon_limit)
                        - float(grant.epsilon_consumed)
                        - float(grant.epsilon_reserved),
                        0.0,
                    ),
                    "planned_epsilon": request.current_form.epsilon if request.current_form else None,
                }
        client_key = http_request.client.host if http_request.client else "unknown"
        try:
            response = agent_service.parse_query(
                request,
                client_key=client_key,
                budget_context=budget_context,
            )
            if request.conversation_id and actor is not None:
                conversations.save_assistant_message(
                    actor, request.conversation_id, request, response
                )
                response.conversation_id = request.conversation_id
            return response
        except AgentRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except DeepSeekNotConfiguredError:
            raise HTTPException(status_code=503, detail="DeepSeek API 未配置") from None
        except DeepSeekAuthError:
            raise HTTPException(status_code=502, detail="模型认证失败，请检查后端 API Key 配置") from None
        except DeepSeekRateLimitError:
            raise HTTPException(status_code=429, detail="模型服务繁忙，请稍后重试") from None
        except DeepSeekTimeoutError:
            raise HTTPException(status_code=504, detail="模型解析超时，请稍后重试") from None
        except DeepSeekServerError:
            raise HTTPException(status_code=502, detail="模型服务异常，请稍后重试") from None
        except DeepSeekInvalidResponseError:
            raise HTTPException(status_code=502, detail="模型返回异常，请稍后重试") from None
        except DeepSeekError:
            raise HTTPException(status_code=502, detail="模型服务不可用，请稍后重试") from None

    @router.get(
        "/agent/conversations",
        response_model=list[AgentConversationSummary],
    )
    def agent_conversations(
        http_request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        session: Session = Depends(get_session),
    ) -> list[AgentConversationSummary]:
        return AgentConversationService(session).list(
            current_user(session, http_request), limit
        )

    @router.post(
        "/agent/conversations",
        response_model=AgentConversationDetail,
        status_code=status.HTTP_201_CREATED,
    )
    def create_agent_conversation(
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> AgentConversationDetail:
        return AgentConversationService(session).create(current_user(session, http_request))

    @router.get(
        "/agent/conversations/{conversation_id}",
        response_model=AgentConversationDetail,
    )
    def get_agent_conversation(
        conversation_id: str,
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> AgentConversationDetail:
        try:
            return AgentConversationService(session).detail(
                current_user(session, http_request), conversation_id
            )
        except AgentConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/agent/conversations/{conversation_id}/tasks/{task_id}",
        response_model=AgentConversationDetail,
    )
    def link_agent_conversation_task(
        conversation_id: str,
        task_id: str,
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> AgentConversationDetail:
        try:
            return AgentConversationService(session).link_task(
                current_user(session, http_request), conversation_id, task_id
            )
        except AgentConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AgentConversationPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/agent/explain-result", response_model=AgentExplainResponse)
    def agent_explain_result(
        request: AgentExplainRequest,
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> AgentExplainResponse:
        if settings.authorization_enforcement_enabled:
            current_user(session, http_request)
        client_key = http_request.client.host if http_request.client else "unknown"
        try:
            return agent_service.explain_result(request, client_key=client_key)
        except AgentRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except DeepSeekNotConfiguredError:
            raise HTTPException(status_code=503, detail="DeepSeek API 未配置") from None
        except DeepSeekAuthError:
            raise HTTPException(status_code=502, detail="模型认证失败，请检查后端 API Key 配置") from None
        except DeepSeekRateLimitError:
            raise HTTPException(status_code=429, detail="模型服务繁忙，请稍后重试") from None
        except DeepSeekTimeoutError:
            raise HTTPException(status_code=504, detail="模型解析超时，请稍后重试") from None
        except DeepSeekServerError:
            raise HTTPException(status_code=502, detail="模型服务异常，请稍后重试") from None
        except DeepSeekInvalidResponseError:
            raise HTTPException(status_code=502, detail="模型返回异常，请稍后重试") from None
        except DeepSeekError:
            raise HTTPException(status_code=502, detail="模型服务不可用，请稍后重试") from None

    @router.post("/agent/governance-advice", response_model=GovernanceAdviceResponse)
    def agent_governance_advice(
        request: GovernanceAdviceRequest,
        http_request: Request,
        session: Session = Depends(get_session),
    ) -> GovernanceAdviceResponse:
        actor = current_user(session, http_request) if settings.authorization_enforcement_enabled else None
        task = session.get(Task, request.task_id)
        # Hide task existence from callers who do not own the corresponding grant/task.
        if task is None or (actor is not None and not can_view_task_agent_context(session, actor, task)):
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status != TaskStatus.COMPLETED.value:
            raise HTTPException(status_code=409, detail="Governance advice is available after task completion")
        client_key = http_request.client.host if http_request.client else "unknown"
        try:
            context = governance_context(session, task, actor)
            return agent_service.governance_advice(context, client_key=client_key)
        except AgentRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except DeepSeekNotConfiguredError:
            raise HTTPException(status_code=503, detail="DeepSeek API 未配置") from None
        except DeepSeekAuthError:
            raise HTTPException(status_code=502, detail="模型认证失败，请检查后端 API Key 配置") from None
        except DeepSeekRateLimitError:
            raise HTTPException(status_code=429, detail="模型服务繁忙，请稍后重试") from None
        except DeepSeekTimeoutError:
            raise HTTPException(status_code=504, detail="模型解析超时，请稍后重试") from None
        except DeepSeekServerError:
            raise HTTPException(status_code=502, detail="模型服务异常，请稍后重试") from None
        except DeepSeekInvalidResponseError:
            raise HTTPException(status_code=502, detail="模型返回异常，请稍后重试") from None
        except DeepSeekError:
            raise HTTPException(status_code=502, detail="模型服务不可用，请稍后重试") from None
    return router


def _audit_to_response(audit: TaskAudit) -> AuditEventResponse:
    return AuditEventResponse(
        task_id=audit.task_id,
        query_type=audit.query_type,
        group_by=audit.group_by,
        bucket_count=audit.bucket_count,
        parties=json.loads(audit.parties_json),
        epsilon=audit.epsilon,
        sensitivity=json.loads(audit.sensitivity_json) if audit.sensitivity_json else None,
        mechanism=audit.mechanism,
        privacy_unit=audit.privacy_unit,
        calculation_mode=audit.calculation_mode,
        budget_before=audit.budget_before,
        budget_after=audit.budget_after,
        execution_time_ms=audit.execution_time_ms,
        status=audit.status,
        created_at=audit.created_at,
        dataset_versions=json.loads(audit.dataset_versions_json or "{}"),
    )
