from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.schemas import HealthResponse
from control_plane.api.routes import create_router
from control_plane.config import ControlSettings, get_settings
from control_plane.database.session import create_session_factory, create_tables, session_dependency
from control_plane.services.compute_client import ComputeClient
from control_plane.services.party_client import PartyClient
from control_plane.services.party_import_client import PartyImportClient
from control_plane.services.system_health_service import SystemHealthService
from control_plane.services.agent_service import AgentService
from control_plane.services.deepseek_client import DeepSeekClient
from control_plane.services.seed_service import seed_access_control


VERIFICATION_UI_DIR = Path(__file__).resolve().parents[1] / "verification_ui"


def create_app(
    settings: ControlSettings | None = None,
    party_client: PartyClient | None = None,
    compute_client: ComputeClient | None = None,
    health_service: SystemHealthService | None = None,
    monitor_store=None,
    agent_service: AgentService | None = None,
    party_import_client: PartyImportClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    factory = create_session_factory(settings.database_url)
    create_tables(factory)
    seed_access_control(
        factory,
        demo_seed_enabled=settings.demo_seed_enabled,
        passwords=settings.demo_passwords,
    )
    party_client = party_client or PartyClient(settings.party_urls, settings.request_timeout, settings.internal_service_token)
    compute_client = compute_client or ComputeClient(settings.compute_urls, settings.request_timeout, settings.internal_service_token)
    health_service = health_service or SystemHealthService(settings)
    agent_service = agent_service or AgentService(
        DeepSeekClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout=settings.deepseek_timeout_seconds,
            max_tokens=settings.deepseek_max_tokens,
            temperature=settings.deepseek_temperature,
        ),
        rate_limit=settings.agent_rate_limit_per_minute,
    )
    party_import_client = party_import_client or PartyImportClient(
        settings.party_urls,
        settings.internal_service_token,
        settings.request_timeout,
    )
    app = FastAPI(title="Energy Trusted Data Space - Control Plane", version="0.4.0")
    # 生产环境禁止默认使用任意来源 "*"；来源必须通过 CORS_ORIGINS 显式配置。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        create_router(
            session_dependency(factory),
            party_client,
            compute_client,
            settings,
            health_service,
            monitor_store,
            agent_service,
            party_import_client,
        )
    )
    app.mount(
        "/verify/assets",
        StaticFiles(directory=VERIFICATION_UI_DIR),
        name="verification-assets",
    )

    @app.get("/verify", include_in_schema=False)
    def verification_page() -> FileResponse:
        return FileResponse(VERIFICATION_UI_DIR / "index.html")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(service=settings.service_name, version="0.4.0")

    return app


app = create_app()
