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
