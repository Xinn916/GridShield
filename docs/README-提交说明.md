# PrivGrid 比赛技术实现材料提交说明

本提交包采用完全离线的 Docker 镜像交付方式。评审人员不需要任何云账号、镜像仓库账号、临时令牌或互联网镜像拉取权限。

## 1. 材料结构

```text
PrivGrid-技术实现材料/
├─ 01-完整源代码/
│  └─ PrivGrid-Source.zip
├─ 02-部署镜像/
│  ├─ privgrid-backend-v4.tar
│  └─ privgrid-frontend-v5.tar
├─ 03-部署配置/
│  ├─ docker-compose.yml
│  └─ cloud/
├─ 04-技术文档/
│  └─ PrivGrid部署与操作手册.pdf
└─ 05-补充材料/
```

## 2. 镜像用途

- `privgrid-backend:v4`：Control Plane、Party A/B/C、Compute S1/S2 共用；
- `privgrid-frontend:v5`：Frontend 使用。

两个标签已直接写入随包提供的 TAR，与比赛版 Compose 完全一致，不需要再次标记。

## 3. 标准离线启动流程

```bash
docker load -i privgrid-backend-v4.tar
docker load -i privgrid-frontend-v5.tar
docker image ls
```

准备数据和本机环境文件后，进入 `03-部署配置`：

```bash
docker compose config -q
docker compose up -d
docker compose ps
```

比赛版 Compose 使用本地标签并设置 `pull_policy: never`。启动过程不会访问外部镜像仓库。

## 4. 数据与环境变量

- 三方业务数据必须按 ORG_A/ORG_B/ORG_C 分别放置，不能集中到单一 Party；
- Benchmark 数据必须使用随源码提供的确定性合成数据；
- 环境文件只在部署机器上创建，不进入提交包；
- 六节点部署必须保留并填写 Control/Party/Compute 私网地址；
- 六节点必须使用一致的强随机内部服务令牌；
- 任何 API Key、密码、Cookie、私钥和真实环境文件均不得进入公开材料。

## 5. 六节点离线分发

backend TAR 复制到 Control、Party A/B/C、Compute S1/S2；frontend TAR 只需复制到 Control。各节点加载镜像后，按照 Compute、Party、Control/Frontend 的顺序执行本节点 Compose。

## 6. 验收要点

- `docker image ls` 可直接看到 `privgrid-backend:v4` 与 `privgrid-frontend:v5`；
- 所有比赛版 Compose 的 `image` 字段均引用上述本地标签；
- Compose 不包含强制在线拉取策略；
- 技术材料不包含镜像仓库凭据或临时令牌；
- `docker compose ps` 中相关容器最终进入健康状态；
- 前端、Agent 工作台、审批、授权、任务、审计、CSV 导入及性能测试按手册完成验证。

完整部署、配置变量、健康检查和角色操作见《PrivGrid 部署与操作手册》。