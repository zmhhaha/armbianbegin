# OAuth 认证服务

为 armbianbegin K8s 集群提供 OAuth 用户认证，基于 [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy) v7.8.0。

## 架构

```
用户 → CF Tunnel → oauth2-proxy:4180 → 后端服务
                         │
                    GitHub / Google OAuth
```

后续如需接入微信/支付宝等，可通过 Casdoor 做 OIDC 中间层。

## 组件

| 组件 | 命名空间 | 端口 | 镜像 |
|------|---------|------|------|
| oauth2-proxy | oauth | 4180, 44180 | `quay.io/oauth2-proxy/oauth2-proxy:v7.8.0` |

## 快速开始

### 1. 注册 OAuth 应用

**GitHub:**
1. https://github.com/settings/developers → New OAuth App
2. Homepage URL: `https://research-agent.panghuer.top`
3. Authorization callback URL: `https://research-agent.panghuer.top/oauth2/callback`

**Google:**
1. https://console.cloud.google.com/apis/credentials → Create OAuth 2.0 Client ID
2. Authorized redirect URIs: `https://research-agent.panghuer.top/oauth2/callback`

### 2. 配置 Secret

编辑 `k8s/secret.yaml`，填入真实凭证。

### 3. 部署

```bash
bash build.sh --deploy
```

## 接入受保护服务

在 `cloudflare-tunnel/operator/tunnel-routes.yaml` 中将 backend 改为 `oauth2-proxy.oauth.svc.cluster.local:4180`。

## Casdoor（可选）

如需接入微信、支付宝等非标准 OAuth 提供商，可以基于 `base` 镜像 + Casdoor 官方 ARM64 二进制自行构建。Dockerfile 模板见本目录。
