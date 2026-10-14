import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.enums import DataImportStatus, OrganizationId, UserRole
from common.schemas import PartyActiveDatasetResponse, PartyDataImportResponse
from control_plane.models.access_control import DataImport, DemoUser
from control_plane.schemas.access_control import DataImportResponse
from control_plane.services.party_import_client import PartyImportClient, PartyImportError
from control_plane.services.security_audit_service import SecurityAuditService


class DataImportPermissionError(PermissionError):
    pass


class DataImportNotFoundError(LookupError):
    pass


class DataImportStateError(RuntimeError):
    pass


class DataImportService:
    def __init__(self, session: Session, party_client: PartyImportClient):
        self.session = session
        self.party_client = party_client
        self.audit = SecurityAuditService(session)

    def upload(self, actor: DemoUser, filename: str, stream) -> DataImportResponse:
        party = self._owner_party(actor)
        safe_filename = self._safe_filename(filename)
        import_id = f"IMPORT-{uuid4().hex[:12].upper()}"
        row = DataImport(
            import_id=import_id,
            party_id=party.value,
            uploader_user_id=actor.user_id,
            original_filename=safe_filename,
            status=DataImportStatus.UPLOADED.value,
            validation_summary_json="{}",
        )
        self.session.add(row)
        self.session.commit()
        self.audit.record(
            "DATA_IMPORT_STARTED",
            actor,
            import_id=import_id,
            import_status=DataImportStatus.UPLOADED.value,
        )
        try:
            result = self.party_client.upload(party, import_id, safe_filename, stream)
        except PartyImportError as exc:
            row.status = DataImportStatus.FAILED.value
            row.error_message = str(exc)
            self.session.commit()
            self.audit.record(
                "DATA_IMPORT_FAILED",
                actor,
                import_id=import_id,
                import_status=DataImportStatus.FAILED.value,
                reason=str(exc),
            )
            raise

        self.audit.record(
            "DATA_IMPORT_UPLOAD_COMPLETED",
            actor,
            import_id=result.import_id,
            source_sha256=result.source_sha256,
            row_count=result.row_count,
            import_status=result.status.value,
        )
        self.audit.record(
            "DATA_IMPORT_VALIDATION_STARTED",
            actor,
            import_id=result.import_id,
            source_sha256=result.source_sha256,
            import_status=DataImportStatus.VALIDATING.value,
        )
        if result.import_id != import_id:
            self.session.delete(row)
            self.session.commit()
            row = self.session.get(DataImport, result.import_id)
            if row is not None:
                return self.to_response(row)
            row = DataImport(
                import_id=result.import_id,
                party_id=party.value,
                uploader_user_id=actor.user_id,
                original_filename=result.source_filename,
                status=result.status.value,
                validation_summary_json="{}",
            )
            self.session.add(row)
        self._apply_party_metadata(row, result)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(DataImport).where(
                    DataImport.party_id == party.value,
                    DataImport.source_sha256 == result.source_sha256,
                )
            )
            if existing is None:
                raise
            row = existing

        event = (
            "DATA_IMPORT_VALIDATED"
            if result.status == DataImportStatus.VALID
            else "DATA_IMPORT_REJECTED"
            if result.status == DataImportStatus.INVALID
            else "DATA_IMPORT_FAILED"
        )
        self.audit.record(
            event,
            actor,
            import_id=row.import_id,
            source_sha256=row.source_sha256,
            row_count=row.row_count,
            import_status=row.status,
            reason=row.error_message,
        )
        return self.to_response(row)

    def list_mine(self, actor: DemoUser) -> list[DataImportResponse]:
        party = self._owner_party(actor)
        rows = list(self.session.scalars(
            select(DataImport)
            .where(DataImport.party_id == party.value)
            .order_by(DataImport.created_at.desc())
        ))
        changed = False
        for row in rows:
            if row.status in {DataImportStatus.UPLOADED.value, DataImportStatus.VALIDATING.value}:
                try:
                    self._apply_party_metadata(row, self.party_client.get(party, row.import_id))
                    changed = True
                except PartyImportError:
                    pass
        try:
            changed = self._reconcile_active(rows, self.party_client.active(party)) or changed
        except PartyImportError:
            pass
        if changed:
            self.session.commit()
        return [self.to_response(row) for row in rows]

    def list_all(self, actor: DemoUser) -> list[DataImportResponse]:
        if actor.role not in {UserRole.AUDITOR.value, UserRole.ADMIN.value}:
            self._unauthorized(actor, "global import metadata is restricted")
        rows = self.session.scalars(select(DataImport).order_by(DataImport.created_at.desc()))
        return [self.to_response(row) for row in rows]

    def get(self, actor: DemoUser, import_id: str) -> DataImportResponse:
        row = self._get_row(import_id)
        if actor.role == UserRole.DATA_OWNER.value:
            if not actor.party_id or row.party_id != actor.party_id:
                self._unauthorized(actor, "import belongs to another Party", import_id)
        elif actor.role not in {UserRole.AUDITOR.value, UserRole.ADMIN.value}:
            self._unauthorized(actor, "role cannot view import metadata", import_id)
        return self.to_response(row)

    def activate(self, actor: DemoUser, import_id: str) -> DataImportResponse:
        party = self._owner_party(actor)
        row = self._get_owned_row(party, import_id)
        if row.status not in {DataImportStatus.VALID.value, DataImportStatus.ARCHIVED.value, DataImportStatus.ACTIVE.value}:
            raise DataImportStateError("only VALID or ARCHIVED imports can be activated")
        previous_active = self.session.scalar(
            select(DataImport).where(
                DataImport.party_id == party.value,
                DataImport.is_active.is_(True),
            )
        )
        result = self.party_client.activate(party, import_id)
        locked = list(
            self.session.scalars(
                select(DataImport)
                .where(DataImport.party_id == party.value)
                .with_for_update()
            )
        )
        for item in locked:
            if item.import_id == import_id:
                self._apply_party_metadata(item, result)
                item.is_active = True
            elif item.is_active:
                item.is_active = False
                item.status = DataImportStatus.ARCHIVED.value
                item.archived_at = result.activated_at
        self.session.commit()
        self.audit.record(
            "DATA_VERSION_ACTIVATED",
            actor,
            import_id=import_id,
            source_sha256=row.source_sha256,
            row_count=row.row_count,
            import_status=DataImportStatus.ACTIVE.value,
        )
        if previous_active is not None and previous_active.import_id != import_id:
            self.audit.record(
                "DATA_VERSION_ARCHIVED",
                actor,
                import_id=previous_active.import_id,
                source_sha256=previous_active.source_sha256,
                row_count=previous_active.row_count,
                import_status=DataImportStatus.ARCHIVED.value,
            )
        return self.to_response(self._get_row(import_id))

    def rollback(self, actor: DemoUser, target_version: str) -> PartyActiveDatasetResponse:
        party = self._owner_party(actor)
        target = None
        if target_version != "BASELINE":
            target = self._get_owned_row(party, target_version)
            if target.status not in {
                DataImportStatus.VALID.value,
                DataImportStatus.ARCHIVED.value,
                DataImportStatus.ACTIVE.value,
            }:
                raise DataImportStateError("rollback target is not a valid historical version")
        previous_active = self.session.scalar(
            select(DataImport).where(
                DataImport.party_id == party.value,
                DataImport.is_active.is_(True),
            )
        )
        result = self.party_client.rollback(party, target_version)
        locked = list(
            self.session.scalars(
                select(DataImport)
                .where(DataImport.party_id == party.value)
                .with_for_update()
            )
        )
        for item in locked:
            was_active = item.is_active
            item.is_active = item.import_id == target_version
            if item.is_active:
                item.status = DataImportStatus.ACTIVE.value
                item.activated_at = result.activated_at
                item.archived_at = None
            elif was_active:
                item.status = DataImportStatus.ARCHIVED.value
        self.session.commit()
        self.audit.record(
            "DATA_VERSION_ROLLED_BACK",
            actor,
            import_id=None if target_version == "BASELINE" else target_version,
            source_sha256=target.source_sha256 if target else None,
            row_count=result.row_count,
            import_status=result.status,
            reason=f"target={target_version}",
        )
        if previous_active is not None and previous_active.import_id != target_version:
            self.audit.record(
                "DATA_VERSION_ARCHIVED",
                actor,
                import_id=previous_active.import_id,
                source_sha256=previous_active.source_sha256,
                row_count=previous_active.row_count,
                import_status=DataImportStatus.ARCHIVED.value,
            )
        return result

    def active(self, actor: DemoUser) -> PartyActiveDatasetResponse:
        party = self._owner_party(actor)
        result = self.party_client.active(party)
        rows = list(self.session.scalars(select(DataImport).where(DataImport.party_id == party.value)))
        if self._reconcile_active(rows, result):
            self.session.commit()
        return result

    def _owner_party(self, actor: DemoUser) -> OrganizationId:
        if actor.role != UserRole.DATA_OWNER.value or not actor.party_id:
            self._unauthorized(actor, "only a bound DATA_OWNER can manage data imports")
        return OrganizationId(actor.party_id)

    def _get_row(self, import_id: str) -> DataImport:
        row = self.session.get(DataImport, import_id)
        if row is None:
            raise DataImportNotFoundError("data import not found")
        return row

    def _get_owned_row(self, party: OrganizationId, import_id: str) -> DataImport:
        row = self._get_row(import_id)
        if row.party_id != party.value:
            raise DataImportPermissionError("data import belongs to another Party")
        return row

    def _unauthorized(self, actor: DemoUser, reason: str, import_id: str | None = None):
        self.audit.record(
            "DATA_IMPORT_UNAUTHORIZED",
            actor,
            import_id=import_id,
            import_status="FAILED",
            reason=reason,
        )
        raise DataImportPermissionError(reason)

    @staticmethod
    def _reconcile_active(rows: list[DataImport], active: PartyActiveDatasetResponse) -> bool:
        changed = False
        for row in rows:
            should_be_active = row.import_id == active.dataset_version
            if row.is_active != should_be_active:
                row.is_active = should_be_active
                changed = True
            if should_be_active and row.status != DataImportStatus.ACTIVE.value:
                row.status = DataImportStatus.ACTIVE.value
                row.activated_at = DataImportService._naive(active.activated_at)
                row.archived_at = None
                changed = True
            elif not should_be_active and row.status == DataImportStatus.ACTIVE.value:
                row.status = DataImportStatus.ARCHIVED.value
                changed = True
        return changed

    @staticmethod
    def _safe_filename(filename: str) -> str:
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            raise DataImportStateError("CSV filename must not contain a path")
        safe = Path(filename).name
        if Path(safe).suffix.lower() != ".csv":
            raise DataImportStateError("only .csv files are accepted")
        if len(safe) > 200:
            raise DataImportStateError("CSV filename is too long")
        return safe

    @staticmethod
    def _apply_party_metadata(row: DataImport, result: PartyDataImportResponse) -> None:
        row.original_filename = result.source_filename
        row.source_sha256 = result.source_sha256
        row.parquet_sha256 = result.parquet_sha256
        row.file_size_bytes = result.file_size_bytes
        row.row_count = result.row_count
        row.valid_row_count = result.valid_row_count
        row.invalid_row_count = result.invalid_row_count
        row.duplicate_count = result.duplicate_count
        row.time_start = result.time_start.replace(tzinfo=None) if result.time_start and result.time_start.tzinfo else result.time_start
        row.time_end = result.time_end.replace(tzinfo=None) if result.time_end and result.time_end.tzinfo else result.time_end
        row.schema_version = result.schema_version
        row.status = result.status.value
        row.validation_summary_json = json.dumps(result.validation_summary.model_dump(mode="json"))
        row.validation_started_at = DataImportService._naive(result.validation_started_at)
        row.validation_completed_at = DataImportService._naive(result.validation_completed_at)
        row.activated_at = DataImportService._naive(result.activated_at)
        row.archived_at = DataImportService._naive(result.archived_at)
        row.is_active = result.status == DataImportStatus.ACTIVE
        row.error_message = result.error_message

    @staticmethod
    def to_response(row: DataImport) -> DataImportResponse:
        return DataImportResponse(
            import_id=row.import_id,
            party_id=row.party_id,
            uploader_user_id=row.uploader_user_id,
            original_filename=row.original_filename,
            source_sha256=row.source_sha256,
            parquet_sha256=row.parquet_sha256,
            file_size_bytes=row.file_size_bytes,
            row_count=row.row_count,
            valid_row_count=row.valid_row_count,
            invalid_row_count=row.invalid_row_count,
            duplicate_count=row.duplicate_count,
            time_start=row.time_start,
            time_end=row.time_end,
            schema_version=row.schema_version,
            import_mode=row.import_mode,
            status=row.status,
            validation_summary=json.loads(row.validation_summary_json or "{}"),
            is_active=row.is_active,
            created_at=row.created_at,
            validation_started_at=row.validation_started_at,
            validation_completed_at=row.validation_completed_at,
            activated_at=row.activated_at,
            archived_at=row.archived_at,
            error_message=row.error_message,
        )

    @staticmethod
    def _naive(value):
        return value.replace(tzinfo=None) if value and value.tzinfo else value
