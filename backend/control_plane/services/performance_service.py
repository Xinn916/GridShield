import json
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.enums import CalculationMode, ComputeTaskStatus, QueryType
from common.performance import (
    BenchmarkPartyRequest,
    BenchmarkTestCreate,
    PerformanceCommunicationEvent,
    PerformancePhase,
    PerformanceSummary,
    PerformanceTestList,
    PerformanceTestResponse,
)
from common.schemas import ComputeTaskRegistration, DistributedDPParameters
from common.time_buckets import generate_time_buckets
from control_plane.models.performance import PerformanceCommunicationEventModel, PerformanceTest
from control_plane.models.task import utc_now
from control_plane.services.aggregation import aggregate_results
from control_plane.services.compute_client import ComputeClient
from control_plane.services.party_client import PartyClient
from control_plane.services.task_service import TaskService


class PerformanceNotFoundError(LookupError):
    pass


class PerformanceService:
    def __init__(
        self, session: Session, party_client: PartyClient, compute_client: ComputeClient,
        *, poll_interval: float = 0.1, poll_attempts: int = 100,
        record_cap: float = 5.0, max_records_per_household_per_day: int = 48,
        max_window_cap: float = 7440.0, minimum_denominator: float = 10.0,
        epsilon_sum_ratio: float = 0.7, epsilon_count_ratio: float = 0.3,
    ):
        self.session = session
        self.party_client = party_client
        self.compute_client = compute_client
        self.poll_interval = poll_interval
        self.poll_attempts = poll_attempts
        self.record_cap = record_cap
        self.max_records_per_household_per_day = max_records_per_household_per_day
        self.max_window_cap = max_window_cap
        self.minimum_denominator = minimum_denominator
        self.epsilon_sum_ratio = epsilon_sum_ratio
        self.epsilon_count_ratio = epsilon_count_ratio

    def create_and_run(self, request: BenchmarkTestCreate, creator_user_id: str) -> PerformanceTest:
        test_id = f"PERF-{uuid.uuid4()}"
        task_id = f"TASK-PERF-{uuid.uuid4().hex}"
        item = PerformanceTest(
            id=test_id, creator_user_id=creator_user_id, benchmark_id=request.benchmark_id,
            parties_json=json.dumps([party.value for party in request.parties]),
            query_type=request.query_type.value, mode=request.mode.value,
            epsilon=request.epsilon, interval=request.interval.value if request.interval else None,
            status="RUNNING", started_at=utc_now(), phases_json="[]",
        )
        self.session.add(item)
        self.session.commit()
        started = time.perf_counter()
        phases: list[PerformancePhase] = []
        events: list[PerformanceCommunicationEvent] = []
        try:
            validation_started = time.perf_counter()
            party_request = self._party_request(request, test_id, task_id)
            phases.append(self._phase("parameter_validation", "参数与模式校验", validation_started))
            if request.mode == CalculationMode.PLAIN:
                self._run_plain(party_request, events, phases)
            else:
                self._run_shared(party_request, events, phases)
            # The reconstructed aggregate is intentionally discarded before persistence/response.
            item.status = "COMPLETED"
        except Exception as exc:
            item.status = "FAILED"
            item.error = self._safe_error(exc)
        finally:
            item.completed_at = utc_now()
            item.total_duration_ms = (time.perf_counter() - started) * 1000
            item.phases_json = json.dumps([phase.model_dump() for phase in phases])
            item.total_communication_bytes = sum(event.total_bytes for event in events)
            item.average_response_ms = (
                sum(event.duration_ms for event in events) / len(events) if events else None
            )
            nodes = {"control"}
            for event in events:
                nodes.update((event.source_node, event.target_node))
                self.session.add(PerformanceCommunicationEventModel(**event.model_dump()))
            item.participant_nodes = len(nodes)
            self.session.commit()
        return item

    def _party_request(self, request, test_id, task_id):
        start_time = datetime(2026, 1, 1)
        end_time = start_time + timedelta(days=7)
        return BenchmarkPartyRequest(
            **request.model_dump(), test_id=test_id, task_id=task_id,
            start_time=start_time, end_time=end_time,
            dp_parameters=self._dp_parameters(request, start_time, end_time),
        )

    def _dp_parameters(self, request, start_time, end_time):
        if request.mode != CalculationMode.DISTRIBUTED_DP:
            return None
        import math
        days = max(1, math.ceil((end_time - start_time).total_seconds() / 86400))
        sensitivity = min(
            self.record_cap * self.max_records_per_household_per_day * days,
            self.max_window_cap,
        )
        return DistributedDPParameters(
            epsilon=request.epsilon,
            sum_epsilon=request.epsilon * self.epsilon_sum_ratio if request.query_type == QueryType.AVERAGE else None,
            count_epsilon=request.epsilon * self.epsilon_count_ratio if request.query_type == QueryType.AVERAGE else None,
            sum_sensitivity=sensitivity if request.query_type in {QueryType.SUM, QueryType.AVERAGE, QueryType.TIME_SERIES} else None,
            count_sensitivity=1.0, minimum_denominator=self.minimum_denominator,
            participants=len(request.parties),
        )

    def _run_plain(self, request, events, phases):
        responses = []
        for party in request.parties:
            response, event = self.party_client.benchmark_plain(party, request)
            responses.append(response.statistics)
            events.append(event)
        # Reuse the production PLAIN aggregation and discard its return value.
        aggregate_started = time.perf_counter()
        aggregate_results(request.query_type, responses)
        phases.append(self._phase("result_reconstruction", "结果汇总", aggregate_started))

    def _run_shared(self, request, events, phases):
        registration = ComputeTaskRegistration(
            task_id=request.task_id, expected_parties=request.parties,
            query_type=request.query_type, group_by=request.interval,
            bucket_count=self._bucket_count(request) if request.query_type == QueryType.TIME_SERIES else None,
        )
        for index in (1, 2):
            _, event = self.compute_client.benchmark_register(index, registration, request.test_id)
            events.append(event)
        sharing_duration = 0.0
        for party in request.parties:
            response, event = self.party_client.benchmark_shared(party, request)
            events.append(event)
            events.extend(response.performance_events)
            sharing_duration += response.share_generation_duration_ms
        phases.extend([
            PerformancePhase(key="share_generation", label="秘密份额生成", duration_ms=sharing_duration),
            PerformancePhase(
                key="share_transfer", label="份额传输",
                duration_ms=sum(event.duration_ms for event in events if event.operation == "submit_share"),
            ),
        ])
        aggregation_started = time.perf_counter()
        first, second = self._wait_for_aggregates(request.task_id, request.test_id, events)
        phases.append(self._phase("secure_aggregation", "安全聚合计算", aggregation_started))
        reconstruction_started = time.perf_counter()
        TaskService._reconstruct(first, second)
        phases.append(self._phase("result_reconstruction", "结果重构", reconstruction_started))

    def _wait_for_aggregates(self, task_id, test_id, events):
        for _ in range(self.poll_attempts):
            first, event_1 = self.compute_client.benchmark_aggregate(1, task_id, test_id)
            second, event_2 = self.compute_client.benchmark_aggregate(2, task_id, test_id)
            events.extend((event_1, event_2))
            if first.status == ComputeTaskStatus.FAILED or second.status == ComputeTaskStatus.FAILED:
                raise RuntimeError("compute aggregation failed")
            if first.status == ComputeTaskStatus.READY and second.status == ComputeTaskStatus.READY:
                return first, second
            time.sleep(self.poll_interval)
        raise TimeoutError("timed out waiting for aggregate shares")

    @staticmethod
    def _phase(key, label, started):
        return PerformancePhase(key=key, label=label, duration_ms=(time.perf_counter() - started) * 1000)

    def _bucket_count(self, request):
        return len(generate_time_buckets(request.start_time, request.end_time, request.interval))

    @staticmethod
    def _safe_error(exc):
        text = str(exc).strip()
        for party in OrganizationId:
            if party.value in text:
                return f"{party.value} Benchmark 数据或服务不可用"
        lowered = text.lower()
        if "compute-s1" in lowered or "compute s1" in lowered:
            return "Compute S1 不可达或计算失败"
        if "compute-s2" in lowered or "compute s2" in lowered:
            return "Compute S2 不可达或计算失败"
        if "timed out" in lowered or "timeout" in lowered:
            return "Benchmark 执行超时，请稍后重试"
        return "Benchmark 执行失败，请稍后重试"

    def get(self, test_id: str, creator_user_id: str | None = None) -> PerformanceTest:
        item = self.session.get(PerformanceTest, test_id)
        if item is None or (creator_user_id is not None and item.creator_user_id != creator_user_id):
            raise PerformanceNotFoundError("Performance test not found")
        return item

    def list(self, limit: int, offset: int, creator_user_id: str | None = None) -> PerformanceTestList:
        condition = PerformanceTest.creator_user_id == creator_user_id if creator_user_id else None
        count_query = select(func.count()).select_from(PerformanceTest)
        item_query = select(PerformanceTest).order_by(PerformanceTest.created_at.desc())
        if condition is not None:
            count_query = count_query.where(condition)
            item_query = item_query.where(condition)
        total = self.session.scalar(count_query) or 0
        items = list(self.session.scalars(
            item_query.limit(limit).offset(offset)
        ))
        return PerformanceTestList(
            items=[self.to_response(item) for item in items], total=total, limit=limit, offset=offset
        )

    def to_response(self, item: PerformanceTest) -> PerformanceTestResponse:
        events = list(self.session.scalars(
            select(PerformanceCommunicationEventModel)
            .where(PerformanceCommunicationEventModel.test_id == item.id)
            .order_by(PerformanceCommunicationEventModel.id)
        ))
        return PerformanceTestResponse(
            id=item.id, benchmark_id=item.benchmark_id,
            parties=json.loads(item.parties_json), query_type=item.query_type, mode=item.mode,
            epsilon=item.epsilon, interval=item.interval, status=item.status,
            summary=PerformanceSummary(
                total_duration_ms=item.total_duration_ms,
                communication_bytes=item.total_communication_bytes,
                participant_nodes=item.participant_nodes, total_nodes=item.total_nodes,
                average_response_ms=item.average_response_ms,
            ),
            phases=[PerformancePhase.model_validate(value) for value in json.loads(item.phases_json)],
            links=[PerformanceCommunicationEvent.model_validate({
                "test_id": event.test_id, "source_node": event.source_node,
                "target_node": event.target_node, "operation": event.operation,
                "request_bytes": event.request_bytes, "response_bytes": event.response_bytes,
                "total_bytes": event.total_bytes, "duration_ms": event.duration_ms,
                "started_at": event.started_at, "completed_at": event.completed_at,
            }) for event in events],
            error=item.error, created_at=item.created_at,
            started_at=item.started_at, completed_at=item.completed_at,
        )
