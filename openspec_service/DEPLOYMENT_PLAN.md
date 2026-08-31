# OpenSpec 对外服务部署方案

## 1. 目标与边界

目标是在服务器 `192.168.137.101` 的现有 Kubernetes 集群中部署一个对外的 OpenSpec 服务，供后续应用快速调用。

需要先明确：OpenSpec 本身是 Node.js CLI 和 Git/Markdown 规格库，不是现成的 HTTP 服务。因此部署内容应是一个受认证的服务适配层，而不是直接把 `openspec` 命令暴露给公网。

建议服务职责：

- 读取、创建、修改、校验和归档 OpenSpec changes/specs；
- 以 JSON API 供 Agent、Web 应用和自动化流程调用；
- 将规划数据保存在独立 Git 工作区（OpenSpec store），每次写操作形成可追踪提交；
- 复用现有 Cloudflare Tunnel 或 Nginx Ingress 对外暴露；
- 认证、密钥和审计与现有 OAuth/Casdoor、Vault、Gitea 基础设施集成。

不建议第一版支持：任意 shell 执行、任意路径读写、直接让公网请求触发 `git push`、多用户同时修改同一文件而没有版本冲突处理。

## 2. 推荐架构

```text
外部 Agent / 应用
        |
HTTPS: openspec.<domain>
        |
Cloudflare Tunnel 或 Nginx Ingress
        |
OpenSpec Service (Node.js/TypeScript, Kubernetes)
        |-- Casdoor/OIDC JWT 校验
        |-- OpenSpec domain adapter / CLI JSON adapter
        |-- 单写锁 + 版本校验
        |
持久化 PVC: /data/workspaces/{projectId}  （每项目独立工作区）
        |-- openspec/specs
        |-- openspec/changes
        |-- .git
        |
Gitea/Git remote（人工 review、备份、跨应用共享）
```

首选把每个项目的规划仓库作为独立 store，而不是混入某个业务代码仓库。单一共享 store 不得用于多用户服务；详见 MULTI_TENANCY.md。OpenSpec 已支持 store、root selection、JSON 输出和 schema；服务层应围绕这些能力设计。

## 3. 与 armbianbegin 现有基础设施的对应关系

- **Kubernetes**：部署 API、Service、PVC、ConfigMap、Secret/ExternalSecret。
- **ARM64 节点**：镜像必须构建并验证 `linux/arm64`；Node.js 20.19+。
- **私有 Registry**：使用 `192.168.137.101:5000` 对镜像进行发布，具体地址以集群统一配置为准。
- **Cloudflare Tunnel**：优先使用现有 tunnel 的 operator/route 模式，避免在节点开放新的公网端口。
- **Nginx Ingress**：若使用域名到 Ingress 的路径，建议使用独立主机名，不要依赖复杂 path rewrite。
- **Casdoor/OAuth**：服务校验 OIDC JWT，按 issuer、audience、scope/role 控制访问；首次身份绑定使用 JWT 邮箱解析 Gitea login，Casdoor/Gitea 用户名可以不同。
- **Vault/External Secrets**：存储 Git remote token、OIDC 配置、服务签名密钥等，不把密钥写入 Git。
- **Gitea**：作为 OpenSpec store 的 Git remote，并通过分支/PR 审核重要规划变更。

## 4. API 最小集合

第一版提供项目限定的只读、校验、变更、apply 和 archive 接口，禁止全局 `/v1/specs`、`/v1/changes`；规范接口面以 DEVELOPMENT_DESIGN.md §8 为准。面向 Codex、Claude Code 等 AI 工具时通过 `/mcp` 的 MCP 端点消费，工具映射见 DEVELOPMENT_DESIGN.md §8。`instructions` 暂不纳入 MVP，避免把领域规则误包装成 LLM 能力。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/healthz` | 存活探针，不访问 Git remote |
| GET | `/readyz` | 检查 PostgreSQL 和启动迁移是否可用 |
| POST | `/v1/projects` | 创建项目（含 Gitea store 初始化） |
| GET | `/v1/projects` | 列出调用方可见项目 |
| GET | `/v1/projects/{projectId}/specs` | 列出规格 |
| GET | `/v1/projects/{projectId}/specs/{id}` | 获取规格内容/结构化 JSON |
| GET | `/v1/projects/{projectId}/changes` | 列出 active changes（archive 不混入活动列表） |
| GET | `/v1/projects/{projectId}/changes/{id}` | 获取 change 文件列表、受限工件内容、任务进度和 revision |
| POST | `/v1/projects/{projectId}/changes/{id}` | 创建 change scaffold |
| PUT | `/v1/projects/{projectId}/changes/{id}` | 更新已有 change 工件 |
| POST | `/v1/projects/{projectId}/changes/{id}/validate` | 校验 change/spec |
| POST | `/v1/projects/{projectId}/changes/{id}/apply-specs` | 应用 delta specs，不直接执行代码 |
| POST | `/v1/projects/{projectId}/changes/{id}/archive` | 合并规格并归档 |

所有写接口必须支持 `Idempotency-Key`；项目 change 创建、更新、apply 和 archive 还要求客户端传递当前 Git commit SHA（REST `If-Match`，MCP `expectedRevision`）。版本不一致时返回 `409 Conflict`，避免静默覆盖。

## 5. 服务实现建议

### 5.1 技术栈

- Node.js 20/22 + ES modules；
- Node.js 原生 HTTP 层，避免引入不必要的运行时；
- 使用 OpenSpec 的解析、校验、artifact graph、archive 领域模块；
- 请求体和路径使用显式白名单校验；
- 通过 request id 和审计表关联结构化操作记录；
- 不允许把用户输入直接拼接到 shell 命令。

### 5.2 OpenSpec 集成方式

优先级：

1. 将可复用逻辑从 OpenSpec CLI 导出为稳定 service API；
2. 对尚未导出的能力，使用受控子进程调用 `openspec ... --json`；
3. 禁止服务执行任意用户提供的命令或路径。

服务进程只允许访问项目工作区根目录（`/data/workspaces/{projectId}`，路径由服务端拼接并做 canonical 校验），并对 change/spec id 做相对路径和字符集校验。写操作按项目在进程内加互斥锁；如果将来扩容多副本，改用 Redis/数据库分布式锁。

## 6. 仓库目录建议

```text
armbianbegin/openspec_service/
├── README.md / DEPLOY.md / DEVELOPMENT_DESIGN.md
├── src/                       # Node HTTP API、认证、Gitea、数据库和 workspace adapter
├── test/                      # 本地 workspace/OpenSpec 回归测试
├── Dockerfile / .dockerignore
├── package.json / pnpm-lock.yaml
├── k8s/                       # namespace、Deployment、Service、PVC、ConfigMap 和迁移文件
└── scripts/                    # build、deploy、bootstrap 和 smoke test
```

外部集成资源不放在 `openspec_service/`：

```text
vault/inventory/openspec-service-externalsecret.yaml
cloudflare-tunnel/operator/openspec-service-route.yaml
```

## 7. 部署步骤

1. 在 `openspec_service/CASDOOR_SETUP.md` 的指引下确认 Casdoor 通用 sso 应用 `panghu-suite`（audience 为其 client_id `ece3f52410b046fe0952`）、issuer 和 JWKS；确认 Gitea 组织 `openspec-service` 和受限服务账号已准备好。
2. 在 Vault 的 `secret/openspec/service` 中准备 Gitea 服务账号字段；运行 `scripts/deploy.sh`，脚本会使用现有 PostgreSQL 管理账号创建/更新 `openspec_service` 数据库用户和数据库，写入 `database_url`，应用 ExternalSecret 并确认能同步 `openspec-service-secrets`。
3. 构建 ARM64 镜像并推送私有 Registry。
4. 运行 `scripts/deploy.sh`，脚本会应用 `openspec_service/k8s/` 的 namespace、PVC、Deployment 和 ClusterIP Service，应用 `vault/inventory/openspec-service-externalsecret.yaml`，并应用 `cloudflare-tunnel/operator/openspec-service-route.yaml`。
5. 通过 `POST /v1/projects` 创建首个项目，服务会在 Gitea 创建私有仓库、初始化目录并授权创建者。
6. 从内网和公网分别执行 smoke test：健康检查、JWT、Gitea ACL、读取 revision、创建 change、校验、apply、archive、Git commit 和冲突。
7. 配置备份：PVC 快照或定时将 Git 工作区推送到 Gitea；保留应用日志和审计日志。

## 8. 安全要求

- 公网只开放 HTTPS；Cloudflare Access 或 OIDC 作为第一道边界，应用自身仍校验 JWT。
- 默认拒绝匿名访问；`/healthz` 仅返回最小状态。
- 用 Kubernetes ServiceAccount 最小权限，不授予 Pod 创建/执行权限。
- 容器以非 root、只读根文件系统运行，项目工作区根目录（`/data/workspaces`）单独可写。
- Git remote token 只从 Vault/ExternalSecret 注入，禁止出现在日志和 API 响应。
- 限制请求体大小、change id、spec id、并发写入和归档频率。
- 对每次写操作记录 user、request id、change id、旧 SHA、新 SHA、结果。

## 9. 可靠性与运维

- 第一版 Deployment `replicas: 1`、`Recreate`，避免同一 RWO PVC 被新旧 Pod 同时使用；通过 PVC 保证升级后工作区不丢失。
- 配置 readiness：store 可读、Git 工作区完整、schema 可解析；Git remote 不可达不应影响只读接口。
- 对 Git 冲突返回 409，并要求客户端重新拉取/合并；不要自动强推。
- 指标至少包括请求耗时、4xx/5xx、Git 操作耗时、校验失败、冲突数、归档数。
- 定期执行 `openspec validate --all --json`，并把结果纳入告警或 CI。

## 10. 分阶段交付

### MVP（代码已完成，待真实部署验收）

- 单副本 Node.js API；
- 每项目独立 Gitea 私有仓库、PVC workspace 和 ACL；
- OIDC/JWT、PostgreSQL 身份映射、审计和幂等；
- specs/changes 查询、validate、创建 change、apply-specs、archive；
- REST + MCP、Cloudflare Tunnel、ARM64 Dockerfile 和 K8s manifests。

### 后续阶段

- Gitea Pull Request、分支保护和用户级 OAuth token；
- 异步任务队列、Web 管理界面、多副本 + advisory lock；
- Webhook、CI 集成、Agent SDK（TypeScript/Python）；
- 跨仓库 references/context 自动聚合和动态 MCP OAuth。

## 11. 开始实施前需确认的参数

- 对外域名已选 `openspec.panghuer.top`，入口使用现有 Cloudflare Tunnel operator；
- Casdoor issuer、client/audience、角色模型需在真实环境确认；
- Gitea `openspec` 组织、仓库命名及备份策略需在真实环境确认；
- PVC 使用 `ceph-rbd`、容量 20Gi，快照策略需在真实环境确认；
- `apply/archive` 已纳入 MVP，并分别要求 Gitea Write/Admin 权限。

## 12. 结论

推荐把 OpenSpec 定位为“Git 化规划服务”：API 层提供统一、受控、机器可读的调用入口，OpenSpec store 保存可审阅的 Markdown 规格，Gitea 负责版本协作，Cloudflare Tunnel/Casdoor/Vault 负责公网入口、认证和秘密管理。这样能最大化复用 `armbianbegin` 已有基础设施，同时保留 OpenSpec 原本的 Git 审计和人工 review 优势。
