from __future__ import annotations

import csv
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_FILES = {
    "epsilon_comparison": "epsilon_comparison.csv",
    "method_comparison": "method_comparison.csv",
    "clipping_comparison": "clipping_comparison.csv",
    "scalability_comparison": "scalability_comparison.csv",
    "communication_comparison": "communication_comparison.csv",
}

DP_METHODS = {"CENTRAL_DP", "LOCAL_DP", "DISTRIBUTED_DP"}
METHOD_LABEL_CN = {
    "CENTRAL_DP": "\u4e2d\u5fc3\u5316\u5dee\u5206\u9690\u79c1\uff08CDP\uff09",
    "LOCAL_DP": "\u672c\u5730\u5dee\u5206\u9690\u79c1\uff08LDP\uff09",
    "DISTRIBUTED_DP": "\u5206\u5e03\u5f0f\u5dee\u5206\u9690\u79c1\uff08DDP\uff09",
}
QUERY_TYPES_EQUAL = ["SUM", "COUNT", "AVERAGE"]

METHOD_COLORS = {
    "CENTRAL_DP": "#1769e0",
    "LOCAL_DP": "#e07b17",
    "DISTRIBUTED_DP": "#12805c",
}
METHOD_MARKERS = {
    "CENTRAL_DP": "o",
    "LOCAL_DP": "s",
    "DISTRIBUTED_DP": "^",
}
METHOD_LINESTYLES = {
    "CENTRAL_DP": "-",
    "LOCAL_DP": "--",
    "DISTRIBUTED_DP": "-.",
}

FORBIDDEN_HEADERS = {"MAIN CATEGORIES", "CATEGORIES", "ACORN-A", "REFERENCE"}


def _setup_chinese_font():
    """Configure matplotlib to use Chinese fonts with graceful fallback."""
    import matplotlib
    import matplotlib.font_manager as fm

    available_fonts = {f.name for f in fm.fontManager.ttflist}
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
    ]
    chosen = None
    for name in candidates:
        if name in available_fonts:
            chosen = name
            break

    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
    else:
        logger.warning(
            "\u672a\u627e\u5230\u4e2d\u6587\u5b57\u4f53\uff0c\u56fe\u8868\u4e2d\u6587\u53ef\u80fd\u65e0\u6cd5\u6b63\u5e38\u663e\u793a\u3002"
            "\u53ef\u7528\u5b57\u4f53: %s",
            sorted(available_fonts)[:20],
        )
        matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]

    matplotlib.rcParams["axes.unicode_minus"] = False


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict, key: str) -> float | None:
    value = row.get(key)
    if value in (None, "", "None"):
        return None
    return float(value)


def _validate_epsilon_csv(path: Path) -> None:
    """Validate that epsilon_comparison.csv has correct schema (not corrupted)."""
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"{path} \u4e3a\u7a7a\uff08\u65e0\u6570\u636e\u884c\uff09")

    headers = set(rows[0].keys())
    forbidden = headers & FORBIDDEN_HEADERS
    if forbidden:
        raise RuntimeError(
            f"{path} \u5305\u542b ACORN \u6570\u636e\u5b57\u6bb5 {sorted(forbidden)}\uff0c\u6587\u4ef6\u53ef\u80fd\u5df2\u88ab\u8986\u76d6\uff0c\u62d2\u7edd\u7ed8\u56fe\uff01"
        )

    required = {"query_type", "method", "epsilon", "true_value", "mae", "rmse", "mean_relative_error"}
    missing = required - headers
    if missing:
        raise RuntimeError(f"{path} \u7f3a\u5c11\u5fc5\u9700\u5b57\u6bb5: {sorted(missing)}")


def _compute_aggregate(
    rows: list[dict],
    error_field: str,
    true_value_field: str = "true_value",
) -> tuple[dict, list[dict]]:
    """
    Compute equal-weight average error across SUM/COUNT/AVERAGE.

    For mean_relative_error: use existing field directly.
    For NRMSE: compute rmse / |true_value| per query_type, then equal-weight average.

    Returns (method_epsilon_map, aggregate_csv_rows).
    """
    import statistics

    dp_rows = [r for r in rows if r["method"] in DP_METHODS]

    # Group by (method, epsilon) and within that by query_type
    grouped: dict[tuple[str, float], dict[str, float]] = {}
    for r in dp_rows:
        key = (r["method"], float(r["epsilon"]))
        qt = r["query_type"]
        if key not in grouped:
            grouped[key] = {}
        if error_field == "mean_relative_error":
            grouped[key][qt] = float(r[error_field])
        else:
            # Compute NRMSE = rmse / |true_value|
            rmse = float(r["rmse"])
            tv = abs(float(r[true_value_field]))
            grouped[key][qt] = rmse / max(tv, 1e-12)

    # Equal-weight average across SUM, COUNT, AVERAGE
    result: dict[tuple[str, float], float] = {}
    for key, qt_values in grouped.items():
        values = [qt_values.get(qt, 0.0) for qt in QUERY_TYPES_EQUAL]
        result[key] = statistics.fmean(values)

    # Build aggregate CSV rows
    csv_rows = []
    for (method, epsilon), avg_val in sorted(result.items(), key=lambda x: (x[0][1], x[0][0])):
        csv_rows.append({
            "epsilon": epsilon,
            "method": method,
            "mean_value": round(avg_val, 10),
            "mean_value_percent": round(avg_val * 100, 6),
            "included_query_types": "SUM,COUNT,AVERAGE",
        })

    return result, csv_rows


def generate_charts(output_dir: Path) -> list[str]:
    os.environ.setdefault("MPLCONFIGDIR", str(output_dir / ".matplotlib-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Validate epsilon CSV before anything else
    epsilon_path = output_dir / CSV_FILES["epsilon_comparison"]
    _validate_epsilon_csv(epsilon_path)

    epsilon_rows = read_csv(epsilon_path)
    method_rows = read_csv(output_dir / CSV_FILES["method_comparison"])
    clipping_rows = read_csv(output_dir / CSV_FILES["clipping_comparison"])
    scalability_rows = read_csv(output_dir / CSV_FILES["scalability_comparison"])

    _setup_chinese_font()
    files = []

    # ================================================================
    # Chart 1: 不同隐私预算下三种差分隐私方法的平均相对误差
    # ================================================================
    mre_aggregate, mre_csv_rows = _compute_aggregate(epsilon_rows, "mean_relative_error")

    fig, ax = plt.subplots(figsize=(9, 5.2))
    for method in ["CENTRAL_DP", "LOCAL_DP", "DISTRIBUTED_DP"]:
        points = sorted(
            [(eps, val) for (m, eps), val in mre_aggregate.items() if m == method],
            key=lambda x: x[0],
        )
        if not points:
            continue
        eps_vals = [p[0] for p in points]
        err_vals = [p[1] * 100 for p in points]
        ax.plot(
            eps_vals,
            err_vals,
            marker=METHOD_MARKERS[method],
            color=METHOD_COLORS[method],
            linestyle=METHOD_LINESTYLES[method],
            linewidth=1.5,
            markersize=6,
            label=METHOD_LABEL_CN[method],
        )
    ax.set_title("\u4e0d\u540c\u9690\u79c1\u9884\u7b97\u4e0b\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u7684\u5e73\u5747\u76f8\u5bf9\u8bef\u5dee")
    ax.set_xlabel("\u9690\u79c1\u9884\u7b97 \u03b5")
    ax.set_ylabel("\u5e73\u5747\u76f8\u5bf9\u8bef\u5dee\uff08%\uff09")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=10, loc="best")
    ax.set_xlim(left=0)
    fig.tight_layout()
    output_path = output_dir / "\u4e0d\u540c\u9690\u79c1\u9884\u7b97\u4e0b\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u7684\u5e73\u5747\u76f8\u5bf9\u8bef\u5dee.png"
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    files.append(output_path.name)

    # ================================================================
    # Chart 2: 不同隐私预算下三种差分隐私方法的归一化均方根误差
    # ================================================================
    nrmse_aggregate, nrmse_csv_rows = _compute_aggregate(epsilon_rows, "nrmse")

    fig, ax = plt.subplots(figsize=(9, 5.2))
    for method in ["CENTRAL_DP", "LOCAL_DP", "DISTRIBUTED_DP"]:
        points = sorted(
            [(eps, val) for (m, eps), val in nrmse_aggregate.items() if m == method],
            key=lambda x: x[0],
        )
        if not points:
            continue
        eps_vals = [p[0] for p in points]
        err_vals = [p[1] * 100 for p in points]
        ax.plot(
            eps_vals,
            err_vals,
            marker=METHOD_MARKERS[method],
            color=METHOD_COLORS[method],
            linestyle=METHOD_LINESTYLES[method],
            linewidth=1.5,
            markersize=6,
            label=METHOD_LABEL_CN[method],
        )
    ax.set_title("\u4e0d\u540c\u9690\u79c1\u9884\u7b97\u4e0b\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u7684\u5f52\u4e00\u5316\u5747\u65b9\u6839\u8bef\u5dee")
    ax.set_xlabel("\u9690\u79c1\u9884\u7b97 \u03b5")
    ax.set_ylabel("\u5f52\u4e00\u5316\u5747\u65b9\u6839\u8bef\u5dee\uff08%\uff09")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=10, loc="best")
    ax.set_xlim(left=0)
    fig.tight_layout()
    output_path = output_dir / "\u4e0d\u540c\u9690\u79c1\u9884\u7b97\u4e0b\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u7684\u5f52\u4e00\u5316\u5747\u65b9\u6839\u8bef\u5dee.png"
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    files.append(output_path.name)

    # ================================================================
    # Chart 3: 三种差分隐私方法综合误差对比（柱状图，epsilon=1.0）
    # ================================================================
    dp_method_rows = [r for r in method_rows if r["method"] in DP_METHODS]
    ref_epsilon = None
    for r in dp_method_rows:
        ref_epsilon = float(r["epsilon"])
        break

    # Equal-weight average of mean_relative_error across SUM/COUNT/AVERAGE
    bar_data: dict[str, list[float]] = {}
    for r in dp_method_rows:
        method = r["method"]
        mre = float(r["mean_relative_error"])
        if method not in bar_data:
            bar_data[method] = []
        bar_data[method].append(mre)

    import statistics
    method_order = ["CENTRAL_DP", "LOCAL_DP", "DISTRIBUTED_DP"]
    bar_values = []
    bar_labels = []
    for method in method_order:
        if method in bar_data and bar_data[method]:
            avg = statistics.fmean(bar_data[method]) * 100
            bar_values.append(avg)
            bar_labels.append(METHOD_LABEL_CN[method])

    fig, ax = plt.subplots(figsize=(8, 5.5))
    bars = ax.bar(
        range(len(bar_labels)),
        bar_values,
        color=[METHOD_COLORS[m] for m in method_order if m in bar_data],
        width=0.5,
        edgecolor="white",
        linewidth=0.8,
    )
    for bar, val in zip(bars, bar_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(bar_values) * 0.01,
            f"{val:.2f}%",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    title_eps = f"\u03b5={ref_epsilon}" if ref_epsilon is not None else ""
    ax.set_title(f"\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u7efc\u5408\u8bef\u5dee\u5bf9\u6bd4\uff08{title_eps}\uff09")
    ax.set_xlabel("\u5dee\u5206\u9690\u79c1\u65b9\u6cd5")
    ax.set_ylabel("\u5e73\u5747\u76f8\u5bf9\u8bef\u5dee\uff08%\uff09")
    ax.set_xticks(range(len(bar_labels)))
    ax.set_xticklabels(bar_labels, fontsize=10)
    ax.grid(True, axis="y", alpha=0.25)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    output_path = output_dir / "\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u7efc\u5408\u8bef\u5dee\u5bf9\u6bd4.png"
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    files.append(output_path.name)

    # ================================================================
    # Chart 4: 不同贡献上限下的总误差对比 (clipping_total_error.png, 中文版)
    # ================================================================
    fig, ax = plt.subplots(figsize=(8, 5))
    query_labels = {"SUM": "SUM\uff08\u6c42\u548c\uff09", "COUNT": "COUNT\uff08\u8ba1\u6570\uff09", "AVERAGE": "AVERAGE\uff08\u5747\u503c\uff09"}
    for query_type in sorted({row["query_type"] for row in clipping_rows}):
        selected = sorted(
            [row for row in clipping_rows if row["query_type"] == query_type],
            key=lambda row: float(row["window_cap"]),
        )
        ax.plot(
            [float(row["window_cap"]) for row in selected],
            [number(row, "total_error") for row in selected],
            marker="o",
            label=query_labels.get(query_type, query_type),
        )
    ax.set_title("\u4e0d\u540c\u8d21\u732e\u4e0a\u9650\u4e0b\u7684\u603b\u8bef\u5dee\u5bf9\u6bd4\uff08\u03b5=1.0\uff09")
    ax.set_xlabel("\u8d21\u732e\u4e0a\u9650\uff08window_cap\uff09")
    ax.set_ylabel("\u5e73\u5747\u7edd\u5bf9\u603b\u8bef\u5dee")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    output_path_cn = output_dir / "\u4e0d\u540c\u8d21\u732e\u4e0a\u9650\u4e0b\u7684\u603b\u8bef\u5dee\u5bf9\u6bd4.png"
    fig.savefig(output_path_cn, dpi=200)
    # Also keep English version
    fig.savefig(output_dir / "clipping_total_error.png", dpi=160)
    plt.close(fig)
    files.append(output_path_cn.name)

    # ================================================================
    # Chart 5: 不同数据规模下的运行时间对比 (runtime_scalability, 中文版)
    # ================================================================
    household_rows = sorted(
        [row for row in scalability_rows if row["scenario"] == "household_count"],
        key=lambda row: int(row["household_count"]),
    )
    party_rows = sorted(
        [row for row in scalability_rows if row["scenario"] == "party_count"],
        key=lambda row: int(row["party_count"]),
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    axes[0].plot(
        [int(row["party_count"]) for row in party_rows],
        [number(row, "total_execution_time_ms") for row in party_rows],
        marker="o",
        label="DISTRIBUTED_DP",
    )
    axes[0].set_xlabel("\u53c2\u4e0e\u65b9\u6570\u91cf")
    axes[0].set_title("\u4e0d\u540c\u53c2\u4e0e\u65b9\u6570\u91cf")
    axes[1].plot(
        [int(row["household_count"]) for row in household_rows],
        [number(row, "total_execution_time_ms") for row in household_rows],
        marker="o",
        label="DISTRIBUTED_DP",
    )
    axes[1].set_xlabel("\u7528\u6237\u6570\u91cf")
    axes[1].set_title("\u4e0d\u540c\u7528\u6237\u6570\u91cf")
    for ax in axes:
        ax.set_ylabel("\u5e73\u5747\u6267\u884c\u65f6\u95f4\uff08ms\uff09")
        ax.grid(True, alpha=0.25)
        ax.legend()
    fig.suptitle("\u4e0d\u540c\u6570\u636e\u89c4\u6a21\u4e0b\u7684\u8fd0\u884c\u65f6\u95f4\u5bf9\u6bd4\uff08\u03b5=1.0\uff09")
    fig.tight_layout()
    output_path_cn = output_dir / "\u4e0d\u540c\u6570\u636e\u89c4\u6a21\u4e0b\u7684\u8fd0\u884c\u65f6\u95f4\u5bf9\u6bd4.png"
    fig.savefig(output_path_cn, dpi=200)
    fig.savefig(output_dir / "runtime_scalability.png", dpi=160)
    plt.close(fig)
    files.append(output_path_cn.name)

    # ================================================================
    # Chart 6: 不同参与方数量下的通信开销对比 (communication_scalability, 中文版)
    # ================================================================
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    axes[0].plot(
        [int(row["party_count"]) for row in party_rows],
        [number(row, "total_communication_bytes") for row in party_rows],
        marker="o",
        color="#12805c",
        label="DISTRIBUTED_DP",
    )
    axes[0].set_xlabel("\u53c2\u4e0e\u65b9\u6570\u91cf")
    axes[0].set_title("\u4e0d\u540c\u53c2\u4e0e\u65b9\u6570\u91cf")
    axes[1].plot(
        [int(row["household_count"]) for row in household_rows],
        [number(row, "total_communication_bytes") for row in household_rows],
        marker="o",
        color="#12805c",
        label="DISTRIBUTED_DP",
    )
    axes[1].set_xlabel("\u7528\u6237\u6570\u91cf")
    axes[1].set_title("\u4e0d\u540c\u7528\u6237\u6570\u91cf")
    for ax in axes:
        ax.set_ylabel("\u5e8f\u5217\u5316\u5b57\u8282\u6570")
        ax.grid(True, alpha=0.25)
        ax.legend()
    fig.suptitle("\u4e0d\u540c\u53c2\u4e0e\u65b9\u6570\u91cf\u4e0b\u7684\u901a\u4fe1\u5f00\u9500\u5bf9\u6bd4\uff08\u03b5=1.0\uff09")
    fig.tight_layout()
    output_path_cn = output_dir / "\u4e0d\u540c\u53c2\u4e0e\u65b9\u6570\u91cf\u4e0b\u7684\u901a\u4fe1\u5f00\u9500\u5bf9\u6bd4.png"
    fig.savefig(output_path_cn, dpi=200)
    fig.savefig(output_dir / "communication_scalability.png", dpi=160)
    plt.close(fig)
    files.append(output_path_cn.name)

    # ================================================================
    # Output aggregate CSV for verification
    # ================================================================
    agg_csv_path = output_dir / "privacy_method_aggregate.csv"
    # Merge MRE and NRMSE aggregate data
    agg_by_key: dict[tuple[str, float], dict] = {}
    for row in mre_csv_rows:
        key = (row["method"], row["epsilon"])
        agg_by_key[key] = {
            "epsilon": row["epsilon"],
            "method": row["method"],
            "mean_relative_error": row["mean_value"],
            "mean_relative_error_percent": row["mean_value_percent"],
            "included_query_types": row["included_query_types"],
        }
    for row in nrmse_csv_rows:
        key = (row["method"], row["epsilon"])
        if key in agg_by_key:
            agg_by_key[key]["mean_normalized_rmse"] = row["mean_value"]
            agg_by_key[key]["mean_normalized_rmse_percent"] = row["mean_value_percent"]
        else:
            agg_by_key[key] = {
                "epsilon": row["epsilon"],
                "method": row["method"],
                "mean_normalized_rmse": row["mean_value"],
                "mean_normalized_rmse_percent": row["mean_value_percent"],
                "included_query_types": row["included_query_types"],
            }

    agg_rows = sorted(agg_by_key.values(), key=lambda x: (x["epsilon"], x["method"]))
    agg_fields = [
        "epsilon", "method", "mean_relative_error", "mean_relative_error_percent",
        "mean_normalized_rmse", "mean_normalized_rmse_percent", "included_query_types",
    ]
    with agg_csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=agg_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(agg_rows)
    files.append(agg_csv_path.name)

    return files


def build_summary(config: dict, output_dir: Path, integrity: dict) -> dict:
    epsilon_rows = read_csv(output_dir / CSV_FILES["epsilon_comparison"])
    clipping_rows = read_csv(output_dir / CSV_FILES["clipping_comparison"])
    method_rows = read_csv(output_dir / CSV_FILES["method_comparison"])
    scalability_rows = read_csv(output_dir / CSV_FILES["scalability_comparison"])
    communication_rows = read_csv(output_dir / CSV_FILES["communication_comparison"])

    best_caps = {}
    for query_type in sorted({row["query_type"] for row in clipping_rows}):
        candidates = [row for row in clipping_rows if row["query_type"] == query_type]
        best = min(candidates, key=lambda row: float(row["total_error"]))
        if query_type == "COUNT":
            best_caps[query_type] = {
                "window_cap": None,
                "total_error": float(best["total_error"]),
                "note": "Not applicable: COUNT sensitivity is 1 and does not depend on window_cap.",
            }
        else:
            best_caps[query_type] = {
                "window_cap": float(best["window_cap"]),
                "total_error": float(best["total_error"]),
            }

    trends = {}
    for query_type in sorted({row["query_type"] for row in epsilon_rows}):
        rows = sorted(
            [
                row
                for row in epsilon_rows
                if row["query_type"] == query_type and row["method"] == "DISTRIBUTED_DP"
            ],
            key=lambda row: float(row["epsilon"]),
        )
        maes = [float(row["mae"]) for row in rows if row["mae"]]
        trends[query_type] = {
            "mae_at_min_epsilon": maes[0] if maes else None,
            "mae_at_max_epsilon": maes[-1] if maes else None,
            "monotonic_non_increasing": all(left >= right for left, right in zip(maes, maes[1:])),
        }

    return {
        "definition": {
            "privacy_unit": "household_id",
            "adjacency": "user-level add/remove",
            "local_dp": "Each participating data holder adds one full Laplace noise draw to its clipped local aggregate before aggregation; this is a data-holder local-noise baseline, not per-meter randomized response.",
        },
        "config": config,
        "best_window_cap_candidates": best_caps,
        "distributed_dp_epsilon_trends": trends,
        "method_rows": method_rows,
        "scalability_rows": scalability_rows,
        "communication_rows": communication_rows,
        "integrity": integrity,
    }


def write_markdown(summary: dict, output_dir: Path) -> None:
    config = summary["config"]
    lines = [
        "# \u5b9e\u9a8c\u62a5\u544a\u6458\u8981 (Experiment Summary)",
        "",
        "## \u914d\u7f6e (Configuration)",
        "",
        f"- \u6570\u636e\u8303\u56f4: `{config['start_time']}` \u81f3 `{config['end_time']}`",
        f"- \u67e5\u8be2\u7c7b\u578b: {', '.join(config['query_types'])}",
        "- \u9690\u79c1\u5355\u5143: `household_id`\uff08\u7528\u6237\u7ea7\u6dfb\u52a0/\u5220\u9664\u90bb\u63a5\uff09",
        f"- \u03b5 \u503c: {', '.join(map(str, config['epsilons']))}",
        f"- \u8d21\u732e\u4e0a\u9650: {', '.join(map(str, config['window_caps']))}",
        f"- \u65b9\u6cd5: {', '.join(config['methods'])}",
        f"- \u6bcf\u7ec4\u8bd5\u9a8c\u6b21\u6570: {config['trials']}",
        f"- \u968f\u673a\u79cd\u5b50: {config['seed'] if config['seed'] is not None else 'SystemRandom'}",
        "",
        "LOCAL_DP \u5728\u672c\u9879\u76ee\u4e2d\u5b9a\u4e49\u4e3a\u6570\u636e\u6301\u6709\u65b9\u7ea7\u672c\u5730\u566a\u58f0\u57fa\u7ebf\uff1a\u6bcf\u4e2a\u53c2\u4e0e\u7684\u56ed\u533a\u5411\u5176\u88ab\u88c1\u526a\u540e\u7684\u5c40\u90e8\u805a\u5408\u7ed3\u679c\u6dfb\u52a0\u4e00\u6b21\u5b8c\u6574\u7684 Laplace \u566a\u58f0\u3002\u8fd9\u4e0d\u662f\u9010\u7535\u8868\u968f\u673a\u54cd\u5e94\u673a\u5236\u3002",
        "",
        "## \u56fe\u8868\u8bf4\u660e",
        "",
        "1. **\u5e73\u5747\u76f8\u5bf9\u8bef\u5dee**\u662f\u5728 SUM\u3001COUNT\u3001AVERAGE \u4e09\u4e2a\u67e5\u8be2\u7c7b\u578b\u4e0a\u8fdb\u884c\u7b49\u6743\u5e73\u5747\uff1b",
        "2. \u7531\u4e8e\u4e09\u4e2a\u67e5\u8be2\u7684\u5355\u4f4d\u548c\u6570\u503c\u8303\u56f4\u4e0d\u540c\uff0c\u672a\u76f4\u63a5\u5e73\u5747\u539f\u59cb MAE\uff1b",
        "3. **\u5f52\u4e00\u5316\u5747\u65b9\u6839\u8bef\u5dee**\u5148\u9664\u4ee5\u5404\u67e5\u8be2\u771f\u5b9e\u503c\uff0c\u518d\u8fdb\u884c\u7b49\u6743\u5e73\u5747\uff1b",
        "4. CDP \u8868\u793a\u4e2d\u5fc3\u5316\u5dee\u5206\u9690\u79c1\uff1b",
        "5. LDP \u662f\u5f53\u524d\u9879\u76ee\u5b9a\u4e49\u7684\u6570\u636e\u6301\u6709\u65b9\u7ea7\u672c\u5730\u566a\u58f0\u5b9e\u9a8c\u57fa\u7ebf\uff1b",
        "6. DDP \u8868\u793a\u672c\u9879\u76ee\u7684\u5206\u5e03\u5f0f\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\uff1b",
        "7. PLAIN \u548c SECRET_SHARE \u4ec5\u7528\u4e8e\u6b63\u786e\u6027\u9a8c\u8bc1\uff0c\u4e0d\u7eb3\u5165\u4e09\u79cd\u5dee\u5206\u9690\u79c1\u65b9\u6cd5\u8bef\u5dee\u66f2\u7ebf\u3002",
        "",
        "## \u53c2\u8003\u65b9\u6cd5\u6307\u6807 (Reference Method Metrics)",
        "",
        "| \u67e5\u8be2 | \u65b9\u6cd5 | \u03b5 | MAE | RMSE | \u5e73\u5747\u76f8\u5bf9\u8bef\u5dee | \u5e73\u5747\u65f6\u95f4 (ms) | \u603b\u5b57\u8282\u6570 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["method_rows"]:
        lines.append(
            f"| {row['query_type']} | {row['method']} | {row['epsilon']} | {row['mae']} | {row['rmse']} | {row['mean_relative_error']} | {row['average_execution_time_ms']} | {row['total_communication_bytes']} |"
        )
    lines.extend(["", "## \u6700\u4f73\u8d21\u732e\u4e0a\u9650 (Best Window Cap Candidates)", "", "| \u67e5\u8be2 | window_cap | \u603b\u8bef\u5dee |", "|---|---:|---:|"])
    for query_type, value in summary["best_window_cap_candidates"].items():
        lines.append(f"| {query_type} | {value['window_cap']} | {value['total_error']} |")
    lines.extend(["", "## \u89c2\u5bdf\u5230\u7684 \u03b5 \u8d8b\u52bf (Observed Epsilon Trends)", ""])
    for query_type, trend in summary["distributed_dp_epsilon_trends"].items():
        lines.append(
            f"- {query_type}: \u6700\u5c0f\u03b5\u65f6 MAE = {trend['mae_at_min_epsilon']}; \u6700\u5927\u03b5\u65f6 MAE = {trend['mae_at_max_epsilon']}; \u5355\u8c03\u975e\u9012\u589e = {trend['monotonic_non_increasing']}."
        )
    lines.extend(
        [
            "",
            "## \u9694\u79bb\u6027 (Isolation)",
            "",
            f"- \u6b63\u5f0f\u6570\u636e\u5e93\u672a\u53d8: {summary['integrity']['database_unchanged']}",
            f"- \u6e90 Parquet \u6587\u4ef6\u672a\u53d8: {summary['integrity']['parquet_unchanged']}",
            "- \u672a\u8c03\u7528\u4e1a\u52a1 API\u3001\u9690\u79c1\u9884\u7b97\u6216\u5ba1\u8ba1\u5de5\u4f5c\u6d41\u3002",
            "",
            "\u672c\u6587\u6863\u4e2d\u6240\u6709\u6570\u503c\u5747\u7531\u751f\u6210\u7684 CSV \u6587\u4ef6\u8ba1\u7b97\u5f97\u51fa\uff0c\u672a\u786c\u7f16\u7801\u4efb\u4f55\u6539\u5584\u767e\u5206\u6bd4\u3002",
        ]
    )
    (output_dir / "experiment_summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_reports(results: dict[str, list[dict]], config: dict, output_dir: Path, integrity: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, filename in CSV_FILES.items():
        write_csv(output_dir / filename, results[key])
    chart_files = generate_charts(output_dir)
    summary = build_summary(config, output_dir, integrity)
    summary["chart_files"] = chart_files
    (output_dir / "experiment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(summary, output_dir)
    return summary
