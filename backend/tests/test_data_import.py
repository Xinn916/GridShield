import asyncio
import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from common.enums import DataImportStatus, OrganizationId, QueryType
from common.schemas import (
    DataValidationSummary,
    PartyActiveDatasetResponse,
    PartyDataImportResponse,
    StatisticsRequest,
)
from control_plane.config import ControlSettings
from control_plane.main import create_app as create_control_app
from party_node.data_repository import DataRepository
from party_node.import_service import ImportRequestError, PartyImportService
from party_node.query_executor import QueryExecutor
from party_node.config import PartySettings
from party_node.main import create_app as create_party_app
from party_node.version_resolver import DataVersionResolver


PASSWORD = "data-import-test"
SCHEMA = pa.schema(
    [
        ("household_id", pa.string()),
        ("organization_id", pa.string()),
        ("timestamp", pa.timestamp("us")),
        ("energy_kwh", pa.float64()),
    ]
)


def baseline(path):
    table = pa.Table.from_pylist(
        [
            {
                "household_id": "BASE-1",
                "organization_id": "ORG_A",
                "timestamp": datetime(2012, 1, 1),
                "energy_kwh": 1.0,
            }
        ],
        schema=SCHEMA,
    )
    pq.write_table(table, path)
    return path


def service(tmp_path):
    base = baseline(tmp_path / "baseline.parquet")
    resolver = DataVersionResolver(base, tmp_path / "imports")
    return PartyImportService(OrganizationId.ORG_A, resolver, max_bytes=4096, max_rows=10), resolver, base


def upload(content: bytes, filename="snapshot.csv"):
    return UploadFile(BytesIO(content), filename=filename)


def run_import(importer, content, import_id="IMPORT-000001", filename="snapshot.csv"):
    return asyncio.run(
        importer.import_csv(upload(content, filename), import_id, OrganizationId.ORG_A)
    )


def valid_csv(energy="2.5", household="H-1", timestamp="2012-02-01T00:00:00"):
    return (
        "energy_kwh,timestamp,organization_id,household_id\n"
        f"{energy},{timestamp},ORG_A,{household}\n"
    ).encode()


def test_valid_csv_is_verified_converted_and_does_not_touch_baseline(tmp_path):
    importer, resolver, base = service(tmp_path)
    before = hashlib.sha256(base.read_bytes()).hexdigest()
    result = run_import(importer, valid_csv())

    assert result.status == DataImportStatus.VALID
    assert result.row_count == result.valid_row_count == 1
    assert result.invalid_row_count == result.duplicate_count == 0
    version_dir = resolver.version_dir(result.import_id)
    converted = pq.ParquetFile(version_dir / "data.parquet")
    assert converted.schema_arrow.equals(SCHEMA, check_metadata=False)
    assert converted.metadata.num_rows == 1
    assert not list(version_dir.glob("*.csv"))
    assert (version_dir / "manifest.json").is_file()
    assert (version_dir / "validation-report.json").is_file()
    assert hashlib.sha256(base.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    ("content", "error_type"),
    [
        (b"household_id,organization_id,timestamp\nH-1,ORG_A,2012-01-01T00:00:00\n", "SCHEMA_MISMATCH"),
        (b"household_id,organization_id,timestamp,energy_kwh,extra\nH-1,ORG_A,2012-01-01T00:00:00,1,x\n", "SCHEMA_MISMATCH"),
        (valid_csv(timestamp="not-a-time"), "INVALID_TIMESTAMP"),
        (valid_csv(energy="NaN"), "INVALID_NUMBER"),
        (valid_csv(energy="Infinity"), "INVALID_NUMBER"),
        (valid_csv(energy="-1"), "INVALID_NUMBER"),
        (valid_csv(household="=1+1"), "FORMULA_INJECTION"),
        (b"household_id,organization_id,timestamp,energy_kwh\n", "EMPTY_DATA"),
    ],
)
def test_invalid_csv_is_rejected_with_bounded_safe_report(tmp_path, content, error_type):
    importer, resolver, _ = service(tmp_path)
    result = run_import(importer, content)
    assert result.status == DataImportStatus.INVALID
    assert any(item.error_type == error_type for item in result.validation_summary.errors)
    assert not (resolver.version_dir(result.import_id) / "data.parquet").exists()
    assert not list(resolver.version_dir(result.import_id).glob("*.csv"))
    serialized = result.model_dump_json()
    assert "H-1,ORG_A" not in serialized


def test_duplicate_key_is_invalid_and_duplicate_upload_is_idempotent(tmp_path):
    importer, _, _ = service(tmp_path)
    duplicate = (
        "household_id,organization_id,timestamp,energy_kwh\n"
        "H-1,ORG_A,2012-01-01T00:00:00,1\n"
        "H-1,ORG_A,2012-01-01T00:00:00,2\n"
    ).encode()
    first = run_import(importer, duplicate)
    second = run_import(importer, duplicate, "IMPORT-000002")
    assert first.status == DataImportStatus.INVALID
    assert first.duplicate_count == 1
    assert second.import_id == first.import_id
    assert second.idempotent is True


def test_filename_encoding_size_and_party_guards(tmp_path):
    importer, _, _ = service(tmp_path)
    with pytest.raises(ImportRequestError):
        run_import(importer, valid_csv(), filename="../snapshot.csv")
    with pytest.raises(ImportRequestError):
        run_import(importer, valid_csv(), filename="snapshot.txt")
    with pytest.raises(ImportRequestError):
        run_import(importer, b"")
    with pytest.raises(ImportRequestError) as oversized:
        run_import(importer, b"x" * 5000)
    assert oversized.value.status_code == 413
    invalid_encoding = run_import(importer, b"household_id,organization_id,timestamp,energy_kwh\n\xff")
    assert invalid_encoding.status == DataImportStatus.INVALID
    assert invalid_encoding.validation_summary.errors[0].error_type == "INVALID_ENCODING"
    with pytest.raises(ImportRequestError) as wrong_party:
        asyncio.run(
            importer.import_csv(
                upload(valid_csv()), "IMPORT-000009", OrganizationId.ORG_B
            )
        )
    assert wrong_party.value.status_code == 403


def test_row_limit_and_conversion_failure_leave_no_active_half_product(tmp_path, monkeypatch):
    importer, resolver, _ = service(tmp_path)
    rows = "".join(
        f"H-{index},ORG_A,2012-01-01T{index:02d}:00:00,1\n" for index in range(11)
    )
    content = ("household_id,organization_id,timestamp,energy_kwh\n" + rows).encode()
    with pytest.raises(ImportRequestError) as too_many:
        run_import(importer, content)
    assert too_many.value.status_code == 413
    assert not list(resolver.storage_dir.glob(".staging-*"))

    def fail_write(*_args, **_kwargs):
        raise OSError("injected conversion failure")

    monkeypatch.setattr(importer, "_write_batch", fail_write)
    failed = run_import(importer, valid_csv(), "IMPORT-000002")
    assert failed.status == DataImportStatus.FAILED
    assert not (resolver.version_dir(failed.import_id) / "data.parquet").exists()
    assert importer.active_summary().dataset_version == "BASELINE"


def test_activation_query_version_and_atomic_rollback(tmp_path):
    importer, resolver, base = service(tmp_path)
    first = run_import(importer, valid_csv(energy="8"), "IMPORT-000001")
    second = run_import(importer, valid_csv(energy="9", timestamp="2012-02-02T00:00:00"), "IMPORT-000002")
    importer.activate(first.import_id)
    assert importer.active_summary().dataset_version == first.import_id
    importer.activate(second.import_id)
    assert importer.get(first.import_id).status == DataImportStatus.ARCHIVED
    assert importer.activate(second.import_id).idempotent is True

    executor = QueryExecutor(DataRepository(base, resolver), OrganizationId.ORG_A)
    result = executor.execute(
        StatisticsRequest(
            task_id="TASK-IMPORT",
            query_type=QueryType.SUM,
            start_time=datetime(2012, 2, 1),
            end_time=datetime(2012, 2, 3),
        )
    )
    # Existing per-record contribution clipping remains unchanged at 5 kWh.
    assert result.value == 5
    assert result.dataset_version == second.import_id

    importer.rollback(first.import_id)
    assert importer.active_summary().dataset_version == first.import_id
    importer.rollback("BASELINE")
    assert importer.active_summary().dataset_version == "BASELINE"


class FakePartyImportClient:
    def __init__(self):
        self.calls = []

    def upload(self, party, import_id, filename, stream):
        self.calls.append((party, import_id, filename))
        return PartyDataImportResponse(
            import_id=import_id,
            party_id=party,
            source_filename=filename,
            source_sha256="a" * 64,
            parquet_sha256="b" * 64,
            file_size_bytes=stream.seek(0, 2),
            row_count=1,
            valid_row_count=1,
            status=DataImportStatus.VALID,
            validation_summary=DataValidationSummary(schema_matches=True),
            created_at=datetime.now(timezone.utc),
        )

    def active(self, party):
        return PartyActiveDatasetResponse(
            party_id=party,
            dataset_version="BASELINE",
            row_count=1,
            status="ACTIVE",
        )


def control_client(tmp_path):
    settings = ControlSettings(
        database_url=f"sqlite:///{(tmp_path / 'imports.db').as_posix()}",
        demo_seed_enabled=True,
        demo_passwords={name: PASSWORD for name in ("analyst_demo", "owner_a", "owner_b", "auditor_demo", "admin_demo")},
    )
    fake = FakePartyImportClient()
    client = TestClient(
        create_control_app(
            settings,
            party_client=object(),
            compute_client=object(),
            party_import_client=fake,
        )
    )
    return client, fake


def login(client, username):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200


def test_control_plane_enforces_owner_session_party_and_metadata_scope(tmp_path):
    client, fake = control_client(tmp_path)
    files = {"file": ("snapshot.csv", valid_csv(), "text/csv")}
    assert client.post("/api/v1/data-imports", files=files).status_code == 401
    login(client, "analyst_demo")
    assert client.post("/api/v1/data-imports", files=files).status_code == 403
    client.post("/api/v1/auth/logout")
    login(client, "auditor_demo")
    assert client.post("/api/v1/data-imports", files=files).status_code == 403
    client.post("/api/v1/auth/logout")
    login(client, "owner_a")
    created = client.post(
        "/api/v1/data-imports",
        data={"party_id": "ORG_B"},
        files=files,
    )
    assert created.status_code == 201, created.text
    import_id = created.json()["import_id"]
    assert fake.calls[0][0] == OrganizationId.ORG_A
    assert b"party_id" not in created.request.url.query
    client.post("/api/v1/auth/logout")
    login(client, "owner_b")
    assert client.get(f"/api/v1/data-imports/{import_id}").status_code == 403


def test_control_responses_do_not_expose_paths_or_raw_rows(tmp_path):
    client, _ = control_client(tmp_path)
    login(client, "owner_a")
    response = client.post(
        "/api/v1/data-imports",
        files={"file": ("snapshot.csv", valid_csv(), "text/csv")},
    )
    text = response.text.lower()
    assert response.status_code == 201
    for forbidden in ("parquet_path", "csv_content", "household_id_list", "/app/imported"):
        assert forbidden not in text


def test_party_import_endpoint_requires_internal_auth_and_matching_party(tmp_path):
    base = baseline(tmp_path / "party.parquet")
    settings = PartySettings(
        OrganizationId.ORG_A,
        "party-a",
        8101,
        base,
        import_storage_dir=tmp_path / "party-imports",
        internal_service_token="test-internal-token",
    )
    client = TestClient(create_party_app(settings))
    files = {"file": ("snapshot.csv", valid_csv(), "text/csv")}
    data = {"import_id": "IMPORT-000001", "party_id": "ORG_A"}
    assert client.post("/internal/imports", data=data, files=files).status_code == 401
    wrong = client.post(
        "/internal/imports",
        data={**data, "party_id": "ORG_B"},
        files=files,
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert wrong.status_code == 403
    accepted = client.post(
        "/internal/imports",
        data=data,
        files=files,
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "VALID"


def test_missing_active_volume_falls_back_to_baseline_with_warning(tmp_path, caplog):
    importer, resolver, base = service(tmp_path)
    item = run_import(importer, valid_csv(), "IMPORT-000001")
    importer.activate(item.import_id)
    (resolver.version_dir(item.import_id) / "data.parquet").unlink()
    resolved = resolver.resolve()
    assert resolved.path == base.resolve()
    assert resolved.version == "BASELINE"
    assert resolved.fallback_warning
    assert "safely using BASELINE" in caplog.text


def test_compose_uses_three_isolated_party_import_volumes_only():
    root = Path(__file__).resolve().parents[2]
    for name in ("compose.yaml", "compose.prod.yaml"):
        text = (root / name).read_text(encoding="utf-8")
        for suffix in "abc":
            volume = f"privgrid-party-{suffix}-imports"
            assert f"{volume}:/app/imported" in text
            assert f"name: {volume}" in text
        for service in ("control-plane", "frontend", "compute-s1", "compute-s2"):
            block = text.split(f"  {service}:", 1)[1].split("\n  ", 1)[0]
            assert "/app/imported" not in block
        for baseline in ("party_a.parquet", "party_b.parquet", "party_c.parquet"):
            assert f"{baseline}:/app/data/{baseline}:ro" in text
