# coredns-split-horizon

在集群内把 `auth.panghuer.top` 分流到集群里的 `ingress-nginx`，让 oauth2-proxy 的内部鉴权
不再出集群绕行公网 VPS 与 frp 隧道。

## 问题

集群里每个 oauth2-proxy 都要访问 `https://auth.panghuer.top` 做 OIDC discovery 与令牌交换，
而 Casdoor 就在同一个集群里。但该域名在公网指向国内 VPS，于是路径变成：

```
Pod → 出集群 → 公网 → VPS nginx → frps → frp 隧道 → 回到家里 → Casdoor → 原路返回
实测 3336 ms（而同一集群内本应 1–3 ms）
```

## 做法

在 CoreDNS 的 Corefile 里追加一条 `rewrite`：

```
rewrite stop name exact auth.panghuer.top ingress-nginx-controller.ingress-nginx.svc.cluster.local
```

- **指向 Service 名，不写 IP** ✓：由 `kubernetes` 插件解析成 ClusterIP，Service 重建、
  ClusterIP 变化都不影响本规则（写死 IP 会在某次重装 ingress-nginx 后悄悄失效）。
- **目标是 ingress-nginx，不是 Casdoor** ✓：客户端连的是 **443 + TLS**，而 Casdoor 只监听
  **8000** 且是明文 HTTP。集群内唯一能用该域名出示正确证书并终结 TLS 的端点就是 ingress-nginx。
- **不改任何现有行** ✓：脚本只在 `.:53` 块末尾追加，并在改动前备份原 ConfigMap。

## 前提（缺一不可）

| 前提 | 在哪 |
|---|---|
| `auth.panghuer.top` 的 Ingress（ingress-nginx 终结 TLS） | `oauth/k8s/auth-ingress.yaml` |
| 该域名的证书（Cloudflare DNS-01 自动签发/续期） | `cert-manager/` |
| default-deny 命名空间的 Pod 能访问 `ingress-nginx` 的 443 | `patches/panghu-chat-ingress-nginx-egress.patch` |

第三条最容易漏：`dsh` 与 `hermes` 是 default-deny，其 egress 白名单里原本只有一条
「公网 443（**且明确排除了 10.0.0.0/8 等私网**）」，分流后 Pod 改连集群内 ClusterIP，
就会被自己的 NetworkPolicy 拦住，表现为连接超时。

## 用法

```bash
bash deploy.sh --dry-run   # 看会插入什么
bash deploy.sh             # 追加规则 + 滚动重启 CoreDNS
bash verify.sh             # 必须从 Pod 内验证（节点用的是宿主机解析器）
```

`verify.sh` 默认借用 `dsh` 命名空间里带 node 的 `dsh-web` Pod 当探针，
可用 `PROBE_NS` / `PROBE_SELECTOR` / `PROBE_CONTAINER` 覆盖。

## 通过条件

1. Pod 内 `auth.panghuer.top` 解析到 `10.x`（集群内），而不是 `62.234.50.20`
2. Pod 内 `https://auth.panghuer.top/.well-known/openid-configuration` 返回 200，
   **且 `issuer` 仍是 `https://auth.panghuer.top`**（issuer 一变，所有 oauth2-proxy 都会拒绝令牌）
3. 回归：`kubernetes.default` 与外网域名仍能解析

## 回滚

```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /tmp/Corefile.rollback
# 删掉 rules.txt 里那三行（两行注释 + 一行 rewrite），再：
kubectl -n kube-system create configmap coredns --from-file=Corefile=/tmp/Corefile.rollback \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n kube-system rollout restart deploy/coredns
```

回滚后内部鉴权会退回走公网 VPS（3.3 s），功能不受影响。

## 实测（2026-10-15）

| | 分流前 | 分流后 |
|---|---|---|
| Pod 内解析 | 62.234.50.20（公网） | **10.105.254.186**（集群内） |
| OIDC discovery | 3336 ms | **91 / 19 / 18 ms** |
| `/api/health` | — | **13 ms** |
| issuer | `https://auth.panghuer.top` | 不变 ✓ |
