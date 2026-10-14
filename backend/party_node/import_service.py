import csv
import hashlib
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import UploadFile

from common.enums import DataImportStatus, OrganizationId
from common.schemas import (
    DataValidationIssue,
    DataValidationSummary,
    PartyActiveDatasetResponse,
    PartyDataImportResponse,
)
from party_node.version_resolver import DataVersionResolver, IMPORT_ID_RE


EXPECTED_COLUMNS = ("household_id", "organization_id", "timestamp", "energy_kwh")
FORMULA_PREFIXES = ("=", "+", "-", "@")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImportRequestError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class PartyImportService:
    def __init__(
        self,
        organization_id: OrganizationId,
        resolver: DataVersionResolver,
        *,
        enabled: bool = True,
        max_bytes: int = 50 * 1024 * 1024,
        max_rows: int = 500_000,
        allowed_encodings: tuple[str, ...] = ("utf-8", "utf-8-sig"),
        max_error_samples: int = 20,
    ):
        self.organization_id = organization_id
        self.resolver = resolver
        self.enabled = enabled
        self.max_bytes = max_bytes
        self.max_rows = max_rows
        self.allowed_encodings = {value.lower() for value in allowed_encodings}
        self.max_error_samples = max_error_samples
        self._schema: pa.Schema | None = None

    @property
    def schema(self) -> pa.Schema:
        if self._schema is not None:
            return self._schema
        baseline = pq.ParquetFile(self.resolver.baseline_path)
        try:
            schema = baseline.schema_arrow
        finally:
            baseline.close()
        expected = pa.schema(
            [
                pa.field("household_id", pa.string()),
                pa.field("organization_id", pa.string()),
                pa.field("timestamp", pa.timestamp("us")),
                pa.field("energy_kwh", pa.float64()),
            ]
        )
        if not schema.equals(expected, check_metadata=False):
            raise RuntimeError("baseline Parquet schema is not the supported energy-v1 schema")
        self._schema = schema
        return schema

    async def import_csv(self, upload: UploadFile, import_id: str, party_id: OrganizationId) -> PartyDataImportResponse:
        if not self.enabled:
            raise ImportRequestError("CSV import is disabled", 503)
        if party_id != self.organization_id:
            raise ImportRequestError("party_id does not match this Party", 403)
        if not IMPORT_ID_RE.fullmatch(import_id):
            raise ImportRequestError("invalid import_id")
        filename = self._safe_filename(upload.filename)
        self.resolver.storage_dir.mkdir(parents=True, exist_ok=True)
        staging = self.resolver.storage_dir / f".staging-{import_id}-{uuid4().hex}"
        staging.mkdir(parents=False, exist_ok=False)
        csv_path = staging / "upload.csv"
        source_hash = hashlib.sha256()
        file_size = 0
        try:
            with csv_path.open("wb") as destination:
                while chunk := await upload.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > self.max_bytes:
                        raise ImportRequestError(
                            f"CSV exceeds the {self.max_bytes} byte limit", 413
                        )
                    source_hash.update(chunk)
                    destination.write(chunk)
            if file_size == 0:
                raise ImportRequestError("CSV file is empty")
            digest = source_hash.hexdigest()
            duplicate = self._find_by_source_hash(digest)
            if duplicate is not None:
                duplicate["idempotent"] = True
                return PartyDataImportResponse.model_validate(duplicate)
            return self._validate_and_convert(
                staging, import_id, filename, digest, file_size
            )
        finally:
            await upload.close()
            csv_path.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def get(self, import_id: str) -> PartyDataImportResponse:
        return PartyDataImportResponse.model_validate(self.resolver.read_manifest(import_id))

    def activate(self, import_id: str) -> PartyDataImportResponse:
        with self.resolver.lock:
            new_manifest = self.resolver.read_manifest(import_id)
            status = new_manifest.get("status")
            current = self.resolver.current_version()
            if current == import_id and status == DataImportStatus.ACTIVE.value:
                new_manifest["idempotent"] = True
                return PartyDataImportResponse.model_validate(new_manifest)
            if current == import_id and status == DataImportStatus.ACTIVATING.value:
                new_manifest["status"] = DataImportStatus.ACTIVE.value
                new_manifest["activated_at"] = new_manifest.get("activated_at") or utc_now().isoformat()
                new_manifest["idempotent"] = True
                self.resolver.write_manifest(import_id, new_manifest)
                return PartyDataImportResponse.model_validate(new_manifest)
            if status not in {
                DataImportStatus.VALID.value,
                DataImportStatus.ARCHIVED.value,
                DataImportStatus.ACTIVATING.value,
            }:
                raise ImportRequestError("only VALID or ARCHIVED versions can be activated", 409)
            data_path = self.resolver.version_dir(import_id) / "data.parquet"
            if not data_path.is_file():
                raise ImportRequestError("target Parquet is unavailable", 409)

            old_manifest = None
            if current != "BASELINE" and current != import_id:
                old_manifest = self.resolver.read_manifest(current)
            original_new = dict(new_manifest)
            original_old = dict(old_manifest) if old_manifest else None
            pointer_switched = False
            try:
                new_manifest["status"] = DataImportStatus.ACTIVATING.value
                self.resolver.write_manifest(import_id, new_manifest)
                self.resolver.switch(import_id)
                pointer_switched = True
                now = utc_now().isoformat()
                if old_manifest is not None:
                    old_manifest["status"] = DataImportStatus.ARCHIVED.value
                    old_manifest["archived_at"] = now
                    old_manifest["idempotent"] = False
                    self.resolver.write_manifest(current, old_manifest)
                new_manifest["status"] = DataImportStatus.ACTIVE.value
                new_manifest["activated_at"] = now
                new_manifest["archived_at"] = None
                new_manifest["idempotent"] = False
                self.resolver.write_manifest(import_id, new_manifest)
            except Exception:
                if pointer_switched:
                    self.resolver.switch(current)
                self.resolver.write_manifest(import_id, original_new)
                if original_old is not None:
                    self.resolver.write_manifest(current, original_old)
                raise
            return PartyDataImportResponse.model_validate(new_manifest)

    def archive(self, import_id: str) -> PartyDataImportResponse:
        with self.resolver.lock:
            if self.resolver.current_version() == import_id:
                raise ImportRequestError("the active version cannot be archived directly", 409)
            manifest = self.resolver.read_manifest(import_id)
            if manifest.get("status") in {
                DataImportStatus.INVALID.value,
                DataImportStatus.FAILED.value,
            }:
                raise ImportRequestError("invalid or failed imports cannot be archived", 409)
            manifest["status"] = DataImportStatus.ARCHIVED.value
            manifest["archived_at"] = utc_now().isoformat()
            self.resolver.write_manifest(import_id, manifest)
            return PartyDataImportResponse.model_validate(manifest)

    def rollback(self, target_version: str) -> PartyActiveDatasetResponse:
        with self.resolver.lock:
            current = self.resolver.current_version()
            if target_version == current:
                return self.active_summary()
            if target_version == "BASELINE":
                old_manifest = None
                if current != "BASELINE":
                    old_manifest = self.resolver.read_manifest(current)
                self.resolver.switch("BASELINE")
                if old_manifest is not None:
                    old_manifest["status"] = DataImportStatus.ARCHIVED.value
                    old_manifest["archived_at"] = utc_now().isoformat()
                    self.resolver.write_manifest(current, old_manifest)
                return self.active_summary()
            self.activate(target_version)
            return self.active_summary()

    def active_summary(self) -> PartyActiveDatasetResponse:
        resolved = self.resolver.resolve()
        return PartyActiveDatasetResponse(
            party_id=self.organization_id,
            dataset_version=resolved.version,
            row_count=resolved.row_count,
            time_start=resolved.time_start,
            time_end=resolved.time_end,
            activated_at=resolved.activated_at,
            status=resolved.status,
            fallback_warning=resolved.fallback_warning,
        )

    def _validate_and_convert(
        self,
        staging: Path,
        import_id: str,
        filename: str,
        source_sha256: str,
        file_size: int,
    ) -> PartyDataImportResponse:
        csv_path = staging / "upload.csv"
        parquet_path = staging / "data.parquet"
        created_at = utc_now()
        validation_started_at = utc_now()
        issues: list[DataValidationIssue] = []
        error_count = 0
        schema_matches = False
        row_count = valid_count = invalid_count = duplicate_count = 0
        time_start = time_end = None
        seen_keys: set[tuple[str, datetime]] = set()
        writer = None
        batch: list[dict] = []

        def add_issue(error_type: str, message: str, row=None, field=None) -> None:
            nonlocal error_count
            error_count += 1
            if len(issues) < self.max_error_samples:
                issues.append(
                    DataValidationIssue(
                        error_type=error_type,
                        row_number=row,
                        field=field,
                        message=message,
                    )
                )

        try:
            if not self.allowed_encodings.intersection({"utf-8", "utf-8-sig"}):
                raise ImportRequestError("configured CSV encodings are unsupported", 503)
            try:
                source = csv_path.open("r", encoding="utf-8-sig", newline="")
                with source:
                    reader = csv.DictReader(source)
                    columns = reader.fieldnames or []
                    schema_matches = len(columns) == len(set(columns)) and set(columns) == set(EXPECTED_COLUMNS)
                    if not schema_matches:
                        add_issue(
                            "SCHEMA_MISMATCH",
                            "CSV columns must exactly match household_id, organization_id, timestamp and energy_kwh",
                        )
                        for _ in reader:
                            row_count += 1
                            invalid_count += 1
                            if row_count > self.max_rows:
                                raise ImportRequestError(
                                    f"CSV exceeds the {self.max_rows} row limit", 413
                                )
                    else:
                        for row_number, row in enumerate(reader, start=2):
                            row_count += 1
                            if row_count > self.max_rows:
                                raise ImportRequestError(
                                    f"CSV exceeds the {self.max_rows} row limit", 413
                                )
                            before_errors = error_count
                            household = (row.get("household_id") or "").strip()
                            organization = (row.get("organization_id") or "").strip()
                            timestamp_text = (row.get("timestamp") or "").strip()
                            energy_text = (row.get("energy_kwh") or "").strip()
                            timestamp_value = None
                            energy_value = None
                            if None in row or any(value is None for value in row.values()):
                                add_issue("CSV_FORMAT", "row has an unexpected number of fields", row_number)
                            self._validate_identifier(household, "household_id", row_number, add_issue)
                            self._validate_identifier(organization, "organization_id", row_number, add_issue)
                            if organization and organization != self.organization_id.value:
                                add_issue(
                                    "PARTY_MISMATCH",
                                    "organization_id does not match this Party",
                                    row_number,
                                    "organization_id",
                                )
                            try:
                                timestamp_value = datetime.fromisoformat(timestamp_text)
                                if timestamp_value.tzinfo is not None:
                                    raise ValueError("timezone-aware timestamps are not accepted")
                            except ValueError:
                                add_issue(
                                    "INVALID_TIMESTAMP",
                                    "timestamp must be a timezone-naive ISO-8601 value",
                                    row_number,
                                    "timestamp",
                                )
                            try:
                                energy_value = float(energy_text)
                                if not math.isfinite(energy_value):
                                    raise ValueError("not finite")
                                if energy_value < 0:
                                    raise ValueError("negative")
                            except ValueError:
                                add_issue(
                                    "INVALID_NUMBER",
                                    "energy_kwh must be a finite non-negative number",
                                    row_number,
                                    "energy_kwh",
                                )
                            if household and timestamp_value is not None:
                                key = (household, timestamp_value)
                                if key in seen_keys:
                                    duplicate_count += 1
                                    add_issue(
                                        "DUPLICATE_KEY",
                                        "duplicate household_id + timestamp key",
                                        row_number,
                                    )
                                else:
                                    seen_keys.add(key)
                            if error_count == before_errors:
                                valid_count += 1
                                time_start = timestamp_value if time_start is None else min(time_start, timestamp_value)
                                time_end = timestamp_value if time_end is None else max(time_end, timestamp_value)
                                batch.append(
                                    {
                                        "household_id": household,
                                        "organization_id": organization,
                                        "timestamp": timestamp_value,
                                        "energy_kwh": energy_value,
                                    }
                                )
                                if len(batch) >= 10_000:
                                    writer = self._write_batch(parquet_path, writer, batch)
                                    batch.clear()
                            else:
                                invalid_count += 1
            except UnicodeDecodeError:
                add_issue("INVALID_ENCODING", "CSV must use UTF-8 or UTF-8-SIG encoding")

            if row_count == 0 and not any(item.error_type == "INVALID_ENCODING" for item in issues):
                add_issue("EMPTY_DATA", "CSV contains no data rows")
            if batch:
                writer = self._write_batch(parquet_path, writer, batch)
            if writer is not None:
                writer.close()
                writer = None

            status = DataImportStatus.INVALID if error_count else DataImportStatus.VALID
            parquet_sha256 = None
            error_message = None
            if status == DataImportStatus.VALID:
                converted = pq.ParquetFile(parquet_path)
                try:
                    if not converted.schema_arrow.equals(self.schema, check_metadata=False):
                        raise RuntimeError("converted Parquet schema does not match baseline")
                    if converted.metadata.num_rows != row_count:
                        raise RuntimeError("converted Parquet row count does not match CSV")
                finally:
                    converted.close()
                parquet_sha256 = self._sha256(parquet_path)
            else:
                parquet_path.unlink(missing_ok=True)
                error_message = "CSV validation failed"

            completed_at = utc_now()
            summary = DataValidationSummary(
                schema_matches=schema_matches,
                error_count=error_count,
                errors=issues,
                errors_truncated=error_count > len(issues),
            )
            manifest = self._manifest(
                import_id,
                filename,
                source_sha256,
                parquet_sha256,
                file_size,
                row_count,
                valid_count,
                invalid_count,
                duplicate_count,
                time_start,
                time_end,
                status,
                summary,
                created_at,
                validation_started_at,
                completed_at,
                error_message,
            )
            self._write_json(staging / "validation-report.json", summary.model_dump(mode="json"))
            self._write_json(staging / "manifest.json", manifest)
            csv_path.unlink(missing_ok=True)
            os.replace(staging, self.resolver.version_dir(import_id))
            return PartyDataImportResponse.model_validate(manifest)
        except ImportRequestError:
            if writer is not None:
                writer.close()
            raise
        except Exception as exc:
            if writer is not None:
                writer.close()
            parquet_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)
            completed_at = utc_now()
            add_issue("CONVERSION_FAILED", "CSV could not be converted to a verified Parquet snapshot")
            summary = DataValidationSummary(
                schema_matches=schema_matches,
                error_count=error_count,
                errors=issues,
                errors_truncated=error_count > len(issues),
            )
            manifest = self._manifest(
                import_id,
                filename,
                source_sha256,
                None,
                file_size,
                row_count,
                valid_count,
                invalid_count,
                duplicate_count,
                time_start,
                time_end,
                DataImportStatus.FAILED,
                summary,
                created_at,
                validation_started_at,
                completed_at,
                f"{type(exc).__name__}: conversion failed",
            )
            self._write_json(staging / "validation-report.json", summary.model_dump(mode="json"))
            self._write_json(staging / "manifest.json", manifest)
            os.replace(staging, self.resolver.version_dir(import_id))
            return PartyDataImportResponse.model_validate(manifest)

    def _find_by_source_hash(self, source_sha256: str) -> dict | None:
        if not self.resolver.storage_dir.is_dir():
            return None
        for child in self.resolver.storage_dir.iterdir():
            if not child.is_dir() or not IMPORT_ID_RE.fullmatch(child.name):
                continue
            try:
                manifest = self.resolver.read_manifest(child.name)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if (
                manifest.get("party_id") == self.organization_id.value
                and manifest.get("source_sha256") == source_sha256
            ):
                return manifest
        return None

    def _manifest(
        self,
        import_id,
        filename,
        source_sha256,
        parquet_sha256,
        file_size,
        row_count,
        valid_count,
        invalid_count,
        duplicate_count,
        time_start,
        time_end,
        status,
        summary,
        created_at,
        validation_started_at,
        validation_completed_at,
        error_message,
    ) -> dict:
        return PartyDataImportResponse(
            import_id=import_id,
            party_id=self.organization_id,
            source_filename=filename,
            source_sha256=source_sha256,
            parquet_sha256=parquet_sha256,
            file_size_bytes=file_size,
            row_count=row_count,
            valid_row_count=valid_count,
            invalid_row_count=invalid_count,
            duplicate_count=duplicate_count,
            time_start=time_start,
            time_end=time_end,
            status=status,
            validation_summary=summary,
            created_at=created_at,
            validation_started_at=validation_started_at,
            validation_completed_at=validation_completed_at,
            error_message=error_message,
        ).model_dump(mode="json")

    def _write_batch(self, path: Path, writer, rows: list[dict]):
        if writer is None:
            writer = pq.ParquetWriter(path, self.schema, compression="snappy")
        writer.write_table(pa.Table.from_pylist(rows, schema=self.schema))
        return writer

    @staticmethod
    def _validate_identifier(value: str, field: str, row: int, add_issue) -> None:
        if not value:
            add_issue("INVALID_IDENTIFIER", f"{field} must not be empty", row, field)
        elif len(value) > 128:
            add_issue("INVALID_IDENTIFIER", f"{field} exceeds 128 characters", row, field)
        elif value.startswith(FORMULA_PREFIXES):
            add_issue("FORMULA_INJECTION", f"{field} starts with an unsafe spreadsheet formula prefix", row, field)
        elif any(ord(char) < 32 for char in value):
            add_issue("INVALID_IDENTIFIER", f"{field} contains control characters", row, field)

    @staticmethod
    def _safe_filename(filename: str | None) -> str:
        if not filename:
            raise ImportRequestError("CSV filename is required")
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ImportRequestError("CSV filename must not contain a path")
        safe = Path(filename).name
        if Path(safe).suffix.lower() != ".csv":
            raise ImportRequestError("only .csv files are accepted")
        if len(safe) > 200:
            raise ImportRequestError("CSV filename is too long")
        return safe

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
