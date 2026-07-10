# OAuth (oauth2-proxy + Casdoor) 部署与运维手册

记录了 oauth2-proxy + Casdoor 部署过程中的架构、流程、运维命令和常见问题。

---

## 目录

- [一、架构概述](#一架构概述)
- [二、部署流程](#二部署流程)
- [三、oauth2-proxy 配置详解](#三oauth2-proxy-配置详解)
- [四、Casdoor 配置](#四casdoor-配置)
- [五、Cloudflare Tunnel 路由](#五cloudflare-tunnel-路由)
- [六、Secret 管理（Vault + ESO）](#六secret-管理vault--eso)
- [七、常用运维命令](#七常用运维命令)
- [八、常见问题与排查](#八常见问题与排查)

---

## 一、架构概述

```
公网用户
    │
    ▼
Cloudflare Tunnel (operator)
    │
    ├── agent.panghuer.top ──▶ portal.agent-portal:80（公开，无需认证）
    │
    ├── research-agent.panghuer.top ──▶ oauth2-proxy-research-agent:4180 ──▶ ui.research-agent:7860
    │
    └── scientific-agent.panghuer.top ──▶ oauth2-proxy-scientific-agent:4180 ──▶ ui.scientific-agent:7861
                                                   │
                                                   ▼
                                           Casdoor OIDC (auth.panghuer.top:8000)
                                                   │
                                                   ▼
                                           MySQL (持久化用户数据)
```

| 组件 | 命名空间 | 端口 | 作用 |
|------|---------|------|------|
| Casdoor | `oauth` | 8000 | OIDC 身份认证提供商 |
| MySQL | `oauth` | 3306 | Casdoor 数据持久化 |
| oauth2-proxy-{target} | `oauth` | 4180 | OIDC 认证代理网关（每服务一个实例） |
| Cloudflare Tunnel | `default` | - | 公网入口，域名路由 |

### 流量路径（以 research-agent 为例）

```
用户浏览器 → research-agent.panghuer.top
  → Cloudflare Tunnel → oauth2-proxy-research-agent:4180
  → 未认证 → 重定向到 Casdoor OIDC 登录页（auth.panghuer.top）
  → 用户登录 → Casdoor 回调 oauth2-proxy → 验证 id_token → 设置 Cookie
  → 注入 X-Forwarded-User/Email 等 Header → 转发到 ui.research-agent:7860 (Gradio)
```

### 关键设计

- **每个需要认证的服务一个 oauth2-proxy 实例**，通过 `__TARGET_NAME__` 占位符模板化部署
- **所有实例共用同一个 Casdoor 应用**（1 套 `client_id/secret`，多个回调 URL）
- **集群内部访问不受影响**，可以通过 `kubectl port-forward` 直连后端服务，绕过认证
- Portal 主页公开，不需要认证

---

## 二、部署流程

### 前置条件

- Helm 已安装
- kubectl 可访问集群
- 私有镜像仓库 `arm-cluster-master:5000` 可用
- Casdoor 和 MySQL 镜像已推送到私有仓库

### Step 1：部署 Casdoor + MySQL

```bash
cd ~/armbianbegin/oauth

# 推送镜像 + 部署 Casdoor 基础服务
bash build.sh --deploy
```

这会部署：
- `namespace.yaml` — `oauth` 命名空间
- `secret.yaml` — oauth2-proxy 凭证（placeholder，后续通过 Vault 同步）
- `casdoor-configmap.yaml` — Casdoor 配置（MySQL 连接、端口）
- `casdoor-deployment.yaml` — Casdoor 服务
- `mysql.yaml` — MySQL 8.0 有状态服务

### Step 2：部署 oauth2-proxy 实例

```bash
# 仅部署 oauth2-proxy（两个实例：research-agent + scientific-agent）
bash build.sh --deploy-proxy

# 验证
kubectl get pods -n oauth | grep oauth2-proxy
# 应看到:
# oauth2-proxy-research-agent-xxx     2/2  Running
# oauth2-proxy-scientific-agent-xxx   2/2  Running
```

`--deploy-proxy` 会执行：
1. 遍历 `research-agent` 和 `scientific-agent`
2. 用 `sed` 替换 `__TARGET_NAME__` 部署两个 ConfigMap
3. 用 `sed` 替换 `__TARGET_NAME__` 部署两个 Deployment + Service
4. 同时同步 Vault 中的 ExternalSecret（如果 Vault 已部署）

### Step 3：更新 Tunnel 路由

```bash
cd ~/armbianbegin/cloudflare-tunnel/operator
kubectl apply -f tunnel-routes.yaml

# 验证
kubectl get tunnelroute
# research-ui     → oauth2-proxy-research-agent.oauth:4180
# scientific-ui   → oauth2-proxy-scientific-agent.oauth:4180
# agent-portal    → portal.agent-portal:80（公开）
```

### Step 4：配置 Casdoor 应用

登录 Casdoor 后台 `https://auth.panghuer.top`（默认账号 `admin / 123456`）。

创建或编辑应用（Application）：
- **名称**: `agent-suite`（或已有应用）
- **类型**: `OIDC`
- **重定向 URL**（每行一个）:
  ```
  https://research-agent.panghuer.top/oauth2/callback
  https://scientific-agent.panghuer.top/oauth2/callback
  ```
- 保存后获取 `Client ID` 和 `Client Secret`

### Step 5：写入凭证到 Vault

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/oauth/oauth2-proxy \
  COOKIE_SECRET="$(openssl rand -hex 16)" \
  OIDC_CLIENT_ID="从Casdoor获取的ClientID" \
  OIDC_CLIENT_SECRET="从Casdoor获取的ClientSecret" \
  OIDC_ISSUER_URL="https://auth.panghuer.top" \
  ALLOWED_DOMAINS="*"

# 强制 ESO 同步
kubectl annotate externalsecret oauth2-proxy-secret -n oauth \
  force-sync=$(date +%s) --overwrite

# 重启 oauth2-proxy 加载新凭证
kubectl rollout restart deploy/oauth2-proxy-research-agent -n oauth
kubectl rollout restart deploy/oauth2-proxy-scientific-agent -n oauth
```

### Step 6：测试

```
浏览器访问 https://research-agent.panghuer.top
→ 跳转到 Casdoor 登录页 → 输入 admin / 123456
→ 登录成功回到 Gradio 界面 ✅

登出: https://research-agent.panghuer.top/oauth2/sign_out
→ 清除 Cookie
```

---

## 三、oauth2-proxy 配置详解

### 部署模板 `oauth/k8s/proxy-deployment.yaml`

通过 `sed "s/__TARGET_NAME__/${target}/g"` 替换 `__TARGET_NAME__` 部署多个实例。

| 参数 | 值 | 说明 |
|------|-----|------|
| `--cookie-secret` | 环境变量 `$(COOKIE_SECRET)` | AES 密钥（必须 32 字符 hex） |
| `--cookie-domain` | `.panghuer.top` | Cookie 作用域 |
| `--cookie-secure` | `true` | 仅 HTTPS |
| `--cookie-samesite` | `lax` | CSRF 防护 |
| `--cookie-expire` | `168h` | Cookie 有效期 7 天 |
| `--cookie-refresh` | `60m` | 每小时刷新 |
| `--redirect-url` | `https://{target}.panghuer.top/oauth2/callback` | OIDC 回调地址 |
| `--reverse-proxy` | `true` | 前面有反向代理 |
| `--ssl-insecure-skip-verify` | `true` | 跳过 Casdoor TLS 验证 |

### ConfigMap 模板 `oauth/k8s/proxy-configmap.yaml`

| 字段 | 值 | 说明 |
|------|-----|------|
| `provider` | `oidc` | OIDC 协议 |
| `scope` | `openid email profile` | 请求的用户信息范围 |
| `issuerURL` | `$(OIDC_ISSUER_URL)` | Casdoor OIDC 端点 |
| `audienceClaims` | `["aud"]` | id_token audience 校验（必须） |
| `upstreams` | `http://ui.{target}.svc.cluster.local:7860` | 后端 Gradio 服务 |
| `proxyWebSockets` | `true` | 支持 Gradio WebSocket |

---

## 四、Casdoor 配置

### 部署文件

| 文件 | 说明 |
|------|------|
| `oauth/k8s/casdoor-deployment.yaml` | Casdoor 服务（端口 8000，环境变量 `origin`） |
| `oauth/k8s/casdoor-configmap.yaml` | MySQL 连接配置 |
| `oauth/k8s/mysql.yaml` | MySQL 8.0 有状态服务（Ceph RBD 持久化） |

### Casdoor 后台配置项

- **OIDC 应用**: 类型选 `OIDC`（支持多回调 URL）
- **回调 URL 格式**: `https://{域名}/oauth2/callback`
- **第三方登录配置**: 见 `wiki/casdoorGithub.md`、`wiki/caldoor第三方.md`

### 关键环境变量

```yaml
env:
- name: origin
  value: "https://auth.panghuer.top"       # Casdoor 外部访问地址
```

---

## 五、Cloudflare Tunnel 路由

### 正式路由定义 `cloudflare-tunnel/operator/tunnel-routes.yaml`

```yaml
# agent-portal 首页（公开）
hostname: agent.panghuer.top
backend: portal.agent-portal.svc.cluster.local:80

# 研究助手 UI（需要 OAuth 认证）
hostname: research-agent.panghuer.top
backend: oauth2-proxy-research-agent.oauth.svc.cluster.local:4180

# 科研综述 UI（需要 OAuth 认证）
hostname: scientific-agent.panghuer.top
backend: oauth2-proxy-scientific-agent.oauth.svc.cluster.local:4180
```

### Service 命名规则

`oauth2-proxy-{__TARGET_NAME__}.oauth.svc.cluster.local:4180`

- Research: `oauth2-proxy-research-agent.oauth.svc.cluster.local:4180`
- Scientific: `oauth2-proxy-scientific-agent.oauth.svc.cluster.local:4180`

---

## 六、Secret 管理（Vault + ESO）

### Secret 文件 `oauth/k8s/secret.yaml`

```yaml
stringData:
  COOKIE_SECRET: "change-me..."         # 32 字符 hex，用 openssl rand -hex 16
  OIDC_CLIENT_ID: "oauth2-proxy-client-id"
  OIDC_CLIENT_SECRET: "oauth2-proxy-client-secret"
  OIDC_ISSUER_URL: "https://auth.panghuer.top"
  ALLOWED_DOMAINS: "*"
```

### ExternalSecret `vault/inventory/oauth-externalsecret.yaml`

从 Vault 路径 `secret/oauth/oauth2-proxy` 同步到 `oauth` 命名空间的 `oauth2-proxy-secret`。

两个 oauth2-proxy 实例**共用同一个 Secret**。

### 更新凭证

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/oauth/oauth2-proxy \
  COOKIE_SECRET="$(openssl rand -hex 16)" \
  OIDC_CLIENT_ID="xxx" \
  OIDC_CLIENT_SECRET="xxx" \
  OIDC_ISSUER_URL="https://auth.panghuer.top" \
  ALLOWED_DOMAINS="*"

# 强制 ESO 同步 + 重启 oauth2-proxy
kubectl annotate externalsecret oauth2-proxy-secret -n oauth \
  force-sync=$(date +%s) --overwrite
kubectl rollout restart deploy/oauth2-proxy-research-agent -n oauth
kubectl rollout restart deploy/oauth2-proxy-scientific-agent -n oauth
```

---

## 七、常用运维命令

### Pod 管理

```bash
# 查看所有 Pod
kubectl get pods -n oauth

# 查看 oauth2-proxy 日志
kubectl logs -n oauth -l app=oauth2-proxy-research-agent --tail=50
kubectl logs -n oauth -l app=oauth2-proxy-scientific-agent --tail=50

# 查看 Casdoor 日志
kubectl logs -n oauth deploy/casdoor --tail=50

# 查看 Casdoor 日志（OIDC 相关）
kubectl logs -n oauth deploy/casdoor --tail=200 | grep -i "oauth\|authorize\|redirect\|callback\|github"
```

### 更新配置

```bash
# 重新部署两个 oauth2-proxy 实例
sed "s/__TARGET_NAME__/research-agent/g" k8s/proxy-configmap.yaml | kubectl apply -f -
sed "s/__TARGET_NAME__/research-agent/g" k8s/proxy-deployment.yaml | kubectl apply -f -
sed "s/__TARGET_NAME__/scientific-agent/g" k8s/proxy-configmap.yaml | kubectl apply -f -
sed "s/__TARGET_NAME__/scientific-agent/g" k8s/proxy-deployment.yaml | kubectl apply -f -
```

### 重启

```bash
# 重启 oauth2-proxy
kubectl rollout restart deploy/oauth2-proxy-research-agent -n oauth
kubectl rollout status deploy/oauth2-proxy-research-agent -n oauth
kubectl rollout restart deploy/oauth2-proxy-scientific-agent -n oauth
kubectl rollout status deploy/oauth2-proxy-scientific-agent -n oauth
```

### 调试直连

```bash
# 端口转发直接访问 Gradio（绕过认证）
kubectl port-forward -n research-agent svc/ui 7860:7860
```

### 查看 Secret

```bash
# 查看 oauth2-proxy 凭证
kubectl get secret oauth2-proxy-secret -n oauth \
  -o json | jq '.data | map_values(@base64d)'

# 查看 Vault 中的值
kubectl exec -n vault vault-0 -- vault kv get secret/oauth/oauth2-proxy
```

---

## 八、常见问题与排查

### 问题 1：COOKIE_SECRET 长度不对

**现象**：
```
invalid configuration: cookie_secret must be 16, 24, or 32 bytes to create an AES cipher, but is 44 bytes
```

**原因**：oauth2-proxy 的 `--cookie-secret` 直接用字符串长度判断 AES key 字节数，**不会做解码**。

| 生成方式 | 字符数 | AES 字节 | 结果 |
|---------|--------|---------|------|
| `openssl rand -base64 32` | 44 | 44 | ❌ |
| `python3 -c "import secrets; print(secrets.token_hex(32))"` | 64 | 64 | ❌ |
| `openssl rand -hex 32` | 64 | 64 | ❌ |
| **`openssl rand -hex 16`** | **32** | **32** | **✅** |

**解决**：
```bash
COOKIE_SECRET="$(openssl rand -hex 16)"
```

---

### 问题 2：id_token audience 验证失败

**现象**：
```
Error redeeming code during OAuth2 callback: could not verify id_token:
audience claims [] do not exist
```

**原因**：oauth2-proxy 的 OIDC 配置中没有指定 `audienceClaims`，导致它去验证一个空的 audience 列表，而 Casdoor 返回的 id_token 中包含 `aud` 声明。

**解决**：在 `oauth/k8s/proxy-configmap.yaml` 的 `oidcConfig` 中添加：
```yaml
oidcConfig:
  issuerURL: ${OIDC_ISSUER_URL}
  audienceClaims: ["aud"]
```

---

### 问题 3：PKCE 警告

**现象**：
```
Warning: Your provider supports PKCE methods ["S256"], but you have not
enabled one with --code-challenge-method
```

**原因**：Casdoor 支持 PKCE，但 oauth2-proxy 默认未启用。

**解决**：在 `proxy-deployment.yaml` 的 `args` 中添加：
```yaml
- "--code-challenge-method=S256"
```

此非必须修复——不启用也不影响功能，只是授权码交换时缺少一层安全加固。

---

### 问题 4：GitHub 第三方登录 redirect_uri 不匹配

**现象**：Casdoor 登录页点击 GitHub 登录时，显示：
```
Be careful! The redirect_uri is not associated with this application.
```

**原因**：Casdoor 往 GitHub OAuth 服务发请求时，`redirect_uri` 使用 Casdoor 自身的回调地址（默认 `https://auth.panghuer.top/callback`）。如果在 GitHub OAuth App 中配置的回调地址不一致，GitHub 会拒绝。

**解决**：
1. 在 GitHub OAuth App 中将回调地址改为 Casdoor 的地址：
   ```
   https://<casdoor-domain>/callback
   ```
2. 确认 Casdoor 中 Provider 配置的 `Client ID` / `Client Secret` 正确
3. 如果 `/api/login/oauth` 路径无法使用，检查 Casdoor 日志确认实际路径：
   ```bash
   kubectl logs -n oauth deploy/casdoor --tail=50 | grep -i callback
   ```

---

### 问题 5：oauth2-proxy 登录后显示 Oops Something went wrong

**现象**：Casdoor 登录成功回调后，oauth2-proxy 显示 500 错误。

**排查步骤**：
```bash
# 1. 先看 oauth2-proxy 日志
kubectl logs -n oauth -l app=oauth2-proxy-research-agent --tail=20

# 2. 再看 Casdoor 日志
kubectl logs -n oauth deploy/casdoor --tail=50 | grep -i "error\|callback\|token"
```

常见原因：
- `audienceClaims` 未配置 → 见问题 2
- COOKIE_SECRET 过长 → 见问题 1
- 回调 URL 不匹配 → 检查 Casdoor 应用配置中的重定向 URL
