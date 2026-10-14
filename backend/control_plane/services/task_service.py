import json
import logging
import math
import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.enums import CalculationMode, ComputeTaskStatus, QueryType, TaskStatus
from common.fixed_point import decode
from common.schemas import (
    ComputeTaskRegistration,
    DistributedDPParameters,
    SecretTaskRequest,
    StatisticsRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskResultResponse,
)
from common.secret_sharing import reconstruct_secret
from common.time_buckets import generate_time_buckets
from control_plane.models.task import Task, utc_now
from control_plane.models.task_audit import TaskAudit
from control_plane.models.access_control import DemoUser
from control_plane.services.aggregation import aggregate_results
from control_plane.services.compute_client import ComputeClient
from control_plane.services.party_client import PartyClient
from control_plane.services.privacy_budget_service import (
    InsufficientPrivacyBudgetError,
    PrivacyBudgetService,
)
from control_plane.services.task_monitor import TaskMonitorStore
from control_plane.services.authorization_service import AuthorizationService
from control_plane.services.security_audit_service import SecurityAuditService


logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self,
        session: Session,
        party_client: PartyClient,
        compute_client: ComputeClient,
        calculation_mode: CalculationMode = CalculationMode.DISTRIBUTED_DP,
        poll_interval: float = 0.1,
        poll_attempts: int = 100,
        default_total_epsilon: float = 20.0,
        subject_id: str = "demo-analyst",
        epsilon_sum_ratio: float = 0.7,
        epsilon_count_ratio: float = 0.3,
        minimum_denominator: float = 10.0,
        record_cap: float = 5.0,
        max_records_per_household_per_day: int = 48,
        max_window_cap: float = 7_440.0,
        monitor: TaskMonitorStore | None = None,
        authorization_enforcement_enabled: bool = False,
    ):
        if not math.isclose(epsilon_sum_ratio + epsilon_count_ratio, 1.0, abs_tol=1e-12):
            raise ValueError("epsilon split ratios must sum to 1")
        self.session = session
        self.party_client = party_client
        self.compute_client = compute_client
        self.calculation_mode = calculation_mode
        self.poll_interval = poll_interval
        self.poll_attempts = poll_attempts
        self.subject_id = subject_id
        self.epsilon_sum_ratio = epsilon_sum_ratio
        self.epsilon_count_ratio = epsilon_count_ratio
        self.minimum_denominator = minimum_denominator
        self.record_cap = record_cap
        self.max_records_per_household_per_day = max_records_per_household_per_day
        self.max_window_cap = max_window_cap
        self.budget_service = PrivacyBudgetService(session, default_total_epsilon)
        self.monitor = monitor
        self.authorization_enforcement_enabled = authorization_enforcement_enabled
        self.authorization_service = AuthorizationService(session)
        self.security_audit = SecurityAuditService(session)

    def create_and_run(self, request: TaskCreateRequest, actor: DemoUser | None = None) -> Task:
        task_id = self._next_task_id()
        grant_reservation_active = False
        grant_operation = None
        is_dp = self.calculation_mode == CalculationMode.DISTRIBUTED_DP
        if self.authorization_enforcement_enabled:
            grant_operation = self.authorization_service.authorize_and_reserve(
                task_id,
                actor,
                request,
                reserve_budget=is_dp,
            )
            grant_reservation_active = is_dp and grant_operation.status == "RESERVED"
        sensitivity = self._sensitivity(request)
        task = Task(
            task_id=task_id,
            grant_id=request.grant_id,
            status=TaskStatus.CREATED.value,
            query_type=request.query_type.value,
            parties_json=json.dumps([party.value for party in request.parties]),
            start_time=self._naive(request.start_time),
            end_time=self._naive(request.end_time),
            group_by=request.group_by.value if request.group_by else None,
            calculation_mode=self.calculation_mode.value,
            epsilon=request.epsilon,
            privacy_unit="household",
            sensitivity_json=json.dumps(sensitivity) if sensitivity is not None else None,
            mechanism=(
                "distributed_vector_laplace"
                if is_dp and request.query_type == QueryType.TIME_SERIES
                else "distributed_laplace" if is_dp else "none"
            ),
            budget_status=(
                grant_operation.status
                if is_dp and grant_operation is not None
                else "PENDING" if is_dp else "NOT_REQUIRED"
            ),
            budget_before=(
                grant_operation.remaining_before
                if is_dp and grant_operation is not None
                else None
            ),
        )
        self.session.add(task)
        self.session.commit()
        if self.authorization_enforcement_enabled:
            self.security_audit.record(
                "TASK_CREATED_WITH_GRANT",
                actor,
                grant_id=request.grant_id,
                task_id=task.task_id,
                decision="CREATED",
            )
        task.started_at = utc_now()
        if self.monitor:
            self.monitor.create(
                task.task_id,
                [party.value for party in request.parties],
                task.started_at,
            )
        reservation_active = False
        rejected_error: InsufficientPrivacyBudgetError | None = None
        try:
            if is_dp:
                if self.authorization_enforcement_enabled:
                    # Authorized DP queries use the Grant ledger exclusively.
                    # Do not create a second subject/GLOBAL reservation.
                    reservation_active = False
                else:
                    operation = self.budget_service.reserve(
                        task.task_id,
                        self.subject_id,
                        "GLOBAL",
                        request.epsilon,
                    )
                    reservation_active = operation.status == "RESERVED"
                    task.budget_status = operation.status
                    task.budget_before = operation.budget_before
                    self.session.commit()

            if self.calculation_mode == CalculationMode.PLAIN:
                result = self._run_plain(task, request)
            else:
                result = self._run_shared(task, request, sensitivity)
            for party_id, warning in result.pop("_dataset_fallbacks", {}).items():
                self.security_audit.record(
                    "DATA_VERSION_FALLBACK",
                    actor,
                    task_id=task.task_id,
                    party_id=party_id,
                    decision="BASELINE",
                    reason=warning,
                )
            if is_dp:
                dataset_versions = result.get("dataset_versions", {})
                result = self._protected_dp_result(request.query_type, result, request.group_by)
                result["dataset_versions"] = dataset_versions
                if self.authorization_enforcement_enabled:
                    operation = self.authorization_service.consume(task.task_id)
                    grant_reservation_active = False
                else:
                    operation = self.budget_service.consume(task.task_id)
                    reservation_active = False
                task.budget_status = operation.status
                task.budget_after = operation.remaining_after if self.authorization_enforcement_enabled else operation.budget_after
            task.result_json = json.dumps(result)
            task.status = TaskStatus.COMPLETED.value
        except InsufficientPrivacyBudgetError as exc:
            if grant_reservation_active:
                operation = self.authorization_service.release(task.task_id)
                task.budget_status = operation.status
                task.budget_after = operation.remaining_after
                grant_reservation_active = False
            if is_dp and reservation_active:
                operation = self.budget_service.release(task.task_id)
                task.budget_status = operation.status
                task.budget_after = operation.budget_after
            task.status = TaskStatus.FAILED.value
            task.budget_status = "REJECTED"
            task.error = str(exc)
            rejected_error = exc
        except Exception as exc:
            if grant_reservation_active:
                operation = self.authorization_service.release(task.task_id)
                task.budget_status = operation.status
                task.budget_after = operation.remaining_after
                grant_reservation_active = False
            if is_dp and reservation_active:
                operation = self.budget_service.release(task.task_id)
                task.budget_status = operation.status
                task.budget_after = operation.budget_after
            task.status = TaskStatus.FAILED.value
            task.error = str(exc)
            logger.exception("%s failed", task.task_id)
        finally:
            task.completed_at = utc_now()
            task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
            self.session.commit()
            self._write_audit(task)
            if self.monitor:
                self.monitor.update(
                    task.task_id,
                    current_stage=task.status,
                    execution_time_ms=task.duration_ms,
                )
        if rejected_error is not None:
            raise rejected_error
        return task

    def _run_plain(self, task: Task, request: TaskCreateRequest) -> dict:
        self._status(task, TaskStatus.LOCAL_COMPUTING)
        responses = [
            self.party_client.statistics(
                party,
                StatisticsRequest(
                    task_id=task.task_id,
                    query_type=request.query_type,
                    start_time=request.start_time,
                    end_time=request.end_time,
                    group_by=request.group_by,
                ),
            )
            for party in request.parties
        ]
        self._status(task, TaskStatus.AGGREGATING)
        result = aggregate_results(request.query_type, responses)
        result["dataset_versions"] = {
            response.organization_id.value: response.dataset_version for response in responses
        }
        result["_dataset_fallbacks"] = {
            response.organization_id.value: response.dataset_fallback_warning
            for response in responses
            if response.dataset_fallback_warning
        }
        return result

    def _run_shared(self, task: Task, request: TaskCreateRequest, sensitivity) -> dict:
        registration = ComputeTaskRegistration(
            task_id=task.task_id,
            expected_parties=request.parties,
            query_type=request.query_type,
            group_by=request.group_by,
            bucket_count=self._bucket_count(request) if request.query_type == QueryType.TIME_SERIES else None,
        )
        self._status(task, TaskStatus.DISPATCHING)
        self.compute_client.register(1, registration)
        self.compute_client.register(2, registration)

        self._status(task, TaskStatus.LOCAL_COMPUTING)
        dp_parameters = self._dp_parameters(request, sensitivity)
        shared_request = SecretTaskRequest(
            task_id=task.task_id,
            query_type=request.query_type,
            start_time=request.start_time,
            end_time=request.end_time,
            group_by=request.group_by,
            expected_parties=request.parties,
            calculation_mode=self.calculation_mode,
            dp_parameters=dp_parameters,
        )
        acknowledgements = [
            self.party_client.dispatch_secret(party, shared_request)
            for party in request.parties
        ]

        self._status(task, TaskStatus.SHARING)
        self._status(task, TaskStatus.AGGREGATING)
        aggregate_1, aggregate_2 = self._wait_for_aggregates(task.task_id)
        if self.monitor:
            self.monitor.update(
                task.task_id,
                party_statuses={party.value: "SHARED" for party in request.parties},
                compute_node_statuses={"S1": "READY", "S2": "READY"},
                submitted_share_count=max(
                    aggregate_1.received_parties, aggregate_2.received_parties
                ),
            )
        self._status(task, TaskStatus.RECONSTRUCTING)
        result = self._reconstruct(aggregate_1, aggregate_2)
        result["dataset_versions"] = {
            ack.party_id.value: ack.dataset_version for ack in acknowledgements
        }
        result["_dataset_fallbacks"] = {
            ack.party_id.value: ack.dataset_fallback_warning
            for ack in acknowledgements
            if ack.dataset_fallback_warning
        }
        if self.calculation_mode != CalculationMode.DISTRIBUTED_DP:
            result["parties"] = [party.value for party in request.parties]
        logger.info("%s reconstruct completed", task.task_id)
        return result

    def _dp_parameters(self, request: TaskCreateRequest, sensitivity):
        if self.calculation_mode != CalculationMode.DISTRIBUTED_DP:
            return None
        return DistributedDPParameters(
            epsilon=request.epsilon,
            sum_epsilon=request.epsilon * self.epsilon_sum_ratio
            if request.query_type == QueryType.AVERAGE
            else None,
            count_epsilon=request.epsilon * self.epsilon_count_ratio
            if request.query_type == QueryType.AVERAGE
            else None,
            sum_sensitivity=sensitivity.get("sum")
            if isinstance(sensitivity, dict)
            else sensitivity
            if request.query_type in (QueryType.SUM, QueryType.TIME_SERIES)
            else None,
            count_sensitivity=1.0,
            minimum_denominator=self.minimum_denominator,
            participants=len(request.parties),
        )

    def _sensitivity(self, request: TaskCreateRequest):
        if self.calculation_mode != CalculationMode.DISTRIBUTED_DP:
            return None
        if request.query_type == QueryType.COUNT:
            return 1.0
        days = max(
            1,
            math.ceil(
                (self._naive(request.end_time) - self._naive(request.start_time)).total_seconds()
                / 86_400
            ),
        )
        window_cap = min(
            self.record_cap * self.max_records_per_household_per_day * days,
            self.max_window_cap,
        )
        if request.query_type in (QueryType.SUM, QueryType.TIME_SERIES):
            return window_cap
        if request.query_type == QueryType.AVERAGE:
            return {"sum": window_cap, "count": 1.0}
        return window_cap

    def _protected_dp_result(self, query_type: QueryType, reconstructed: dict, group_by=None) -> dict:
        if query_type == QueryType.SUM:
            return {"value": reconstructed["value"]}
        if query_type == QueryType.COUNT:
            return {"value": max(0.0, reconstructed["value"])}
        if query_type == QueryType.TIME_SERIES:
            buckets = [
                {"timestamp": item["timestamp"], "value": max(float(item["sum"]), 0.0)}
                for item in reconstructed.get("series", [])
            ]
            return {
                "group_by": group_by.value if group_by else None,
                "bucket_count": len(buckets),
                "buckets": buckets,
                "metrics": self._load_metrics(buckets),
            }
        noisy_count = reconstructed["count"]
        if noisy_count <= 0 or noisy_count < self.minimum_denominator:
            raise ValueError("noisy count is below the protected minimum denominator")
        return {"value": reconstructed["sum"] / max(noisy_count, self.minimum_denominator)}

    @staticmethod
    def _load_metrics(buckets: list[dict]) -> dict:
        if not buckets:
            return {
                "peak_value": None,
                "peak_timestamp": None,
                "valley_value": None,
                "valley_timestamp": None,
                "peak_valley_difference": None,
                "average_load": None,
                "load_factor": None,
            }
        peak = max(buckets, key=lambda item: item["value"])
        valley = min(buckets, key=lambda item: item["value"])
        average = sum(item["value"] for item in buckets) / len(buckets)
        peak_value = peak["value"]
        return {
            "peak_value": peak_value,
            "peak_timestamp": peak["timestamp"],
            "valley_value": valley["value"],
            "valley_timestamp": valley["timestamp"],
            "peak_valley_difference": peak_value - valley["value"],
            "average_load": average,
            "load_factor": average / peak_value if peak_value > 0 else None,
        }

    @classmethod
    def _bucket_count(cls, request: TaskCreateRequest) -> int:
        return len(
            generate_time_buckets(
                cls._naive(request.start_time), cls._naive(request.end_time), request.group_by
            )
        )

    def _wait_for_aggregates(self, task_id: str):
        for _ in range(self.poll_attempts):
            first = self.compute_client.aggregate(1, task_id)
            second = self.compute_client.aggregate(2, task_id)
            if first.status == ComputeTaskStatus.FAILED or second.status == ComputeTaskStatus.FAILED:
                raise RuntimeError("compute aggregation failed")
            if first.status == ComputeTaskStatus.READY and second.status == ComputeTaskStatus.READY:
                return first, second
            time.sleep(self.poll_interval)
        raise TimeoutError("timed out waiting for aggregate shares")

    @staticmethod
    def _reconstruct(first, second) -> dict:
        if first.share_index != 1 or second.share_index != 2:
            raise ValueError("aggregate share indexes are invalid")
        if (
            first.query_type != second.query_type
            or first.scale != second.scale
            or first.count_scale != second.count_scale
        ):
            raise ValueError("aggregate metadata does not match")
        if first.payload is None or second.payload is None or first.scale is None:
            raise ValueError("aggregate payload is missing")

        query_type = first.query_type
        if query_type == QueryType.SUM:
            total = decode(reconstruct_secret(first.payload.value, second.payload.value), first.scale)
            return {"sum": total, "value": total}
        if query_type == QueryType.COUNT:
            count_value = reconstruct_secret(first.payload.value, second.payload.value)
            count = decode(count_value, first.scale) if first.scale != 1 else count_value
            return {"count": count, "value": count}
        if query_type == QueryType.AVERAGE:
            total = decode(reconstruct_secret(first.payload.sum, second.payload.sum), first.scale)
            count_value = reconstruct_secret(first.payload.count, second.payload.count)
            count = decode(count_value, first.count_scale) if first.count_scale != 1 else count_value
            return {"sum": total, "count": count, "value": total / count if count else None}

        left = {item.timestamp: item.value for item in first.payload.buckets or []}
        right = {item.timestamp: item.value for item in second.payload.buckets or []}
        if set(left) != set(right):
            raise ValueError("time-series aggregate buckets do not match")
        series = [
            {
                "timestamp": timestamp.isoformat(),
                "sum": decode(reconstruct_secret(left[timestamp], right[timestamp]), first.scale),
            }
            for timestamp in sorted(left)
        ]
        return {"sum": sum(item["sum"] for item in series), "series": series}

    def _write_audit(self, task: Task) -> None:
        audit = self.session.get(TaskAudit, task.task_id) or TaskAudit(
            task_id=task.task_id, created_at=task.created_at
        )
        audit.query_type = task.query_type
        audit.group_by = task.group_by
        result = json.loads(task.result_json or "{}")
        audit.bucket_count = result.get("bucket_count")
        audit.parties_json = task.parties_json
        audit.epsilon = task.epsilon
        audit.sensitivity_json = task.sensitivity_json
        audit.mechanism = task.mechanism
        audit.privacy_unit = task.privacy_unit
        audit.calculation_mode = task.calculation_mode
        audit.budget_before = task.budget_before
        audit.budget_after = task.budget_after
        audit.execution_time_ms = task.duration_ms
        audit.status = task.status
        audit.dataset_versions_json = json.dumps(result.get("dataset_versions", {}))
        self.session.add(audit)
        self.session.commit()

    def _status(self, task: Task, status: TaskStatus) -> None:
        task.status = status.value
        self.session.commit()
        if self.monitor:
            self.monitor.update(task.task_id, current_stage=status.value)
        logger.info("%s stage %s", task.task_id, status.value)

    def get(self, task_id: str) -> Task | None:
        return self.session.get(Task, task_id)

    def list_recent(self, limit: int = 10) -> list[Task]:
        return list(
            self.session.scalars(
                select(Task).order_by(Task.created_at.desc()).limit(limit)
            )
        )

    @staticmethod
    def to_response(task: Task) -> TaskResponse:
        return TaskResponse(
            task_id=task.task_id,
            grant_id=task.grant_id,
            status=task.status,
            query_type=task.query_type,
            parties=json.loads(task.parties_json),
            start_time=task.start_time,
            end_time=task.end_time,
            group_by=task.group_by,
            calculation_mode=task.calculation_mode,
            epsilon=task.epsilon,
            privacy_unit=task.privacy_unit,
            sensitivity=json.loads(task.sensitivity_json) if task.sensitivity_json else None,
            budget_status=task.budget_status,
            created_at=task.created_at,
            updated_at=task.updated_at,
            duration_ms=task.duration_ms,
            error=task.error,
        )

    @staticmethod
    def to_result(task: Task) -> TaskResultResponse:
        privacy = None
        if task.calculation_mode == CalculationMode.DISTRIBUTED_DP:
            privacy = {
                "epsilon": task.epsilon,
                "privacy_unit": task.privacy_unit,
                "sensitivity": json.loads(task.sensitivity_json),
                "mechanism": task.mechanism,
            }
            if task.query_type == QueryType.TIME_SERIES:
                privacy["post_processing"] = ["non_negative_clamp", "load_metrics"]
        return TaskResultResponse(
            task_id=task.task_id,
            status=task.status,
            query_type=task.query_type,
            calculation_mode=task.calculation_mode,
            privacy=privacy,
            result=json.loads(task.result_json or "{}"),
        )

    def _next_task_id(self) -> str:
        count = self.session.scalar(select(func.count()).select_from(Task)) or 0
        while True:
            task_id = f"TASK-{count + 1:06d}"
            if self.session.get(Task, task_id) is None:
                return task_id
            count += 1

    @staticmethod
    def _naive(value: datetime) -> datetime:
        return value.replace(tzinfo=None) if value.tzinfo else value
