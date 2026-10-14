# 能源可信数据空间后端

本项目实现三方 Parquet 数据节点、总控任务管理、贡献度裁剪、定点数编码、两节点加法秘密共享、用户级分布式差分隐私，以及账号密码、HttpOnly Session Cookie、RBAC 和园区权限绑定。PLAIN、SECRET_SHARE 和 DISTRIBUTED_DP 均支持 SUM、COUNT、AVERAGE、TIME_SERIES。当前不包含 DID、钱包或区块链能力。

## 计算模式

- `DISTRIBUTED_DP`：默认模式。园区本地裁剪后生成部分拉普拉斯噪声，将“局部统计 + 部分噪声”整体编码并秘密拆分；总控只能重构带噪联合结果。
- `SECRET_SHARE`：实验对照模式。园区本地裁剪和统计后，只向 S1/S2 分别提交模素数域秘密份额；总控重构无噪联合结果。
- `PLAIN`：保留的实验对照模式。园区向总控返回裁剪后的局部统计，由总控直接汇总。

模式只能通过总控后端环境变量设置，创建任务的前端请求不包含模式字段：

```powershell
$env:CALCULATION_MODE="DISTRIBUTED_DP"
```

贡献度裁剪以 `household_id` 为隐私保护单位。默认单条记录上限为 5.0 kWh、每户每天最多 48 条，并按查询跨度应用窗口总贡献上限。COUNT 表示查询范围内不同家庭的数量。

## 分布式噪声原理

采用用户级 add/remove 邻接关系。COUNT 敏感度固定为 1；SUM 敏感度等于裁剪器为查询窗口计算的 `window_cap`。AVERAGE 不直接加噪，而是使用 70% epsilon 保护 sum、30% epsilon 保护 count，再计算 `noisy_sum / noisy_count`。

对于 `m` 个实际参与方和拉普拉斯尺度 `b=sensitivity/epsilon`，每个园区独立生成：

```text
Gamma(1/m, b) - Gamma(1/m, b)
```

所有园区部分噪声之和服从 `Laplace(0,b)`。生产任务使用 `secrets.SystemRandom`，不设置固定种子；部分噪声不离开园区明文边界，也不写日志。

TIME_SERIES 是一次向量查询，支持 `30m`、`1h`、`1d` 左闭右开时间桶。所有园区生成完全相同的桶，缺失桶补 0。每个家庭先执行记录级裁剪，再形成完整时间序列向量；若向量 L1 总贡献超过 `window_cap`，所有桶按同一比例缩放。整条向量的 L1 敏感度是 `window_cap`，不是 `window_cap * bucket_count`。

DISTRIBUTED_DP TIME_SERIES 中，每个园区对每个桶独立生成 Gamma 差部分噪声，再将“本地桶值 + 部分噪声”定点编码并拆分给 S1/S2。整条曲线共同使用请求中的一次 epsilon。总控重构后只获得带噪曲线，并执行非负截断；峰值、谷值、峰谷差、平均负荷和负荷率只基于截断后的发布曲线计算，这些后处理不额外消费预算。

## 隐私预算

演示主体为 `demo-analyst`，默认 GLOBAL 总预算为 20 epsilon，单次请求 epsilon 必须满足 `0 < epsilon <= 5`。DP 任务执行前预留，成功后消费，失败后释放；`task_id` 唯一预留记录保证重试不重复扣除。

查看预算：

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/privacy/budgets?subject_id=demo-analyst&data_scope=GLOBAL"
```

### 本地演示预算重置（仅开发环境）

`scripts\reset_demo_budget.py` 是仅限本地开发和演示的命令行脚本，不提供 HTTP 接口，严禁用于生产数据库。默认目标是 `demo-analyst` 的 `GLOBAL` 预算。执行前会打印当前总预算、已用、预留和剩余值；不带 `--confirm` 时只预览：

```powershell
cd D:\Program\ChallengeCup
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe backend\scripts\reset_demo_budget.py
```

确认重置为 20 epsilon：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\reset_demo_budget.py --total-epsilon 20 --confirm
```

也可以传入其他本地演示总预算，例如 `--total-epsilon 50 --confirm`。脚本使用 SQLite 事务，只更新预算行，不删除任务、审计或预留记录；若存在活动中的预留，会保留记录并打印警告。生产环境不得运行此脚本。

## SECRET_SHARE 调用流程

1. 总控创建 SQLite 任务，并向 S1/S2 注册任务及预期参与方。
2. 总控把相同查询下发给选中的园区节点。
3. 园区读取自己的 Parquet，在本地执行贡献度裁剪和统计。
4. 浮点统计值以 `SCALE=1_000_000` 编码为整数；COUNT 使用 `scale=1`。
5. 园区把每个整数拆成两份，分别提交到 S1 和 S2。
6. S1/S2 各自收齐参与方份额后，在模素数域内聚合。
7. 总控轮询两个计算节点，取得两个聚合份额并重构。
8. 总控解码最终结果、更新任务状态和执行耗时；数据库不保存园区局部明文统计。

以下命令均在项目根目录 `D:\Program\ChallengeCup` 的 PowerShell 中执行，要求 Python 3.11+。

## 1. 创建环境并安装依赖

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

若 PowerShell 禁止激活脚本，可以直接使用 `backend\.venv\Scripts\python.exe` 执行后续命令。

## 2. 检查数据集

```powershell
python backend\scripts\inspect_dataset.py
```

报告写入 `backend\reports\dataset_inspection.json`。脚本递归读取 `dataset\halfhourly_dataset` 的 CSV，并使用 DuckDB 流式扫描。

## 3. 生成三方样本数据

```powershell
python backend\scripts\prepare_sample_data.py
```

输出为后端使用的 `data_processed\party_a.parquet`、`party_b.parquet`、`party_c.parquet`，以及便于 VS Code 插件预览的 Snappy 副本 `data_processed\preview_snappy\party_a.parquet`、`party_b.parquet`、`party_c.parquet`。预览副本使用 `index=False`，字段与后端文件一致。汇总信息写入 `sample_summary.json`。固定随机种子为 2026，原始数据不会被修改。

## 4. 初始化 SQLite

```powershell
$env:PYTHONPATH="backend"
python -c "from control_plane.main import app; print('SQLite initialized')"
```

默认数据库为 `backend\control_plane.db`。

## 5. 启动六个服务

分别打开六个 PowerShell 窗口；先启动 S1/S2，再启动三个园区，最后启动总控。每个窗口先设置 `$env:PYTHONPATH="backend"`。

```powershell
# 总控，8000
python -m uvicorn control_plane.main:app --port 8000

# 园区 A，8101
$env:PARTY_ID="ORG_A"; python -m uvicorn party_node.main:app --port 8101

# 园区 B，8102
$env:PARTY_ID="ORG_B"; python -m uvicorn party_node.main:app --port 8102

# 园区 C，8103
$env:PARTY_ID="ORG_C"; python -m uvicorn party_node.main:app --port 8103

# 计算节点 S1，8201
$env:COMPUTE_NODE_ID="S1"; python -m uvicorn compute_node.main:app --port 8201

# 计算节点 S2，8202
$env:COMPUTE_NODE_ID="S2"; python -m uvicorn compute_node.main:app --port 8202
```

也可以直接使用统一启动器，服务名依次为 `control`、`party-a`、`party-b`、`party-c`、`compute-s1`、`compute-s2`：

```powershell
python backend\scripts\run_service.py control
python backend\scripts\run_service.py party-a
```

## 6. 调用接口

Swagger 地址为 `http://127.0.0.1:8000/docs`。PowerShell 示例：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/parties
curl.exe -X POST http://127.0.0.1:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"query_type":"SUM","parties":["ORG_A","ORG_B","ORG_C"],"start_time":"2012-11-11T00:00:00","end_time":"2012-11-12T00:00:00","group_by":null,"epsilon":1.0}'
curl.exe -X POST http://127.0.0.1:8000/api/v1/tasks -H "Content-Type: application/json" -d '{"query_type":"TIME_SERIES","parties":["ORG_A","ORG_B","ORG_C"],"start_time":"2012-11-11T00:00:00","end_time":"2012-11-12T00:00:00","group_by":"1h","epsilon":1.0}'
```

再使用返回的任务编号访问：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/tasks/TASK-000001
curl.exe http://127.0.0.1:8000/api/v1/tasks/TASK-000001/result
```

## 7. 运行测试

```powershell
$env:PYTHONPATH="backend"
python -m pytest -c backend\pytest.ini
```

测试覆盖定点数与负数、标量和数组秘密共享、向量贡献裁剪、三种 TIME_SERIES 粒度、PLAIN/SECRET_SHARE 等价性、分布噪声统计性质、四类 DP 查询流程、时间桶一致性、预算预留状态机、重复提交幂等、安全边界和审计存储。

## 8. 运行模式对比实验

离线实验直接复用后端组件和三方 Parquet，不切换生产服务配置，也不消费正式隐私预算：

```powershell
python backend\experiments\compare_modes.py --query-type SUM --repeats 20
```

脚本依次测试 epsilon `0.1/0.5/1.0/2.0/4.0`，输出真实值、私有结果均值、MAE、RMSE、相对误差和平均执行时间到 `backend\reports\experiments\` 的 JSON 与 CSV。

## 独立实验评估框架

统一入口不会调用正式任务 API，不连接或修改 `backend\control_plane.db`，不消费正式隐私预算、不写正式审计，也不会修改 Parquet 或影响正在运行的六个服务。运行前后会对正式数据库和三份 Parquet 计算 SHA-256；如果发现变化，实验会失败并报告。

五种实验方法：

- `PLAIN`：贡献裁剪后的准确联合统计，是误差基准。
- `SECRET_SHARE`：对相同裁剪统计执行定点编码和两份加法共享，不加噪。
- `CENTRAL_DP`：实验可信中心在全局裁剪聚合值上加入一次 Laplace 噪声，仅作为对照。
- `LOCAL_DP`：数据持有方级本地噪声基线；每个参与园区对自己的裁剪聚合值加入一份完整 Laplace 噪声后再聚合。它不是逐电表终端的 randomized response，方差会随参与园区数增长。
- `DISTRIBUTED_DP`：复用 Gamma 差无限可分原理，每方生成 `Gamma(1/m,b)-Gamma(1/m,b)` 部分噪声，再定点编码和秘密共享。

默认对 SUM、COUNT、AVERAGE，五种方法、五档 epsilon 各运行 100 次：

```powershell
cd D:\Program\ChallengeCup
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe -m experiments.run_benchmarks --query-type ALL --trials 100 --seed 2026
```

命令行支持：

```powershell
backend\.venv\Scripts\python.exe -m experiments.run_benchmarks `
  --query-type SUM COUNT AVERAGE `
  --trials 100 `
  --epsilons 0.1 0.5 1.0 2.0 4.0 `
  --window-caps 20 30 50 100 240 `
  --party-counts 1 2 3 `
  --household-counts 50 100 200 300 `
  --seed 2026 `
  --output-dir backend\reports\experiments
```

省略 `--seed` 时实验使用独立 `SystemRandom`；指定 seed 时仅实验随机源可复现，生产任务仍使用安全随机源。输出目录必须位于 `backend\reports\experiments` 内。

固定输出：

- `epsilon_comparison.csv`、`method_comparison.csv`
- `clipping_comparison.csv`、`scalability_comparison.csv`
- `communication_comparison.csv`
- `experiment_summary.json`、`experiment_summary.md`
- `epsilon_mae.png`、`epsilon_rmse.png`
- `method_relative_error.png`、`clipping_total_error.png`
- `runtime_scalability.png`、`communication_scalability.png`

通信量只记录 JSON 序列化后的字节长度，不把秘密份额写入报告。峰值内存使用 Python `tracemalloc`，主要反映实验编排层内存，不等同于 DuckDB 原生内存的完整进程 RSS。

## 9. 验证单个计算节点无法查看真实值

创建任务后，读取任一计算节点的聚合接口：

```powershell
curl.exe http://127.0.0.1:8201/internal/tasks/TASK-000001/aggregate
```

S1 返回的 `payload` 是 `share_index=1` 的模素数域聚合份额，通常表现为一个很大的随机整数，不是用电统计值。只访问 S1 无法恢复结果；必须同时取得 S2 的 `share_index=2` 聚合份额，并由总控执行模加法重构和定点解码。

计算节点日志不记录真实统计值，园区日志只记录裁剪前后数量和被裁剪的总量，不记录原始家庭记录或局部统计结果。

## 后端验证页面

先按“启动六个服务”章节启动 S1/S2、三个园区节点和总控，然后使用桌面浏览器访问：

```text
http://127.0.0.1:8000/verify
```

该页面是 `backend/verification_ui` 下的独立原生 HTML/CSS/JavaScript 工具，不依赖正式 `frontend`、npm 或构建流程。

手动验证步骤：

1. 点击“检查所有服务”，确认六个服务均显示在线。
2. 在查询表单中选择 TIME_SERIES、`group_by=1h`，设置一天时间范围、三个园区和 `epsilon=1.0` 后提交。
3. 在任务状态和带噪结果区域查看实际 `calculation_mode`、敏感度、机制及执行耗时。
4. 比较页面顶部任务前后的剩余预算；每个成功 DISTRIBUTED_DP 查询都会消费请求中的 epsilon。
5. 使用“随机性验证”串行运行相同查询，观察多次带噪结果、均值和样本标准差。
6. 检查结果包含 24 个时间桶、带噪折线图和峰谷指标，并确认预算只减少 1.0。
7. 再次提交相同查询，确认两条带噪曲线不同；检查 S1/S2 日志不包含明文曲线或部分噪声。
8. 使用“非法参数验证”发送 epsilon=0、epsilon=6、空园区和反向时间请求，确认 HTTP 错误且预算不变。

epsilon 对比测试固定消耗 15 epsilon，运行前应先确认预算充足。验证页面不会提供模式切换，也不会请求真实未加噪结果、园区局部统计、partial noise 或秘密份额。

## 当前阶段边界

DISTRIBUTED_DP 下总控只获得带噪结果，不获得真实联合统计或部分噪声。TIME_SERIES 当前按每个时间桶独立加入拉普拉斯噪声，不自动平滑；计算节点份额仍保存在进程内存中，重启后未完成任务需要重新下发。DID、钱包和区块链能力仍未实现。

## 前后端联调（正式 frontend 接入真实后端）

正式前端位于 `frontend/`，使用 Vite（vanilla JS，无框架）作为开发服务器，环境变量通过 `.env` 配置。

### 1. 重置本地演示预算

仅限本地演示，重置前会打印当前预算：

```powershell
cd D:\Program\ChallengeCup
$env:PYTHONPATH="backend"
backend\.venv\Scripts\python.exe backend\scripts\reset_demo_budget.py --total-epsilon 20 --confirm
```

### 2. 启动六个后端服务

方式一：手动打开六个窗口（按 README 前面章节）。方式二：使用后台启动脚本（detached，不占用终端）：

```powershell
python backend\scripts\manage_services.py start
```

服务日志写入 `backend\logs\`，停止全部服务：

```powershell
python backend\scripts\manage_services.py stop
```

### 3. 启动 frontend

```powershell
cd D:\Program\ChallengeCup\frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。

### 4. 配置 VITE_API_BASE_URL

`frontend/.env`（已提供默认值）：

```ini
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCK=false
```

- API 地址统一由 `src/api/client.js` 读取，禁止散落在页面组件中；
- mock 必须显式开启（`VITE_USE_MOCK=true`），默认关闭；关闭后绝不显示硬编码任务结果；
- 后端不可用时页面显示真实错误，不会偷偷回退到假数据。

控制面环境由后端 `APP_ENV` 配置，允许值为 `development`、`testing`、`production`。前端通过只读的 `GET /api/v1/public/config` 获取该值并显示环境徽标，用户不能在界面中切换环境。本地 PowerShell 启动时可在启动控制面前设置：

```powershell
$env:APP_ENV="development"
```

### 开发环境测试账号

仅当后端启用 `DEMO_SEED_ENABLED=true` 且配置对应密码时，以下预置账号可用于本地开发。登录页不会展示这些账号或密码；角色与园区权限始终以后端 Session 返回值为准。

| 用户名 | 开发默认密码 | 角色 | 园区 |
|---|---|---|---|
| `analyst_demo` | `analyst-demo` | 数据分析员 | - |
| `owner_a` | `owner-a-demo` | 园区管理员 | `ORG_A` |
| `owner_b` | `owner-b-demo` | 园区管理员 | `ORG_B` |
| `owner_c` | `owner-c-demo` | 园区管理员 | `ORG_C` |
| `auditor_demo` | `auditor-demo` | 审计员 | - |
| `admin_demo` | `admin-demo` | 系统管理员 | - |

这些密码只用于 `.env.docker.example` 对应的本地开发配置，生产环境必须禁用开发种子账号或更换独立凭据。

### 5. 打开智能查询工作台

在登录页输入账号和密码。登录成功后，前端通过 `/api/v1/auth/me` 读取真实 `username`、`role` 和 `party_id`，再加载对应角色的工作台。数据分析员可从左侧进入“授权查询”；默认时间为 `2012-11-11 00:00 ~ 2012-11-12 00:00`，ε 默认 1.0。

### 6. 提交 TIME_SERIES 任务

查询类型选择“时间序列 TIME_SERIES”，时间粒度选择 `1h`，点击“提交隐私查询”。任务创建后每 1 秒轮询一次状态，最多等待 60 秒；超时只提示，不会自动重复创建任务（避免重复消费预算）。

### 7. 查看预算变化

提交前“查询参数”面板显示剩余预算与本次预计消耗；任务成功或失败后自动重新拉取预算。预算不足时显示后端 409 错误，不会自动降低 ε。

### 8. 查看任务状态和负荷曲线

结果面板展示 24 个 1h 时间桶的带噪负荷折线图（原生 SVG，与现有视觉一致），并展示 peak_value / peak_timestamp / valley_value / valley_timestamp / peak_valley_difference / average_load / load_factor。图表只使用后端返回的带噪 buckets，不请求真实值、园区局部结果或秘密份额。

### 9. 常见问题

- **CORS 报错**：控制面默认只允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`；如需其他来源，通过环境变量配置：
  ```powershell
  $env:CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,https://example.com"
  ```
  生产环境禁止默认使用 `*`。
- **端口占用**：Vite 固定 5173（strictPort），六个后端端口分别为 8000 / 8101-8103 / 8201-8202；被占用时先停止旧进程。
- **预算不足**：默认总预算 20 ε，单次 ε 最大 5；耗尽后按第 1 步重置，或提高 `--total-epsilon`。
- **看不到真实数据**：确认 `frontend/.env` 中 `VITE_USE_MOCK=false`，且 `VITE_API_BASE_URL` 指向运行中的控制面。
- **前端测试**：`cd frontend && npm test`（Node 内置测试运行器，39 项，含 DOM 冒烟测试；`RUN_LIVE_E2E=1` 时额外跑真实后端端到端用例）。

## DeepSeek Agent（自然语言隐私查询）

### 1. 创建并配置 API Key

1. 在 DeepSeek 开放平台创建 API Key（不要粘贴到任何聊天窗口）；
2. 将 Key 写入 `backend/.env`：

```ini
DEEPSEEK_API_KEY=sk-你的真实Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=20
```

Key 只允许出现在后端环境变量中，禁止写入 frontend、README、测试代码、日志或提交到 Git。

### 2. 启动服务

配置 Key 后重启控制面：

```powershell
python backend\scripts\manage_services.py stop
python backend\scripts\manage_services.py start
```

### 3. Agent 自然语言解析流程

1. 智能查询工作台输入自然语言，点击发送；
2. 前端调用 `POST /api/v1/agent/parse-query`（只带文本与当前表单）；
3. 后端把固定系统提示词与输入发送给 DeepSeek，模型只返回 JSON 查询草案；
4. 后端执行白名单二次校验（query_type/parties/group_by/epsilon/时间范围）后才返回；
5. 前端展示识别结果、缺失参数与安全提醒，并自动填入右侧表单（变更字段高亮）；
6. **Agent 绝不自动提交任务**，必须由用户点击“提交隐私查询”后才会创建真实任务、消费 epsilon。

任务完成后可点击“生成智能解读”，调用 `POST /api/v1/agent/explain-result` 对已发布的带噪结果生成通俗说明。

### 4. 模型安全边界

- 模型只能生成查询参数草案，不能决定敏感度、裁剪规则、秘密共享参数或预算；
- 输入含“原始数据 / Parquet / 不要加噪 / 关闭差分隐私 / 秘密份额 / 绕过预算 / 自动提交 / 重复执行”等指令时直接拒绝；
- 模型输出含 sensitivity、window_cap、record_cap、share、noise、raw 等越权字段时整包拒绝；
- 相对时间（今天/昨天/当天）由后端基于当前日期解析，且必须落在数据集时间范围 `2012-11-11 ~ 2012-12-10` 内；
- 解析接口不创建任务、不预留/消费预算、不访问园区节点、不写任务审计。

### 5. 模型不可用时的手动降级

- Agent 不可用只影响左侧自然语言解析区域；
- 右侧手动查询表单仍可正常提交真实查询；
- 不启用伪造的 mock Agent，不拿固定示例冒充模型结果。

### 6. 常见错误

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| DeepSeek API 未配置 | `DEEPSEEK_API_KEY` 为空 | 写入 backend/.env 并重启控制面 |
| 模型认证失败 | 401/403 | 检查 Key 是否正确、是否过期 |
| 模型服务繁忙 | 429 | 稍后重试；单 IP 每分钟最多 10 次解析 |
| 模型解析超时 | 20 秒超时 | 稍后重试（后端自动重试一次） |
| 模型服务异常 | 5xx | 检查 DeepSeek 服务状态 |

### 7. 轮换 Key

修改 `backend/.env` 中的 `DEEPSEEK_API_KEY` 后重启控制面即可；旧 Key 不要写入任何代码或文档。

### 8. 检查前端构建产物不含 Key

```powershell
cd frontend
npm run build
Select-String -Path dist\* -Pattern "DEEPSEEK_API_KEY|api.deepseek.com|Bearer sk-" -Recurse
```

应无任何匹配输出。前端源码中也不得出现 `api.deepseek.com`、`deepseek-v4-flash` 或 `Authorization` 头。
## Benchmark Performance API

性能测试使用独立的合成数据路径 `BENCHMARK_DATA_PATH`，不会替换或回退到业务
Parquet。Control 仅向 Party 发送查询规格，Party 复用正式 `QueryExecutor`；秘密分享和
分布式差分隐私模式继续复用定点数、加法秘密分享、Party 分布式噪声、S1/S2 聚合与
Control 重构代码。重构后的业务结果立即丢弃，公开响应和数据库只保存性能元数据。

登录后的 `ANALYST` 和 `ADMIN` 可使用：

- `POST /api/v1/performance-tests`
- `GET /api/v1/performance-tests?limit=10&offset=0`
- `GET /api/v1/performance-tests/{test_id}`

Benchmark 不要求业务 Grant，也不调用业务 Privacy Budget 的 reserve/consume；正常
`/api/v1/tasks` 的授权和预算校验保持不变。内部 Benchmark 请求需要
`INTERNAL_SERVICE_TOKEN`，并沿 Control → Party → Compute 传递同一个
`X-PrivGrid-Performance-Test-ID`。

通信量按调用方记录实际 JSON 请求体和响应体的 UTF-8 字节数，即
`request_bytes + response_bytes`。当前不包含 HTTP/TCP/IP 头，也不使用 tcpdump；每条
跨节点调用只由调用方记录一次，避免双计。CPU、内存和实时 Mbps 尚未采集，前端继续
显示 `--`，不会生成模拟指标。
