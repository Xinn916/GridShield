import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

import pyarrow.compute as pc
import pyarrow.parquet as pq


logger = logging.getLogger(__name__)
IMPORT_ID_RE = re.compile(r"^IMPORT-[A-Za-z0-9_-]{6,48}$")


@dataclass(frozen=True)
class ResolvedDataset:
    path: Path
    version: str
    row_count: int
    time_start: datetime | None
    time_end: datetime | None
    activated_at: datetime | None = None
    status: str = "ACTIVE"
    fallback_warning: str | None = None


class DataVersionResolver:
    """Resolves an immutable Party-local snapshot without exposing its path."""

    def __init__(self, baseline_path: Path | str, storage_dir: Path | str):
        self.baseline_path = Path(baseline_path).resolve()
        self.storage_dir = Path(storage_dir).resolve()
        self.pointer_path = self.storage_dir / "active.json"
        self.lock = RLock()

    def resolve(self) -> ResolvedDataset:
        with self.lock:
            try:
                version = self._read_pointer()
                if version == "BASELINE":
                    return self._baseline()
                version_dir = self.version_dir(version)
                data_path = (version_dir / "data.parquet").resolve()
                if not data_path.is_file() or not data_path.is_relative_to(self.storage_dir):
                    raise FileNotFoundError("active imported Parquet is unavailable")
                manifest = self.read_manifest(version)
                return ResolvedDataset(
                    path=data_path,
                    version=version,
                    row_count=int(manifest.get("row_count") or 0),
                    time_start=self._datetime(manifest.get("time_start")),
                    time_end=self._datetime(manifest.get("time_end")),
                    activated_at=self._datetime(manifest.get("activated_at")),
                    status=str(manifest.get("status") or "ACTIVE"),
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                warning = f"active import unavailable; safely using BASELINE ({type(exc).__name__})"
                logger.warning(warning)
                baseline = self._baseline()
                return ResolvedDataset(**{**baseline.__dict__, "fallback_warning": warning})

    def switch(self, version: str) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if version != "BASELINE":
            data_path = self.version_dir(version) / "data.parquet"
            if not data_path.is_file():
                raise FileNotFoundError("target data version is unavailable")
        temporary = self.storage_dir / f".active-{uuid4().hex}.tmp"
        temporary.write_text(json.dumps({"dataset_version": version}), encoding="utf-8")
        os.replace(temporary, self.pointer_path)

    def current_version(self) -> str:
        with self.lock:
            return self._read_pointer()

    def version_dir(self, import_id: str) -> Path:
        if not IMPORT_ID_RE.fullmatch(import_id):
            raise ValueError("invalid import_id")
        path = (self.storage_dir / import_id).resolve()
        if not path.is_relative_to(self.storage_dir):
            raise ValueError("import path escapes Party storage")
        return path

    def read_manifest(self, import_id: str) -> dict:
        manifest_path = self.version_dir(import_id) / "manifest.json"
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, import_id: str, manifest: dict) -> None:
        version_dir = self.version_dir(import_id)
        temporary = version_dir / f".manifest-{uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, version_dir / "manifest.json")

    def _read_pointer(self) -> str:
        if not self.pointer_path.is_file():
            return "BASELINE"
        payload = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        version = payload.get("dataset_version", "BASELINE")
        if version != "BASELINE" and not IMPORT_ID_RE.fullmatch(str(version)):
            raise ValueError("invalid active dataset pointer")
        return str(version)

    def _baseline(self) -> ResolvedDataset:
        parquet = pq.ParquetFile(self.baseline_path)
        try:
            row_count = parquet.metadata.num_rows
        finally:
            parquet.close()
        table = pq.read_table(self.baseline_path, columns=["timestamp"])
        return ResolvedDataset(
            path=self.baseline_path,
            version="BASELINE",
            row_count=row_count,
            time_start=pc.min(table["timestamp"]).as_py(),
            time_end=pc.max(table["timestamp"]).as_py(),
            status="ACTIVE",
        )

    @staticmethod
    def _datetime(value) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value) if isinstance(value, str) else value
