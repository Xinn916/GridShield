# 前后端 API 契约草案

## 范围

前端当前通过 `frontend/src/mock.js` 提供全部页面数据，`frontend/src/api.js` 仅保留了请求封装和页面级占位路径。本阶段不修改前端代码；后端只实现三方普通统计查询链路。DID、隐私预算、差分隐私、秘密共享、区块链审计和大模型解释均列为下一阶段。

所有时间使用 ISO 8601，统计区间统一为 `[start_time, end_time)`。组织标识使用 `ORG_A`、`ORG_B`、`ORG_C`。

## 当前已实现

### 服务健康检查

`GET /health` 适用于总控、三个园区节点和两个计算节点。

响应字段：`service`、`status`、`timestamp`、`version`。

### 园区列表与数据状态

`GET /api/v1/parties`

对应前端模块：数据接入页三个园区、系统总览节点状态。

响应为数组，每项包含：`organization_id`、`status`、`url`、`record_count`、`household_count`、`start_time`、`end_time`。节点离线时返回 `status=offline` 和 `error`。

### 创建联合统计任务

`POST /api/v1/tasks`

对应前端模块：智能查询工作台的任务参数与提交动作。

请求示例：

```json
{
  "query_type": "TIME_SERIES",
  "parties": ["ORG_A", "ORG_B", "ORG_C"],
  "start_time": "2012-11-11T00:00:00",
  "end_time": "2012-11-12T00:00:00",
  "group_by": "1h"
}
```

`query_type` 仅允许 `SUM`、`COUNT`、`AVERAGE`、`TIME_SERIES`；`TIME_SERIES` 的 `group_by` 仅允许 `30m`、`1h`、`1d`。响应包含 `task_id`、`status`、查询参数、`created_at`、`updated_at` 和可选 `error`。

### 查询任务与结果

- `GET /api/v1/tasks/{task_id}`：对应最近任务、任务状态。
- `GET /api/v1/tasks/{task_id}/result`：对应查询结果表和趋势图。

结果的公共字段为 `task_id`、`status`、`result`。`result` 包含 `sum`、`count`、`parties`；SUM/COUNT/AVERAGE 另含 `value`，TIME_SERIES 另含 `series[]`，每个点包含 `timestamp`、`sum`、`count`。AVERAGE 的 `value` 为所有园区总和除以总计数。

### 园区内部接口

`POST /internal/statistics` 仅供总控调用，请求字段为 `task_id`、`query_type`、`start_time`、`end_time`、`group_by`。园区节点只查询自身固定 Parquet 文件，不接受 SQL。

`GET /internal/metadata` 返回该园区记录数、家庭数与时间范围。

## 建议的下一阶段接口

| 前端硬编码模块 | 建议路径 | 主要字段 | 当前状态 |
| --- | --- | --- | --- |
| 系统总览 KPI、趋势 | `GET /api/v1/dashboard/overview` | parties、queries、budget、alerts、trend、health | 下一阶段 |
| 最近任务列表 | `GET /api/v1/tasks?limit=5` | items、total、分页字段 | 当前仅支持按 ID 查询 |
| 智能查询自然语言 | `POST /api/v1/agent/queries` | question、plan、template、parameters | 下一阶段（大模型） |
| 节点运行资源 | `GET /api/v1/nodes` | node_id、cpu、memory、latency、status | 下一阶段 |
| 隐私预算 | `GET /api/v1/privacy/budgets` | subject、allocated、used、remaining | 下一阶段（隐私机制） |
| 隐私计算进度 | `GET /api/v1/compute/tasks/{id}` | steps、metrics、events | 下一阶段（秘密共享/噪声） |
| 审计事件 | `GET /api/v1/audit/events` | event_id、task_id、actor、risk、timestamp | 下一阶段（审计存证） |
| 安全策略 | `GET/PUT /api/v1/security/policies` | privacy、clipping、roles、templates | 下一阶段 |

前端的 `mockData.query.params` 含总负荷、可调节负荷、储能容量、隐私预算和模板等字段。本阶段数据只有 `energy_kwh`，因此只映射总用电量统计；其他指标不得伪造为已支持。
