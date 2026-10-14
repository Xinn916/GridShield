"""Backward-compatible focused entry point for the unified benchmark framework."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from common.enums import QueryType
from experiments.models import BenchmarkConfig
from experiments.run_benchmarks import DEFAULT_OUTPUT_DIR, ensure_output_dir, run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a focused five-method comparison.")
    parser.add_argument("--query-type", choices=["SUM", "COUNT", "AVERAGE"], default="SUM")
    parser.add_argument("--start-time", type=datetime.fromisoformat, default=datetime(2012, 11, 11))
    parser.add_argument("--end-time", type=datetime.fromisoformat, default=datetime(2012, 11, 12))
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    config = BenchmarkConfig(
        query_types=[QueryType(args.query_type)],
        trials=args.repeats,
        seed=args.seed,
        start_time=args.start_time,
        end_time=args.end_time,
        output_dir=ensure_output_dir(args.output_dir),
    )
    run(config)


if __name__ == "__main__":
    main()
