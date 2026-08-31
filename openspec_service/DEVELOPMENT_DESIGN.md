# OpenSpec、Gitea、Casdoor 总体开发设计

## 1. 设计目标

OpenSpec Service 为后续应用提供统一的规格和变更 API。对外通过两种契约提供：REST JSON（脚本与内部契约）和 MCP（面向 Codex、Claude Code、Cursor 等 AI 工具）。LLM 能力由用户自己的 Codex、Claude、Cursor、Copilot 或其他 AI 工具提供，服务不直接调用 LLM。

服务从第一版开始采用项目级用户隔离：Casdoor 负责认证，Gitea 负责用户/组织/仓库权限，OpenSpec Service 负责 API、权限复核和 OpenSpec 领域操作。

```text
Casdoor：你是谁
Gitea：你能访问哪个项目、能做什么
OpenSpec Service：对项目执行哪些规格操作
Vault：凭据放在哪里
Cloudflare Tunnel：怎样安全到达服务
```

## 2. 总体架构

```text
用户 / AI Agent / 业务应用
          |
          | HTTPS + Bearer JWT
          v
Cloudflare Tunnel
openspec.panghuer.top
          |
          v
OpenSpec Service
  |-- Casdoor JWT 校验
  |-- Casdoor 用户到 Gitea 用户映射
  |-- Gitea 仓库 ACL 检查
  |-- OpenSpec parse / validate / archive
  |-- 项目工作区和 Git revision 管理
  |-- 审计日志
  |
  +--> PostgreSQL：项目注册表、身份映射、审计和任务状态
  +--> Vault：服务凭据、OAuth token、项目 Git 凭据
  +--> Gitea：独立 OpenSpec 仓库、权限、分支和 PR
```

## 3. 隔离模型

每个 OpenSpec 项目对应一个 Gitea 私有仓库：

```text
gitea/openspec/project-a-specs
gitea/openspec/project-b-specs
alice/personal-project-specs
```

项目之间不共享：

- specs 和 changes 文件；
- Git 历史和 revision；
- 可写工作目录；
- Gitea token；
- 归档和审计范围。

API 不接受客户端提供的文件路径、仓库地址、分支或 shell 参数。客户端只能提交数据库生成的 `projectId`，服务端将它映射到已登记的 Gitea 仓库和工作区。

## 4. 认证流程

### 4.1 用户登录

用户在 Casdoor 完成登录，获得 OIDC/JWT。JWT 至少包含：

```json
{
  "sub": "casdoor-user-id",
  "email": "alice@example.com",
  "iss": "https://auth.panghuer.top",
  "aud": "ece3f52410b046fe0952",
  "exp": 1770000000
}
```

OpenSpec Service 验证 JWT 的签名、issuer、audience、过期时间和 `sub`。audience 使用通用 sso 应用 `panghu-suite` 的 client_id（`ece3f52410b046fe0952`），不要求每个服务单独注册 Casdoor 应用。健康检查可以匿名访问，其他接口默认必须携带 Bearer JWT。

### 4.2 Casdoor 与 Gitea 用户映射

Gitea 配置 Casdoor 为 OAuth/OIDC 身份提供方，使两个系统可以使用同一邮箱关联用户；两边的登录名不要求相同：

```text
Casdoor 用户（用户名 alice-casdoor，邮箱 alice@example.com）
  -> Gitea 用户（用户名 alice-gitea，邮箱 alice@example.com）
```

首次请求时，服务使用 JWT 的 `email` claim 调用 Gitea 用户搜索接口，要求精确匹配且只有一个结果，然后把实际 Gitea login 写入 `openspec_identity_map`。映射的主键是 Casdoor `sub`，实际 Gitea login 只在首次绑定时解析；绑定完成后，后续 ACL 查询使用数据库中保存的 login，即使用户修改 Casdoor 邮箱也不会自动切换到另一个 Gitea 账号。没有邮箱、邮箱未精确匹配、匹配多个 Gitea 用户或 Gitea API 不返回可核对邮箱时，服务拒绝绑定。

用于用户搜索的服务账号 Token 必须具备最小的 Gitea `read:user` 能力，以及创建私有仓库、初始化文件和查询 collaborator 权限所需的仓库权限；不使用全局管理员 Token。Casdoor 应用必须申请 `email` scope，并确保 JWT 包含可信的 `email` claim。

## 5. Gitea 权限模型

Gitea 私有仓库 ACL 是项目授权的最终来源，OpenSpec Service 不复制一套成员权限表。

| Gitea 权限 | OpenSpec 能力 |
|---|---|
| None | 不可访问，API 返回 404 |
| Read | 查询 specs、changes、状态和 revision |
| Write | 创建/修改 change、执行 validate 和受控 spec 更新 |
| Admin | archive、项目设置、成员管理、凭据轮换 |

Gitea 组织 Team 用于批量授权，个人仓库 collaborator 用于个人项目或例外授权。移除 Gitea 成员后，OpenSpec API 下一次请求立即失去访问权限。

## 6. 权限检查流程

每个业务请求严格按以下顺序处理：

```text
请求
  |
  v
校验 Casdoor JWT
  |
  v
解析 sub / email，并按邮箱解析 Gitea login
  |
  v
projectId -> 项目注册表 -> Gitea owner/repository
  |
  v
查询用户对 Gitea 仓库的权限
  |
  +-- 无权限：404
  +-- Read：允许读操作
  +-- Write：允许写和 validate
  +-- Admin：允许 archive 和管理操作
```

服务账号不能使用全局管理员 Token 代替真实用户授权。MVP 使用受限服务账号：只拥有只读的仓库权限查询能力和项目仓库操作能力；以服务账号执行 git push 时，commit author 必须写真实 Casdoor 用户，真实 actor 由审计日志记录。用户绑定的 Gitea OAuth Token（支持以用户身份 push / 开 PR）是二期增强，需处理 refresh token 轮换；用户 token 作用域覆盖其全部仓库，不能视为项目级隔离。

ACL 检查依赖 Gitea API 可用性。Gitea API 不可达时无法完成授权，应失败关闭（fail-closed）或采用短 TTL 缓存（如 30-60s，撤权时接受短暂延迟）；这不同于 git remote 不可达——后者只影响 push/clone，不影响已检出工作区的只读查询。

## 7. 项目创建流程

```text
管理员
  |
  | POST /v1/projects
  v
OpenSpec Service
  |
  | 1. 校验 Casdoor JWT
  | 2. 确认管理员/组织权限
  | 3. 在 Gitea 创建私有仓库
  | 4. 初始化 OpenSpec 目录和 schema
  | 5. 建立 projectId 映射
  | 6. 将创建者设为 Gitea 仓库 Admin（collaborator），即项目初始 owner（不写独立成员表）
  v
Gitea OpenSpec 仓库
```

初始化结构：

```text
openspec-project-a/
├── openspec/
│   ├── specs/
│   ├── changes/
│   └── config.yaml
└── .openspec-store/
    └── store.yaml
```

数据库只保存项目映射和审计信息：

```text
project_id
gitea_owner
gitea_repository
default_branch
created_by
created_at
```

成员和读写权限以 Gitea 为准。

首个项目引导：由于授权依赖 Gitea ACL，需提供一次性 bootstrap 流程（管理员在 Gitea 创建仓库并授权后，服务登记 `projectId` 映射），避免权限检查自身无法初始化。

## 8. API 设计

禁止使用没有项目边界的全局业务接口：

```text
/v1/specs
/v1/changes
```

使用项目限定路径：

```text
POST /v1/projects
GET  /v1/projects
GET  /v1/projects/{projectId}/specs
GET  /v1/projects/{projectId}/changes
GET  /v1/projects/{projectId}/changes/{changeId}
POST /v1/projects/{projectId}/changes/{changeId}
PUT  /v1/projects/{projectId}/changes/{changeId}
POST /v1/projects/{projectId}/changes/{changeId}/validate
POST /v1/projects/{projectId}/changes/{changeId}/apply-specs
POST /v1/projects/{projectId}/changes/{changeId}/archive
```

除项目创建（仅需要幂等键）外，所有会改变项目 Git 工作区的请求要求：

- `Authorization: Bearer <Casdoor JWT>`；
- `Idempotency-Key`；
- `If-Match: <Git SHA>`；
- 服务端生成的 request ID。

Git SHA 不匹配时返回 `409 Conflict`，不得静默覆盖其他用户的提交。

### MCP 接入（面向 AI 工具的消费方式）

REST 是内部与脚本契约；面向 Codex、Claude Code、Cursor 等 AI 工具，统一通过 MCP（Model Context Protocol）消费。服务在公开端点挂一个远程 MCP server，复用同一套 JWT 校验与项目隔离，不做第二套认证。

- 端点：`https://openspec.panghuer.top/mcp`，使用 streamable HTTP transport；对仅支持 SSE 的客户端提供兼容路由。
- 认证：客户端将 Casdoor JWT 放入 `Authorization: Bearer <JWT>`，服务端复用 §4 的 JWT 校验中间件。每个开发者使用自己的 token；CI/脚本使用受限服务账号 token。
- 工具与 REST 一一对应，项目边界在服务端强制：

| MCP tool | 对应 REST |
|---|---|
| `list_projects` | `GET /v1/projects` |
| `list_specs` | `GET /v1/projects/{projectId}/specs` |
| `list_changes` | `GET /v1/projects/{projectId}/changes` |
| `get_change` | `GET /v1/projects/{projectId}/changes/{changeId}` |
| `create_proposal` | `POST /v1/projects/{projectId}/changes/{changeId}` |
| `update_proposal` | `PUT /v1/projects/{projectId}/changes/{changeId}` |
| `validate_change` | `POST /v1/projects/{projectId}/changes/{changeId}/validate` |
| `apply_specs` | `POST /v1/projects/{projectId}/changes/{changeId}/apply-specs` |
| `archive_change` | `POST /v1/projects/{projectId}/changes/{changeId}/archive` |

- 客户端配置示例：

```bash
# Codex
codex mcp add openspec --transport streamable-http \
  https://openspec.panghuer.top/mcp \
  --header "Authorization: Bearer $CASDOOR_JWT"

# Claude Code
claude mcp add --transport http openspec \
  https://openspec.panghuer.top/mcp \
  --header "Authorization: Bearer $CASDOOR_JWT"
```

- 写工具仍要求 `Idempotency-Key` 与当前 revision（REST 使用 `If-Match`，MCP 使用 `expectedRevision`）；MCP 层把服务端 request ID 关联到工具调用，保证审计可追踪。
- 不依赖 GitMCP 等第三方托管作为 store 操作入口：它们只暴露仓库浏览资源，不带本项目的权限、写入与审计能力。

## 9. OpenSpec 读写流程

### 9.1 读取

```text
用户 -> Casdoor JWT -> OpenSpec API
     -> JWT 校验
     -> Gitea ACL 检查
     -> 加载 project workspace
     -> 读取 openspec/specs 或 changes
     -> 返回 JSON/Markdown
```

### 9.2 创建或修改 change

```text
1. 校验 JWT 和 Gitea Write 权限
2. 校验 projectId/changeId
3. 取得项目工作区和项目写锁
4. 校验 If-Match Git SHA
5. 写入 proposal/spec/design/tasks
6. 执行 OpenSpec validate
7. Git commit
8. 记录 actor、旧 SHA、新 SHA 和 action
9. 返回新 revision
```

### 9.3 Git 分支策略

MVP 可以由服务统一提交，但必须在审计中保留真实 Casdoor 用户。稳定版本建议每个用户使用独立分支：

```text
users/alice/add-dark-mode
```

完成后由服务创建 Gitea Pull Request，利用 Gitea 的 review、分支保护和合并记录完成协作。

## 10. Vault 设计

### 服务级密钥

```text
secret/openspec/service
```

保存 Gitea 仓库创建权限、数据库连接串等。MVP 只校验 Casdoor JWT 的公钥，不需要把 Casdoor client secret 注入 API；未来动态 OAuth 再单独增加。

### 用户级 Gitea OAuth Token

```text
secret/openspec/users/{casdoor-sub}/gitea
```

保存 access token、refresh token、过期时间和 Gitea 用户名。若使用用户 OAuth Token，服务按请求获取，不把所有用户 token 注入同一个 Pod Secret。

### 项目级凭据

```text
secret/openspec/projects/{project-id}/git
```

只允许存放该项目专用的 Git 凭据，不能使用全局管理员 Token。注意：Gitea access token 按权限类型作用域（如 `write:repository`），不按仓库隔离；"项目级"隔离靠该凭据对应的账号只以 collaborator 身份存在于该项目仓库（而非组织成员），从物理上无法访问其他仓库。

## 11. Cloudflare Tunnel

Cloudflare Tunnel 只负责公网 HTTPS 和流量转发，不负责项目权限：

```text
openspec.panghuer.top
  -> main tunnel
  -> openspec-service.openspec.svc.cluster.local:8080
```

TunnelRoute 使用独立 hostname，不使用复杂 path rewrite。Cloudflare Access 可以作为边界防护，但 API 仍必须验证 Casdoor JWT，不能只信任 Cloudflare Header。

## 12. 组件职责

| 组件 | 职责 |
|---|---|
| Casdoor | 用户登录、OIDC、JWT、组织身份 |
| Gitea | 用户、组织、私有仓库、ACL、分支、PR、Git 历史 |
| OpenSpec Service | API、MCP server、JWT 校验、Gitea 权限检查、OpenSpec 解析/校验/归档 |
| PostgreSQL | 项目注册表、身份映射、审计日志、任务状态 |
| Vault | OAuth secret、Gitea token、数据库密码 |
| Cloudflare Tunnel | 公网 HTTPS 和内部 Service 转发 |
| OpenSpec CLI/库 | proposal/spec/design/tasks、validate、archive 领域逻辑 |
| 用户 AI 工具 | LLM 推理、上下文理解、生成和修改工件 |

## 13. 开发顺序

1. 配置 Casdoor OIDC 和 Gitea OAuth/OIDC 用户映射。
2. 创建 PostgreSQL 项目注册表和审计表，不复制 Gitea 成员 ACL。
3. 实现 JWT 中间件和 Gitea 权限检查中间件。
4. 将 API 全部改为 project-scoped 路径。
5. 实现每项目 Git workspace、路径校验、项目级锁和 revision 条件写入。
6. 实现项目创建、Gitea 私有仓库初始化和 Vault 凭据生命周期。
7. 完成 specs/changes 查询和 validate。
8. 增加 MCP server 适配层（streamable HTTP + Bearer JWT），验证 Codex/Claude Code 可读写。
9. 部署 OpenSpec 核心 Kubernetes 资源；Vault ExternalSecret 和 Cloudflare TunnelRoute 分别由 `../vault/inventory/` 与 `../cloudflare-tunnel/operator/` 管理。
10. 完成跨用户、跨项目、撤权、并发冲突和恢复测试后再开放公网。
11. 后续再增加 Gitea Pull Request、异步任务和多副本分布式锁。

## 14. 必须通过的验收场景

- 用户 A 无法读取用户 B 无权限的项目；
- 用户从 Gitea 项目移除后，API 立即拒绝访问；
- Read 用户无法创建或修改 change；
- Write 用户无法 archive 或管理成员；
- projectId 不能访问另一个项目的文件或 Git workspace；
- 客户端提交路径、remote、分支或 shell 参数时请求被拒绝；
- 两个用户同时写入同一项目时，一个请求因 SHA 冲突返回 `409`；
- Pod 重启后项目工作区和 Git 历史不丢失；
- Gitea remote 暂时不可用时，不泄露 token，且服务返回可诊断错误；
- Gitea API 不可达时授权检查失败关闭或走短 TTL 缓存，不静默放行；
- Cloudflare 公网访问经过 HTTPS、JWT 和 Gitea ACL 三层校验。
- Codex/Claude Code 通过远程 MCP 读取 specs 并创建/校验 change，各用其 JWT 时互不影响、审计完整。

## 15. 当前实现的部署要求

当前目录已经按本设计实现 project-scoped API、每项目 workspace、Casdoor sub 到 Gitea username 的不可变映射和 Gitea ACL 复核；`k8s/` 使用 `/data/workspaces/{projectId}` 和单副本 PVC。部署前仍必须完成真实 Casdoor 应用、Gitea 组织/受限服务账号、PostgreSQL、Vault ExternalSecret 和 Cloudflare 配置，禁止使用全局管理员 token 或跳过 JWT/ACL 校验。Vault 和 Cloudflare 的部署资源不放在本目录，分别维护于 `../vault/` 和 `../cloudflare-tunnel/`；Casdoor 配置见本目录的 `CASDOOR_SETUP.md`。
