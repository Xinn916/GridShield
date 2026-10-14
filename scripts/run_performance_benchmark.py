#!/usr/bin/env python3
"""Run the 12-combination PrivGrid Benchmark matrix through Control Plane only.

The script deliberately uses only the public Control Plane HTTP API. It does not
connect to Party/Compute nodes and does not inspect frontend DOM or Docker state.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import html
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


DEFAULT_BASE_URL = "http://120.46.215.94"
BENCHMARK_ID = "ENERGY_BENCHMARK_V1"
PARTIES = ("ORG_A", "ORG_B", "ORG_C")
QUERY_TYPES = ("SUM", "COUNT", "AVERAGE", "TIME_SERIES")
MODES = ("PLAIN", "SECRET_SHARE", "DISTRIBUTED_DP")
TIME_SERIES_INTERVAL = "1h"
DDP_EPSILON = 1.0
MAX_CONSECUTIVE_FAILURES = 4  # stop after failures exceed three consecutive attempts
RAW_FIELDS = (
    "timestamp", "benchmark_id", "query_type", "mode", "interval", "epsilon",
    "parties", "run_index", "run", "status", "test_id", "duration_ms",
    "communication_bytes", "communication_kb", "average_response_ms",
    "participant_nodes", "error",
)
SUMMARY_FIELDS = (
    "query_type", "mode", "interval", "epsilon", "samples",
    "duration_mean_ms", "duration_std_ms", "duration_min_ms", "duration_max_ms",
    "communication_mean_kb", "communication_std_kb", "communication_min_kb",
    "communication_max_kb",
)


@dataclass(frozen=True)
class Experiment:
    query_type: str
    mode: str
    interval: str | None
    epsilon: float | None

    @property
    def label(self) -> str:
        return f"{self.query_type} / {self.mode}"

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "benchmark_id": BENCHMARK_ID,
            "parties": list(PARTIES),
            "query_type": self.query_type,
            "mode": self.mode,
        }
        if self.interval is not None:
            payload["interval"] = self.interval
        if self.epsilon is not None:
            payload["epsilon"] = self.epsilon
        return payload


def build_experiment_matrix() -> list[Experiment]:
    """Return the fixed query-type-major, mode-minor 4 x 3 matrix."""
    return [
        Experiment(
            query_type=query_type,
            mode=mode,
            interval=TIME_SERIES_INTERVAL if query_type == "TIME_SERIES" else None,
            epsilon=DDP_EPSILON if mode == "DISTRIBUTED_DP" else None,
        )
        for query_type in QUERY_TYPES
        for mode in MODES
    ]


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _redact(text: str) -> str:
    """Keep errors useful without allowing credentials or cookies into output."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(
        r"(?i)(authorization|cookie|token|password|api[_ -]?key)\s*[:=]\s*[^,;\s]+",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] or "请求失败，请稍后重试"


def safe_error_summary(error: BaseException, status: int | None = None) -> str:
    prefix = f"HTTP {status}: " if status else ""
    return _redact(prefix + str(error))


def _json_or_none(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _api_error_message(raw: bytes, status: int) -> str:
    data = _json_or_none(raw)
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("message") or data.get("error")
        if isinstance(detail, list):
            detail = "; ".join(str(item) for item in detail)
        if isinstance(detail, str) and detail.strip():
            return _redact(str(detail))
    return _redact(f"HTTP {status}: 上游接口请求失败")


class ControlPlaneClient:
    """Small cookie-aware HTTP client for the existing Control Plane API."""

    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                if response.status >= 400:
                    raise ApiError(_api_error_message(raw, response.status), response.status)
                return _json_or_none(raw)
        except HTTPError as exc:
            raw = exc.read()
            raise ApiError(_api_error_message(raw, exc.code), exc.code) from exc
        except URLError as exc:
            raise ApiError(f"网络请求失败: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ApiError("请求超时") from exc

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self.request("/api/v1/auth/login", "POST", {"username": username, "password": password})
        if not isinstance(data, dict):
            raise ApiError("登录响应格式无效")
        me = self.request("/api/v1/auth/me")
        if not isinstance(me, dict):
            raise ApiError("登录会话验证失败")
        return me

    def start_test(self, experiment: Experiment) -> dict[str, Any]:
        data = self.request("/api/v1/performance-tests", "POST", experiment.payload())
        if not isinstance(data, dict):
            raise ApiError("性能测试响应格式无效")
        return data

    def get_test(self, test_id: str) -> dict[str, Any]:
        data = self.request(f"/api/v1/performance-tests/{test_id}")
        if not isinstance(data, dict):
            raise ApiError("性能测试详情响应格式无效")
        return data


def wait_for_completion(
    client: ControlPlaneClient,
    response: dict[str, Any],
    timeout_seconds: float,
    poll_interval: float,
) -> dict[str, Any]:
    status = response.get("status")
    if status in {"COMPLETED", "FAILED"}:
        return response
    test_id = response.get("id")
    if not isinstance(test_id, str) or not test_id:
        raise ApiError("性能测试响应缺少 test_id")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
        response = client.get_test(test_id)
        if response.get("status") in {"COMPLETED", "FAILED"}:
            return response
    raise ApiError("Benchmark 执行超时，请稍后重试")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _csv_number(value: Any, digits: int = 6) -> str:
    number = _number(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}".rstrip("0").rstrip(".") or "0"


def execute_once(
    client: ControlPlaneClient,
    experiment: Experiment,
    timeout_seconds: float,
    poll_interval: float,
    run_index: int,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    base: dict[str, Any] = {
        "timestamp": timestamp,
        "benchmark_id": BENCHMARK_ID,
        "query_type": experiment.query_type,
        "mode": experiment.mode,
        "interval": experiment.interval or "",
        "epsilon": _csv_number(experiment.epsilon),
        "parties": "|".join(PARTIES),
        "run_index": run_index,
        "run": run_index,
        "status": "FAILED",
        "test_id": "",
        "duration_ms": "",
        "communication_bytes": "",
        "communication_kb": "",
        "average_response_ms": "",
        "participant_nodes": "",
        "error": "",
    }
    try:
        response = wait_for_completion(
            client,
            client.start_test(experiment),
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        )
        status = response.get("status")
        base["status"] = status if isinstance(status, str) else "FAILED"
        base["test_id"] = response.get("id") if isinstance(response.get("id"), str) else ""
        if base["status"] != "COMPLETED":
            base["error"] = _redact(str(response.get("error") or "Benchmark 执行失败，请稍后重试"))
            return base
        summary = response.get("summary")
        if not isinstance(summary, dict):
            raise ApiError("性能测试响应缺少 summary")
        duration = _number(summary.get("total_duration_ms"))
        communication = _number(summary.get("communication_bytes"))
        if duration is None or communication is None:
            raise ApiError("性能测试响应缺少真实性能指标")
        base["duration_ms"] = _csv_number(duration)
        base["communication_bytes"] = int(communication)
        base["communication_kb"] = _csv_number(communication / 1024)
        base["average_response_ms"] = _csv_number(summary.get("average_response_ms"))
        participant_nodes = summary.get("participant_nodes")
        base["participant_nodes"] = int(participant_nodes) if isinstance(participant_nodes, (int, float)) else ""
        return base
    except Exception as exc:  # Never abort the complete matrix for one failed run.
        base["error"] = safe_error_summary(exc)
        return base


def _stats(values: Iterable[float]) -> tuple[float | None, float | None, float | None, float | None]:
    values = list(values)
    if not values:
        return None, None, None, None
    return (
        statistics.mean(values),
        statistics.pstdev(values) if len(values) > 1 else 0.0,
        min(values),
        max(values),
    )


def summarize(experiment: Experiment, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in rows if row.get("status") == "COMPLETED"]
    durations = [float(row["duration_ms"]) for row in successful if row.get("duration_ms") != ""]
    communications = [float(row["communication_kb"]) for row in successful if row.get("communication_kb") != ""]
    duration_stats = _stats(durations)
    communication_stats = _stats(communications)
    return {
        "query_type": experiment.query_type,
        "mode": experiment.mode,
        "interval": experiment.interval or "",
        "epsilon": _csv_number(experiment.epsilon),
        "samples": len(successful),
        "duration_mean_ms": _csv_number(duration_stats[0]),
        "duration_std_ms": _csv_number(duration_stats[1]),
        "duration_min_ms": _csv_number(duration_stats[2]),
        "duration_max_ms": _csv_number(duration_stats[3]),
        "communication_mean_kb": _csv_number(communication_stats[0]),
        "communication_std_kb": _csv_number(communication_stats[1]),
        "communication_min_kb": _csv_number(communication_stats[2]),
        "communication_max_kb": _csv_number(communication_stats[3]),
    }


def _unique_stem(output_dir: Path, timestamp: str) -> str:
    stem = timestamp
    suffix = 1
    while any((output_dir / f"{prefix}_{stem}.csv").exists() for prefix in ("raw_results", "summary")):
        stem = f"{timestamp}_{suffix:02d}"
        suffix += 1
    return stem


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def generate_plots(summary_rows: list[dict[str, Any]], output_dir: Path, timestamp: str) -> list[Path]:
    """Generate optional paper-friendly PNGs when the existing matplotlib is available."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return []
    paths: list[Path] = []
    x = list(range(len(QUERY_TYPES)))
    width = 0.24
    for metric, ylabel, filename, std_metric in (
        ("duration_mean_ms", "Average Duration (ms)", "duration_comparison", "duration_std_ms"),
        ("communication_mean_kb", "Average Communication (KB)", "communication_comparison", "communication_std_kb"),
    ):
        figure, axis = plt.subplots(figsize=(10, 5.5))
        for index, mode in enumerate(MODES):
            values = []
            errors = []
            for query_type in QUERY_TYPES:
                row = next(item for item in summary_rows if item["query_type"] == query_type and item["mode"] == mode)
                values.append(float(row[metric]) if row[metric] != "" else float("nan"))
                errors.append(float(row[std_metric]) if row[std_metric] != "" else 0.0)
            axis.bar(np.array(x) + (index - 1) * width, values, width, yerr=errors, capsize=3, label=mode)
        axis.set_xticks(x, QUERY_TYPES)
        axis.set_ylabel(ylabel)
        axis.set_title("PrivGrid Benchmark v2")
        axis.legend()
        axis.grid(axis="y", alpha=0.25)
        figure.tight_layout()
        path = output_dir / f"{filename}_{timestamp}.png"
        figure.savefig(path, dpi=160)
        plt.close(figure)
        paths.append(path)
    return paths


def run_matrix(
    client: ControlPlaneClient,
    warmup: int,
    runs: int,
    timeout_seconds: float,
    poll_interval: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for experiment in build_experiment_matrix():
        print("=" * 56)
        print(f"Benchmark: {experiment.label}")
        print(f"Warmup: {warmup}")
        print(f"Runs: {runs}")
        print("=" * 56)
        combo_rows: list[dict[str, Any]] = []
        consecutive_failures = 0
        stopped = False
        for index in range(1, warmup + 1):
            row = execute_once(client, experiment, timeout_seconds, poll_interval, 0)
            ok = row["status"] == "COMPLETED"
            print(f"Warmup {index}/{warmup} ... {'OK' if ok else 'FAILED'}")
            consecutive_failures = 0 if ok else consecutive_failures + 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("连续失败超过 3 次，停止当前组合。")
                stopped = True
                break
        if not stopped:
            for index in range(1, runs + 1):
                row = execute_once(client, experiment, timeout_seconds, poll_interval, index)
                combo_rows.append(row)
                raw_rows.append(row)
                ok = row["status"] == "COMPLETED"
                if ok:
                    consecutive_failures = 0
                    print(f"Run {index}/{runs} ... {_csv_number(row['duration_ms'])} ms | {_csv_number(row['communication_kb'])} KB")
                else:
                    consecutive_failures += 1
                    print(f"Run {index}/{runs} ... FAILED: {row['error']}")
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print("连续失败超过 3 次，停止当前组合。")
                        break
        summary = summarize(experiment, combo_rows)
        summary_rows.append(summary)
        print(f"完成：Mean Duration: {summary['duration_mean_ms'] or '—'} ms | Mean Communication: {summary['communication_mean_kb'] or '—'} KB")
    return raw_rows, summary_rows


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通过 Control Plane 执行 PrivGrid v2 Benchmark 批量实验")
    parser.add_argument("--base-url", default=os.getenv("PRIVGRID_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--username", default="analyst_demo")
    parser.add_argument("--warmup", type=_positive_int, default=3)
    parser.add_argument("--runs", type=_positive_int, default=20)
    parser.add_argument("--timeout", type=float, default=120.0, help="单次测试及轮询超时（秒）")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-results"))
    parser.add_argument("--plots", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    if args.runs == 0:
        parser.error("--runs 必须大于 0")
    if args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("--timeout 和 --poll-interval 必须大于 0")

    password = getpass.getpass("Benchmark password: ")
    client = ControlPlaneClient(args.base_url, timeout=args.timeout)
    try:
        user = client.login(args.username, password)
    except Exception as exc:
        print(f"登录失败: {safe_error_summary(exc)}", file=sys.stderr)
        return 2
    role = user.get("role") if isinstance(user, dict) else None
    if role not in {"ANALYST", "ADMIN"}:
        print("登录账号没有运行 Benchmark 的权限。", file=sys.stderr)
        return 2
    print(f"已通过 Control Plane 登录（{args.username}，{role}）。")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _unique_stem(output_dir, datetime.now().strftime("%Y%m%d_%H%M%S"))
    raw_rows, summary_rows = run_matrix(client, args.warmup, args.runs, args.timeout, args.poll_interval)
    raw_path = output_dir / f"raw_results_{timestamp}.csv"
    summary_path = output_dir / f"summary_{timestamp}.csv"
    write_csv(raw_path, RAW_FIELDS, raw_rows)
    write_csv(summary_path, SUMMARY_FIELDS, summary_rows)
    print(f"原始结果: {raw_path}")
    print(f"汇总结果: {summary_path}")
    if args.plots:
        for path in generate_plots(summary_rows, output_dir, timestamp):
            print(f"图表结果: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
