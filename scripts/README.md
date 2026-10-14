# Performance Benchmark 批量实验

`run_performance_benchmark.py` 只访问 Control Plane 的登录和 Performance API，不连接 Party、Compute，不读取前端 DOM，也不调用 Docker。

脚本默认执行 4 种查询类型 × 3 种计算模式，共 12 个组合；每个组合先预热 3 次，再记录 20 次正式运行。正式结果写入 `benchmark-results/`，失败运行会保留在原始 CSV，但不会进入成功样本的均值/标准差。

## 本地冒烟（PowerShell）

```powershell
python scripts/run_performance_benchmark.py --base-url http://120.46.215.94 --username analyst_demo --warmup 0 --runs 1
```

密码会通过 `getpass` 隐藏输入。Windows PowerShell 不需要反斜杠续行；如需换行请使用反引号：

```powershell
python scripts/run_performance_benchmark.py `
  --base-url http://120.46.215.94 `
  --username analyst_demo `
  --warmup 0 `
  --runs 1
```

## 正式实验

```powershell
python scripts/run_performance_benchmark.py --base-url http://120.46.215.94 --username analyst_demo --warmup 3 --runs 20
```

正式实验前请确认入口、安全组、账号权限和六节点健康状态。脚本不会替用户执行 240 次实验，只有运行上述命令才会真正发起请求。

可用参数：

- `--base-url`：Control/Frontend 公网入口，也可传 `http://localhost:8080` 做本地验证；
- `--warmup`：预热次数，默认 3；
- `--runs`：正式次数，默认 20；
- `--timeout`：单次测试及轮询超时，默认 120 秒；
- `--poll-interval`：异步详情轮询间隔，默认 1 秒；
- `--output-dir`：结果目录，默认 `benchmark-results`；
- `--no-plots`：不生成可选 PNG 图表。

TIME_SERIES 固定发送 `interval=1h`；其他查询不发送 interval。只有 DISTRIBUTED_DP 发送 `epsilon=1.0`，PLAIN 和 SECRET_SHARE 不发送 epsilon。通信 KB 以 `communication_bytes / 1024` 计算。

输出文件：

- `raw_results_YYYYMMDD_HHMMSS.csv`：每次正式运行的原始指标和安全错误摘要；
- `summary_YYYYMMDD_HHMMSS.csv`：12 个组合各一行，包含 duration/communication 的 mean、population std、min、max；
- 若 matplotlib 可用，默认额外生成 duration 和 communication 对比 PNG。

不要把密码、Session Cookie、`INTERNAL_SERVICE_TOKEN` 或其他 Secret 写入命令历史、CSV 或日志。
