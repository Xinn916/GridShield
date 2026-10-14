from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pyarrow.parquet as pq


PROJECT_DIR = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_DIR / "scripts" / "generate_benchmark_data.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_benchmark_data", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generator_is_schema_compatible_distinct_and_reproducible(tmp_path: Path) -> None:
    generator = load_generator()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generator.generate(1_000, first, PROJECT_DIR / "data_processed")
    generator.generate(1_000, second, PROJECT_DIR / "data_processed")

    reference = pq.read_schema(PROJECT_DIR / "data_processed" / "party_a.parquet").remove_metadata()
    names = ["party_a_benchmark.parquet", "party_b_benchmark.parquet", "party_c_benchmark.parquet"]
    first_digests = []
    for name in names:
        left = first / name
        right = second / name
        assert pq.read_schema(left).remove_metadata() == reference
        assert pq.ParquetFile(left).metadata.num_rows == 1_000
        assert digest(left) == digest(right)
        first_digests.append(digest(left))
    assert len(set(first_digests)) == 3


def test_generated_identifiers_are_explicitly_synthetic(tmp_path: Path) -> None:
    generator = load_generator()
    generator.generate(200, tmp_path, PROJECT_DIR / "data_processed")
    for prefix, name in (("A", "party_a_benchmark.parquet"), ("B", "party_b_benchmark.parquet"), ("C", "party_c_benchmark.parquet")):
        ids = pq.read_table(tmp_path / name, columns=["household_id"])["household_id"].to_pylist()
        assert ids
        assert all(value.startswith(f"SYNTHETIC_{prefix}_HH_") for value in ids)
