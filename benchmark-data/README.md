# Benchmark 合成数据说明

本目录的数据全部为确定性生成的合成能源负荷数据，不包含真实能源用户记录，也没有复制、抽样或变换 `data_processed/` 中的业务数据行。

这些文件仅用于系统性能 Benchmark，不用于业务分析结论，不参与 Access Request、Approval、Grant 或业务隐私预算流程：

- `party_a_benchmark.parquet`
- `party_b_benchmark.parquet`
- `party_c_benchmark.parquet`

三份文件采用与现有 Party `DataRepository` 兼容的相同 schema：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `household_id` | string | 带 `SYNTHETIC_A/B/C` 前缀的虚拟家庭标识 |
| `organization_id` | string | 对应的 `ORG_A`、`ORG_B` 或 `ORG_C` |
| `timestamp` | timestamp[us] | 从 2026-01-01 开始的连续 30 分钟时间点 |
| `energy_kwh` | double | 非负的合成半小时用电量 |

默认每个 Party 生成 100,000 行，共 300,000 行。基础随机种子为 `20260813`，三方分别使用 `20260814`、`20260815`、`20260816`。相同脚本、参数和依赖版本会生成相同内容；三方 schema 相同，但标识和数值不同。

## 重新生成

在项目根目录执行：

```powershell
backend\.venv\Scripts\python.exe scripts\generate_benchmark_data.py --rows 100000
```

可以通过 `--rows` 生成其他规模。脚本只使用 `pyarrow` 读取现有三方 Parquet 的 schema，不读取真实数据行或真实统计分布。

## 未来部署位置约定

- Party A：`/opt/privgrid/benchmark/party_a_benchmark.parquet`
- Party B：`/opt/privgrid/benchmark/party_b_benchmark.parquet`
- Party C：`/opt/privgrid/benchmark/party_c_benchmark.parquet`

Control 与 Compute 节点不保存 Benchmark 原始数据，仍保持 Party 本地持有模式。
