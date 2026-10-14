import logging
import math
from threading import RLock
from typing import Callable

import httpx

from common.distributed_noise import DistributedLaplaceNoise
from common.enums import CalculationMode, QueryType
from common.exceptions import UpstreamServiceError
from common.fixed_point import SCALE, encode
from common.schemas import (
    PartyTaskAck,
    SecretTaskRequest,
    ShareBucket,
    SharePayload,
    ShareSubmission,
    StatisticsRequest,
)
from common.secret_sharing import split_secret
from party_node.query_executor import QueryExecutor


logger = logging.getLogger(__name__)
ShareSubmitter = Callable[[int, ShareSubmission], None]


class ShareService:
    def __init__(
        self,
        executor: QueryExecutor,
        compute_urls: dict[int, str],
        timeout: float = 30.0,
        submitter: ShareSubmitter | None = None,
        noise_generator: DistributedLaplaceNoise | None = None,
    ):
        self.executor = executor
        self.compute_urls = compute_urls
        self.timeout = timeout
        self._custom_submitter = submitter
        self.submitter = submitter or self._submit_http
        self.noise_generator = noise_generator or DistributedLaplaceNoise()
        self._cache: dict[str, tuple[dict, tuple[ShareSubmission, ShareSubmission], str, str | None]] = {}
        self._lock = RLock()

    def process(self, request: SecretTaskRequest) -> PartyTaskAck:
        acknowledgement, _, _, _ = self.process_measured(request)
        return acknowledgement

    def process_measured(
        self, request: SecretTaskRequest, *, test_id: str | None = None, internal_token: str | None = None
    ) -> tuple[PartyTaskAck, float, float, list]:
        from datetime import datetime
        from time import perf_counter
        from common.performance import PerformanceCommunicationEvent

        signature = request.model_dump(mode="json")
        local_duration_ms = 0.0
        share_generation_duration_ms = 0.0
        with self._lock:
            cached = self._cache.get(request.task_id)
            if cached is not None:
                if cached[0] != signature:
                    raise ValueError("task_id was already used with different parameters")
                submissions = cached[1]
                dataset_version = cached[2]
                fallback_warning = cached[3]
            else:
                local_started = perf_counter()
                local = self.executor.execute(
                    StatisticsRequest(
                        task_id=request.task_id,
                        query_type=request.query_type,
                        start_time=request.start_time,
                        end_time=request.end_time,
                        group_by=request.group_by,
                    )
                )
                local_duration_ms = (perf_counter() - local_started) * 1000
                share_started = perf_counter()
                submissions = self._build_submissions(request, local)
                share_generation_duration_ms = (perf_counter() - share_started) * 1000
                dataset_version = local.dataset_version
                fallback_warning = local.dataset_fallback_warning
                self._cache[request.task_id] = (signature, submissions, dataset_version, fallback_warning)

        events = []
        for index, submission in ((1, submissions[0]), (2, submissions[1])):
            if test_id is None:
                self.submitter(index, submission)
                continue
            payload = submission.model_dump_json().encode("utf-8")
            started_at = datetime.utcnow()
            started = perf_counter()
            if self._custom_submitter is not None:
                self._custom_submitter(index, submission)
                response_content = b""
            else:
                response_content = self._submit_http(
                    index, submission, test_id=test_id, internal_token=internal_token, return_content=True
                )
            completed_at = datetime.utcnow()
            events.append(PerformanceCommunicationEvent(
                test_id=test_id,
                source_node=f"party-{self.executor.organization_id.value[-1].lower()}",
                target_node=f"compute-s{index}",
                operation="submit_share",
                request_bytes=len(payload), response_bytes=len(response_content),
                total_bytes=len(payload) + len(response_content),
                duration_ms=(perf_counter() - started) * 1000,
                started_at=started_at, completed_at=completed_at,
            ))
        logger.info("%s %s shares submitted", request.task_id, self.executor.organization_id.value)
        acknowledgement = PartyTaskAck(
            task_id=request.task_id,
            party_id=self.executor.organization_id,
            status="SHARED",
            bucket_count=len(submissions[0].payload.buckets or [])
            if request.query_type == QueryType.TIME_SERIES
            else None,
            dataset_version=dataset_version,
            dataset_fallback_warning=fallback_warning,
        )
        return acknowledgement, local_duration_ms, share_generation_duration_ms, events

    def _build_submissions(self, request: SecretTaskRequest, local) -> tuple[ShareSubmission, ShareSubmission]:
        payload_1: SharePayload
        payload_2: SharePayload
        scale = SCALE
        count_scale = 1
        if request.calculation_mode == CalculationMode.DISTRIBUTED_DP:
            payload_1, payload_2, scale, count_scale = self._build_dp_payloads(request, local)
        elif request.query_type == QueryType.SUM:
            first, second = split_secret(encode(local.sum))
            payload_1, payload_2 = SharePayload(value=first), SharePayload(value=second)
        elif request.query_type == QueryType.COUNT:
            scale = 1
            first, second = split_secret(local.count)
            payload_1, payload_2 = SharePayload(value=first), SharePayload(value=second)
        elif request.query_type == QueryType.AVERAGE:
            sum_first, sum_second = split_secret(encode(local.sum))
            count_first, count_second = split_secret(local.count)
            payload_1 = SharePayload(sum=sum_first, count=count_first)
            payload_2 = SharePayload(sum=sum_second, count=count_second)
        else:
            buckets_1: list[ShareBucket] = []
            buckets_2: list[ShareBucket] = []
            for point in local.series or []:
                first, second = split_secret(encode(point["sum"]))
                buckets_1.append(ShareBucket(timestamp=point["timestamp"], value=first))
                buckets_2.append(ShareBucket(timestamp=point["timestamp"], value=second))
            payload_1 = SharePayload(buckets=buckets_1)
            payload_2 = SharePayload(buckets=buckets_2)

        common = {
            "task_id": request.task_id,
            "party_id": self.executor.organization_id,
            "expected_parties": request.expected_parties,
            "query_type": request.query_type,
            "scale": scale,
            "count_scale": count_scale,
            "group_by": request.group_by,
            "bucket_count": len(local.series or []) if request.query_type == QueryType.TIME_SERIES else None,
        }
        return (
            ShareSubmission(share_index=1, payload=payload_1, **common),
            ShareSubmission(share_index=2, payload=payload_2, **common),
        )

    def _build_dp_payloads(
        self, request: SecretTaskRequest, local
    ) -> tuple[SharePayload, SharePayload, int, int]:
        parameters = request.dp_parameters
        if parameters is None:
            raise ValueError("dp_parameters are required")
        expected_cap = self.executor.clipper.window_cap(
            self.executor._naive(request.start_time), self.executor._naive(request.end_time)
        )
        if request.query_type in (QueryType.SUM, QueryType.AVERAGE, QueryType.TIME_SERIES) and not math.isclose(
            parameters.sum_sensitivity, expected_cap, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("sum_sensitivity does not match the configured window_cap")
        if not math.isclose(parameters.count_sensitivity, 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("COUNT sensitivity must be 1")

        if request.query_type == QueryType.SUM:
            noise = self.noise_generator.partial_noise(
                parameters.sum_sensitivity, parameters.epsilon, parameters.participants
            )
            first, second = split_secret(encode(local.sum + noise))
            return SharePayload(value=first), SharePayload(value=second), SCALE, 1
        if request.query_type == QueryType.COUNT:
            noise = self.noise_generator.partial_noise(
                parameters.count_sensitivity, parameters.epsilon, parameters.participants
            )
            first, second = split_secret(encode(local.count + noise))
            return SharePayload(value=first), SharePayload(value=second), SCALE, SCALE

        if request.query_type == QueryType.TIME_SERIES:
            first_buckets: list[ShareBucket] = []
            second_buckets: list[ShareBucket] = []
            # Vector DP uses one independent Gamma-difference draw per aligned bucket.
            for point in local.series or []:
                noise = self.noise_generator.partial_noise(
                    parameters.sum_sensitivity, parameters.epsilon, parameters.participants
                )
                first, second = split_secret(encode(point["sum"] + noise))
                first_buckets.append(ShareBucket(timestamp=point["timestamp"], value=first))
                second_buckets.append(ShareBucket(timestamp=point["timestamp"], value=second))
            return SharePayload(buckets=first_buckets), SharePayload(buckets=second_buckets), SCALE, 1

        sum_noise = self.noise_generator.partial_noise(
            parameters.sum_sensitivity, parameters.sum_epsilon, parameters.participants
        )
        count_noise = self.noise_generator.partial_noise(
            parameters.count_sensitivity, parameters.count_epsilon, parameters.participants
        )
        sum_first, sum_second = split_secret(encode(local.sum + sum_noise))
        count_first, count_second = split_secret(encode(local.count + count_noise))
        return (
            SharePayload(sum=sum_first, count=count_first),
            SharePayload(sum=sum_second, count=count_second),
            SCALE,
            SCALE,
        )

    def _submit_http(
        self, share_index: int, submission: ShareSubmission, *, test_id: str | None = None,
        internal_token: str | None = None, return_content: bool = False,
    ):
        try:
            headers = {}
            if test_id:
                headers["X-PrivGrid-Performance-Test-ID"] = test_id
            if internal_token:
                headers["X-Internal-Token"] = internal_token
            url = f"{self.compute_urls[share_index]}{'/internal/benchmark/shares' if test_id else '/internal/shares'}"
            if test_id:
                body = submission.model_dump_json().encode("utf-8")
                headers["Content-Type"] = "application/json"
                response = httpx.post(url, content=body, headers=headers, timeout=self.timeout)
            else:
                response = httpx.post(
                    url, json=submission.model_dump(mode="json"), headers=headers, timeout=self.timeout
                )
            response.raise_for_status()
            return response.content if return_content else None
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"compute S{share_index} submission failed: {exc}") from exc
