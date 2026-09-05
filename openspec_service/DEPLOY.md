# OpenSpec Service 开发与部署说明

## 本地开发

```bash
npm install
DATABASE_URL=postgresql://... GITEA_TOKEN=... OIDC_ISSUER=... OIDC_JWKS_URL=... npm start
```

仓库使用 `pnpm-lock.yaml` 锁定依赖；本地也可以运行 `pnpm install --frozen-lockfile`。容器构建不复制本地 `node_modules`。

服务不调用 LLM。用户自己的 AI 工具通过 REST 或 MCP 提供 proposal/spec/design/tasks 内容；服务负责项目授权、持久化、校验和 Git 审计。

## 集成配置文件位置

OpenSpec 目录只维护 API 自身的核心资源。外部基础设施清单和 Casdoor 配置分别位于：

- Vault：`../vault/inventory/openspec-service-externalsecret.yaml`
- Cloudflare：`../cloudflare-tunnel/operator/openspec-service-route.yaml`
- Casdoor/OAuth：`CASDOOR_SETUP.md`

因此 `openspec_service/k8s/` 的 Kustomize 不会创建 ExternalSecret 或 TunnelRoute。

Gitea Issue 审批自动创建项目的配置和 Webhook 初始化见
[`PROJECT_REQUEST_APPROVAL.md`](PROJECT_REQUEST_APPROVAL.md)。该流程需要额外的
`gitea_webhook_secret` Vault 字段；在写入该字段前不要应用更新后的 ExternalSecret。

### Gitea Issue 审批自动创建项目

用户在 `https://openspec.panghuer.top/project-requests` 填写表单，服务自动在
`openspec-service/project-requests` 创建标准 Issue。管理员检查申请后添加
`status:approved` 标签。Gitea 通过 Issues Webhook 调用
`POST /webhooks/gitea`，服务验证 HMAC 签名和审批人的 Admin/Owner 权限后，一次性创建
Gitea 私有 OpenSpec store、初始化 `openspec/`、授权申请人、评论 `projectId` 并关闭 Issue。
服务不轮询 Issue；重复 Webhook 使用 Issue 编号幂等处理，不会重复创建项目。

部署顺序如下，必须先写入 Webhook secret：

```bash
WEBHOOK_SECRET="$(openssl rand -hex 32)"
kubectl -n vault exec vault-0 -- vault kv patch secret/openspec/service \
  gitea_webhook_secret="${WEBHOOK_SECRET}"

bash openspec_service/scripts/build.sh
bash openspec_service/scripts/deploy.sh --wait
```

然后创建申请仓库、Issue 模板、状态标签和 Gitea Webhook：

```bash
export GITEA_TOKEN='<受限 Gitea token>'
export GITEA_WEBHOOK_SECRET='<与 Vault 中相同的 secret>'
bash openspec_service/scripts/bootstrap-project-requests.sh
```

默认 Webhook 目标是集群内地址：

```text
http://openspec-service.openspec.svc.cluster.local:8080/webhooks/gitea
```

用户权限、Issue 模板、失败重试和安全边界见
[`PROJECT_REQUEST_APPROVAL.md`](PROJECT_REQUEST_APPROVAL.md)。

## Vault 初始化

`deploy.sh` 会按照 Hublog 的部署流程，使用现有 PostgreSQL 管理账号自动创建或更新
`openspec_service` 角色和数据库，并将同一个数据库密码写入 Vault。首次部署前只需要在
可信终端准备 OpenSpec 的 Gitea 服务账号字段：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/openspec/service \
  gitea_provision_token='<受限 Gitea token>' \
  gitea_username='openspec-service'
```

也可以直接用 `scripts/provision-gitea.sh` 自动完成：校验 token 有效性、组织 `openspec-service` 存在性、用户邮箱对 token 可见，再用 `vault kv patch`（**不会覆盖 `database_url`**）写入 Vault，并触发 ExternalSecret 同步与滚动重启：

```bash
GITEA_TOKEN='<受限 Gitea token>' GITEA_USERNAME='zmh_haha' \
  bash openspec_service/scripts/provision-gitea.sh
```

**网页版领取 JWT（可选，推荐）**：`https://openspec.panghuer.top/token` 页面让任意用户
用浏览器登录 Casdoor 后直接复制自己的 JWT。需要两步准备：

1. Casdoor 管理员在 `panghu-suite` 的 Redirect URLs 增加 `https://openspec.panghuer.top/token`。
2. 把 client secret 写入 Vault（用 `kv patch`，不覆盖已有键）：
   ```bash
   kubectl -n vault exec vault-0 -- vault kv patch secret/openspec/service \
     casdoor_client_secret='<panghu-suite client secret>'
   ```
3. 应用 ExternalSecret 并重启（`scripts/deploy.sh --wait` 或手动 force-sync + restart）。

`gitea_provision_token` 只用于创建/初始化 OpenSpec 私有仓库、查询 Gitea 用户邮箱和查询 collaborator 权限，不得使用 Gitea 全局管理员 token。创建 Token 时至少授予 `read:user` 以及仓库创建/内容写入/协作者管理所需的最小权限。`gitea_username` 必须是该 token 所属的 Gitea 登录名，用于 Git HTTP Basic 认证；它不是组织名。你的组织名 `openspec-service` 配置在 `k8s/core.yaml` 的 `GITEA_OWNER`。

Casdoor 用户名不需要与 Gitea 用户名相同。服务首次看到某个 Casdoor `sub` 时，会用 JWT 的 `email` claim 调用 Gitea 用户搜索接口，要求邮箱精确匹配且只对应一个 Gitea 用户，然后保存实际 Gitea login；后续请求使用这个不可变绑定。Casdoor 应用需要启用 `email` scope，并确保每个 JWT 带有可信邮箱。

上面的 Vault 路径已有 `database_url` 时，脚本会复用其中的密码并同步 PostgreSQL；没有时会自动生成密码。也可以显式指定密码（密码只会通过环境变量传给脚本，不要提交到 Git）：

```bash
OPENSPEC_DB_PASSWORD='<password>' bash openspec_service/scripts/deploy.sh --wait
```

## Casdoor 与 Gitea

详细 Casdoor 应用配置见 `CASDOOR_SETUP.md`。

1. 使用 Casdoor 通用 sso 应用 `panghu-suite`，audience 为其 client_id `ece3f52410b046fe0952`，并确保 JWT 返回可信 `email` claim（不要求每个服务单独注册应用）。
2. 确认 discovery 返回的真实 `issuer` 和 `jwks_uri`，更新 `k8s/core.yaml`。
3. 在 Gitea 配置 Casdoor OAuth/OIDC；不要求 Casdoor `preferred_username` 与 Gitea 用户名相同，但必须保证两边用户邮箱唯一且一致。
4. 将管理员 Casdoor `sub` 写入 `BOOTSTRAP_ADMIN_SUBJECTS`，然后滚动更新服务。

## 构建与部署

从 `armbianbegin` 仓库根目录执行：

```bash
# 部署前预检（只读；传真实 JWT 可额外验证 aud/email/sub）
CASDOOR_JWT="$CASDOOR_JWT" bash openspec_service/scripts/preflight.sh
bash openspec_service/scripts/build.sh
bash openspec_service/scripts/deploy.sh --wait
```

`build.sh` 默认构建并推送 `linux/arm64` 镜像；只构建不推送时使用 `bash openspec_service/scripts/build.sh --no-push`。`deploy.sh` 会先应用 OpenSpec 核心资源，然后创建数据库用户、同步 Vault、等待 ExternalSecret 并滚动重启服务，最后应用 Cloudflare TunnelRoute。需要分阶段部署时可使用 `--core-only`、`--skip-vault` 或 `--skip-cloudflare`。

默认 PostgreSQL 管理账号为 `appuser`，管理数据库为 `appdb`；可通过 `POSTGRES_ADMIN_USER`、`POSTGRES_ADMIN_DB` 覆盖。`--skip-vault` 会跳过数据库和 Vault 初始化，仅适合已有 Secret 的场景。

集群现有 Registry 使用 HTTPS；在执行 build/push 和节点拉取前，先按集群 CA 配置 Docker/containerd 信任，不能把 `5000` 当作明文 HTTP Registry。

当前清单使用每项目 Git workspace 的共享 PVC 根目录 `/data/workspaces/{project UUID}`；项目授权边界由 JWT + Gitea ACL + 服务端路径映射共同保证。多副本前必须把进程锁替换为 PostgreSQL advisory lock。

## API 与 MCP

REST 和 MCP 共用项目授权。MCP 地址为 `https://openspec.panghuer.top/mcp`，客户端使用 Casdoor Bearer JWT。业务路径必须带 `projectId`：

```text
GET  /v1/projects
GET  /v1/projects/{projectId}/specs
GET  /v1/projects/{projectId}/changes
POST /v1/projects/{projectId}/changes/{changeId}
PUT  /v1/projects/{projectId}/changes/{changeId}
POST /v1/projects/{projectId}/changes/{changeId}/validate
POST /v1/projects/{projectId}/changes/{changeId}/apply-specs
POST /v1/projects/{projectId}/changes/{changeId}/archive
```

创建或更新 change 的请求体可带 `files` 对象，例如 `{"files":{"proposal.md":"...","design.md":"..."}}`；服务不会调用 LLM，只保存用户提供的内容。先读取 specs 或 changes 列表取得当前 `revision`，然后请求必须带 `Idempotency-Key` 和 `If-Match`，同一用户/项目复用同键会重放原响应。`POST` 只创建新 change，`PUT` 更新已有 change 工件。

`apply-specs` 使用 OpenSpec 官方 delta merge 更新主 specs，但保留 active change；`archive` 要求 Gitea Admin 权限，会在更新主 specs 后将 change 移至 `openspec/changes/archive/YYYY-MM-DD-{changeId}`。两个操作都必须带 `Idempotency-Key` 和当前 Git SHA 的 `If-Match`。

首个项目创建使用 `POST /v1/projects`，仅 `BOOTSTRAP_ADMIN_SUBJECTS` 中的用户可调用；后续项目访问完全由 Gitea 仓库 ACL 决定。
