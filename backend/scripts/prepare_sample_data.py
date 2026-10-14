from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from inspect_dataset import DEFAULT_DATASET, source_sql


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "data_processed"
PREVIEW_DIRNAME = "preview_snappy"
SEED = 2026
PARTIES = [("ORG_A", "party_a.parquet"), ("ORG_B", "party_b.parquet"), ("ORG_C", "party_c.parquet")]


def serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def id_digest(ids: list[str]) -> str:
    payload = "\n".join(sorted(ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def prepare_sample_data(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    files = sorted(dataset_dir.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found under {dataset_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = output_dir / PREVIEW_DIRNAME
    preview_dir.mkdir(parents=True, exist_ok=True)
    source = source_sql(files)
    connection = duckdb.connect(":memory:")
    connection.execute("SET threads TO 4")
    connection.execute(f"SET temp_directory='{(output_dir / '.duckdb_tmp').as_posix()}'")

    normalized = f"""
        SELECT trim(LCLid) AS household_id,
               try_cast(trim(tstp) AS TIMESTAMP) AS timestamp,
               try_cast(trim("energy(kWh/hh)") AS DOUBLE) AS energy_kwh,
               "energy(kWh/hh)" AS raw_energy
        FROM {source}
    """
    print("Building per-household daily coverage table...")
    connection.execute(
        f"""
        CREATE TEMP TABLE daily_counts AS
        SELECT household_id, cast(timestamp AS DATE) AS day, count(*) AS record_count
        FROM ({normalized})
        WHERE household_id IS NOT NULL AND household_id <> ''
          AND timestamp IS NOT NULL AND energy_kwh IS NOT NULL AND energy_kwh >= 0
        GROUP BY household_id, day
        """
    )
    bounds = connection.execute("SELECT min(day), max(day) FROM daily_counts").fetchone()
    if bounds[0] is None or (bounds[1] - bounds[0]).days < 29:
        raise ValueError("Dataset does not contain a 30-day period")

    window_start = connection.execute(
        """
        WITH calendar AS (
            SELECT day::DATE AS day
            FROM generate_series(?::DATE, ?::DATE, INTERVAL '1 day') AS value(day)
        ), totals AS (
            SELECT day, sum(record_count) AS records FROM daily_counts GROUP BY day
        ), rolling AS (
            SELECT calendar.day,
                   sum(coalesce(totals.records, 0)) OVER (
                       ORDER BY calendar.day ROWS BETWEEN CURRENT ROW AND 29 FOLLOWING
                   ) AS window_records
            FROM calendar LEFT JOIN totals USING (day)
        )
        SELECT day FROM rolling WHERE day <= ?::DATE - INTERVAL '29 days'
        ORDER BY window_records DESC, day ASC LIMIT 1
        """,
        [bounds[0], bounds[1], bounds[1]],
    ).fetchone()[0]
    window_end = window_start + timedelta(days=30)

    connection.execute(
        """
        CREATE TEMP TABLE selected_households AS
        WITH ranked AS (
            SELECT household_id, sum(record_count) AS records,
                   row_number() OVER (
                       ORDER BY sum(record_count) DESC, hash(household_id || ?) ASC, household_id ASC
                   ) AS rank
            FROM daily_counts WHERE day >= ? AND day < ?
            GROUP BY household_id
        )
        SELECT household_id,
               CASE WHEN rank <= 100 THEN 'ORG_A'
                    WHEN rank <= 200 THEN 'ORG_B' ELSE 'ORG_C' END AS organization_id
        FROM ranked WHERE rank <= 300
        """,
        [str(SEED), window_start, window_end],
    )
    selected_count = connection.execute("SELECT count(*) FROM selected_households").fetchone()[0]
    if selected_count != 300:
        raise ValueError(f"Only {selected_count} eligible households were found; 300 are required")

    print(f"Selected window: {window_start} through {window_end} (exclusive)")
    connection.execute(
        f"""
        CREATE TEMP TABLE sample_raw AS
        SELECT n.household_id, s.organization_id, n.timestamp, n.energy_kwh, n.raw_energy
        FROM ({normalized}) n
        JOIN selected_households s USING (household_id)
        WHERE n.timestamp >= ? AND n.timestamp < ?
        """,
        [window_start, window_end],
    )
    cleaning = connection.execute(
        """
        SELECT
            count(*) FILTER (WHERE raw_energy IS NULL OR trim(raw_energy) = '' OR lower(trim(raw_energy)) = 'null') AS missing_energy,
            count(*) FILTER (WHERE raw_energy IS NOT NULL AND trim(raw_energy) <> '' AND lower(trim(raw_energy)) <> 'null' AND energy_kwh IS NULL) AS invalid_energy,
            count(*) FILTER (WHERE energy_kwh < 0) AS negative_energy,
            count(*) - count(DISTINCT (household_id, organization_id, timestamp, energy_kwh)) AS duplicates
        FROM sample_raw
        """
    ).fetchone()
    connection.execute(
        """
        CREATE TEMP TABLE sample_clean AS
        SELECT DISTINCT household_id, organization_id, timestamp, energy_kwh
        FROM sample_raw
        WHERE timestamp IS NOT NULL AND energy_kwh IS NOT NULL AND energy_kwh >= 0
        """
    )

    summary: dict[str, Any] = {
        "seed": SEED,
        "selected_window": {"start": window_start.isoformat(), "end_exclusive": window_end.isoformat(), "days": 30},
        "cleaning": {
            "missing_energy_removed": cleaning[0],
            "invalid_energy_removed": cleaning[1],
            "negative_energy_removed": cleaning[2],
            "duplicate_records_removed": cleaning[3],
            "invalid_timestamp_removed": 0,
            "note": "Rows with invalid timestamps cannot be assigned to the selected time window and are reported by dataset_inspection.json.",
        },
        "parties": {},
    }
    for organization_id, filename in PARTIES:
        target = (output_dir / filename).resolve()
        preview_target = (preview_dir / filename).resolve()
        escaped_target = target.as_posix().replace("'", "''")
        connection.execute(
            f"""COPY (
                    SELECT household_id, organization_id, timestamp, energy_kwh
                    FROM sample_clean WHERE organization_id = ?
                    ORDER BY household_id, timestamp
                ) TO '{escaped_target}' (FORMAT PARQUET, COMPRESSION ZSTD)""",
            [organization_id],
        )
        preview_frame = connection.execute(
            """SELECT household_id, organization_id, timestamp, energy_kwh
               FROM sample_clean WHERE organization_id = ?
               ORDER BY household_id, timestamp""",
            [organization_id],
        ).fetch_df()
        preview_frame.to_parquet(
            preview_target,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        row = connection.execute(
            """SELECT count(DISTINCT household_id), count(*), min(timestamp), max(timestamp), sum(energy_kwh)
               FROM sample_clean WHERE organization_id = ?""",
            [organization_id],
        ).fetchone()
        ids = [item[0] for item in connection.execute(
            "SELECT household_id FROM selected_households WHERE organization_id = ? ORDER BY household_id",
            [organization_id],
        ).fetchall()]
        summary["parties"][organization_id] = {
            "file": str(target),
            "preview_file": str(preview_target),
            "preview_compression": "snappy",
            "household_count": row[0],
            "record_count": row[1],
            "time_range": {"start": serialize(row[2]), "end": serialize(row[3])},
            "energy_kwh_sum": float(row[4] or 0),
            "household_ids_sha256": id_digest(ids),
        }

    summary_path = output_dir / "sample_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare three deterministic 100-household Parquet samples.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    prepare_sample_data(args.dataset_dir, args.output_dir)


if __name__ == "__main__":
    main()
