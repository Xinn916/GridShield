from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_DIR / "dataset" / "halfhourly_dataset"
DEFAULT_REPORT = PROJECT_DIR / "backend" / "reports" / "dataset_inspection.json"


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def source_sql(files: list[Path]) -> str:
    paths = ", ".join("'" + file.as_posix().replace("'", "''") + "'" for file in files)
    return f"read_csv([{paths}], header=true, all_varchar=true, union_by_name=true)"


def inspect_dataset(dataset_dir: Path, report_path: Path) -> dict[str, Any]:
    files = sorted(dataset_dir.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found under {dataset_dir}")

    connection = duckdb.connect(":memory:")
    connection.execute("SET threads TO 4")
    source = source_sql(files)
    columns = [row[0] for row in connection.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    required = {"LCLid", "tstp", "energy(kWh/hh)"}
    missing = required.difference(columns)
    if missing:
        raise ValueError(f"Required columns missing: {sorted(missing)}; actual columns: {columns}")

    samples = [dict(zip(columns, row)) for row in connection.execute(f"SELECT * FROM {source} LIMIT 10").fetchall()]
    aggregate = connection.execute(
        f"""
        SELECT
            count(*) AS total_records,
            count(DISTINCT nullif(trim(LCLid), '')) AS households,
            min(try_cast(trim(tstp) AS TIMESTAMP)) AS min_timestamp,
            max(try_cast(trim(tstp) AS TIMESTAMP)) AS max_timestamp,
            count(*) FILTER (WHERE LCLid IS NULL OR trim(LCLid) = '' OR lower(trim(LCLid)) = 'null') AS missing_household,
            count(*) FILTER (WHERE tstp IS NULL OR trim(tstp) = '' OR lower(trim(tstp)) = 'null') AS missing_timestamp,
            count(*) FILTER (WHERE "energy(kWh/hh)" IS NULL OR trim("energy(kWh/hh)") = '' OR lower(trim("energy(kWh/hh)")) = 'null') AS missing_energy,
            count(*) FILTER (WHERE tstp IS NOT NULL AND trim(tstp) <> '' AND lower(trim(tstp)) <> 'null' AND try_cast(trim(tstp) AS TIMESTAMP) IS NULL) AS invalid_timestamp,
            count(*) FILTER (WHERE "energy(kWh/hh)" IS NOT NULL AND trim("energy(kWh/hh)") <> '' AND lower(trim("energy(kWh/hh)")) <> 'null' AND try_cast(trim("energy(kWh/hh)") AS DOUBLE) IS NULL) AS invalid_energy,
            count(*) FILTER (WHERE try_cast(trim("energy(kWh/hh)") AS DOUBLE) < 0) AS negative_energy
        FROM {source}
        """
    ).fetchone()
    names = [item[0] for item in connection.description]
    metrics = dict(zip(names, aggregate))

    completeness = connection.execute(
        f"""
        WITH per_household AS (
            SELECT trim(LCLid) AS household_id,
                   count(*) AS records,
                   min(try_cast(trim(tstp) AS TIMESTAMP)) AS start_time,
                   max(try_cast(trim(tstp) AS TIMESTAMP)) AS end_time,
                   count(*) FILTER (WHERE try_cast(trim(tstp) AS TIMESTAMP) IS NOT NULL
                                     AND try_cast(trim("energy(kWh/hh)") AS DOUBLE) IS NOT NULL
                                     AND try_cast(trim("energy(kWh/hh)") AS DOUBLE) >= 0) AS valid_records
            FROM {source}
            WHERE nullif(trim(LCLid), '') IS NOT NULL
            GROUP BY 1
        )
        SELECT min(records), max(records), avg(records), median(records),
               min(valid_records), max(valid_records), avg(valid_records), median(valid_records)
        FROM per_household
        """
    ).fetchone()

    report = {
        "dataset_path": str(dataset_dir.resolve()),
        "file_count": len(files),
        "file_format": "CSV",
        "total_bytes": sum(file.stat().st_size for file in files),
        "columns": columns,
        "field_mapping": {
            "household_id": "LCLid",
            "timestamp": "tstp",
            "energy_kwh": "energy(kWh/hh)",
        },
        "sample_rows": samples,
        "total_records": metrics["total_records"],
        "household_count": metrics["households"],
        "time_range": {
            "start": json_value(metrics["min_timestamp"]),
            "end": json_value(metrics["max_timestamp"]),
        },
        "missing_values": {
            "household_id": metrics["missing_household"],
            "timestamp": metrics["missing_timestamp"],
            "energy_kwh": metrics["missing_energy"],
        },
        "anomalies": {
            "invalid_timestamp": metrics["invalid_timestamp"],
            "invalid_energy": metrics["invalid_energy"],
            "negative_energy": metrics["negative_energy"],
        },
        "household_completeness": dict(
            zip(
                [
                    "min_records", "max_records", "average_records", "median_records",
                    "min_valid_records", "max_valid_records", "average_valid_records", "median_valid_records",
                ],
                completeness,
            )
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=json_value), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=json_value))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the London half-hourly smart-meter CSV files.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    inspect_dataset(args.dataset_dir, args.output)


if __name__ == "__main__":
    main()
