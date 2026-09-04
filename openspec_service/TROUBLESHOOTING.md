# OpenSpec 服务排障手册（Troubleshooting）

本文档记录 Casdoor + Gitea + OpenSpec 从零跑通过程中实际遇到的问题与解决方案，
供部署、排障和复现时参考。所有内容基于 2026-08/09 在 `arm-cluster-master`
（192.168.137.101）的真实部署验证。

> 相关文档：`CASDOOR_SETUP.md`（Casdoor 配置）、`DEPLOY.md`（部署）、
> `MULTI_TENANCY.md` / `DEVELOPMENT_DESIGN.md`（设计）、`DEVELOPMENT_BACKLOG.md`（待办）。

---

## 0. 快速定位

部署前/排障第一步先跑预检脚本（只读，自动检查本手册里 80% 的项）：

```bash
# master 上，master 的 /tmp/casdoor.jwt 存有已拿到的 JWT 时可带 --jwt 验证 claims
CASDOOR_JWT="$(cat /tmp/casdoor.jwt)" bash openspec_service/scripts/preflight.sh --jwt "$(cat /tmp/casdoor.jwt)"
```

预检覆盖：K8s 可达、namespace、Casdoor discovery（issuer/jwks_uri）、`OIDC_AUDIENCE`、
`BOOTSTRAP_ADMIN_SUBJECTS` 占位符、JWT 的 aud/email/sub、Gitea token 有效性/组织/邮箱可见性、
Vault 三键（`gitea_provision_token`/`gitea_username`/`database_url`）、ExternalSecret Ready、
Deployment/PVC/PostgreSQL。

---

## 1. 认证与 JWT

### 1.1 服务端报 `JSON Web Key Set malformed`（401）
- **现象**：所有带 JWT 的请求返回 401，`/v1/projects` 返回
  `{"error":"unauthorized","message":"Invalid bearer token: JSON Web Key Set malformed"}`。
- **原因**：`OIDC_JWKS_URL` 配成了 `https://auth.panghuer.top/.well-known/jwks.json`，
  而该 URL 返回的不是 JWKS（实际返回 `{"status":"error","msg":"Unauthorized operation"}`）。
  Casdoor discovery（`/.well-known/openid-configuration`）返回的真实 `jwks_uri` 是
  `/.well-known/jwks`（无 `.json` 后缀）。
- **解决**：`k8s/core.yaml` 的 `OIDC_JWKS_URL` 改为 `https://auth.panghuer.top/.well-known/jwks`，
  重新 `kubectl apply -k k8s` 并重启。**教训：JWKS URL 以 discovery 返回的 `jwks_uri` 为准，
  不要自行拼 URL。**

### 1.2 `OIDC_AUDIENCE` 不匹配（所有请求 401）
- **现象**：preflight 报 `OIDC_AUDIENCE 应为 ...，当前为 openspec-api`。
- **原因**：服务端校验 `aud` claim，而 Casdoor 的 JWT `aud` = **签发该 JWT 的应用的
  `client_id`**（OIDC 规范）。本集群复用了通用 sso 应用 `panghu-suite`，其 client_id 是
  `ece3f52410b046fe0952`，不是自定义的 `openspec-api`。
- **解决**：`OIDC_AUDIENCE` 设为 `ece3f52410b046fe0952`（即 panghu-suite 的 client_id）。
  这样不要求每个服务单独注册 Casdoor 应用。

### 1.3 JWT 的 `aud` 是数组
- **现象**：preflight 报 `JWT aud=['ece3f52410b046fe0952'] 与期望 ... 不一致`。
- **原因**：OIDC 规范允许 `aud` 是字符串或数组，Casdoor 签发的是**数组**
  `["ece3f52410b046fe0952"]`。preflight 脚本最初按字符串比较，误报。
- **解决**：服务端 jose 的 `audience` 校验天然兼容数组，无需改服务。仅修正了
  `scripts/preflight.sh` 的比较逻辑（先展开数组再判断成员）。

### 1.4 密码登录走不通：`Unauthorized operation` / `deny`
- **现象**：`POST /api/signin` 报 `{"status":"error","msg":"Unauthorized operation"}`，
  Casdoor 日志里 `POST /api/signin ... result = deny`。
- **原因**：用户是通过 **GitHub OAuth** 注册的 Casdoor 账户（`user.github` 字段有值），
  **从未设置 Casdoor 密码**（`hash`/`pre_hash` 为空）；且 `panghu-suite` 应用的 providers
  只有 `github` 和 `provider_email`，**没有 password provider**。密码登录对这种账户永远失败。
- **解决**：改用**浏览器授权码流**获取 JWT（见 `scripts/get-token.sh`），不要用密码登录。
  排查时用 `select name,github,hash<>'' as has_password from user where name='...'` 确认是否无密码。

### 1.5 Casdoor `/api/signin` 报 `GetOwnerAndNameFromId() error, wrong token count`
- **原因**：该版本 Casdoor 要求 `username` 用 **`组织/用户名`** 格式（如 `Normal-User/zmhhaha`），
  裸用户名无法解析。
- **解决**：`curl -d "username=Normal-User/zmhhaha" ...`。（仅当用户有密码时此路径才有意义。）

### 1.6 获取 JWT 的可行方式对比
| 方式 | 可用性 | 说明 |
|---|---|---|
| `POST /api/login/oauth/access_token` + `grant_type=password` | ❌ | 本 Casdoor 禁用了 password grant |
| `POST /api/signin`（密码） | ⚠️ | 仅对有密码的用户；本环境用户走 GitHub 无密码 |
| **浏览器授权码流** | ✅ | `scripts/get-token.sh`；需管理员在 panghu-suite 白名单加 `https://openspec.panghuer.top/mcp` |

授权码流前置：Casdoor 管理员在 应用 → panghu-suite → Redirect URLs 增加
`https://openspec.panghuer.top/mcp`（用户 `zmhhaha` 非管理员，需 admin 账号操作）。

### 1.7 Casdoor 用户 `sub` 与 Gitea 用户映射
- Gitea 用户 `zmh_haha` 的 `login_name` = `27714443`，与 Casdoor 用户 `zmhhaha` 的
  `sub`/`id` 一致 —— 说明 Gitea 的 Casdoor OAuth 外部 ID 绑定用的就是 Casdoor 的 `id`，
  映射关系可靠。
- 身份绑定（`openspec_identity_map`）以 **邮箱** 为首次解析依据：Casdoor JWT 的 `email`
  必须与 Gitea 用户邮箱**完全一致**。本环境两者均为 `zmh_haha@163.com`。
- **注意**：Gitea 对非管理员默认可能隐藏用户邮箱。服务用 `read:user` token 调
  `/users/search` 必须能看到邮箱，否则绑定会 409。用 `scripts/preflight.sh` 或
  `scripts/provision-gitea.sh` 提前验证。

---

## 2. Gitea 与 Vault 凭据

### 2.1 ExternalSecret 报 `cannot find secret data for key: "database_url"`
- **现象**：`kubectl -n openspec describe externalsecret openspec-service-secrets` 报
  `error processing spec.data[0] (key: secret/data/openspec/service), err: cannot find secret data for key: "database_url"`，
  Ready=False。
- **原因**：手动 `vault kv put secret/openspec/service gitea_provision_token=... gitea_username=...`
  在 KV v2 里是**整体替换**，把 `deploy.sh` 之前写入的 `database_url` 冲掉了。
- **解决**：用 `vault kv patch`（增量）而不是 `kv put`。`scripts/provision-gitea.sh` 已用 patch。
  ```bash
  kubectl -n vault exec vault-0 -- vault kv patch secret/openspec/service \
    database_url='postgresql://openspec_service:<密码>@postgres.data.svc.cluster.local:5432/openspec_service'
  ```
  然后触发 ExternalSecret 同步并重启：
  ```bash
  kubectl -n openspec annotate externalsecret openspec-service-secrets "force-sync=$(date +%s)" --overwrite
  kubectl -n openspec rollout restart deployment/openspec-service
  ```

### 2.2 Pod 一直跑着失效的 Gitea token
- **现象**：preflight 报 `Gitea token 无效`；`/api/v1/user` 报 `user does not exist`。
- **原因**：k8s Secret 里的 `GITEA_TOKEN` 已过期/被轮换，而 ExternalSecret 因缺
  `database_url` 一直同步失败，Pod 用旧值运行。
- **解决**：修好 Vault（补 `database_url`）→ force-sync ExternalSecret → 重启。
  `scripts/deploy.sh --wait` 会自动完成整套（补 database_url → 同步 → apply → 重启）。

### 2.3 Gitea token 认证的用户名
- Gitea 的 HTTP Basic 认证中，token 作为密码，**用户名可以是任意值**（token 值本身定位归属者）。
  实测 `zmhhaha` / `zmh_haha` 均返回 200。
- 规范上仍建议 `GITEA_USERNAME` 填 token 所属的 **Gitea 登录名**（如 `zmh_haha`），
  便于审计。该值在 Vault `secret/openspec/service` 的 `gitea_username`。

---

## 3. 镜像与构建

### 3.1 服务报 `Gitea clone failed: spawn git ENOENT`（503）
- **现象**：`GET /v1/projects/{id}/specs` 返回 503 `dependency_unavailable`，
  message 为 `Gitea clone failed: spawn git ENOENT`。
- **原因**：基础镜像 `arm64v8/node:22-bookworm-slim` **没有 `git`**，而服务在
  `ensureWorkspace` 里直接 spawn git clone。
- **解决**：Dockerfile 安装 git（见 `openspec_service/Dockerfile`），重新构建镜像并部署。

### 3.2 apt 源卡死：`apt-get update` 卡在 deb.debian.org
- **现象**：构建时 `apt-get update` 长时间卡在 `Get:1 http://deb.debian.org/debian bookworm InRelease`，
  进程 0% CPU。
- **原因**：集群出口访问 `deb.debian.org` 不可靠（curl 目录能 200，但 apt 具体文件卡死）。
- **解决**：参照 `base/Dockerfile`，apt 源换成中科大镜像
  `mirrors.ustc.edu.cn`（同时替换 `security.debian.org`）：
  ```dockerfile
  RUN sed -i -e "s/deb.debian.org/mirrors.ustc.edu.cn/g" \
             -e "s/security.debian.org/mirrors.ustc.edu.cn/g" \
             /etc/apt/sources.list.d/debian.sources && \
      apt-get update && \
      apt-get install -y --no-install-recommends git ca-certificates && \
      rm -rf /var/lib/apt/lists/*
  ```

### 3.3 版本标签
- 本项目统一用 `latest` 镜像标签 + `imagePullPolicy: Always`，不用数字版本号。
  重新构建后 `kubectl -n openspec rollout restart deployment/openspec-service` 即可拉新。

---

## 4. OpenSpec 领域

### 4.1 validate 返回 422 `must include at least one scenario`
- **现象**：`POST .../validate` 返回 422，message 为
  `ADDED "Login" must include at least one scenario`。
- **原因**：OpenSpec 要求每条 `### Requirement:` 至少带一个 `#### Scenario:`（含
  `- **WHEN** ... - **THEN** ...`）。测试内容太简略。
- **解决**：按 OpenSpec 规范写 delta spec：
  ```markdown
  ## ADDED Requirements

  ### Requirement: Login
  The system SHALL accept a login.

  #### Scenario: Login works
  - **WHEN** credentials are valid
  - **THEN** access is granted
  ```

### 4.2 内部路径泄露（已修复）
- 早期 `validate` / `archive` 会把 OpenSpec 输出的 `root.path`（`/data/workspaces/{uuid}`）暴露给客户端。
- 已修复：`src/workspace.mjs` 的 `redactOpenSpecOutput()` 在**成功与失败路径**都删除 `root`
  和 `archive.path`，与 `archive` 的脱敏一致。

### 4.3 变更不存在时的行为
- `POST .../changes/{id}` 幂等语义：同 key 重放返回原响应；`PUT` 用于更新已有 change；
  `validate` 不要求 `If-Match`（不改工作区）；`apply-specs` / `archive` 要求
  `Idempotency-Key` + `If-Match`。
- **archive 失败的重试陷阱**：`archive` 成功后 change 会移入 `openspec/changes/archive/YYYY-MM-DD-{changeId}`。
  若 archive 失败，change 保持 active；此时若 `archive/YYYY-MM-DD-{changeId}` 已存在
  （例如上次已归档过），重试会返回 422 `archive_target_exists`。冒烟脚本因此使用
  **每次唯一的 change id**（`login-$(date +%s)`）。当前无删除 change 的 API。

---

### 4.4 Codex 报 `streamable HTTP session expired with 404 Not Found`
- **现象**：Codex 连 `https://openspec.panghuer.top/mcp` 报
  `streamable HTTP session expired with 404 Not Found`，工具调用失败。
- **原因**：MCP 服务对**未知方法**（Codex 定时发的 `ping`、能力探测 `resources/list` 等）返回了
  **HTTP 404**。Codex 的 RMCP 客户端把 404 判定为 session 失效且不会自动重连
  （openai/codex issue #13969）。
- **解决**：按 MCP 规范修正 `src/mcp.mjs`——未知方法返回 **HTTP 200 + JSON-RPC
  `-32601 Method not found`**；只有 session 失效才返回 **404**（让客户端重连）；补了
  `ping` 与 `notifications/cancelled` 处理；所有响应带 `mcp-session-id`。

## 5. armbianbegin OpenSpec 项目注册

- 登记前：`armbianbegin` 源码在 GitHub，不在 Gitea；Gitea 里只有 `openspec-service/project-a-specs`。登记后，Gitea 中应出现独立的 `openspec-service/armbianbegin` OpenSpec store，源码仓库仍可保留在 GitHub。
- 处理：执行 `bash openspec_service/scripts/register-project.sh`，将返回的 UUID 写入 `.openspec-project.json`；后续 Codex/Claude Code 任务必须使用该 `projectId`，不能继续使用 `project-a-specs`。

## 6. Drone（未启用，仅记录）

- `.drone.yml` 是 **Drone 监听/触发构建的流水线文件**，不是部署清单。它必须放在
  **Drone 激活的那个 Gitea 仓库根目录**。
  要让 Drone 构建，需要把源码推到 Gitea 仓库并激活，且集群 runner 是
  `drone-runner-kube`（**不是 docker runner**），`type: docker` + docker.sock 的写法不适用，
  需改用 DinD/kaniko。当前不作为部署阻塞，暂缓。

---

## 7. 运维速查

```bash
# 重新构建 + 推送 + 部署（master 上）
cd /root/armbianbegin && bash openspec_service/scripts/build.sh
bash openspec_service/scripts/deploy.sh --wait

# 只重启拉新镜像（镜像已 push 后）
kubectl -n openspec rollout restart deployment/openspec-service

# 查看状态
kubectl -n openspec get pods,pvc,svc,externalsecret
kubectl -n openspec logs deploy/openspec-service --tail=50
kubectl -n openspec describe externalsecret openspec-service-secrets

# Vault 检查
kubectl -n vault exec vault-0 -- vault kv get secret/openspec/service

# Gitea token 有效性
curl -s -H "Authorization: token <GITEA_TOKEN>" http://<gitea-ip>:3000/api/v1/user
```

## 8. 待办/已知问题清单

- [ ] 跨副本部署：进程锁与 MCP session 目前都在单进程内存，多副本需 PostgreSQL advisory lock / 分布式 session。
- [ ] 本地测试环境需 node（当前 Windows 开发机 node 不在 PATH，测试在 master/CI 上跑）。
- [ ] Cloudflare Access 边界策略、监控、备份（见 DEVELOPMENT_BACKLOG.md P1/P2）。
