# cert-manager

在集群内自动签发与续期 TLS 证书，为 `auth.panghuer.top` 的**集群内分流**提供 443 + 正确 SNI
的终结端点。集群里的 Pod 访问 `https://auth.panghuer.top` 时不再需要出集群绕行 VPS 与 frp
隧道（实测该路径 3.3 s，而 Casdoor 就在同一个集群内）。

## 版本

`v1.19.6`。理由见 `mirror.sh` 顶部：v1.19 仍在安全支持窗口内；该版本清单只使用 v1 API 组，
与本集群 Kubernetes **v1.31.2** 兼容（对着下载下来的清单核对，不是照抄支持表）。

## 三个文件的分工

| 文件 | 作用 | 是否碰集群 |
|---|---|---|
| `mirror.sh` | 固定版本抓上游清单 → 镜像改到私有 registry → 断言 arm64 → 搬运镜像 | **不碰** |
| `deploy.sh` | 应用清单 + 打本集群差异补丁 | 碰 |
| `verify.sh` | 验证**真能签发证书**，而不只是 Pod 在跑 | 读 + 自测后清理 |

## 用法

```bash
bash mirror.sh              # 先搬镜像（需要 docker + 私有 registry 可推）
bash deploy.sh --dry-run    # 看会做什么
bash deploy.sh              # 安装
bash verify.sh              # 端到端验证
```

## 通过条件

1. `cert-manager` / `-webhook` / `-cainjector` 三个 Deployment 各有 ≥1 个就绪副本
2. 6 个 CRD 均 `Established=True`
3. webhook 对非法请求能给出准入响应
4. 自测命名空间里 `SelfSigned` Issuer + Certificate **真的签出** `tls.crt`（`verify.sh` 结束前清理）

## 本集群与上游的差异（都在 `deploy.sh`）

1. `nodeSelector kubernetes.io/arch: arm64` —— 本集群全是 arm64
2. `resources.requests` **与** `limits` 都给 —— 仓库约定要求两者并存
3. `--acme-http01-solver-image` 指向私有 registry —— 该镜像不在清单里，是控制器解题时自己拉的；
   本仓库用 DNS-01 不需要解题 Pod，但参数照样设上，免得日后改用 HTTP-01 时悄悄依赖 quay.io

## 与 Cloudflare DNS-01 的关系

Cloudflare provider 是 cert-manager **内置**的，不需要额外 webhook，因此除上面三个镜像外
无需其他组件。API Token（Zone:DNS:Edit + Zone:Zone:Read，限 `panghuer.top`）由使用者自建
Secret，**不进入本仓库**：

```bash
kubectl -n cert-manager create secret generic cloudflare-api-token \
  --from-literal=api-token='<token>'
```

## 为什么需要它（背景）

集群里的 oauth2-proxy 要把 `https://auth.panghuer.top` 当作 OIDC issuer 访问。若在 CoreDNS
里把该域名指向 Casdoor 的 ClusterIP，会同时撞上两个问题：Casdoor 只监听 **8000** 且是**明文
HTTP**，而客户端连的是 **443 + TLS**。因此集群内需要一个「443 + 能出示该域名证书」的端点 ——
这正是集群里已有的 `ingress-nginx` 加上本组件签出的证书所提供的东西。
