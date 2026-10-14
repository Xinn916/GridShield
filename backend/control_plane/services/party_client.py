from datetime import datetime
from time import perf_counter
from typing import Any

import httpx

from common.enums import OrganizationId
from common.exceptions import UpstreamServiceError
from common.schemas import PartyTaskAck, SecretTaskRequest, StatisticsRequest, StatisticsResponse
from common.performance import (
    BenchmarkPartyRequest, BenchmarkPlainResponse, BenchmarkSharedResponse,
    PerformanceCommunicationEvent, PERFORMANCE_HEADER,
)


class PartyClient:
    def __init__(self, party_urls: dict[OrganizationId, str], timeout: float = 30.0, internal_token: str = ""):
        self.party_urls = party_urls
        self.timeout = timeout
        self.internal_token = internal_token

    def benchmark_plain(self, party: OrganizationId, request: BenchmarkPartyRequest):
        return self._benchmark_request(party, "/internal/benchmark/statistics", request, BenchmarkPlainResponse)

    def benchmark_shared(self, party: OrganizationId, request: BenchmarkPartyRequest):
        return self._benchmark_request(party, "/internal/benchmark/tasks", request, BenchmarkSharedResponse)

    def _benchmark_request(self, party, path, request, response_model):
        body = request.model_dump_json().encode("utf-8")
        started_at = datetime.utcnow()
        started = perf_counter()
        try:
            response = httpx.post(
                f"{self.party_urls[party]}{path}", content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Token": self.internal_token,
                    PERFORMANCE_HEADER: request.test_id,
                }, timeout=self.timeout,
            )
            response.raise_for_status()
            parsed = response_model.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"{party.value} Benchmark request failed: {exc}") from exc
        completed_at = datetime.utcnow()
        event = PerformanceCommunicationEvent(
            test_id=request.test_id, source_node="control",
            target_node=f"party-{party.value[-1].lower()}", operation=path.rsplit("/", 1)[-1],
            request_bytes=len(body), response_bytes=len(response.content),
            total_bytes=len(body) + len(response.content),
            duration_ms=(perf_counter() - started) * 1000,
            started_at=started_at, completed_at=completed_at,
        )
        return parsed, event

    def statistics(self, party: OrganizationId, request: StatisticsRequest) -> StatisticsResponse:
        try:
            response = httpx.post(
                f"{self.party_urls[party]}/internal/statistics",
                json=request.model_dump(mode="json"),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return StatisticsResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"{party.value} request failed: {exc}") from exc

    def dispatch_secret(self, party: OrganizationId, request: SecretTaskRequest) -> PartyTaskAck:
        try:
            response = httpx.post(
                f"{self.party_urls[party]}/internal/tasks",
                json=request.model_dump(mode="json"),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return PartyTaskAck.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"{party.value} secret task failed: {exc}") from exc

    def describe(self, party: OrganizationId) -> dict[str, Any]:
        base_url = self.party_urls[party]
        try:
            health = httpx.get(f"{base_url}/health", timeout=self.timeout)
            metadata = httpx.get(f"{base_url}/internal/metadata", timeout=self.timeout)
            health.raise_for_status()
            metadata.raise_for_status()
            return {
                "organization_id": party.value,
                "status": health.json().get("status", "ok"),
                "url": base_url,
                **metadata.json(),
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "organization_id": party.value,
                "status": "offline",
                "url": base_url,
                "error": str(exc),
            }
