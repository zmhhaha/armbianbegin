# 平台现状调查：公网暴露与认证

> 调查时间：2026-09-16，代码基准 HEAD `3dd4128`。
> 范围：`oauth/`、`cloudflare-tunnel/`、`portal/`、`nginx_gateway/`、`vault/`、`openspec_service/`。
> 用途：回答"要把一个新的内部 web 服务暴露到公网并做认证，该怎么做、有哪些坑"。
> 行号基于该次调查，代码演进后会漂移，引用前先核对。

## 结论摘要（TL;DR）

- **标准做法**是给每个服务起一个独立的 `oauth2-proxy-<name>` Deployment（不是 sidecar），再把 Cloudflare 后台的 hostname backend 指向它。幂等可复制。
- **`oauth2-proxy` 现状等于没有准入控制**：`--email-domain=*`，任何 Casdoor 用户都能过。单用户白名单、MFA 在现网**都没有先例**。
- **唯一的 per-user 鉴权先例是 `openspec_service` 的应用内 JWT `sub` 白名单**，而且它的路由是绕过 oauth2-proxy 直连后端的。要"只允许某一个人"，照抄这个，不要试图在 oauth2-proxy 层做。
- **Cloudflare Tunnel 的路由不在代码里**：实际生效的路由在 Cloudflare 后台，仓库内的 `tunnel-routes.yaml` 只是备份，`kubectl apply` 不生效。这是一条手工控制台操作。
- **WebSocket / SSE 有现成配方**：configmap 里 `proxyWebSockets: true`，长流加 `timeout: 80s`，应用侧要关缓冲。

## 一、对外暴露链路

```
用户 → Cloudflare 边缘 → cloudflared（远程管理模式）→ oauth2-proxy-<target>.oauth:4180 → 上游 svc
```

cloudflared 跑在**远程管理模式**，只注入 `TUNNEL_TOKEN`，路由由后台下发：

- `cloudflare-tunnel/manual/deployment.yaml:61` — `exec cloudflared tunnel --no-autoupdate run --token $TUNNEL_TOKEN`
- `cloudflare-tunnel/entrypoint.sh:17-19` — 三种模式，优先 `TUNNEL_TOKEN`
- Operator 版：`cloudflare-tunnel/operator/controller.py` 只为 Tunnel CR 建 Deployment；TunnelRoute CR 写出的 ConfigMap **从未被挂载**（见 `cloudflare-tunnel/README.md:79-102`）

**权威路由来源不在仓库里。** `cloudflare-tunnel/README.md:79` 明确写：实际生效的路由在 Cloudflare 后台 → Public Hostname 列表。仓库内 `tunnel-routes.yaml` 只是备份，`kubectl apply` 不生效（`README.md:81`、`operator/tunnel-routes.yaml:5-14`）。

> ⚠️ 排期含义：任何"配置 Cloudflare Tunnel 路由"的任务都是**控制台手工操作**，不可提交、不可回滚审计。别把它当成代码任务。

### 现存 hostname

公开直连（无认证代理），`cloudflare-tunnel/operator/tunnel-routes.yaml:26-68`：

| hostname | backend |
|---|---|
| `agent.panghuer.top` | `portal.agent-portal:80` |
| `chat.panghuer.top` | `portal.chat-portal:80` |
| `tool.panghuer.top` | `portal.tool-portal:80` |
| `game.panghuer.top` | `portal.game-portal:80` |

经 SSO 代理（backend 全是 `oauth2-proxy-*.oauth:4180`），`tunnel-routes.yaml:70-289` —— 约 20 个：research-agent、scientific-agent、literature-downloader、school-of-one、qianfu、guanliao、tewu、txt2img、daofaziran-agent、fofawubian-agent、zhongkuifumo-agent、yimaneili-agent、zhenzhuzhida-agent、zhougongjiemeng-agent、game-review-agent、xiaotanrenjian-agent、bingbichunqiu-agent、xuye、shapan、hublog。

GitOps 直连（无认证代理），`cloudflare-tunnel/operator/gitops-routes.yaml:2-19`：`gitea.panghuer.top` → `gitea.gitops:3000`、`drone.panghuer.top` → `drone-server.gitops:8080`。

**绕过 oauth2-proxy 的例外**：`cloudflare-tunnel/operator/openspec-service-route.yaml:10-11` —— `openspec.panghuer.top` → `openspec-service.openspec.svc.cluster.local:8080`，鉴权完全在应用内做（Bearer JWT）。这是"不要 oauth2-proxy"的现成先例。

## 二、Casdoor / OIDC / oauth2-proxy

- **Casdoor 独立 Deployment**（非 sidecar）：`oauth/k8s/casdoor-deployment.yaml:5-62`，Service `casdoor:8000`（`:64-78`），MySQL 后端（`casdoor-configmap.yaml:13`），外部地址 `https://auth.panghuer.top`（`casdoor-deployment.yaml:31`）。
- **oauth2-proxy 每服务一个独立 Deployment**，2 副本：`oauth/k8s/proxy-deployment.yaml:39-42`（`oauth2-proxy-__TARGET_NAME__`）、`:113-129`（Service :4180）。
- 用 sed 模板化多实例：`oauth/k8s/deploy-agent-proxy.sh:20-28`、`deploy-game-proxy.sh:16-17`、`deploy-hublog-proxy.sh:15-23`。
- 镜像 `arm-cluster-master:5000/oauth2-proxy:v7.8.0`（`proxy-deployment.yaml:58`）。
- 上游指向规则在 configmap：agent 类 Gradio 7860（`proxy-configmap.yaml:33`）、游戏类 nginx 80（`game-proxy-configmap.yaml:33`）、hublog `hublog-api:80`（`hublog-proxy-configmap.yaml:26`）、txt2img `ui.txt2img:7860`（`txt2img-proxy-configmap.yaml:35`）。
- **身份注入头**：`X-Auth-Request-Sub` / `X-Forwarded-User` / `X-Forwarded-Email` / `X-Forwarded-Preferred-Username`（`hublog-proxy-configmap.yaml:30-43`、`game-proxy-configmap.yaml:38-50`）。下游靠信任这些头识别用户：`panghu_game/XuYe/server.py:86`、`panghu_chat/hublog/README.md:73`、`panghu_game/TaShuo/deploy/README.md:42`。
- 共享同一 OIDC client：OpenSpec 用 Casdoor `panghu-suite` 的 client_id `ece3f52410b046fe0952`（`openspec_service/k8s/core.yaml:13,16`），issuer `https://auth.panghuer.top`（`:12`）。

## 三、准入控制：现状几乎没有

> 📌 **更新（2026-09-16）**：仓库里出现了第一份 per-user 白名单配置 —— `oauth/k8s/hermes-proxy-container.yaml`（Hermes，未提交）。它用 `--authenticated-emails-file` 精确到单个邮箱、`--cookie-name=__Host-hermes` 且不设 domain。本节"现网无先例"说的仍是**已部署**的服务；要抄写法，直接看那份模板。详见 [hermes-code-review.md](hermes-code-review.md) 第一节第 5 条。

### MFA

**全仓零痕迹。** grep `mfa|totp|2fa|two-factor|multi-factor|authenticator` 无有效匹配。Casdoor 侧只有邮箱验证码超时 `verificationCodeTimeout = 10`（`oauth/k8s/casdoor-configmap.yaml:15`），这不是 MFA。若 Casdoor 后台开了 MFA，配置在其数据库里，不在本仓库。

### 单用户白名单

oauth2-proxy 层**没有**单用户/邮箱 allowlist：

- 唯一准入门是 `--email-domain=$(ALLOWED_DOMAINS)`（`proxy-deployment.yaml:73`、`game-proxy-deployment.yaml:76`）
- 而 `ALLOWED_DOMAINS` 的值是 `"*"`（`oauth/k8s/secret.yaml:21`、`vault/inventory/oauth-externalsecret.yaml:51`）＝ **放行任何 Casdoor 用户**
- 全仓无 `--authenticated-emails-file`，无 `--allowed-group`

oauth2-proxy 有的是**匿名放行路由**（`--skip-auth-route`，按路径不按用户）：

- game：UUID 分享页与只读 API（`game-proxy-deployment.yaml:84-85`）
- hublog：`/signed-out`、UUID 分享页、评论只读、静态资源（`deploy-hublog-proxy.sh:18-22`）

**唯一的 per-user 机制在应用层** —— `openspec_service` 用 JWT `sub`：

- `openspec_service/k8s/core.yaml:26` — `BOOTSTRAP_ADMIN_SUBJECTS: "27714443"`
- `openspec_service/src/config.mjs:19` — 解析成 `bootstrapSubjects` Set
- `openspec_service/src/rest.mjs:153` — `if(!config.bootstrapSubjects.has(sub)) throw forbidden();`（目前只用于"创建首个项目"）
- 其余权限走 Gitea ACL：`openspec_service/src/rest.mjs:13,89`、`project-webhook.mjs:8,49`

> 💡 **要"只允许一个人"就照抄这条路**：应用内校验 JWT `sub` + 直连后端（见上一节的 openspec 路由）。在 oauth2-proxy 层加白名单需要 `--authenticated-emails-file`，现网没有先例，且它管的是"能否登录"而不是"能否访问这个服务"。

## 四、会话 cookie

oauth2-proxy 参数（`oauth/k8s/proxy-deployment.yaml:60-78`，游戏版 `game-proxy-deployment.yaml:61-85` 同）：

| 参数 | 值 | 出处 |
|---|---|---|
| cookie-secret | `$(COOKIE_SECRET)` | `proxy-deployment.yaml:62` |
| cookie-domain | `.panghuer.top` | `:63` |
| cookie-secure | `true` | `:64` |
| cookie-samesite | `lax` | `:65` |
| cookie-csrf-per-request | `true` | `:67` |
| cookie-csrf-expire | `5m` | `:68` |
| cookie-expire | `720h`（30 天） | `:70` |
| cookie-refresh | `24h` | `:71` |
| cookie-name | `_oauth2_proxy`（各实例同名） | `:72` |

- **HttpOnly 没有显式设置** —— 全仓无 `--cookie-httponly`，靠 oauth2-proxy 默认值。
- **cookie secret 是全局共享的一份**，不是每服务独立：`oauth/k8s/secret.yaml:7-11` 定义 placeholder，真值经 Vault `secret/oauth/oauth2-proxy` 同步（`vault/inventory/oauth-externalsecret.yaml:34-37`）。所有 oauth2-proxy 实例共用 `oauth2-proxy-secret`（`oauth-externalsecret.yaml:17-18`、`oauth/README.md:61`、`vault/inventory/04-oauth.md:33`）。
- `COOKIE_SECRET` 必须是 **32 字符 hex**，不能用 base64（`oauth/k8s/secret.yaml:8-11`、`vault/inventory/oauth-externalsecret.yaml:13-15`、`oauth/wiki/deployment-guide.md:456-474`）。
- **游戏版额外用 Redis 存 session**（cookie 只放会话 ID）：`game-proxy-deployment.yaml:73-74` — `--session-store-type=redis` + `--redis-connection-url=redis://:$(REDIS_PASSWORD)@redis.data.svc.cluster.local:6379/2`；envFrom `guanliao-redis-secret`（`:94-95`）。**agent 版仍是默认 cookie 存储**（`proxy-deployment.yaml` 无 session-store 参数）。
- 应用层自己**不设会话 cookie**：全仓 grep `Set-Cookie` 无匹配。应用统一是"信任 oauth2-proxy 注入的头"模型。

> ⚠️ 含义：新服务若走 oauth2-proxy 且不覆盖 cookie-name/domain，就与现有全部子域**共享同一个 `_oauth2_proxy` 登录态**。任何"独立、隔离的会话"要求都需要显式覆盖 cookie-name 和 cookie-domain，这属于新设计。
>
> 📌 **现成写法**：`oauth/k8s/hermes-proxy-container.yaml` 用 `--cookie-name=__Host-hermes` + 不设 `--cookie-domain` 做到了独立 cookie。注意 `__Host-` 前缀**强制要求** Secure + `Path=/` + 无 Domain 三条同时成立，那份模板三条都满足。

## 五、WebSocket / SSE 反代

**oauth2-proxy 层有显式 WebSocket 配置** —— 4 个 configmap 全部 `proxyWebSockets: true`：`proxy-configmap.yaml:35`、`game-proxy-configmap.yaml:35`、`hublog-proxy-configmap.yaml:28`、`txt2img-proxy-configmap.yaml:37`（说明见 `oauth/wiki/deployment-guide.md:207`「支持 Gradio WebSocket」）。

**唯一的 SSE 长连接超时先例**是 GuanLiao 部署时把上游 `timeout: 80s` 注入 game-proxy configmap：

```bash
# panghu_game/GuanLiao/deploy/deploy.sh:43
sed -e 's/__TARGET_NAME__/guanliao/g' -e '/proxyWebSockets: true/a\          timeout: 80s' \
  ".../oauth/k8s/game-proxy-configmap.yaml" > "${tmp_dir}/oauth-config.yaml"
```

背景与"不能只看 HTTP 200"的核对要求见 `panghu_game/GuanLiao/deploy/README.md:59,91`。

**Cloudflare Tunnel 侧无显式 WS/SSE 配置** —— 全仓 grep `originRequest|noTLSVerify|http2Origin` 无匹配；TunnelRoute CRD schema 只有 tunnelRef/hostname/backend/path（`cloudflare-tunnel/operator/crds.yaml:77-91`）。远程管理模式下 WS/SSE 由 CF 自动透传。`GuanLiao/deploy/README.md:91` 提示：若流被 Cloudflare 或中间代理缓冲，需核对那条路由的缓存/转换规则。

**应用侧关缓冲头**的现成写法：

- `panghu_game/ShaPan/server/src/index.mjs:124` — `content-type: text/event-stream`、`cache-control: no-cache, no-transform`、`connection: keep-alive`、`x-accel-buffering: no`
- `panghu_game/GuanLiao/src/routes/agents.ts:30-31` — `Content-Type: text/event-stream` + `Cache-Control: no-cache, no-store, no-transform`
- `openspec_service/src/mcp.mjs:98` — MCP GET 直接写 `text/event-stream`（且这条路由直连后端，不经过 oauth2-proxy）
- `llm-service/upstream.py:85-86` — 透传上游 SSE content-type

**nginx-ingress 侧无 WebSocket/SSE 配置** —— `nginx_gateway/hadoop-webui-ingress.yaml:6-20` 只有 CORS + `configuration-snippet`（Host/X-Real-IP/X-Forwarded-Proto），无 `proxy-read-timeout`/`proxy-buffering`/upgrade 映射。`nginx_gateway/self-built/nginx-config.yaml` 是通用模板。全仓唯一 `proxy-read-timeout` 在 `panghu_game/School_Of_One/deploy/k8s/ingress.yaml:16`（值 60）。

## 六、Vault 中 secret 与 ExternalSecret 的组织

**路径约定：`secret/data/<namespace>/<app-name>/<key>`**（`vault/README.md:163-167` 总则，映射表 `:169-186`）。KV v2 的 `data/` 规则：写入不加前缀，读/remoteRef 要加（`vault/README.md:112-131`）。

现存 27 个 ExternalSecret（`vault/inventory/`）：oauth、openspec-service、postgres、redis、guanliao-redis、gitops、elasticsearch、llm-service、各 `*-llm-token`（guanliao/qianfu/shapan/tashuo/tewu/xuye）、rag-llm、rag-callers，以及各游戏/业务 agent 各一份。Hublog 有独立分类路径 `secret/hublog/database|redis|auth`（`hublog-externalsecret.yaml:8-9,27,31`）。

写法约定（例：`oauth-externalsecret.yaml:20-33`）：`secretStoreRef: {name: vault-backend, kind: ClusterSecretStore}`、`refreshInterval: 1h`、`creationPolicy: Owner`。ClusterSecretStore 在 `vault/k8s/cluster-secret-store.yaml`；脚本 `vault/scripts/{init-vault.sh,unseal.sh,login.sh,fix-eso-auth.sh,seed-secrets.sh,store-s3-credentials.sh}`。

> ⚠️ 运维约定：删 secret 必须用 `vault kv metadata delete` —— `vault kv delete` 只软删，历史版本仍可读（`vault/README.md:213-239`）。

## 七、对新服务的影响清单

1. 加公网认证 = 在 `oauth/k8s/` sed 起一个 `oauth2-proxy-<name>` Deployment + **去 Cloudflare 后台**改那条 hostname 的 backend。
2. 想做单用户白名单 → **两条现成路**：(a) `oauth2-proxy` 的 `--authenticated-emails-file`（见 `oauth/k8s/hermes-proxy-container.yaml`）；(b) 应用内 JWT `sub` 白名单 + 直连后端路由（见 `openspec_service` + `openspec-service-route.yaml`）。前者更省事，后者能承载更多按用户区分的权限。
3. MFA 想开就得先在 Casdoor 侧确认是否支持，仓库里查不到。
4. 要独立会话 → 覆盖 cookie-name 为 `__Host-*` 且不设 cookie-domain（见上），否则与现网所有子域共享 `_oauth2_proxy`。
5. 有流式响应 → `proxyWebSockets: true` + 长流的 `timeout`，应用侧加 `x-accel-buffering: no`。
