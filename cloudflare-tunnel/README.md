# Cloudflare Tunnel for Kubernetes

将 K8s 集群内部服务通过 Cloudflare Tunnel 安全暴露到公网。

## 两种方案

| | manual/ | operator/ |
|---|---|---|
| 模式 | 手动 Deployment + Ingress | Kubernetes Operator (CRD) |
| 部署 | `bash deploy.sh` | `bash deploy.sh` 然后 `kubectl apply -f example-tunnel.yaml` |
| 多 Tunnel | 每个隧道复制一套 YAML | 每个 Tunnel 一个 CR |
| 路由管理 | 手动写 Ingress | TunnelRoute CR 声明式 |
| 自动修复 | 无 | Operator 监听 CR 变更自动同步 |
| 适合 | 1-2 个固定隧道 | 多 Agent 多隧道 |

---

## manual/ — 手动部署

```bash
cd manual
# 1. 把 CF tunnel token 写入 .token
# 2. 部署
bash deploy.sh
```

目录：
- `Dockerfile` / `entrypoint.sh` — cloudflared 镜像
- `k8s/` — Deployment, Service, ConfigMap, Secret
- `deploy.sh` — 构建镜像 + 部署到 K8s
- `.token` — token 文件（gitignored）

---

## operator/ — Operator 部署

```bash
cd operator
# 1. 写入 .token
# 2. 部署 Operator
bash deploy.sh

# 3. 创建 Tunnel
kubectl apply -f example-tunnel.yaml
```

目录：
- `crds.yaml` — Tunnel + TunnelRoute CRD 定义
- `controller.py` — Python kopf 控制器（监听 CRD 变更）
- `Dockerfile` — Operator 镜像
- `deploy.sh` — 构建 + 部署 Operator + 读取 .token 创建 Secret
- `deployment.yaml` / `rbac.yaml` — Operator 自身部署
- `.token` — token 文件（gitignored）

声明式创建 Tunnel：
```yaml
apiVersion: cf.armbianbegin.io/v1
kind: Tunnel
metadata:
  name: my-tunnel
spec:
  tunnelToken: cf-tunnel-token  # deploy.sh 自动创建
  replicas: 2
---
apiVersion: cf.armbianbegin.io/v1
kind: TunnelRoute
metadata:
  name: my-route
spec:
  tunnelRef: my-tunnel
  hostname: app.panghuer.top
  backend: my-service.default.svc.cluster.local:8080
```

---

## 路由的权威来源（重要）

**实际生效的路由在 Cloudflare 后台 → 该 tunnel 的 Public Hostname 列表**，不在这个仓库里。

`operator/tunnel-routes.yaml` 目前是那份配置的**备份**，`kubectl apply` 它不会改变任何路由。原因在 `controller.py`：

| CRD | operator 实际做的事 | 是否影响路由 |
| --- | --- | --- |
| `Tunnel` | 建 `cf-tunnel-<name>` Deployment，只注入 `TUNNEL_TOKEN` | ✅ 生效（cloudflared 起来，走**远程管理模式**） |
| `TunnelRoute` | 把 ingress 写进 ConfigMap `cf-tunnel-cfg-<name>` | ❌ **不生效** |

`TunnelRoute` 不生效有两处实现问题：

1. `_build_deployment()` 构造的 Pod 既没有 `volumes` 也没有 `volumeMounts`，那个 ConfigMap 从来没挂进 cloudflared 容器；容器只靠 `TUNNEL_TOKEN` 启动。
2. `tunnelroute_reconcile()` 每次都用「只含本次这一条」的 config 覆盖整个 ConfigMap，多路由会互相覆盖，最后只剩最后被 reconcile 的那一条。

因此：

- **加/改路由请去 Cloudflare 后台**，然后把同样的条目同步回 `tunnel-routes.yaml`，保持备份完整。
- 排查「某个域名不通」时，先看后台的 Public Hostname 列表，而不是这个文件。

### 如果将来想改成声明式

不能只修上面两个 bug。cloudflared 用 token 启动时是**远程管理模式**，一旦给它挂上本地 `--config`，它就切换成**本地管理模式**，**后台那批 Public Hostname 会被全部忽略** —— 切换那一刻所有域名一起断。

正确顺序是：先把后台的全部 hostname 搬进 `tunnel-routes.yaml`，并让 reconcile 合并同一 tunnel 的所有路由；再挂载配置、切换模式。
