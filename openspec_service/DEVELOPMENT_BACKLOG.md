# OpenSpec 服务待开发内容

> 注：多租户与项目级隔离从第一版即生效，见 DEVELOPMENT_DESIGN.md 与 MULTI_TENANCY.md。本清单中 `/data/store` 单 store 相关项仅作为原型/模板参考，生产按项目工作区实现。

## 检查基线

- 检查对象：`192.168.137.101`（`arm-cluster-master`）
- 检查日期：2026-08-30
- 系统：Armbian 26.5.1 / Debian 12 / ARM64
- Kubernetes：v1.31.14
- 集群节点：5 个，当前全部 `Ready`
- 服务器资源：8 vCPU、15 GiB 内存、根盘 228 GiB（已用约 24%）

## 已部署基础设施（可复用）

- Kubernetes、Docker、kubelet、CoreDNS、Flannel
- Nginx Ingress Controller
- Cloudflare Tunnel Operator 和主 Tunnel
- Gitea、Drone CI
- Casdoor、OAuth2 Proxy
- Vault、External Secrets
- Ceph、CephFS/RBD CSI 和 StorageClass
- PostgreSQL、MySQL、Redis、Elasticsearch、SQLite
- Ceph 自带 Prometheus、Grafana、Alertmanager、Node Exporter
- ARM64 私有 Docker Registry（端口 `5000`）

## P0：OpenSpec 服务上线前必须完成

### 1. OpenSpec API 服务

- [x] 创建 Node.js HTTP API 项目
- [x] 固定 Node.js 20.19+ 运行时和 ARM64 镜像构建清单
- [x] 实现 `/healthz` 和 `/readyz`
- [x] 实现递归 specs 查询接口
- [x] 实现 changes 查询接口和 change 详情（活动 change 排除 archive；详情返回受限工件内容与 taskStatus）
- [x] 实现 change 创建和更新接口
- [x] 实现 change/spec 校验接口
- [ ] 实现 `instructions` 接口，返回 Agent 可消费的下一步操作（仅规则化下一步提示，不调用 LLM；无法清晰定义则移出 MVP）
- [x] 实现 MCP server 适配层（streamable HTTP + Bearer JWT），映射 specs/changes/validate 等工具，见 DEVELOPMENT_DESIGN.md §8（当前为单副本 session；跨副本存储留 P2）
- [x] 实现 `apply-specs` 和 `archive`（REST/MCP 均支持，受 Gitea Write/Admin ACL 控制）
- [x] change 创建/更新、apply、archive 支持 `Idempotency-Key` 和 `If-Match`，并将幂等记录保存到 PostgreSQL
- [x] 所有写接口支持 `expectedRevision`，Git SHA 不一致时返回 `409 Conflict`
- [x] 禁止任意 shell 执行和任意路径读写（仅调用固定 OpenSpec CLI，工件路径白名单）

### 2. OpenSpec store 模板与项目工作区

- [ ] 在 Gitea 创建独立仓库模板，例如 `openspec-store`（当前项目创建流程会直接初始化新仓库）
- [x] 初始化 `openspec/specs/`、`openspec/changes/` 和 `.openspec-store/store.yaml`
- [x] 创建 OpenSpec 服务专用 PVC，当前使用 `ceph-rbd` 单副本模式
- [x] 生产按项目划分工作区 `/data/workspaces/{projectId}`（见 MULTI_TENANCY.md）；`/data/store` 仅用于单项目原型/模板
- [x] 配置 Git remote、默认分支和真实用户提交者身份
- [x] 明确服务自动 commit；默认不自动 push
- [x] 配置 Git 冲突处理：脏工作区或 SHA 过期返回 409，不强制覆盖

### 3. 认证和授权

- [ ] 在 Casdoor 创建 OpenSpec API 应用
- [ ] 确认 OIDC issuer、client ID、audience 和回调/受众配置
- [x] API 校验 JWT 的签名、issuer、audience、过期时间
- [x] 定义 Gitea 仓库 ACL（Read/Write/Admin）到 OpenSpec 能力（viewer/editor/owner）的角色映射
- [x] 配置服务专用 ExternalSecret 清单
- [x] API 默认拒绝匿名请求，只有健康检查允许最小匿名响应
- [x] 提供首个租户/项目的 bootstrap 流程（Gitea 创建仓库并授权服务账号、登记 projectId 映射）

### 4. Kubernetes 资源

- [x] 创建专用 namespace `openspec`
- [x] 创建不授予额外 RBAC 权限的 ServiceAccount
- [x] 创建 ConfigMap（运行参数、workspace 路径和 OIDC 配置）
- [x] 创建 Deployment，第一版 `replicas: 1`
- [x] 创建 ClusterIP Service（端口 `8080`）
- [x] 创建 PVC 和备份标签
- [x] 配置非 root、只读根文件系统、资源 requests/limits
- [x] 配置 liveness/readiness/startup probes
- [ ] 配置 PodDisruptionBudget（扩容到多副本后启用）

### 5. 对外访问

- [x] 确认对外域名 `openspec.panghuer.top`
- [x] 增加 Cloudflare TunnelRoute，后端指向 `openspec-service.openspec.svc.cluster.local:8080`
- [x] 不使用复杂 path rewrite，采用独立 hostname
- [ ] 配置 Cloudflare Access 或等价的边界策略
- [ ] 进行公网 HTTPS、DNS、JWT 和 CORS 验证

## P1：建议在 MVP 后补齐

### 6. 监控和日志

- [ ] 安装 Metrics Server，验证 `kubectl top nodes/pods -A`
- [ ] 为 OpenSpec 服务暴露 Prometheus metrics
- [ ] 将 API、Git 操作、校验失败、冲突和归档计数接入监控，并覆盖 MCP 工具调用
- [ ] 部署集中式日志采集（Loki + Fluent Bit/Vector，或现有日志方案）
- [ ] 记录审计字段：用户、request id、change id、旧 SHA、新 SHA、结果
- [ ] 为 5xx、连续 readiness 失败、磁盘/PVC 使用率建立告警

### 7. 备份和恢复

- [ ] 为 OpenSpec store 配置 Git 远端备份策略
- [ ] 为 store PVC 配置 Ceph 快照或定期备份
- [ ] 配置 Kubernetes 资源备份（Velero 或现有备份系统）
- [ ] 验证 Vault 数据恢复流程
- [ ] 验证 Gitea 仓库、数据库和附件恢复流程
- [ ] 编写 OpenSpec 服务灾难恢复 Runbook

### 8. HTTPS 证书能力

- [ ] 如果继续完全使用 Cloudflare Tunnel，可暂不部署 cert-manager
- [ ] 如果需要 Nginx Ingress 直接终止 HTTPS，部署 cert-manager
- [ ] 配置 DNS-01 或 HTTP-01 签发策略，并验证续期

## P2：后续演进

- [ ] 多副本部署和 Redis/数据库分布式锁
- [ ] 多租户隔离增强：每项目 PVC / 命名空间 / Job 级强隔离（多租户与项目级授权基线已纳入 v1）
- [ ] 异步 apply/archive 任务队列
- [ ] Web 管理界面和变更审阅
- [ ] TypeScript/Python Agent SDK
- [ ] Webhook、CI 和 Gitea PR 集成
- [ ] 跨仓库 references/context 自动聚合
- [ ] MCP 服务的 OAuth 动态授权（私有服务初期用 Bearer token，开放第三方应用时启用 OAuth）

## 上线前阻塞问题

以下问题在部署 OpenSpec 服务前应处理或记录豁免：

- [ ] Ceph 当前为 `HEALTH_WARN`：1 台主机 cephadm 检查失败、3 个 stray daemons、部分 monitor 节点空间偏低
- [ ] 私有 Registry 端口 `5000` 使用 HTTPS；必须为构建节点和 Kubernetes 节点配置正确 CA/Registry 信任，不能按 HTTP 使用
- [ ] OpenSpec Kubernetes 清单尚未在集群 apply；需部署并验证 TunnelRoute、Deployment、Service、PVC 和 ExternalSecret
- [ ] 当前尚未在真实环境创建 OpenSpec API 对应 Casdoor 应用、JWT scope 和 Vault 密钥
- [ ] 当前没有明确 OpenSpec store 的 Gitea 仓库地址、分支策略和备份策略

## 推荐实施顺序

1. 处理或接受 Ceph/Registry 风险，确认镜像能在 ARM64 集群拉取。
2. 在 Casdoor、Gitea、PostgreSQL 和 Vault 完成真实配置。
3. 构建并推送 ARM64 镜像，部署 namespace、ExternalSecret、Deployment、Service、PVC 和 TunnelRoute。
4. 完成内网 smoke test：JWT、Gitea ACL、创建 change、validate、apply、archive 和 revision 冲突。
5. 完成公网 HTTPS、Cloudflare 路由和 MCP 客户端 smoke test。
6. 补齐 Metrics Server、集中日志、备份恢复和撤权演练。
7. 评估多副本 advisory lock、异步任务和 PR 流程。

## 验收清单

- [ ] 未认证请求被拒绝
- [ ] 有效 JWT 可以读取 specs/changes
- [ ] 创建 change 后能在 store PVC 中看到完整目录
- [ ] 校验失败返回结构化错误
- [ ] 并发写入或 SHA 过期返回 `409 Conflict`
- [ ] archive 后 delta spec 正确合并并保留 Git 记录
- [ ] Pod 重启后数据不丢失
- [ ] git remote 不可达时，已检出工作区的只读查询仍可用并产生告警；Gitea API 不可达时授权检查 fail-closed 或走短 TTL 缓存，不静默放行
- [ ] Cloudflare 公网访问使用 HTTPS 且域名路由正确
- [ ] `kubectl top`、日志查询、备份恢复验证通过
