from pathlib import Path
from typing import Any
from contextlib import contextmanager
from threading import local

import duckdb

from common.exceptions import DataFileUnavailableError
from party_node.version_resolver import DataVersionResolver


class DataRepository:
    def __init__(self, parquet_path: Path | str, resolver: DataVersionResolver | None = None):
        self.parquet_path = Path(parquet_path).resolve()
        self.resolver = resolver
        self._local = local()

    @contextmanager
    def snapshot(self):
        resolved = self.resolver.resolve() if self.resolver else None
        previous = getattr(self._local, "snapshot", None)
        self._local.snapshot = resolved
        try:
            yield resolved.version if resolved else "BASELINE"
        finally:
            self._local.snapshot = previous

    def _active_path(self) -> Path:
        snapshot = getattr(self._local, "snapshot", None)
        if snapshot is not None:
            return snapshot.path
        return self.resolver.resolve().path if self.resolver else self.parquet_path

    def snapshot_warning(self) -> str | None:
        snapshot = getattr(self._local, "snapshot", None)
        return snapshot.fallback_warning if snapshot is not None else None

    def _connection(self) -> duckdb.DuckDBPyConnection:
        parquet_path = self._active_path()
        if not parquet_path.is_file():
            raise DataFileUnavailableError("Party data file is unavailable")
        connection = duckdb.connect(":memory:")
        connection.read_parquet(str(parquet_path)).create_view("party_data")
        return connection

    def fetch_one(self, sql: str, parameters: list[Any]) -> tuple[Any, ...]:
        with self._connection() as connection:
            return connection.execute(sql, parameters).fetchone()

    def fetch_all(self, sql: str, parameters: list[Any]) -> list[tuple[Any, ...]]:
        with self._connection() as connection:
            return connection.execute(sql, parameters).fetchall()

    def metadata(self) -> dict[str, Any]:
        with self.snapshot() as dataset_version:
            row = self.fetch_one(
                "SELECT count(*), count(DISTINCT household_id), min(timestamp), max(timestamp) FROM party_data",
                [],
            )
        return {
            "record_count": row[0],
            "household_count": row[1],
            "start_time": row[2],
            "end_time": row[3],
            "dataset_version": dataset_version,
        }
