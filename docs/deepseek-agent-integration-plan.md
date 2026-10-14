# DeepSeek 自然语言 Agent 接入方案

> 生成日期：2026-08-01
> 基线：Git tag `v0.6-before-agent`（已提交，backend 历史已通过 subtree 导入根仓库）

## 一、项目结构检查结果

### 后端

- 依赖管理：`backend/requirements.txt`（fastapi、pydantic、duckdb、pandas、pyarrow、SQLAlchemy、httpx、matplotlib、pytest、uvicorn）。
- FastAPI 配置：`control_plane/main.py` 的 `create_app()`；配置对象为 `control_plane/config.py` 中的 `ControlSettings` dataclass，`get_settings()` 从环境变量读取。
- 已有 HTTP 客户端：httpx（`PartyClient`、`ComputeClient`、`SystemHealthService` 均使用）。venv 中存在未声明的 openai SDK，本方案不引入，统一复用已声明的 httpx 直连 `/chat/completions`。
- 路由前缀：`/api/v1`（控制面）。
- 审计结构：`TaskAudit` 表 + `GET /api/v1/audit/events`、`GET /api/v1/audit/events/{task_id}`；Agent 解析不写任务审计。

### 前端

- 自然语言输入：`main.js` 智能查询页 `<input id="query-input">` + `<button data-action="send-query">`；当前 `handleAction("send-query")` 只是 toast，未接后端。
- 查询表单状态：`state.query` + `readQueryForm()` / `syncGroupByControl()` / `updateQueryRuntime()`；payload 构建在 `query-controller.js` 的 `toTaskPayload()`（非 TIME_SERIES 不携带 group_by）。
- 错误提示：`toast`、`.api-state.error`、`#q-form-error`、`#q-result`、`#q-status`。

## 二、修改文件

### 后端新增

| 文件 | 内容 |
| --- | --- |
| `backend/control_plane/services/deepseek_client.py` | httpx 客户端：`chat_json()`、错误分类、超时/5xx 最多一次重试 |
| `backend/control_plane/services/agent_prompts.py` | 固定系统提示词（解析 + 解释），前端不可传入 |
| `backend/control_plane/services/agent_service.py` | 解析/解释编排：输入校验、注入预过滤、输出白名单校验、相对时间解析、限频、安全日志 |
| `backend/tests/test_agent_parse.py` | 25 项 mock 测试（不调用真实 API） |

### 后端修改

| 文件 | 修改 |
| --- | --- |
| `backend/control_plane/config.py` | 增加 `deepseek_api_key/base_url/model/timeout_seconds`、`agent_rate_limit_per_minute` |
| `backend/common/schemas.py` | `AgentParseRequest/Response`、`AgentExplainRequest/Response`、`TaskDraft` |
| `backend/control_plane/api/routes.py` | `POST /api/v1/agent/parse-query`、`POST /api/v1/agent/explain-result` |
| `backend/control_plane/main.py` | 注入 AgentService（测试可替换） |
| `backend/.env.example` | `DEEPSEEK_API_KEY=`（空）、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DEEPSEEK_TIMEOUT_SECONDS` |

### 前端新增

| 文件 | 内容 |
| --- | --- |
| `frontend/src/api/agent.js` | `parseNaturalLanguageQuery()`、`explainResult()`，走统一 API client |
| `frontend/src/agent/agent-controller.js` | 草案应用逻辑（纯函数 `applyDraft` + 请求状态机，独立于 main.js） |
| `frontend/tests/agent.test.js`、`frontend/tests/agent-dom.test.js` | 前端 15 项测试 |

### 前端修改

| 文件 | 修改 |
| --- | --- |
| `frontend/src/main.js` | `send-query` 接真实解析接口；展示识别结果/缺失/警告；填充并高亮表单；新增“生成智能解读”按钮；**不自动提交** |
| `frontend/src/styles.css` | 少量 `.agent-changed` / 解析状态样式 |

## 三、数据流

```text
用户输入 → 点击发送（按钮禁用）
  → POST /api/v1/agent/parse-query（只带 text + current_form，最多 1000 字符）
  → 后端：注入预过滤 → DeepSeek JSON 输出 → Pydantic + 白名单二次校验
  → 返回 task_draft / missing_fields / warnings / explanation
  → 前端：展示 Agent 回复，填充右侧表单并高亮变更字段
  → 用户点击“提交隐私查询”（现有流程，创建任务/轮询/预算）
  → 结果展示 → 用户点击“生成智能解读” → POST /api/v1/agent/explain-result（只带带噪摘要）
```

解析接口不创建任务、不预留/消费预算、不访问园区节点、不写任务审计。

## 四、安全边界

- 模型只输出查询参数草案；权限、预算、敏感度、裁剪、秘密共享参数全部由现有后端规则决定。
- 输出白名单：`query_type ∈ {SUM,COUNT,AVERAGE,TIME_SERIES}`、`parties ⊆ {ORG_A,ORG_B,ORG_C}`、`group_by ∈ {null,30m,1h,1d}`（TS 必填）、`epsilon ∈ null ∪ (0,5]`。
- 时间只接受数据集白名单 `2012-11-11 ~ 2012-12-11` 内的完整时间；相对时间由后端传入的当前日期解析，不在范围内不猜测。
- 输入含“原始 Parquet / 不要加噪 / 关闭差分隐私 / 份额 / 局部总量 / window_cap / 绕过预算 / 自动提交 / 重复执行”等模式 → 本地预过滤直接 REFUSED；模型输出含 `sensitivity/window_cap/record_cap/budget/share/noise/raw` 等越权字段 → 删除并 REFUSED。
- API Key 只从后端环境变量读取；不写入前端/文档/日志/响应/构建产物。
- 日志只记录 request_id、endpoint、model、latency_ms、success、token_usage、输入字符数与 SHA-256；不记录原文、Key、Authorization、完整模型响应。

## 五、API Key 管理

- 环境变量：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-v4-flash`、`DEEPSEEK_TIMEOUT_SECONDS=20`。
- 只写入 `backend/.env`（已被 .gitignore 忽略）；`.env.example` 中 Key 为空。
- 缺失 Key → 503 “DeepSeek API 未配置”，手动表单不受影响。
- 不打印、不复制、不记录旧 Key；轮换方式：修改 `backend/.env` 后重启控制面。

## 六、失败降级

- 模型不可用（未配置/401/429/超时/5xx/非法 JSON/空内容）：前端 Agent 区域显示对应中文错误，右侧手动表单保持可用，真实查询流程不受影响；不启用 mock Agent、不用固定示例冒充结果。
- 超时/5xx 最多一次安全重试；4xx、参数校验、预算不足不重试。
- 结果解释失败：真实指标仍正常展示，解释区只提示失败。

## 七、测试方案

- 后端：统一 FakeDeepSeekClient（不调用真实 API），覆盖 25 项要求（Key 缺失、SUM/COUNT/AVERAGE 无 group_by、TIME_SERIES=1h、非法枚举拒绝、epsilon 缺失为 null、越权字段拒绝、注入拒绝、非法 JSON/空 content/超时/429、解析不建任务/不扣预算/不写审计、超长输入、日志无 Key）。
- 前端：mock agent API 的 DOM 测试 + 纯函数测试，覆盖 15 项要求；静态扫描 `src/` 与 `dist/` 不含 `DEEPSEEK_API_KEY`、`api.deepseek.com`、`Authorization`。
- 回归：后端 pytest 全量、前端 npm test 全量、npm run build、python 编译检查、node 语法检查。
