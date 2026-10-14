"""Generate deterministic synthetic energy data for performance benchmarks.

The generator reads only Parquet schemas from ``data_processed``. It never
loads, samples, or derives statistics from business data rows.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_DIR = PROJECT_DIR / "data_processed"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "benchmark-data"
BASE_SEED = 20260813
DEFAULT_ROWS = 100_000
PARTIES = (
    ("A", "ORG_A", "party_a.parquet", "party_a_benchmark.parquet", BASE_SEED + 1),
    ("B", "ORG_B", "party_b.parquet", "party_b_benchmark.parquet", BASE_SEED + 2),
    ("C", "ORG_C", "party_c.parquet", "party_c_benchmark.parquet", BASE_SEED + 3),
)
EXPECTED_SCHEMA = pa.schema(
    [
        pa.field("household_id", pa.string(), nullable=True),
        pa.field("organization_id", pa.string(), nullable=True),
        pa.field("timestamp", pa.timestamp("us"), nullable=True),
        pa.field("energy_kwh", pa.float64(), nullable=True),
    ]
)


def schema_signature(schema: pa.Schema) -> list[tuple[str, str]]:
    return [(field.name, str(field.type)) for field in schema]


def validate_reference_schemas(reference_dir: Path) -> pa.Schema:
    """Validate schema compatibility without reading any Parquet data row."""
    schemas = [pq.read_schema(reference_dir / item[2]).remove_metadata() for item in PARTIES]
    expected = schema_signature(EXPECTED_SCHEMA)
    for party, schema in zip(PARTIES, schemas, strict=True):
        if schema_signature(schema) != expected:
            raise ValueError(f"{party[2]} schema is incompatible: {schema}")
    if any(schema != schemas[0] for schema in schemas[1:]):
        raise ValueError("Party reference schemas are not identical")
    return schemas[0]


def synthetic_table(party_prefix: str, organization_id: str, rows: int, seed: int) -> pa.Table:
    if rows <= 0:
        raise ValueError("--rows must be a positive integer")

    # 250 virtual households give 400 half-hour observations each at 100K rows.
    household_count = min(250, max(1, math.ceil(rows / 400)))
    row_index = np.arange(rows, dtype=np.int64)
    household_index = row_index % household_count
    interval_index = row_index // household_count
    timestamps = np.datetime64("2026-01-01T00:00:00", "us") + interval_index * np.timedelta64(30, "m")

    rng = np.random.default_rng(seed)
    half_hour = interval_index % 48
    day = interval_index // 48
    morning_peak = np.exp(-0.5 * ((half_hour - 15) / 4.0) ** 2)
    evening_peak = np.exp(-0.5 * ((half_hour - 38) / 5.0) ** 2)
    household_factor = 0.78 + (household_index % 31) * 0.018
    weekly_factor = np.where(day % 7 >= 5, 1.08, 1.0)
    noise = rng.normal(0.0, 0.035, rows)
    energy_kwh = np.maximum(
        0.03,
        (0.16 + 0.34 * morning_peak + 0.58 * evening_peak) * household_factor * weekly_factor + noise,
    ).round(6)

    household_ids = np.array(
        [f"SYNTHETIC_{party_prefix}_HH_{index + 1:04d}" for index in household_index],
        dtype=object,
    )
    return pa.Table.from_arrays(
        [
            pa.array(household_ids, type=pa.string()),
            pa.array(np.full(rows, organization_id, dtype=object), type=pa.string()),
            pa.array(timestamps, type=pa.timestamp("us")),
            pa.array(energy_kwh, type=pa.float64()),
        ],
        schema=EXPECTED_SCHEMA,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(rows: int, output_dir: Path, reference_dir: Path) -> list[dict[str, object]]:
    reference_schema = validate_reference_schemas(reference_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for prefix, organization_id, _, filename, seed in PARTIES:
        target = output_dir / filename
        table = synthetic_table(prefix, organization_id, rows, seed)
        if schema_signature(table.schema) != schema_signature(reference_schema):
            raise AssertionError(f"Generated schema for {organization_id} is incompatible")
        pq.write_table(table, target, compression="zstd", use_dictionary=True)
        metadata = pq.ParquetFile(target).metadata
        generated.append(
            {
                "party": organization_id,
                "file": str(target),
                "rows": metadata.num_rows,
                "seed": seed,
                "sha256": file_sha256(target),
                "bytes": target.stat().st_size,
            }
        )
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic Party benchmark Parquet files.")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="Rows generated for each Party")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE_DIR)
    args = parser.parse_args()
    for result in generate(args.rows, args.output_dir.resolve(), args.reference_dir.resolve()):
        print(
            f"{result['party']}: {result['rows']} rows, seed={result['seed']}, "
            f"bytes={result['bytes']}, sha256={result['sha256']}"
        )


if __name__ == "__main__":
    main()
