from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from common.enums import QueryType
from experiments.benchmark_runner import BenchmarkRunner
from experiments.data import PARTY_FILES, PROJECT_DIR
from experiments.models import BenchmarkConfig, ExperimentMode
from experiments.reporting import write_reports


DEFAULT_OUTPUT_DIR = PROJECT_DIR / "backend" / "reports" / "experiments"
FORMAL_DATABASE = PROJECT_DIR / "backend" / "control_plane.db"


def fingerprint(path: Path) -> dict | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest()}


def integrity_snapshot() -> dict:
    return {
        "database": fingerprint(FORMAL_DATABASE),
        "parquet": {party.value: fingerprint(path) for party, path in PARTY_FILES.items()},
    }


def ensure_output_dir(path: Path) -> Path:
    resolved = path.resolve()
    root = DEFAULT_OUTPUT_DIR.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"output-dir must be inside {root}")
    return resolved


def parse_query_types(values: list[str]) -> list[QueryType]:
    if "ALL" in values:
        return [QueryType.SUM, QueryType.COUNT, QueryType.AVERAGE]
    return list(dict.fromkeys(QueryType(value) for value in values))


def run(config: BenchmarkConfig) -> dict:
    before = integrity_snapshot()
    results = BenchmarkRunner(config).run()
    after = integrity_snapshot()
    integrity = {
        "database_before": before["database"],
        "database_after": after["database"],
        "database_unchanged": before["database"] == after["database"],
        "parquet_before": before["parquet"],
        "parquet_after": after["parquet"],
        "parquet_unchanged": before["parquet"] == after["parquet"],
    }
    if not integrity["database_unchanged"] or not integrity["parquet_unchanged"]:
        raise RuntimeError("formal database or source Parquet changed during benchmark")
    config_payload = {
        "query_types": [value.value for value in config.query_types],
        "trials": config.trials,
        "epsilons": config.epsilons,
        "window_caps": config.window_caps,
        "party_counts": config.party_counts,
        "household_counts": config.household_counts,
        "seed": config.seed,
        "output_dir": str(config.output_dir),
        "start_time": config.start_time.isoformat(),
        "end_time": config.end_time.isoformat(),
        "methods": [mode.value for mode in ExperimentMode],
    }
    return write_reports(results, config_payload, config.output_dir, integrity)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated privacy-computing benchmarks.")
    parser.add_argument(
        "--query-type",
        nargs="+",
        choices=["SUM", "COUNT", "AVERAGE", "ALL"],
        default=["ALL"],
    )
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--epsilons", nargs="+", type=float, default=[0.1, 0.5, 1.0, 2.0, 4.0])
    parser.add_argument("--window-caps", nargs="+", type=float, default=[20, 30, 50, 100, 240])
    parser.add_argument("--party-counts", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--household-counts", nargs="+", type=int, default=[50, 100, 200, 300])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.trials <= 0:
        parser.error("--trials must be positive")
    if any(value <= 0 for value in args.epsilons):
        parser.error("epsilons must be positive")
    if any(value <= 0 for value in args.window_caps):
        parser.error("window-caps must be positive")
    if any(value not in (1, 2, 3) for value in args.party_counts):
        parser.error("party-counts must be 1, 2, or 3")
    if any(value <= 0 or value > 300 for value in args.household_counts):
        parser.error("household-counts must be between 1 and 300")
    output_dir = ensure_output_dir(args.output_dir)
    config = BenchmarkConfig(
        query_types=parse_query_types(args.query_type),
        trials=args.trials,
        epsilons=args.epsilons,
        window_caps=args.window_caps,
        party_counts=args.party_counts,
        household_counts=args.household_counts,
        seed=args.seed,
        output_dir=output_dir,
    )
    summary = run(config)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "database_unchanged": summary["integrity"]["database_unchanged"],
                "parquet_unchanged": summary["integrity"]["parquet_unchanged"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
