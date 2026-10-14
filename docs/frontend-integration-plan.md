# 正式 frontend 接入真实后端 - 集成方案

> 生成日期：2026-07-31
> 原则：不改变现有视觉设计与页面布局；逐步接入真实接口；后端稳定接口不做大规模改动。

## 一、前端现状检查结果

### 1. 技术栈与框架

- 无框架、无构建工具、无 `package.json`：`frontend/` 目前是纯原生 ES Module 单页应用。
- 入口：`frontend/index.html` → `src/main.js`（约 1300 行，单文件包含全部页面渲染与交互）。
- 静态服务：`frontend/server.cjs`（Node http 静态服务器，端口 5173），仅用于本地预览。
- Node 环境：v24.11.1；npm 11.6.2（本机 PowerShell 禁止执行 `npm.ps1`，需用 `npm.cmd`）。

### 2. 路由结构

- 无路由库。`main.js` 内通过 `state.page` + `pages` 映射（`overview / query / compute / data / policy / audit / report / settings`）在单页内切换渲染。
- 登录为本地模拟状态（`state.loggedIn`），导航为侧边栏按钮。

### 3. 页面 / 组件目录

- 页面函数：`overview()`、`queryPage()`、`computePage()`、`dataPage()`、`policyPage()`、`auditPage()`、`reportPage()`、`settingsPage()`，全部定义在 `main.js`。
- 无独立组件目录；公共 UI 片段函数（`statCard`、`panel`、`table`、`tag`、`lineChart`、`donutChart`、`spark`、`computeProgress` 等）也定义在 `main.js`。
- 样式：`src/styles.css`（34KB，含页面级类，如 `.kv-table`、`.form2`、`.advice-box`、`.metric-pills`、`.timeline`）。

### 4. 当前 API 封装

- `src/api.js`：占位层。`request()` 在 `options.mock !== false` 时直接返回假响应；`endpoints` 为页面级路径常量。页面目前从不发起真实请求。
- `main.js` 顶部 `import { endpoints, request } from "./api.js"`，仅在导航切换时调用一次占位请求。

### 5. 图表库

- 无第三方图表库。现有图表均为原生 SVG 手写：
  - `lineChart(labels, values, opts)`：折线图（智能查询、数据接入、总览趋势共用）；
  - `donutChart({total, data})`：CSS conic-gradient 环形图（总览）；
  - `spark()`：迷你折线。

### 6. 环境变量

- 目前没有任何环境变量机制；也没有 `.env`、`.env.example`、Vite 配置。

### 7. 硬编码数据位置

- `src/mock.js`（约 30KB）：登录 DID、通知、总览、数据接入、智能查询、分布式计算、策略、审计、设置、报表的全部展示数据。
- `src/main.js`：页面函数直接引用 `mockData.*`；部分交互（toast、modal）也是写死文案。
- 计划替换的硬编码：智能查询表单/结果、总览 KPI/最近任务/健康度、计算监控任务状态、预算展示、审计事件列表。保留的静态内容（架构流程图、接入方式说明等）不属于后端数据，继续使用 mock。

### 8. 页面与后端现有接口对应关系

| 前端页面 | 对应后端接口 | 现状 |
| --- | --- | --- |
| 智能查询工作台 | `GET /api/v1/parties`、`GET /api/v1/privacy/budgets`、`POST /api/v1/tasks`、`GET /api/v1/tasks/{id}`、`GET /api/v1/tasks/{id}/result` | 已存在，前端未接入 |
| 系统总览 | `GET /api/v1/system/health`、`GET /api/v1/parties`、`GET /api/v1/tasks`、`GET /api/v1/privacy/budgets` | 已存在，前端未接入 |
| 分布式隐私计算监控 | `GET /api/v1/tasks/{id}/monitor`（新增最小安全接口） | 需后端补充 |
| 预算展示 | `GET /api/v1/privacy/budgets` | 已存在，前端未接入 |
| 审计追溯 | `GET /api/v1/audit/events`（新增列表接口）、`GET /api/v1/audit/events/{task_id}` | 已存在单条接口，需补列表 |
| 数据接入 / 策略 / 报表 / 设置 | 后端暂无对应业务接口 | 本阶段保持 mock |

## 二、技术方案

1. 引入 Vite（vanilla JS 模式，不引入框架、不重写页面）：
   - 支持 `VITE_API_BASE_URL`、`VITE_USE_MOCK` 环境变量（`import.meta.env`）；
   - dev server 固定 `http://localhost:5173`（与后端 CORS 配置一致）；
   - 保留 `server.cjs` 作为无构建静态预览的备用入口。
2. 新增统一 API 客户端 `src/api/client.js`（JS + JSDoc 类型注释；项目不使用 TypeScript，不强行引入 TS 工具链）。
3. 新增领域 API 模块：`parties.js`、`tasks.js`、`privacy.js`、`audit.js`、`system.js`。
4. 新增查询控制器与工具模块：`src/query/query-controller.js`、`src/utils/polling.js`、`src/utils/format.js`，将“创建任务、轮询、结果解析、预算刷新”逻辑与 DOM 分离，便于 Node 内置测试。
5. 前端测试使用 Node 24 内置 `node --test` + 全局 `fetch` mock，不新增测试框架依赖。
6. 后端仅做最小安全补充：控制面 CORS、任务监控接口、审计事件列表接口；不动差分隐私 / 秘密共享 / 预算规则 / Parquet / 实验代码。

## 三、准备修改的文件

### 新增文件

| 文件 | 内容 |
| --- | --- |
| `frontend/package.json` | `type: module`、Vite 依赖、`dev/build/preview/test` 脚本 |
| `frontend/vite.config.js` | 端口 5173、strictPort |
| `frontend/.env.example` | `VITE_API_BASE_URL=http://127.0.0.1:8000`、`VITE_USE_MOCK=false` |
| `frontend/.env` | 同 `.env.example` 的本地默认值 |
| `frontend/src/config.js` | 统一读取 `import.meta.env` / `process.env`，导出 API 地址、mock 开关、轮询参数 |
| `frontend/src/api/client.js` | 统一请求层：baseURL、超时、AbortController、JSON/HTTP/网络错误解析 |
| `frontend/src/api/endpoints.js` | 后端路径常量 |
| `frontend/src/api/parties.js` | `GET /api/v1/parties` |
| `frontend/src/api/tasks.js` | 创建/查询/结果/最近任务 |
| `frontend/src/api/privacy.js` | 预算查询 |
| `frontend/src/api/audit.js` | 审计列表与单条 |
| `frontend/src/api/system.js` | 系统健康检查 |
| `frontend/src/utils/polling.js` | 任务轮询（1s、60s 超时、可取消、不自动重试） |
| `frontend/src/utils/format.js` | 数值/中文枚举映射/结果与指标格式化、图表数据构造 |
| `frontend/src/query/query-controller.js` | 表单校验、提交、轮询、结果与预算刷新状态机 |
| `frontend/tests/client.test.js` | API 客户端测试 |
| `frontend/tests/tasks.test.js` | 任务创建参数与校验测试 |
| `frontend/tests/polling.test.js` | 轮询停止/超时/取消测试 |
| `frontend/tests/query-controller.test.js` | 完整提交流程测试 |
| `frontend/tests/format.test.js` | 展示格式化与图表数据测试 |
| `backend/control_plane/services/task_monitor.py` | 任务监控内存存储（仅状态，不含份额/明文） |
| `backend/tests/test_cors.py` | CORS 配置测试 |
| `backend/tests/test_task_monitor.py` | 监控接口与字段安全测试 |
| `backend/tests/test_audit_list.py` | 审计事件列表测试 |

### 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `frontend/src/api.js` | 改为重新导出新客户端（兼容旧引用） |
| `frontend/src/main.js` | 智能查询、总览、计算监控、预算、审计页接入真实数据与状态；保留其余 mock 页面与整体布局 |
| `frontend/src/styles.css` | 仅补充加载/空态/错误提示所需的最小样式类（不改变现有视觉） |
| `backend/control_plane/config.py` | 增加 `cors_origins` 配置（环境变量 `CORS_ORIGINS`，默认仅本地 5173 两个来源） |
| `backend/control_plane/main.py` | 注册 CORSMiddleware |
| `backend/control_plane/api/routes.py` | 增加任务监控、审计事件列表接口，并把监控存储注入 TaskService |
| `backend/control_plane/services/task_service.py` | 生命周期中同步监控状态（不改变预算/算法逻辑） |
| `backend/common/schemas.py` | 增加 `TaskMonitorResponse`、审计列表响应 |
| `backend/.env.example` | 增加 `CORS_ORIGINS` 示例 |
| `README.md`（根目录或 backend） | 增加前后端联调说明 |

## 四、分阶段实施顺序

严格按以下顺序，不跨阶段大改：

1. 阶段零：环境与基础设施（Vite、env、CORS、API 客户端、工具模块）。
2. 第一阶段：智能查询工作台（表单 → 创建任务 → 轮询 → 结果展示 → 隐私说明 → 预算联动）。
3. 第二阶段：系统总览（服务/园区/预算/最近任务/成功失败统计/平均耗时）。
4. 第三阶段：计算监控（新增后端监控接口 + 页面接入）。
5. 第四阶段：预算与审计（预算接口 + 审计列表接口 + 页面接入）。
6. 测试与 README。

## 五、安全与兼容约束

- 不修改三份 Parquet、数据划分脚本、差分隐私算法、秘密共享算法、预算扣除规则、实验结果、验证页面功能。
- 前端不得请求 `/internal/statistics`、计算节点份额接口或任何未加噪结果；页面只渲染后端返回的带噪结果。
- mock 必须显式开启（`VITE_USE_MOCK=true`），默认关闭；关闭后不显示任何硬编码任务结果。
- 后端不可用时前端展示明确错误，不静默回退到 mock。
- 控制面 CORS 默认只允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`，`*` 不作为默认值。

## 六、实施状态（2026-08-01）

- 阶段零～四全部完成：Vite 环境、CORS、统一 API 客户端、智能查询工作台、系统总览、计算监控、预算与审计页均已接入真实后端。
- 后端新增接口：`GET /api/v1/tasks/{task_id}/monitor`（仅阶段与计数，无份额/明文）、`GET /api/v1/audit/events`（审计列表，安全字段）。
- 后端 86 项测试通过（原 72 项 + CORS/监控/审计列表新增）；前端 39 项测试通过（Node 内置测试 + jsdom DOM 冒烟测试，含可选的真实后端端到端用例）。
- 端到端联调验证通过：SUM 任务 `TASK-000023`、TIME_SERIES 任务 `TASK-000024`，预算 20 → 18，CORS 头正确。
- 尚未接入真实接口的页面：数据接入、安全策略、报表中心、系统设置（保持 mock 原型）；DID 登录、区块链存证、大模型 Agent 仍为后续阶段。
