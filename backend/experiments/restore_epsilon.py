"""只重新生成 epsilon_comparison.csv，不运行完整的 BenchmarkRunner。

运行所有 epsilon 对比实验（SUM/COUNT/AVERAGE × 5个DP方法 × 5档epsilon × 100 trials）
并验证 CSV schema、数据库完整性。
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from common.enums import QueryType
from experiments.benchmark_runner import BenchmarkRunner, summarize_trials
from experiments.data import ExperimentData, PARTY_FILES, PROJECT_DIR
from experiments.models import BenchmarkConfig, ExperimentMode

OUTPUT_DIR = PROJECT_DIR / "backend" / "reports" / "experiments"
FORMAL_DATABASE = PROJECT_DIR / "backend" / "control_plane.db"
TARGET_FILE = OUTPUT_DIR / "epsilon_comparison.csv"

REQUIRED_COLUMNS = {
    "query_type",
    "method",
    "epsilon",
    "true_value",
    "mae",
    "rmse",
    "mean_relative_error",
}

FORBIDDEN_HEADERS = {"MAIN CATEGORIES", "CATEGORIES", "ACORN-A", "REFERENCE"}


def fingerprint(path: Path) -> dict | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest()}


def validate_csv(path: Path) -> dict:
    """验证 CSV schema 和内容。"""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])

    # 检查禁止的 header
    forbidden_found = headers & FORBIDDEN_HEADERS
    if forbidden_found:
        raise ValueError(
            f"CSV header 包含 ACORN 数据标识字段: {sorted(forbidden_found)}，"
            f"文件可能已被覆盖！"
        )

    # 检查必需字段
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise ValueError(f"CSV 缺少必需字段: {sorted(missing)}，实际字段: {sorted(headers)}")

    # 读取数据行
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError("CSV 文件为空（无数据行）")

    epsilons = sorted({float(row["epsilon"]) for row in rows})
    expected_epsilons = [0.1, 0.5, 1.0, 2.0, 4.0]
    if epsilons != expected_epsilons:
        raise ValueError(f"epsilon 值不匹配，期望 {expected_epsilons}，实际 {epsilons}")

    query_types = sorted({row["query_type"] for row in rows})
    expected_query_types = ["AVERAGE", "COUNT", "SUM"]
    if query_types != expected_query_types:
        raise ValueError(f"query_type 不匹配，期望 {expected_query_types}，实际 {query_types}")

    methods = sorted({row["method"] for row in rows})
    required_methods = {"CENTRAL_DP", "DISTRIBUTED_DP", "LOCAL_DP"}
    if not required_methods.issubset(methods):
        raise ValueError(f"method 缺少差分隐私方法，期望至少包含 {sorted(required_methods)}，实际 {methods}")

    # 验证数值可解析
    for i, row in enumerate(rows):
        for col in ["epsilon", "true_value", "mae", "rmse", "mean_relative_error"]:
            try:
                float(row[col])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"第 {i + 2} 行（数据第 {i + 1} 行）字段 {col} 无法解析为数值: {row.get(col)}") from exc

    return {
        "row_count": len(rows),
        "columns": sorted(headers),
        "epsilons": epsilons,
        "query_types": query_types,
        "methods": methods,
        "valid": True,
    }


def atomic_write_csv(rows: list[dict], output_path: Path, fieldnames: list[str]) -> None:
    """通过临时文件原子写入，防止覆盖损坏。"""
    # 安全检查：输出路径必须在 backend/reports/experiments 下
    resolved = output_path.resolve()
    root = OUTPUT_DIR.resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"输出路径 {output_path} 不在 {OUTPUT_DIR} 下，拒绝写入")

    fd, tmp_path = tempfile.mkstemp(
        suffix=".csv", prefix="epsilon_restore_", dir=str(root)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        # 原子替换（Windows 需要先删除）
        if output_path.exists():
            output_path.unlink()
        os.rename(tmp_path, str(output_path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def run_epsilon_only():
    """只运行 epsilon 对比实验，不运行 clipping/scalability/communication。"""
    config = BenchmarkConfig(
        query_types=[QueryType.SUM, QueryType.COUNT, QueryType.AVERAGE],
        trials=100,
        epsilons=[0.1, 0.5, 1.0, 2.0, 4.0],
        seed=2026,
        output_dir=OUTPUT_DIR,
        start_time=datetime(2012, 11, 11),
        end_time=datetime(2012, 11, 12),
    )

    data = ExperimentData()
    rng_seed = config.seed
    from experiments.primitives import ExperimentRandom
    from experiments.benchmark_runner import TrialExecutor

    rng = ExperimentRandom(rng_seed)
    executor = TrialExecutor(rng, config.minimum_denominator)

    from common.enums import OrganizationId as OrgId

    all_parties = list(OrgId)

    base = data.prepare(
        all_parties,
        config.start_time,
        config.end_time,
        240.0,
    )

    epsilon_rows = []
    total_runs = len(config.query_types) * len(config.epsilons) * len(ExperimentMode)
    current = 0

    print(f"开始生成 epsilon 对比数据（共 {total_runs} 组，每组 {config.trials} 次试验）...")
    started = time.perf_counter()

    for query_type in config.query_types:
        true_value = base.true_value(query_type)
        for epsilon in config.epsilons:
            for mode in ExperimentMode:
                current += 1
                print(f"  [{current}/{total_runs}] {query_type.value} ε={epsilon} {mode.value} ...", end=" ", flush=True)
                t0 = time.perf_counter()
                trials = [
                    executor.execute(base, query_type, mode, epsilon)
                    for _ in range(config.trials)
                ]
                row = summarize_trials(trials, true_value, query_type, mode, epsilon)
                epsilon_rows.append(row)
                elapsed = time.perf_counter() - t0
                print(f"{elapsed:.1f}s")

    elapsed_total = time.perf_counter() - started
    print(f"实验完成，总耗时 {elapsed_total:.1f}s（{elapsed_total / 60:.1f} 分钟）")

    # 获取字段名
    fieldnames = list(epsilon_rows[0].keys()) if epsilon_rows else []

    return epsilon_rows, fieldnames


def main():
    print("=" * 60)
    print("epsilon_comparison.csv 恢复脚本")
    print("=" * 60)

    # 1. 运行前快照
    print("\n[1/5] 运行前完整性快照...")
    before_db = fingerprint(FORMAL_DATABASE)
    before_parquet = {party.value: fingerprint(path) for party, path in PARTY_FILES.items()}
    print(f"  Database SHA-256: {before_db['sha256'][:16]}...")
    for party, fp in before_parquet.items():
        print(f"  {party} SHA-256: {fp['sha256'][:16]}...")

    # 2. 运行 epsilon 实验
    print("\n[2/5] 运行 epsilon 对比实验...")
    rows, fieldnames = run_epsilon_only()

    # 3. 原子写入
    print(f"\n[3/5] 原子写入 {TARGET_FILE}（{len(rows)} 行）...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(rows, TARGET_FILE, fieldnames)
    print("  写入完成")

    # 4. 验证
    print("\n[4/5] 验证 CSV schema...")
    validation = validate_csv(TARGET_FILE)
    print(f"  行数: {validation['row_count']}")
    print(f"  列: {validation['columns']}")
    print(f"  epsilons: {validation['epsilons']}")
    print(f"  query_types: {validation['query_types']}")
    print(f"  methods: {validation['methods']}")
    print(f"  验证结果: {'通过' if validation['valid'] else '失败'}")

    # 5. 运行后快照与对比
    print("\n[5/5] 运行后完整性验证...")
    after_db = fingerprint(FORMAL_DATABASE)
    after_parquet = {party.value: fingerprint(path) for party, path in PARTY_FILES.items()}

    db_unchanged = before_db["sha256"] == after_db["sha256"]
    parquet_unchanged = all(
        before_parquet[p]["sha256"] == after_parquet[p]["sha256"]
        for p in before_parquet
    )

    print(f"  Database unchanged: {db_unchanged}")
    print(f"  Parquet unchanged: {parquet_unchanged}")

    if not db_unchanged:
        print("  *** 警告：正式数据库被修改！ ***")
    if not parquet_unchanged:
        print("  *** 警告：Parquet 文件被修改！ ***")

    # 保存验证报告
    report = {
        "action": "restore_epsilon_comparison",
        "timestamp": datetime.now().isoformat(),
        "validation": validation,
        "integrity": {
            "database_unchanged": db_unchanged,
            "parquet_unchanged": parquet_unchanged,
            "database_before_sha256": before_db["sha256"],
            "database_after_sha256": after_db["sha256"],
        },
    }
    report_path = OUTPUT_DIR / "epsilon_restore_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n恢复报告已保存: {report_path}")

    print("\n" + "=" * 60)
    print("恢复完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
