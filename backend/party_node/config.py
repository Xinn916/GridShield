import os
from dataclasses import dataclass, field
from pathlib import Path

from common.enums import OrganizationId


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


@dataclass(frozen=True)
class PartySettings:
    organization_id: OrganizationId
    service_name: str
    port: int
    parquet_path: Path
    benchmark_data_path: Path | None = None
    record_cap: float = 5.0
    max_records_per_household_per_day: int = 48
    max_window_cap: float = 7_440.0
    compute_urls: dict[int, str] = field(
        default_factory=lambda: {1: "http://127.0.0.1:8201", 2: "http://127.0.0.1:8202"}
    )
    request_timeout: float = 30.0
    import_storage_dir: Path = Path("imported")
    csv_import_enabled: bool = True
    csv_import_max_bytes: int = 50 * 1024 * 1024
    csv_import_max_rows: int = 500_000
    csv_import_allowed_encodings: tuple[str, ...] = ("utf-8", "utf-8-sig")
    internal_service_token: str = "change-me-local-demo"


PARTY_DEFAULTS = {
    OrganizationId.ORG_A: ("party-a", 8101, "party_a.parquet"),
    OrganizationId.ORG_B: ("party-b", 8102, "party_b.parquet"),
    OrganizationId.ORG_C: ("party-c", 8103, "party_c.parquet"),
}


def get_settings() -> PartySettings:
    organization_id = OrganizationId(os.getenv("PARTY_ID", "ORG_A"))
    service_name, port, filename = PARTY_DEFAULTS[organization_id]
    enabled = os.getenv("CSV_IMPORT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    return PartySettings(
        organization_id=organization_id,
        service_name=os.getenv("SERVICE_NAME", service_name),
        port=int(os.getenv("PORT", str(port))),
        parquet_path=Path(os.getenv("PARQUET_PATH", PROJECT_DIR / "data_processed" / filename)),
        benchmark_data_path=Path(os.getenv("BENCHMARK_DATA_PATH", PROJECT_DIR / "benchmark-data" / filename.replace(".parquet", "_benchmark.parquet"))),
        record_cap=float(os.getenv("RECORD_CAP", "5.0")),
        max_records_per_household_per_day=int(os.getenv("MAX_RECORDS_PER_HOUSEHOLD_PER_DAY", "48")),
        max_window_cap=float(os.getenv("MAX_WINDOW_CAP", "7440.0")),
        compute_urls={
            1: os.getenv("COMPUTE_S1_URL", "http://127.0.0.1:8201"),
            2: os.getenv("COMPUTE_S2_URL", "http://127.0.0.1:8202"),
        },
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "30")),
        import_storage_dir=Path(os.getenv("IMPORT_STORAGE_DIR", PROJECT_DIR / ".runtime" / service_name / "imported")),
        csv_import_enabled=enabled,
        csv_import_max_bytes=int(os.getenv("CSV_IMPORT_MAX_BYTES", str(50 * 1024 * 1024))),
        csv_import_max_rows=int(os.getenv("CSV_IMPORT_MAX_ROWS", "500000")),
        csv_import_allowed_encodings=tuple(
            item.strip().lower()
            for item in os.getenv("CSV_IMPORT_ALLOWED_ENCODINGS", "utf-8,utf-8-sig").split(",")
            if item.strip()
        ),
        internal_service_token=os.getenv("INTERNAL_SERVICE_TOKEN", "change-me-local-demo"),
    )
