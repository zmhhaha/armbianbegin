# Cloudflare Tunnel for Kubernetes

基于官方 `cloudflare/cloudflared` 镜像，在 K8s 集群中部署 Cloudflare Tunnel，将集群内部服务安全暴露到公网。

## 架构

```
互联网用户
    │
    ▼
┌──────────────────┐
│  Cloudflare Edge  │  ← 免费 SSL、DDoS 防护、CDN
└──────┬───────────┘
       │ cloudflared (双向 QUIC/HTTP2)
       ▼
┌──────────────────────┐
│   K8s Cluster        │
│  ┌────────────────┐  │
│  │ cloudflared x2 │  │  ← Deployment (高可用)
│  │ (tunnel 守护)   │  │
│  └───────┬────────┘  │
│          │            │
│  ┌───────▼────────┐  │
│  │ 内部 Service    │  │  ← 你的应用
│  │ (app:8080)     │  │
│  └────────────────┘  │
└──────────────────────┘
```

## 前置条件

1. Cloudflare 账号 + 一个托管在 Cloudflare 的域名
2. K8s 集群 (1.24+)
3. Docker（构建镜像用，或直接用官方镜像）

## 快速开始（推荐：TUNNEL_TOKEN 方式）

### 1. 在 Cloudflare 创建 Tunnel

```bash
# 方式 A：Web 界面
# Cloudflare Zero Trust → Networks → Tunnels → Create a tunnel
# 名称随意（如 k8s-cluster），选择 Docker 环境
# 复制显示的 token（以 eyJ 开头的一长串）

# 方式 B：命令行
cloudflared tunnel login
cloudflared tunnel create k8s-cluster
cloudflared tunnel token k8s-cluster   # 获取 token
```

### 2. 构建镜像

```bash
cd cloudflare-tunnel-operator
docker build -t cloudflare-tunnel-operator:latest .
```

如果需要推送到私有仓库：
```bash
docker tag cloudflare-tunnel-operator:latest your-registry/cloudflared:latest
docker push your-registry/cloudflared:latest
# 修改 k8s/deployment.yaml 中的 image
```

### 3. 创建 Secret 并部署

```bash
# 创建 namespace + secret
kubectl create namespace cloudflare-tunnel
kubectl create secret generic tunnel-credentials \
  --from-literal=token="eyJh..." \
  -n cloudflare-tunnel

# 一键部署
kubectl apply -k ./k8s

# 查看状态
kubectl get pods -n cloudflare-tunnel
kubectl logs -f deployment/cloudflared -n cloudflare-tunnel
```

### 4. 配置 DNS 路由

在 Cloudflare Zero Trust → Tunnels → 你的 tunnel → Public Hostname：

| 子域名 | 域名 | Service |
|--------|------|---------|
| `app` | `example.com` | `http://my-app.default.svc.cluster.local:8080` |
| `api` | `example.com` | `http://api-service.default.svc.cluster.local:3000` |

> DNS 会自动在 Cloudflare 创建 CNAME 记录，指向 `*.cfargotunnel.com`

## 配置方式对比

| 方式 | 复杂度 | 适用场景 |
|------|--------|----------|
| **TUNNEL_TOKEN** | ⭐ | 单隧道、Cloudflare 面板管理路由 |
| **config.yml** | ⭐⭐ | 多域名、精细控制 ingress 规则 |
| **credentials.json** | ⭐⭐⭐ | 已有 tunnel、迁移场景 |

## 方式 B：config.yml + credentials.json（高级）

适合需要在本地管理 ingress 规则的场景。

```bash
# 1. 创建 tunnel
cloudflared tunnel create k8s-cluster
# 生成: ~/.cloudflared/<tunnel-id>.json

# 2. 导入 credentials
kubectl create secret generic tunnel-credentials \
  --from-file=credentials.json=~/.cloudflared/<tunnel-id>.json \
  -n cloudflare-tunnel

# 3. 编辑 k8s/tunnel-configmap.yaml，配置 ingress 规则

# 4. 编辑 k8s/deployment.yaml：
#    - 取消 env: TUNNEL_TOKEN 下的注释/删除
#    - 取消 credentials 和 config 的 volumeMounts 和 volumes 注释

# 5. 部署
kubectl apply -k ./k8s

# 6. DNS 路由
cloudflared tunnel route dns <tunnel-id> app.example.com
```

## 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -n cloudflare-tunnel
# NAME                          READY   STATUS    RESTARTS   AGE
# cloudflared-xxxxxxxxx-xxxxx   1/1     Running   0          1m
# cloudflared-xxxxxxxxx-yyyyy   1/1     Running   0          1m

# 检查日志（应该看到 connection 建立）
kubectl logs deployment/cloudflared -n cloudflare-tunnel
# 2025-XX-XX INFO Registered tunnel connection ...
# 2025-XX-XX INFO Connection <id> registered ...

# 检查 metrics
kubectl port-forward deployment/cloudflared 2001:2001 -n cloudflare-tunnel
curl http://localhost:2001/ready
curl http://localhost:2001/metrics
```

## 监控

cloudflared 内置 Prometheus metrics，已通过 Service 暴露：

```bash
# Prometheus 抓取目标
# http://cloudflared-metrics.cloudflare-tunnel.svc.cluster.local:2001/metrics
```

可用的 metrics：
- `cloudflared_tunnel_active_connections` — 活跃连接数
- `cloudflared_tunnel_requests_total` — 请求总量
- `cloudflared_tunnel_server_locations` — 连接的 Cloudflare 边缘节点

如果集群有 Prometheus Operator，取消 `k8s/service.yaml` 中 ServiceMonitor 的注释即可自动接入。

## 高可用说明

- Deployment 默认 2 副本 + Pod 反亲和 → 打散到不同节点
- cloudflared 客户端与 Cloudflare Edge 保持多条 QUIC 连接
- 一个副本故障时流量自动切到同 Tunnel 的另一个副本
- Cloudflare 侧天然支持多连接负载均衡

## TLS / SSL 配置

Cloudflare Edge 到访客：自动 SSL（免费）  
Cloudflare Edge 到 cloudflared：双向加密 QUIC/HTTP2  
cloudflared 到 K8s Service：HTTP（集群内部，建议用 cert-manager 等加密内部流量）

## 故障排查

```bash
# Pod 起不来
kubectl describe pod -n cloudflare-tunnel

# 常见问题：
# 1. TUNNEL_TOKEN 错误 → 检查 token 是否过期
# 2. DNS 路由配了但访问 404 → 检查 config.yml 中 service URL 格式
# 3. 连接断开频繁 → 检查网络策略/防火墙是否允许 7844 端口出站

# 手动测试连接
kubectl run test --rm -it --image=busybox -n cloudflare-tunnel -- sh
# nc -vz cloudflared-metrics 2001
```

## 清理

```bash
kubectl delete -k ./k8s
kubectl delete secret tunnel-credentials -n cloudflare-tunnel
# 去 Cloudflare Zero Trust 面板手动删除 tunnel
```
