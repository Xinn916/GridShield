import hmac
from fastapi import FastAPI, Header, HTTPException

from common.schemas import (
    ComputeTaskRegistration,
    HealthResponse,
    ShareAggregateResponse,
    ShareReceipt,
    ShareSubmission,
)
from common.performance import PERFORMANCE_HEADER
from compute_node.config import ComputeSettings, get_settings
from compute_node.share_store import ShareStore, ShareStoreError


def create_app(
    settings: ComputeSettings | None = None, share_store: ShareStore | None = None
) -> FastAPI:
    settings = settings or get_settings()
    share_store = share_store or ShareStore(settings.node_id, settings.share_index)
    app = FastAPI(title=f"Energy Trusted Data Space - {settings.service_name}", version="0.2.0")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, version="0.2.0")

    @app.post("/internal/tasks/register", response_model=ShareAggregateResponse)
    def register(registration: ComputeTaskRegistration) -> ShareAggregateResponse:
        try:
            return share_store.register(registration)
        except ShareStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def verify_benchmark(token: str | None, test_id: str | None) -> None:
        if not token or not hmac.compare_digest(token, settings.internal_service_token):
            raise HTTPException(status_code=401, detail="invalid internal service credential")
        if not test_id:
            raise HTTPException(status_code=400, detail="performance test identity is required")

    @app.post("/internal/benchmark/tasks/register", response_model=ShareAggregateResponse)
    def benchmark_register(
        registration: ComputeTaskRegistration,
        x_internal_token: str | None = Header(default=None),
        x_privgrid_performance_test_id: str | None = Header(default=None, alias=PERFORMANCE_HEADER),
    ) -> ShareAggregateResponse:
        verify_benchmark(x_internal_token, x_privgrid_performance_test_id)
        try:
            return share_store.register(registration)
        except ShareStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/internal/benchmark/shares", response_model=ShareReceipt)
    def benchmark_submit_share(
        submission: ShareSubmission,
        x_internal_token: str | None = Header(default=None),
        x_privgrid_performance_test_id: str | None = Header(default=None, alias=PERFORMANCE_HEADER),
    ) -> ShareReceipt:
        verify_benchmark(x_internal_token, x_privgrid_performance_test_id)
        try:
            return share_store.submit(submission)
        except ShareStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/internal/benchmark/tasks/{task_id}/aggregate", response_model=ShareAggregateResponse)
    def benchmark_aggregate(
        task_id: str,
        x_internal_token: str | None = Header(default=None),
        x_privgrid_performance_test_id: str | None = Header(default=None, alias=PERFORMANCE_HEADER),
    ) -> ShareAggregateResponse:
        verify_benchmark(x_internal_token, x_privgrid_performance_test_id)
        try:
            return share_store.aggregate(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.post("/internal/shares", response_model=ShareReceipt)
    def submit_share(submission: ShareSubmission) -> ShareReceipt:
        try:
            return share_store.submit(submission)
        except ShareStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/internal/tasks/{task_id}/aggregate", response_model=ShareAggregateResponse)
    def aggregate(task_id: str) -> ShareAggregateResponse:
        try:
            return share_store.aggregate(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    return app


app = create_app()
