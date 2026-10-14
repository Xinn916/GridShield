import time
from datetime import datetime, timezone

import httpx

from common.schemas import ServiceHealthResponse, SystemHealthResponse
from control_plane.config import ControlSettings


class SystemHealthService:
    def __init__(
        self,
        settings: ControlSettings,
        client: httpx.Client | None = None,
    ):
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.request_timeout)

    def check_all(self) -> SystemHealthResponse:
        endpoints = [
            ("control", "总控服务", f"http://127.0.0.1:{self.settings.port}", "/health"),
            ("frontend", "前端网关 Nginx", self.settings.frontend_gateway_url, "/healthz"),
            ("party-a", "园区 A", self.settings.party_urls[next(p for p in self.settings.party_urls if p.value == "ORG_A")], "/health"),
            ("party-b", "园区 B", self.settings.party_urls[next(p for p in self.settings.party_urls if p.value == "ORG_B")], "/health"),
            ("party-c", "园区 C", self.settings.party_urls[next(p for p in self.settings.party_urls if p.value == "ORG_C")], "/health"),
            ("compute-s1", "计算节点 S1", self.settings.compute_urls[1], "/health"),
            ("compute-s2", "计算节点 S2", self.settings.compute_urls[2], "/health"),
        ]
        return SystemHealthResponse(
            services=[self._check(service_id, name, endpoint, path) for service_id, name, endpoint, path in endpoints],
            checked_at=datetime.now(timezone.utc),
        )

    def _check(self, service_id: str, name: str, endpoint: str, path: str = "/health") -> ServiceHealthResponse:
        started = time.perf_counter()
        try:
            response = self.client.get(f"{endpoint.rstrip('/')}{path}")
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            return ServiceHealthResponse(
                service_id=service_id,
                name=name,
                endpoint=endpoint,
                online=payload.get("status", "ok") == "ok",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                service=payload.get("service") or ("nginx" if service_id == "frontend" else None),
                version=payload.get("version"),
            )
        except Exception as exc:
            return ServiceHealthResponse(
                service_id=service_id,
                name=name,
                endpoint=endpoint,
                online=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error=str(exc),
            )
