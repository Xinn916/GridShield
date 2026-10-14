from datetime import datetime
from time import perf_counter
import httpx

from common.exceptions import UpstreamServiceError
from common.schemas import ComputeTaskRegistration, ShareAggregateResponse
from common.performance import PerformanceCommunicationEvent, PERFORMANCE_HEADER


class ComputeClient:
    def __init__(self, compute_urls: dict[int, str], timeout: float = 30.0, internal_token: str = ""):
        self.compute_urls = compute_urls
        self.timeout = timeout
        self.internal_token = internal_token

    def benchmark_register(self, share_index, request, test_id):
        return self._benchmark_request(
            "POST", f"{self.compute_urls[share_index]}/internal/benchmark/tasks/register",
            test_id, f"compute-s{share_index}", request.model_dump_json().encode("utf-8"),
        )

    def benchmark_aggregate(self, share_index, task_id, test_id):
        return self._benchmark_request(
            "GET", f"{self.compute_urls[share_index]}/internal/benchmark/tasks/{task_id}/aggregate",
            test_id, f"compute-s{share_index}", None,
        )

    def _benchmark_request(self, method, url, test_id, target, body):
        started_at = datetime.utcnow()
        started = perf_counter()
        try:
            response = httpx.request(
                method, url, content=body,
                headers={"Content-Type": "application/json", "X-Internal-Token": self.internal_token, PERFORMANCE_HEADER: test_id},
                timeout=self.timeout,
            )
            response.raise_for_status()
            parsed = ShareAggregateResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"compute Benchmark request failed: {exc}") from exc
        completed_at = datetime.utcnow()
        request_bytes = len(body or b"")
        return parsed, PerformanceCommunicationEvent(
            test_id=test_id, source_node="control", target_node=target,
            operation="register" if method == "POST" else "aggregate",
            request_bytes=request_bytes, response_bytes=len(response.content),
            total_bytes=request_bytes + len(response.content),
            duration_ms=(perf_counter() - started) * 1000,
            started_at=started_at, completed_at=completed_at,
        )

    def register(self, share_index: int, request: ComputeTaskRegistration) -> ShareAggregateResponse:
        return self._request(
            "POST",
            f"{self.compute_urls[share_index]}/internal/tasks/register",
            request.model_dump(mode="json"),
        )

    def aggregate(self, share_index: int, task_id: str) -> ShareAggregateResponse:
        return self._request(
            "GET", f"{self.compute_urls[share_index]}/internal/tasks/{task_id}/aggregate"
        )

    def _request(self, method: str, url: str, payload: dict | None = None) -> ShareAggregateResponse:
        try:
            response = httpx.request(method, url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return ShareAggregateResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"compute request failed: {exc}") from exc
