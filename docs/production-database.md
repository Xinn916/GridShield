# 控制平面数据库：本地 SQLite 与生产 PostgreSQL

## 本地演示模式

默认 `compose.yaml` 使用 SQLite，并通过 `privgrid-control-data` 命名卷保存控制平面元数据。SQLite 中保存：

- 演示用户与哈希后的登录凭证；
- 哈希后的会话 token；
- 数据使用申请、审批与 Grant；
- 隐私预算、预留记录、任务与审计事件。

三个园区的大规模能源读数不进入 SQLite。它们继续由 party-a、party-b、party-c 分别从只读挂载的 Parquet 文件读取，控制平面不会收到 Parquet 路径或原始逐户记录。

SQLite 适用于本地原型、单个 control-plane 和低并发演示，不应被描述为生产集群数据库。

## 可选生产 PostgreSQL

`compose.prod.yaml` 提供官方 `postgres:16-alpine` 服务：

- 数据保存在 `privgrid-postgres-data` 命名卷；
- 通过 `pg_isready` 健康检查；
- 不向宿主机发布 5432 端口；
- control-plane 仍只读取统一的 `DATABASE_URL`；
- Python 使用 SQLAlchemy 和 `psycopg` 驱动。

复制 `.env.docker.example` 为本机 `.env.docker`，将 `POSTGRES_PASSWORD` 替换为强随机密码。启动时由操作者显式提供环境文件：

```powershell
& "C:\Users\ASUS\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" compose --env-file .env.docker -f compose.prod.yaml up -d
```

该配置会创建一套新的 PostgreSQL 元数据数据库，不会自动迁移、复制或删除现有 SQLite 数据。切换已有环境前，应先制定并验证显式数据迁移方案。

当前启动初始化使用 SQLAlchemy `create_all`，对空数据库是幂等的，也没有 `drop_all`。早期 SQLite 的补列兼容逻辑只在 SQLite 执行；后续生产 schema 变更应引入 Alembic 并经过人工审核，不能在启动时执行破坏性迁移。

## 并发与生产边界

隐私预算预留使用带“剩余额度充足”条件的原子 `UPDATE`；预留消费和释放使用状态条件更新。PostgreSQL 会对被更新行加锁，因此当前规则不需要额外修改业务算法。预算首次创建同时受 `(subject_id, data_scope)` 唯一约束保护，并处理并发创建冲突。

多实例部署前仍必须执行并发、故障恢复和事务隔离验证，并配置：

- 反向代理 HTTPS；
- 外部密钥管理；
- 独立数据库备份与恢复演练；
- 监控、容量规划和连接池参数。

## 当前未实现

下列能力仅是规划项，不能标注为已连接或已启用：

- Redis；
- MQTT 实时接入；
- OSS 或其他对象存储服务；
- SMTP 邮件与短信通知网关；
- DID 钱包验签；
- 双因素认证；
- IP 白名单。

