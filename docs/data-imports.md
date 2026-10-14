# 园区 CSV 安全导入与数据版本

## 范围与数据边界

当前版本仅支持 `FULL_SNAPSHOT` 完整快照导入。DATA_OWNER 通过 control-plane 完成会话认证，文件流仅转发给账号绑定的 Party；Party 是唯一校验、转换和保存导入数据的组件。control-plane 的 SQLite/PostgreSQL 只保存导入元数据和审计事件，不保存 CSV 内容、逐户读数、标识符列表或 Parquet 路径。Compute 节点不会接触 CSV 或 Parquet。

本地演示由 control-plane 作为认证流式网关。FastAPI 的 multipart 层可能为大请求使用生命周期受控的临时上传文件，但应用不会把完整 CSV 写入控制数据库或业务目录，转发时也不会一次性读入内存。生产部署可改为 control-plane 签发短期上传凭证，由浏览器直传绑定 Party；本版本不为此引入对象存储或新网关。

## CSV 结构

三份正式基线 Parquet 的结构一致：

| 列 | 类型 | 规则 |
|---|---|---|
| `household_id` | string | 非空、最多 128 字符、不得以 `= + - @` 开头 |
| `organization_id` | string | 必须等于当前 Party 的 `ORG_A`、`ORG_B` 或 `ORG_C` |
| `timestamp` | timestamp[us] | 无时区 ISO-8601 时间 |
| `energy_kwh` | double | 有限且非负 |

列顺序可以不同，但不得缺列、重复列或增加列。唯一键为 `household_id + timestamp`；发现重复时整个快照为 `INVALID`，不会静默去重。只接受 UTF-8/UTF-8-SIG `.csv`，默认上限 50 MiB、500,000 行。空文件、仅表头文件、NaN、Infinity、非法时间和组织不匹配都会被拒绝。错误报告最多返回有限的错误类型、行号、字段和安全说明，不包含原始行。

## Party 存储与切换

只读基线保持不变：`/app/data/party_a.parquet`、`party_b.parquet`、`party_c.parquet`。每个 Party 使用独立命名卷挂载 `/app/imported`：

- `privgrid-party-a-imports`
- `privgrid-party-b-imports`
- `privgrid-party-c-imports`

成功或失败后原始临时 CSV 都会删除。合法快照以 `data.parquet`、`manifest.json`、`validation-report.json` 保存；无效快照只保留安全报告与 manifest。转换分批进行，临时 Parquet 复读验证 schema 和行数并计算 SHA-256 后，才通过原子目录重命名成为 `VALID`。

上传不会自动启用。DATA_OWNER 可将 `VALID` 版本原子切换为 `ACTIVE`，旧活动版本变为 `ARCHIVED`；也可回滚到历史有效版本或 `BASELINE`。活动指针切换失败时旧指针仍生效，版本目录不会在查询期间删除。同一 Party 进程内使用锁串行化激活操作；多实例生产部署需要数据库锁或分布式锁，本版本不为演示引入 Redis。

查询开始时解析一次活动版本，并在该次查询内固定该不可变文件。活动卷丢失或指针损坏时安全回退基线并产生警告；任务结果和任务审计中的 `dataset_versions` 记录每个 Party 实际使用的 `BASELINE` 或 `IMPORT-*`，不返回内部路径。

## 状态与审计

状态为 `UPLOADED → VALIDATING → VALID/INVALID`、`VALID → ACTIVATING → ACTIVE`，被替换的活动版本为 `ARCHIVED`；系统错误为 `FAILED`。审计记录上传、校验、拒绝、失败、激活、归档、回滚和越权事件，仅包含用户、角色、Party、import_id、SHA-256、行数、状态、原因和时间。

## 配置与持久化注意事项

可配置 `CSV_IMPORT_ENABLED`、`CSV_IMPORT_MAX_BYTES`、`CSV_IMPORT_MAX_ROWS`、`CSV_IMPORT_ALLOWED_ENCODINGS`、`IMPORT_STORAGE_DIR` 和仅服务间使用的 `INTERNAL_SERVICE_TOKEN`。容器重建后命名卷中的导入版本仍保留；普通停止请使用 `docker compose down`。不要执行 `docker compose down -v`，该命令会删除控制数据库和三个 Party 导入卷。

增量追加、MQTT、数据库直连、API/HTTPS 外部接入仍是规划功能，当前未实现。
