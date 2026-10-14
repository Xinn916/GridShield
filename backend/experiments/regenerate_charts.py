"""重新生成实验图表：只读取 reports/experiments 下的 CSV，不重新运行实验。

修复说明（2026-08-01）：本文件曾被 acorn_details.csv 内容意外覆盖，
Git 历史中不存在未损坏版本，按 reporting.generate_charts 的现有接口重建。
"""
from __future__ import annotations

from pathlib import Path

from experiments.data import PROJECT_DIR
from experiments.reporting import generate_charts

OUTPUT_DIR = PROJECT_DIR / "backend" / "reports" / "experiments"


def main() -> None:
    generated = generate_charts(OUTPUT_DIR)
    print(f"已重新生成 {len(generated)} 个图表文件到 {OUTPUT_DIR}")
    for name in generated:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
