from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ==============================
# 基本配置
# ==============================

RESULT_DIR = Path("benchmark-results")

# Windows 中文字体
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Arial Unicode MS",
]
plt.rcParams["axes.unicode_minus"] = False


QUERY_ORDER = [
    "SUM",
    "COUNT",
    "AVERAGE",
    "TIME_SERIES",
]

MODE_ORDER = [
    "PLAIN",
    "SECRET_SHARE",
    "DISTRIBUTED_DP",
]

QUERY_LABELS = {
    "SUM": "求和",
    "COUNT": "计数",
    "AVERAGE": "平均值",
    "TIME_SERIES": "时间序列",
}

MODE_LABELS = {
    "PLAIN": "明文计算",
    "SECRET_SHARE": "秘密共享",
    "DISTRIBUTED_DP": "分布式差分隐私",
}


def find_latest_summary():
    files = sorted(
        RESULT_DIR.glob("summary_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            f"在 {RESULT_DIR.resolve()} 中没有找到 summary_*.csv"
        )

    return files[0]


def load_data(path):
    df = pd.read_csv(path)

    required_columns = {
        "query_type",
        "mode",
        "duration_mean_ms",
        "communication_mean_kb",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"CSV 缺少必要字段：{sorted(missing)}"
        )

    return df


def get_value(df, query_type, mode, column):
    row = df[
        (df["query_type"] == query_type)
        & (df["mode"] == mode)
    ]

    if row.empty:
        return np.nan

    return float(row.iloc[0][column])


def add_value_labels(ax, bars, decimal_places=1):
    """
    在柱状图顶部显示具体数值。
    """
    for bar in bars:
        height = bar.get_height()

        if np.isnan(height):
            continue

        ax.annotate(
            f"{height:.{decimal_places}f}",
            xy=(
                bar.get_x() + bar.get_width() / 2,
                height,
            ),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )


def draw_grouped_chart(
    df,
    value_column,
    ylabel,
    output_path,
    decimal_places=1,
):
    x = np.arange(len(QUERY_ORDER))

    width = 0.24

    offsets = {
        "PLAIN": -width,
        "SECRET_SHARE": 0,
        "DISTRIBUTED_DP": width,
    }

    fig, ax = plt.subplots(figsize=(11, 6))

    for mode in MODE_ORDER:
        values = [
            get_value(df, query, mode, value_column)
            for query in QUERY_ORDER
        ]

        bars = ax.bar(
            x + offsets[mode],
            values,
            width,
            label=MODE_LABELS[mode],
        )

        add_value_labels(
            ax,
            bars,
            decimal_places=decimal_places,
        )

    # 横轴
    ax.set_xticks(x)
    ax.set_xticklabels(
        [QUERY_LABELS[q] for q in QUERY_ORDER],
        fontsize=11,
    )

    # 纵轴
    ax.set_ylabel(
        ylabel,
        fontsize=12,
    )

    # 不设置 title
    # 即不会出现 PrivGrid Benchmark v2

    ax.legend(
        fontsize=10,
        frameon=False,
    )

    # 只保留轻微横向参考线
    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.25,
    )

    # 去掉上边框和右边框
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.tick_params(
        axis="both",
        labelsize=10,
    )

    # 给柱顶数字留一点空间
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(ymin, ymax * 1.12)

    plt.tight_layout()

    fig.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    print(f"已生成：{output_path}")


def main():
    summary_path = find_latest_summary()

    print(f"读取实验数据：{summary_path}")

    df = load_data(summary_path)

    # ==============================
    # 图 1：运行时间
    # ==============================

    draw_grouped_chart(
        df=df,
        value_column="duration_mean_ms",
        ylabel="平均运行时间（ms）",
        output_path=RESULT_DIR / "平均运行时间对比.png",
        decimal_places=1,
    )

    # ==============================
    # 图 2：通信开销
    # ==============================

    draw_grouped_chart(
        df=df,
        value_column="communication_mean_kb",
        ylabel="平均通信开销（KB）",
        output_path=RESULT_DIR / "平均通信开销对比.png",
        decimal_places=2,
    )

    print()
    print("绘图完成。")
    print(f"数据来源：{summary_path}")
    print(f"运行时间图：{RESULT_DIR / '平均运行时间对比.png'}")
    print(f"通信开销图：{RESULT_DIR / '平均通信开销对比.png'}")


if __name__ == "__main__":
    main()