# 多用户隔离设计

## 决策

OpenSpec Service 从第一版即采用项目级多租户。不得部署当前以单个 `/data/store` 和单个 `openspec-git` Secret 为中心的清单；它只能作为早期本地原型参考。

隔离模型：

```text
Casdoor 用户 (JWT sub)
  -> organization / tenant
  -> OpenSpec project
  -> Gitea 私有仓库 ACL（Read=viewer / Write=editor / Admin=owner）
  -> 独立 Gitea repository + 独立工作目录（MVP 使用受限服务账号访问）
```

一个项目对应一个 OpenSpec store 仓库。项目之间不共享 specs、changes、Git 历史、凭据或可写工作区。

## 不可变安全边界

- 所有业务 API 必须使用 `/v1/projects/{projectId}/...`，禁止全局 `/v1/specs`、`/v1/changes`。
- `projectId` 是数据库生成的 UUID，不是文件路径、仓库名或用户提供的目录。
- 每个请求先验 JWT，再用 `sub` 和项目 UUID 从注册表得到 Gitea 仓库，实时查询该仓库的 Gitea ACL；无访问权限一律返回 404，避免泄露项目存在性。
- 角色由 Gitea 仓库权限直接映射，服务不再维护独立成员表：`Read`=viewer 只能读；`Write`=editor 可创建/更新/校验；`Admin`=owner 才可归档、管理成员和凭据轮换。
- 服务端从数据库获取 project 的 Git remote/credential reference；客户端不能提交 remote、store path、branch 或 shell 参数。
- 工作目录固定为 `/data/workspaces/{project UUID}`，路径由服务端拼接并经过 canonical path 校验。
- MVP 使用 Vault KV 路径 `secret/openspec/service` 注入受限 Gitea service account token；该 token 不能是全局管理员 token。按项目 Vault 凭据路径留作后续用户 OAuth/项目凭据增强。
- 每次写操作按 project UUID 加锁；将来多副本改为 PostgreSQL advisory lock 或 Redis lock。

## 数据库模型

使用现有 `data/postgres`，建立独立数据库/用户 `openspec_service`。服务自身只拥有这个数据库的权限。本库只保存项目映射、Casdoor identity 映射、审计和幂等状态；授权事实来源是 Gitea 仓库 ACL，不复制成员表（见 DEVELOPMENT_DESIGN.md §5、§7）。

```sql
create table openspec_projects (
  id uuid primary key default gen_random_uuid(),
  gitea_owner text not null,
  gitea_repository text not null unique,
  default_branch text not null default 'main',
  created_by text not null,
  created_at timestamptz not null default now()
);

create table openspec_identity_map (
  subject text primary key,
  gitea_username text not null unique,
  created_at timestamptz not null default now()
);

create table openspec_audit_events (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references openspec_projects(id),
  subject text not null,
  action text not null,
  request_id uuid not null,
  revision_before text,
  revision_after text,
  created_at timestamptz not null default now()
);

create index openspec_audit_project_created_idx
  on openspec_audit_events (project_id, created_at desc);
```

## API 表面

```text
POST /v1/projects                         create tenant project + Gitea store
GET  /v1/projects                         list only caller-visible projects
GET  /v1/projects/{projectId}/specs
GET  /v1/projects/{projectId}/changes
POST /v1/projects/{projectId}/changes/{changeId}
PUT  /v1/projects/{projectId}/changes/{changeId}
POST /v1/projects/{projectId}/changes/{changeId}/validate
POST /v1/projects/{projectId}/changes/{changeId}/apply-specs
POST /v1/projects/{projectId}/changes/{changeId}/archive
```

写请求要求 `Idempotency-Key` 和 `If-Match: <Git SHA>`。服务在授权、锁和 Git revision 均通过后才写入。

## Gitea 与 Vault 生命周期

创建项目由 bootstrap owner 发起，但服务使用受限 Gitea service account 创建私有仓库。注意 Gitea access token 按权限类型作用域（如 `write:repository`），不能按仓库限定；项目级用户权限仍由每个仓库 ACL 决定，服务账号只用于仓库创建、clone 和 ACL 查询。MVP 将该服务级 token 从 `secret/openspec/service` 通过 ExternalSecret 注入 Pod；用户 token 和按项目 Vault 凭据留作后续增强，不能在 MVP 中误当作独立 token。

## Kubernetes 存储

单副本 MVP 使用一个 `ceph-rbd` PVC，里面按项目 UUID 划分工作目录。该目录不是授权边界，真正的边界是 API 授权、项目独立 Git remote 和独立 Vault secret。若需要更强的运行时隔离或多副本，改为每项目 PVC/Job，或由 Git clone 到短生命周期 emptyDir 工作区后销毁。

## Casdoor

JWT 至少验证 issuer、audience、签名、过期时间和 `sub`。Casdoor organization 用于项目创建和租户归属校验，但项目成员权限必须来自 Gitea 仓库 ACL，不能仅依赖客户端传来的组织字段或 JWT 角色声明。

## 实施门槛

代码已经完成 PostgreSQL 项目映射、JWT/Gitea ACL、按项目 Git workspace 和 revision 防覆盖。真实部署前仍必须创建 PostgreSQL 数据库/用户、Vault `secret/openspec/service`、受限 Gitea service account、Casdoor 应用，并确认 `k8s/` 中的 issuer/JWKS、镜像地址和 bootstrap subject 已替换占位值；Vault ExternalSecret 请使用 `../vault/inventory/openspec-service-externalsecret.yaml`，Cloudflare TunnelRoute 请使用 `../cloudflare-tunnel/operator/openspec-service-route.yaml`，未完成这些配置时禁止把 TunnelRoute 暴露到公网。
