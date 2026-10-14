import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from common.enums import CalculationMode, OrganizationId


BACKEND_DIR = Path(__file__).resolve().parents[1]
AppEnvironment = Literal["development", "testing", "production"]


def _load_env_file(path: Path) -> None:
    """加载 backend/.env（仅当环境变量未设置时生效），真实 Key 只从这里读取。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class ControlSettings:
    service_name: str = "control-plane"
    port: int = 8000
    app_env: AppEnvironment = "development"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'control_plane.db').as_posix()}"
    request_timeout: float = 30.0
    calculation_mode: CalculationMode = CalculationMode.DISTRIBUTED_DP
    aggregate_poll_interval: float = 0.1
    aggregate_poll_attempts: int = 100
    default_total_epsilon: float = 20.0
    subject_id: str = "demo-analyst"
    epsilon_sum_ratio: float = 0.7
    epsilon_count_ratio: float = 0.3
    minimum_denominator: float = 10.0
    record_cap: float = 5.0
    max_records_per_household_per_day: int = 48
    max_window_cap: float = 7_440.0
    party_urls: dict[OrganizationId, str] = field(
        default_factory=lambda: {
            OrganizationId.ORG_A: "http://127.0.0.1:8101",
            OrganizationId.ORG_B: "http://127.0.0.1:8102",
            OrganizationId.ORG_C: "http://127.0.0.1:8103",
        }
    )
    compute_urls: dict[int, str] = field(
        default_factory=lambda: {
            1: "http://127.0.0.1:8201",
            2: "http://127.0.0.1:8202",
        }
    )
    frontend_gateway_url: str = "http://127.0.0.1:8080"
    # 控制面 CORS 允许来源：默认仅本地 Vite 开发地址，禁止默认使用 "*"。
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: ("http://localhost:5173", "http://127.0.0.1:5173")
    )
    # DeepSeek Agent 配置：真实 Key 只允许来自环境变量（backend/.env），禁止写入前端或仓库。
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 20.0
    deepseek_max_tokens: int = 1200
    deepseek_temperature: float = 0.0
    agent_rate_limit_per_minute: int = 10
    authorization_enforcement_enabled: bool = False
    demo_seed_enabled: bool = False
    session_ttl_seconds: int = 28_800
    session_cookie_name: str = "privgrid_session"
    session_cookie_secure: bool = False
    demo_passwords: dict[str, str] = field(default_factory=dict)
    csv_import_enabled: bool = True
    csv_import_max_bytes: int = 50 * 1024 * 1024
    csv_import_max_rows: int = 500_000
    internal_service_token: str = "change-me-local-demo"


def get_settings() -> ControlSettings:
    _load_env_file(BACKEND_DIR / ".env")

    def parse_cors_origins(value: str | None) -> tuple[str, ...]:
        if not value:
            return ControlSettings().cors_origins
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def flag(name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "testing", "production"}:
        raise ValueError("APP_ENV must be one of: development, testing, production")

    return ControlSettings(
        service_name=os.getenv("SERVICE_NAME", "control-plane"),
        port=int(os.getenv("PORT", "8000")),
        app_env=app_env,
        database_url=os.getenv("DATABASE_URL", ControlSettings.database_url),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "30")),
        calculation_mode=CalculationMode(os.getenv("CALCULATION_MODE", "DISTRIBUTED_DP")),
        aggregate_poll_interval=float(os.getenv("AGGREGATE_POLL_INTERVAL", "0.1")),
        aggregate_poll_attempts=int(os.getenv("AGGREGATE_POLL_ATTEMPTS", "100")),
        default_total_epsilon=float(os.getenv("DEFAULT_TOTAL_EPSILON", "20.0")),
        subject_id=os.getenv("PRIVACY_SUBJECT_ID", "demo-analyst"),
        epsilon_sum_ratio=float(os.getenv("EPSILON_SUM_RATIO", "0.7")),
        epsilon_count_ratio=float(os.getenv("EPSILON_COUNT_RATIO", "0.3")),
        minimum_denominator=float(os.getenv("MINIMUM_DENOMINATOR", "10.0")),
        record_cap=float(os.getenv("RECORD_CAP", "5.0")),
        max_records_per_household_per_day=int(os.getenv("MAX_RECORDS_PER_HOUSEHOLD_PER_DAY", "48")),
        max_window_cap=float(os.getenv("MAX_WINDOW_CAP", "7440.0")),
        party_urls={
            party: os.getenv(
                f"PARTY_{party.value.removeprefix('ORG_')}_URL",
                os.getenv(f"{party.value}_URL", url),
            )
            for party, url in ControlSettings().party_urls.items()
        },
        compute_urls={
            1: os.getenv("COMPUTE_S1_URL", "http://127.0.0.1:8201"),
            2: os.getenv("COMPUTE_S2_URL", "http://127.0.0.1:8202"),
        },
        frontend_gateway_url=os.getenv("FRONTEND_GATEWAY_URL", "http://127.0.0.1:8080"),
        cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        deepseek_timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "20")),
        deepseek_max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "1200")),
        deepseek_temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
        agent_rate_limit_per_minute=int(os.getenv("AGENT_RATE_LIMIT_PER_MINUTE", "10")),
        authorization_enforcement_enabled=flag("AUTHORIZATION_ENFORCEMENT_ENABLED"),
        demo_seed_enabled=flag("DEMO_SEED_ENABLED"),
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "28800")),
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "privgrid_session"),
        session_cookie_secure=flag("SESSION_COOKIE_SECURE"),
        demo_passwords={
            username: os.getenv(variable, "")
            for username, variable in {
                "analyst_demo": "DEMO_ANALYST_PASSWORD",
                "owner_a": "DEMO_OWNER_A_PASSWORD",
                "owner_b": "DEMO_OWNER_B_PASSWORD",
                "owner_c": "DEMO_OWNER_C_PASSWORD",
                "auditor_demo": "DEMO_AUDITOR_PASSWORD",
                "admin_demo": "DEMO_ADMIN_PASSWORD",
            }.items()
        },
        csv_import_enabled=flag("CSV_IMPORT_ENABLED", True),
        csv_import_max_bytes=int(os.getenv("CSV_IMPORT_MAX_BYTES", str(50 * 1024 * 1024))),
        csv_import_max_rows=int(os.getenv("CSV_IMPORT_MAX_ROWS", "500000")),
        internal_service_token=os.getenv("INTERNAL_SERVICE_TOKEN", "change-me-local-demo"),
    )
