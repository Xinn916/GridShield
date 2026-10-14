# PrivGrid 六节点离线部署说明

本目录是比赛提交版六节点部署配置。所有应用镜像均随技术实现材料离线交付，不需要访问镜像仓库，不需要登录凭据，也不执行在线拉取。

## 1. 离线镜像

提交材料包含：

- `02-部署镜像/privgrid-backend-v4.tar`，加载后标签为 `privgrid-backend:v4`；
- `02-部署镜像/privgrid-frontend-v5.tar`，加载后标签为 `privgrid-frontend:v5`。

`privgrid-backend:v4` 用于 Control Plane、Party A/B/C、Compute S1/S2；`privgrid-frontend:v5` 仅用于 Control 节点的 Frontend。

## 2. 节点与目录

| 节点 | Compose 副本 | 需要的镜像 |
|---|---|---|
| Control | `control/compose.yaml` | backend v4、frontend v5 |
| Party A | `party-a/compose.yaml` | backend v4 |
| Party B | `party-b/compose.yaml` | backend v4 |
| Party C | `party-c/compose.yaml` | backend v4 |
| Compute S1 | `compute-s1/compose.yaml` | backend v4 |
| Compute S2 | `compute-s2/compose.yaml` | backend v4 |

每台机器建议使用 `/opt/privgrid` 作为工作目录，并把对应 Compose 复制为 `/opt/privgrid/compose.yaml`。

## 3. 保留的网络参数

六节点仍需配置真实私网通信地址：

- `CONTROL_PRIVATE_IP`
- `PARTY_A_PRIVATE_IP`
- `PARTY_B_PRIVATE_IP`
- `PARTY_C_PRIVATE_IP`
- `COMPUTE_S1_PRIVATE_IP`
- `COMPUTE_S2_PRIVATE_IP`

这些参数用于节点间通信，与镜像仓库无关。环境文件还应设置一致的强随机 `INTERNAL_SERVICE_TOKEN`，并按需配置会话、模型服务和数据路径。环境文件、密钥和真实地址不得进入公开提交包。

## 4. 分发与加载镜像

把 backend TAR 复制到六台节点；把 frontend TAR 额外复制到 Control。每台节点按需执行：

```bash
docker load -i privgrid-backend-v4.tar
```

Control 额外执行：

```bash
docker load -i privgrid-frontend-v5.tar
```

检查本地标签：

```bash
docker image ls | grep privgrid
```

预期出现 `privgrid-backend:v4`；Control 还应出现 `privgrid-frontend:v5`。

## 5. 数据分发

- Party A 只放置 ORG_A 的基线与合成 Benchmark 数据；
- Party B 只放置 ORG_B 的基线与合成 Benchmark 数据；
- Party C 只放置 ORG_C 的基线与合成 Benchmark 数据；
- Compute 节点不放 Parquet；
- Control 节点不放 Party 原始业务数据。

## 6. 启动顺序

1. Compute S1、Compute S2；
2. Party A、Party B、Party C；
3. Control Plane、Frontend；
4. Control 宿主机入口 Nginx/HTTPS。

每台节点执行：

```bash
cd /opt/privgrid
docker compose config -q
docker compose up -d
docker compose ps
```

比赛版 Compose 使用 `pull_policy: never`，只使用已经加载到本机的离线镜像。

## 7. 入口与安全

Control 的 Frontend 绑定 `127.0.0.1:8080`，由宿主机 Nginx 提供 HTTP/HTTPS 入口。公网演示建议启用有效 HTTPS，以支持安全 Cookie 和浏览器中文语音输入。Party、Compute 和 Control Plane 服务端口应仅在私网或容器网络中开放。

## 8. 验证

```bash
docker compose ps
curl --fail http://127.0.0.1:8080/healthz
```

在 Control 私网侧继续检查 Party 8101/8102/8103 与 Compute 8201/8202 的 `/health`。整个交付流程不需要互联网镜像仓库权限。