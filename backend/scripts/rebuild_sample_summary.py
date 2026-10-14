from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data_processed"
SUMMARY_PATH = DATA_DIR / "sample_summary.json"
PARTIES = {
    "ORG_A": DATA_DIR / "party_a.parquet",
    "ORG_B": DATA_DIR / "party_b.parquet",
    "ORG_C": DATA_DIR / "party_c.parquet",
}
EXPECTED_COLUMNS = ["household_id", "organization_id", "timestamp", "energy_kwh"]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def household_digest(household_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(household_ids)).encode("utf-8")).hexdigest()


def serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def rebuild_summary(summary_path: Path = SUMMARY_PATH) -> dict[str, Any]:
    for path in PARTIES.values():
        if not path.is_file():
            raise FileNotFoundError(f"Parquet file not found: {path}")

    before = {organization: file_sha256(path) for organization, path in PARTIES.items()}
    connection = duckdb.connect(":memory:")
    party_summaries: dict[str, Any] = {}
    household_sets: dict[str, set[str]] = {}

    for organization, path in PARTIES.items():
        columns = [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]
        if columns != EXPECTED_COLUMNS:
            raise ValueError(f"Unexpected schema in {path}: {columns}")
        row = connection.execute(
            """SELECT count(DISTINCT household_id), count(*), min(timestamp), max(timestamp),
                      coalesce(sum(energy_kwh), 0), min(organization_id), max(organization_id)
               FROM read_parquet(?)""",
            [str(path)],
        ).fetchone()
        if row[5] != organization or row[6] != organization:
            raise ValueError(f"organization_id mismatch in {path}")
        ids = [
            item[0]
            for item in connection.execute(
                "SELECT DISTINCT household_id FROM read_parquet(?) ORDER BY household_id",
                [str(path)],
            ).fetchall()
        ]
        household_sets[organization] = set(ids)
        party_summaries[organization] = {
            "file": str(path.resolve()),
            "household_count": int(row[0]),
            "record_count": int(row[1]),
            "start_time": serialize(row[2]),
            "end_time": serialize(row[3]),
            "energy_sum": float(row[4]),
            "household_ids_sha256": household_digest(ids),
        }

    organizations = list(PARTIES)
    mutually_exclusive = all(
        household_sets[left].isdisjoint(household_sets[right])
        for index, left in enumerate(organizations)
        for right in organizations[index + 1 :]
    )
    all_households = set().union(*household_sets.values())
    global_start = min(datetime.fromisoformat(item["start_time"]) for item in party_summaries.values())
    global_observed_end = max(datetime.fromisoformat(item["end_time"]) for item in party_summaries.values())

    paths = [str(path) for path in PARTIES.values()]
    interval = connection.execute(
        """WITH timestamps AS (
               SELECT DISTINCT timestamp FROM read_parquet(?)
           ), differences AS (
               SELECT timestamp - lag(timestamp) OVER (ORDER BY timestamp) AS difference
               FROM timestamps
           )
           SELECT min(difference) FROM differences WHERE difference > INTERVAL '0 seconds'""",
        [paths],
    ).fetchone()[0]
    interval = interval or timedelta(minutes=30)
    end_exclusive = global_observed_end + interval
    duration_days = (end_exclusive - global_start).total_seconds() / 86_400
    completeness = connection.execute(
        """WITH per_household AS (
               SELECT household_id, count(*) AS records
               FROM read_parquet(?) GROUP BY household_id
           )
           SELECT min(records), max(records) FROM per_household""",
        [paths],
    ).fetchone()
    expected_records_per_household = round(duration_days * 86_400 / interval.total_seconds())

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_from": "existing_parquet_files",
        "schema": EXPECTED_COLUMNS,
        "parties": party_summaries,
        "households_mutually_exclusive": mutually_exclusive,
        "global": {
            "household_count": len(all_households),
            "record_count": sum(item["record_count"] for item in party_summaries.values()),
            "start_time": global_start.isoformat(),
            "end_time": global_observed_end.isoformat(),
            "energy_sum": sum(item["energy_sum"] for item in party_summaries.values()),
        },
        "continuous_window": {
            "start_time": global_start.isoformat(),
            "end_time_exclusive": end_exclusive.isoformat(),
            "last_observation_time": global_observed_end.isoformat(),
            "days": duration_days,
            "interval_minutes": interval.total_seconds() / 60,
            "expected_records_per_household": expected_records_per_household,
            "minimum_records_per_household": int(completeness[0]),
            "maximum_records_per_household": int(completeness[1]),
            "is_complete": (
                completeness[0] == expected_records_per_household
                and completeness[1] == expected_records_per_household
                and all(
                    item["start_time"] == global_start.isoformat()
                    and item["end_time"] == global_observed_end.isoformat()
                    for item in party_summaries.values()
                )
            ),
        },
    }

    after = {organization: file_sha256(path) for organization, path in PARTIES.items()}
    unchanged = before == after
    if not unchanged:
        raise RuntimeError("A source Parquet file changed while rebuilding the summary")
    summary["source_integrity"] = {
        "algorithm": "SHA-256",
        "before": before,
        "after": after,
        "unchanged": unchanged,
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = summary_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(summary_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    rebuild_summary()
