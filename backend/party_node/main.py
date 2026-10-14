import hmac
from time import perf_counter

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

from common.exceptions import DataFileUnavailableError, UpstreamServiceError
from common.enums import OrganizationId
from common.schemas import (
    DistributedDPParameters,
    HealthResponse,
    PartyTaskAck,
    SecretTaskRequest,
    StatisticsRequest,
    StatisticsResponse,
    PartyActiveDatasetResponse,
    PartyDataImportResponse,
    PartyRollbackRequest,
)
from common.performance import BenchmarkPartyRequest, BenchmarkPlainResponse, BenchmarkSharedResponse, PERFORMANCE_HEADER
from party_node.config import PartySettings, get_settings
from party_node.contribution_clipper import ContributionClipper
from party_node.data_repository import DataRepository
from party_node.query_executor import QueryExecutor
from party_node.share_service import ShareService
from party_node.import_service import ImportRequestError, PartyImportService
from party_node.version_resolver import DataVersionResolver


def create_app(settings: PartySettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    resolver = DataVersionResolver(settings.parquet_path, settings.import_storage_dir)
    repository = DataRepository(settings.parquet_path, resolver)
    executor = QueryExecutor(
        repository,
        settings.organization_id,
        ContributionClipper(
            record_cap=settings.record_cap,
            max_records_per_household_per_day=settings.max_records_per_household_per_day,
            max_window_cap=settings.max_window_cap,
        ),
    )
    share_service = ShareService(executor, settings.compute_urls, settings.request_timeout)
    benchmark_repository = DataRepository(settings.benchmark_data_path) if settings.benchmark_data_path else None
    benchmark_executor = QueryExecutor(
        benchmark_repository,
        settings.organization_id,
        ContributionClipper(
            record_cap=settings.record_cap,
            max_records_per_household_per_day=settings.max_records_per_household_per_day,
            max_window_cap=settings.max_window_cap,
        ),
    ) if benchmark_repository else None
    benchmark_share_service = ShareService(benchmark_executor, settings.compute_urls, settings.request_timeout) if benchmark_executor else None
    import_service = PartyImportService(
        settings.organization_id,
        resolver,
        enabled=settings.csv_import_enabled,
        max_bytes=settings.csv_import_max_bytes,
        max_rows=settings.csv_import_max_rows,
        allowed_encodings=settings.csv_import_allowed_encodings,
    )
    app = FastAPI(title=f"Energy Trusted Data Space - {settings.service_name}", version="0.1.0")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name)

    @app.get("/internal/metadata")
    def metadata() -> dict:
        try:
            return {"organization_id": settings.organization_id, **repository.metadata()}
        except DataFileUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/internal/statistics", response_model=StatisticsResponse)
    def statistics(request: StatisticsRequest) -> StatisticsResponse:
        try:
            return executor.execute(request)
        except DataFileUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/internal/tasks", response_model=PartyTaskAck)
    def secret_task(request: SecretTaskRequest) -> PartyTaskAck:
        try:
            return share_service.process(request)
        except DataFileUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except UpstreamServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def verify_benchmark_auth(token: str | None, test_id: str | None, request_test_id: str) -> None:
        if not token or not hmac.compare_digest(token, settings.internal_service_token):
            raise HTTPException(status_code=401, detail="invalid internal service credential")
        if not test_id or not hmac.compare_digest(test_id, request_test_id):
            raise HTTPException(status_code=400, detail="performance test identity mismatch")
        if benchmark_executor is None:
            raise HTTPException(status_code=503, detail=f"{settings.organization_id.value} Benchmark data is unavailable")

    @app.post("/internal/benchmark/statistics", response_model=BenchmarkPlainResponse)
    def benchmark_statistics(
        request: BenchmarkPartyRequest,
        x_internal_token: str | None = Header(default=None),
        x_privgrid_performance_test_id: str | None = Header(default=None, alias=PERFORMANCE_HEADER),
    ) -> BenchmarkPlainResponse:
        verify_benchmark_auth(x_internal_token, x_privgrid_performance_test_id, request.test_id)
        started = perf_counter()
        result = benchmark_executor.execute(StatisticsRequest(
            task_id=request.task_id, query_type=request.query_type,
            start_time=request.start_time, end_time=request.end_time, group_by=request.interval,
        ))
        return BenchmarkPlainResponse(statistics=result, local_duration_ms=(perf_counter() - started) * 1000)

    @app.post("/internal/benchmark/tasks", response_model=BenchmarkSharedResponse)
    def benchmark_secret_task(
        request: BenchmarkPartyRequest,
        x_internal_token: str | None = Header(default=None),
        x_privgrid_performance_test_id: str | None = Header(default=None, alias=PERFORMANCE_HEADER),
    ) -> BenchmarkSharedResponse:
        verify_benchmark_auth(x_internal_token, x_privgrid_performance_test_id, request.test_id)
        try:
            ack, local_ms, sharing_ms, events = benchmark_share_service.process_measured(
                SecretTaskRequest(
                    task_id=request.task_id, query_type=request.query_type,
                    start_time=request.start_time, end_time=request.end_time,
                    group_by=request.interval, expected_parties=request.parties,
                    calculation_mode=request.mode,
                    dp_parameters=request.dp_parameters,
                ),
                test_id=request.test_id, internal_token=settings.internal_service_token,
            )
            return BenchmarkSharedResponse(
                acknowledgement=ack, local_duration_ms=local_ms,
                share_generation_duration_ms=sharing_ms, performance_events=events,
            )
        except DataFileUnavailableError as exc:
            raise HTTPException(status_code=503, detail=f"{settings.organization_id.value} Benchmark data is unavailable") from exc
        except (UpstreamServiceError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    def verify_import_auth(token: str | None) -> None:
        if not token or not hmac.compare_digest(token, settings.internal_service_token):
            raise HTTPException(status_code=401, detail="invalid internal service credential")

    @app.get("/internal/imports/active", response_model=PartyActiveDatasetResponse)
    def active_import(x_internal_token: str | None = Header(default=None)) -> PartyActiveDatasetResponse:
        verify_import_auth(x_internal_token)
        return import_service.active_summary()

    @app.post("/internal/imports", response_model=PartyDataImportResponse)
    async def create_import(
        file: UploadFile = File(...),
        import_id: str = Form(...),
        party_id: OrganizationId = Form(...),
        x_internal_token: str | None = Header(default=None),
    ) -> PartyDataImportResponse:
        verify_import_auth(x_internal_token)
        try:
            return await import_service.import_csv(file, import_id, party_id)
        except ImportRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/internal/imports/{import_id}", response_model=PartyDataImportResponse)
    def get_import(import_id: str, x_internal_token: str | None = Header(default=None)) -> PartyDataImportResponse:
        verify_import_auth(x_internal_token)
        try:
            return import_service.get(import_id)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="data import not found") from exc

    @app.post("/internal/imports/{import_id}/activate", response_model=PartyDataImportResponse)
    def activate_import(import_id: str, x_internal_token: str | None = Header(default=None)) -> PartyDataImportResponse:
        verify_import_auth(x_internal_token)
        try:
            return import_service.activate(import_id)
        except ImportRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="data import not found") from exc

    @app.post("/internal/imports/{import_id}/archive", response_model=PartyDataImportResponse)
    def archive_import(import_id: str, x_internal_token: str | None = Header(default=None)) -> PartyDataImportResponse:
        verify_import_auth(x_internal_token)
        try:
            return import_service.archive(import_id)
        except ImportRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="data import not found") from exc

    @app.post("/internal/imports/{import_id}/rollback", response_model=PartyActiveDatasetResponse)
    def rollback_import(
        import_id: str,
        payload: PartyRollbackRequest,
        x_internal_token: str | None = Header(default=None),
    ) -> PartyActiveDatasetResponse:
        verify_import_auth(x_internal_token)
        if payload.target_version not in {"BASELINE", import_id}:
            raise HTTPException(status_code=400, detail="rollback target does not match route")
        try:
            return import_service.rollback(payload.target_version)
        except ImportRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="rollback target not found") from exc

    return app


app = create_app()
