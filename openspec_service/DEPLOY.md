# OpenSpec Service 开发与部署说明

## 本地开发

```bash
npm install
DATABASE_URL=postgres://... GITEA_TOKEN=... OIDC_ISSUER=... OIDC_JWKS_URL=... npm start
```

仓库使用 `pnpm-lock.yaml` 锁定依赖；本地也可以运行 `pnpm install --frozen-lockfile`。容器构建不复制本地 `node_modules`。

服务不调用 LLM。用户自己的 AI 工具通过 REST 或 MCP 提供 proposal/spec/design/tasks 内容；服务负责项目授权、持久化、校验和 Git 审计。

## 集成配置文件位置

OpenSpec 目录只维护 API 自身的核心资源。外部基础设施清单和 Casdoor 配置分别位于：

- Vault：`../vault/inventory/openspec-service-externalsecret.yaml`
- Cloudflare：`../cloudflare-tunnel/operator/openspec-service-route.yaml`
- Casdoor/OAuth：`CASDOOR_SETUP.md`

因此 `openspec_service/k8s/` 的 Kustomize 不会创建 ExternalSecret 或 TunnelRoute。

## Vault 初始化

在可信终端向现有 Vault 写入服务级密钥：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/openspec/service \
  database_url='postgres://openspec_service:<password>@postgres.data.svc.cluster.local:5432/openspec_service' \
  gitea_provision_token='<受限 Gitea token>' \
  gitea_username='openspec-service'
```

`gitea_provision_token` 只用于创建/初始化 OpenSpec 私有仓库和查询 collaborator 权限，不得使用 Gitea 全局管理员 token。`gitea_username` 必须是该 token 所属的 Gitea 登录名，用于 Git HTTP Basic 认证；它不是组织名。你的组织名 `openspec-service` 配置在 `k8s/core.yaml` 的 `GITEA_OWNER`。项目访问仍按 Casdoor sub 到 Gitea username 的不可变映射检查。PostgreSQL 数据库/用户需先由管理员创建。

## Casdoor 与 Gitea

详细 Casdoor 应用配置见 `CASDOOR_SETUP.md`。

1. 在 Casdoor 创建 `openspec-api` OIDC 应用，audience 为 `openspec-api`。
2. 确认 discovery 返回的真实 `issuer` 和 `jwks_uri`，更新 `k8s/core.yaml`。
3. 在 Gitea 配置 Casdoor OAuth/OIDC，使 Casdoor `preferred_username` 映射为 Gitea 用户名。
4. 将管理员 Casdoor `sub` 写入 `BOOTSTRAP_ADMIN_SUBJECTS`，然后滚动更新服务。

## 构建与部署

从 `armbianbegin` 仓库根目录执行：

```bash
docker build --platform linux/arm64 -t arm-cluster-master:5000/openspec-service:0.1.0 openspec_service
docker push arm-cluster-master:5000/openspec-service:0.1.0
kubectl apply -k openspec_service/k8s/
kubectl apply -f vault/inventory/openspec-service-externalsecret.yaml
kubectl apply -f cloudflare-tunnel/operator/openspec-service-route.yaml
kubectl -n openspec get pods,pvc,externalsecret,svc
```

建议先应用 OpenSpec 核心资源，确认 `openspec` namespace 已创建后，再应用 Vault ExternalSecret；TunnelRoute 可在 OpenSpec Service 的 ClusterIP Service 创建后应用。

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
