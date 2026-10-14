# GridShield

GridShield原名PrivGrid-Agent，部分内部标识和文档仍保留旧名称。

> 数据库部署说明：本地演示使用 SQLite 保存控制平面元数据，园区原始能源数据保持为只读 Parquet；可选生产 PostgreSQL 配置、并发边界和未实现能力见 [docs/production-database.md](docs/production-database.md)。

面向能源可信数据空间的多方安全协同与隐私保护平台。

本项目通过三个数据提供方、两个非串通计算节点、一个控制平面和一个前端服务，实现多方联合统计、秘密共享、分布式差分隐私、隐私预算管理、审计追踪以及自然语言查询 Agent。

## 1. 系统组成

Docker Compose 启动后共运行 7 个容器：

| 服务 | 容器名 | 作用 | 本机端口 |
|---|---|---|---:|
| frontend | `privgrid-frontend` | 前端页面与 Nginx 反向代理 | 8080 |
| control-plane | `privgrid-control` | 任务调度、预算、审计、Agent、结果汇总 | 8000 |
| party-a | `privgrid-party-a` | ORG_A 数据处理节点 | 8101 |
| party-b | `privgrid-party-b` | ORG_B 数据处理节点 | 8102 |
| party-c | `privgrid-party-c` | ORG_C 数据处理节点 | 8103 |
| compute-s1 | `privgrid-compute-s1` | 第一秘密份额计算节点 | 8201 |
| compute-s2 | `privgrid-compute-s2` | 第二秘密份额计算节点 | 8202 |

请求流转关系：

```text
浏览器
  ↓
frontend
  ↓
control-plane
  ↓
party-a / party-b / party-c
  ↓
compute-s1 / compute-s2
  ↓
control-plane 汇总结果
  ↓
frontend 展示
```

## 2. 环境要求

推荐使用 Docker 启动。

需要安装：

- Windows 10/11
- Docker Desktop
- Docker Compose
- Git

确认 Docker 正常：

```powershell
docker version
docker compose version
```

`docker version` 应同时显示 `Client` 和 `Server`。

## 3. 第一次启动

### 3.1 进入项目目录

```powershell
cd D:\Program\ChallengeCup
```

### 3.2 创建 Docker 环境变量文件

项目根目录应存在：

```text
.env.docker.example
```

复制为：

```powershell
Copy-Item .env.docker.example .env.docker
```

编辑 `.env.docker`，按实际需要填写配置，例如：

```env
APP_ENV=development
DEEPSEEK_API_KEY=请填写你自己的API密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=20
DEFAULT_TOTAL_EPSILON=20
```

`APP_ENV` 仅允许 `development`、`testing`、`production`。控制面通过安全的公共配置接口向前端提供该值，界面中的环境徽标不可手动切换。

注意：

- 不要把真实 API Key 写入 `README.md`
- 不要提交 `.env.docker`
- `.env.docker` 应被 `.gitignore` 忽略

检查：

```powershell
git check-ignore .env.docker
git ls-files .env.docker
```

第二条命令应没有输出。

### 3.3 检查 Compose 配置

```powershell
docker compose config -q
```

成功时通常没有输出。

不要使用普通的：

```powershell
docker compose config
```

因为它可能打印展开后的环境变量。

### 3.4 导入比赛离线镜像

```powershell
docker load -i ..\..\02-部署镜像\privgrid-backend-v4.tar
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
```

比赛材料会导入两个本地镜像：

```text
privgrid-backend:v4
privgrid-frontend:v5
```

### 3.5 启动全部服务

```powershell
docker compose up -d
```

### 3.6 查看状态

```powershell
docker compose ps
```

正常情况下应看到 7 个服务均为：

```text
Up ... (healthy)
```

### 3.7 打开系统

浏览器访问：

```text
http://localhost:8080
```

控制平面健康检查：

```text
http://localhost:8000/health
```

## 4. 日常启动

已经构建过镜像时，只需：

```powershell
cd D:\Program\ChallengeCup
docker compose up -d
docker compose ps
```

然后访问：

```text
http://localhost:8080
```

## 5. 修改代码后重新启动

后端或前端代码发生修改后：

```powershell
docker load -i ..\..\02-部署镜像\privgrid-backend-v4.tar
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
docker compose up -d
docker compose ps
```

也可以：

```powershell
docker compose up -d
```

如只修改了 `compose.yaml` 中的环境变量，一般不必重新构建镜像：

```powershell
docker compose up -d --force-recreate
docker compose ps
```

## 6. 常用命令

查看状态：

```powershell
docker compose ps
```

查看全部日志：

```powershell
docker compose logs --tail=100
```

查看某个服务日志：

```powershell
docker compose logs --tail=200 control-plane
docker compose logs --tail=200 party-a
docker compose logs --tail=200 compute-s1
```

实时跟踪日志：

```powershell
docker compose logs -f control-plane
```

按 `Ctrl+C` 退出日志跟踪，不会停止容器。

重启全部服务：

```powershell
docker compose restart
docker compose ps
```

停止并删除容器，但保留数据库卷：

```powershell
docker compose down
```

再次启动：

```powershell
docker compose up -d
```

## 7. 数据持久化

控制平面的 SQLite 数据保存在 Docker 命名卷：

```text
privgrid-control-data
```

其中包括任务、预算和审计等信息。

不要执行：

```powershell
docker compose down -v
```

`-v` 会删除命名卷，可能导致 SQLite 数据丢失。

也不要随意执行：

```powershell
docker system prune -a
```

## 8. 数据隔离

三个数据提供方分别只读挂载自己的数据：

```text
party-a → data_processed/party_a.parquet
party-b → data_processed/party_b.parquet
party-c → data_processed/party_c.parquet
```

检查挂载内容：

```powershell
docker compose exec party-a sh -c "find /app/data -maxdepth 1 -type f -print"
docker compose exec party-b sh -c "find /app/data -maxdepth 1 -type f -print"
docker compose exec party-c sh -c "find /app/data -maxdepth 1 -type f -print"
```

每个 Party 应只看到自己的 Parquet 文件。

## 9. Party 与计算节点通信

三个 Party 容器必须使用 Docker 服务名访问 S1、S2：

```env
COMPUTE_S1_URL=http://compute-s1:8201
COMPUTE_S2_URL=http://compute-s2:8202
```

不能在容器中使用：

```text
http://127.0.0.1:8201
http://127.0.0.1:8202
```

因为容器里的 `127.0.0.1` 指向容器自身。

秘密共享任务出现 502 时，查看：

```powershell
docker compose logs --tail=200 party-a
docker compose logs --tail=200 compute-s1
docker compose logs --tail=200 compute-s2
docker compose logs --tail=200 control-plane
```

## 10. 功能验证

聚合查询示例：

```text
模式：DISTRIBUTED_DP
查询类型：SUM
园区：ORG_A、ORG_B、ORG_C
开始时间：2012-11-11 00:00
结束时间：2012-11-12 00:00
epsilon：1.0
```

检查：

- 任务状态为 `COMPLETED`
- 返回带噪结果
- 隐私预算减少一次
- 生成审计记录

时序查询示例：

```text
模式：DISTRIBUTED_DP
查询类型：TIME_SERIES
园区：ORG_A、ORG_B、ORG_C
开始时间：2012-11-11 00:00
结束时间：2012-11-12 00:00
group_by：1h
epsilon：1.0
```

检查：

- 返回 24 个时间桶
- 折线图正常显示
- 整条曲线只扣一次 epsilon
- 任务状态为 `COMPLETED`
- 生成审计记录

Agent 查询示例：

```text
查询三个园区在2012年11月11日全天每小时的联合用电负荷，隐私预算为1
```

Agent 应只解析并填写表单，不自动提交任务。

## 11. 本地测试

后端：

```powershell
cd D:\Program\ChallengeCup
$env:PYTHONPATH="backend"
python -m pytest -c backend\pytest.ini
```

前端：

```powershell
cd D:\Program\ChallengeCup\frontend
npm test
npm run build
```

## 12. 常见问题

### Docker 命令找不到

确认 Docker Desktop 已启动，然后重新打开 PowerShell 或 VS Code：

```powershell
where.exe docker
docker version
```

### 容器为 unhealthy

```powershell
docker compose ps
docker compose logs --tail=200 服务名
```

### 页面无法打开

```powershell
docker compose ps
docker compose logs --tail=200 frontend
```

访问：

```text
http://localhost:8080
```

### 查询返回 502

检查 Party 和 Compute 日志，并确认：

```powershell
docker compose exec party-a python -c "import os; print(os.getenv('COMPUTE_S1_URL')); print(os.getenv('COMPUTE_S2_URL'))"
```

应输出：

```text
http://compute-s1:8201
http://compute-s2:8202
```

### 修改代码后页面没有变化

```powershell
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
docker compose up -d frontend
```

浏览器执行：

```text
Ctrl + F5
```

## 13. 项目目录

```text
ChallengeCup/
├─ backend/
├─ frontend/
├─ data_processed/
├─ dataset/
├─ docs/
├─ compose.yaml
├─ compose.prod.yaml
├─ .env.docker.example
├─ .env.docker
├─ .dockerignore
├─ .gitignore
└─ README.md
```

## 14. 快速命令汇总

园区 CSV 完整快照导入、校验、版本激活与回滚说明见 [docs/data-imports.md](docs/data-imports.md)。三个正式基线 Parquet 始终只读；导入版本保存在三个 Party 各自的命名卷中，控制数据库仅保存安全元数据。

第一次启动：

```powershell
cd D:\Program\ChallengeCup
Copy-Item .env.docker.example .env.docker
docker compose config -q
docker load -i ..\..\02-部署镜像\privgrid-backend-v4.tar
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
docker compose up -d
docker compose ps
```

日常启动：

```powershell
cd D:\Program\ChallengeCup
docker compose up -d
docker compose ps
```

停止：

```powershell
docker compose down
```

查看日志：

```powershell
docker compose logs --tail=100
```

访问系统：

```text
http://localhost:8080
```


启动：
cd D:\Program\ChallengeCup
docker compose up -d
docker compose ps

docker compose up -d
