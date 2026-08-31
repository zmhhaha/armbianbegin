# 当前开发状态

## 本地代码已完成

- 项目级 REST API 路由和 UUID 边界；
- Casdoor OIDC/JWT 校验；
- Gitea collaborator ACL 查询，API 不可达时失败关闭；
- PostgreSQL 项目映射、Casdoor sub 到 Gitea username 的不可变映射、审计和幂等表；
- 每项目 Git workspace、递归 specs 查询、活动 changes 查询、change 工件内容和 taskStatus、路径校验、项目级进程锁和 If-Match revision 检查；
- 用户提供的 proposal/design/tasks/spec 工件创建和更新、文件数量和大小限制、Git author；
- OpenSpec CLI `validate --json`、官方 delta merge、`apply-specs` 和 `archive` 接入；
- archive 后规格合并、日期归档目录移动、Git commit 和归档结果脱敏；
- MCP `POST /mcp` 的 initialize、tools/list、tools/call，以及带 Bearer JWT、归属校验、过期和数量上限的基础 session/SSE GET；
- REST/MCP 写操作的 PostgreSQL `Idempotency-Key`，以及项目创建失败回滚；
- Kubernetes namespace、workspace PVC、ClusterIP Service；Vault ExternalSecret 和 Cloudflare TunnelRoute 已分别归档到 `../vault/inventory/` 与 `../cloudflare-tunnel/operator/`；
- Gitea 私有项目创建、OpenSpec 目录初始化和 bootstrap 脚本；
- 只读部署 smoke test 脚本（健康、就绪和 JWT 项目列表）；
- 本地 Node 回归测试 7/7 通过，目标源文件语法检查通过。

## 需要真实环境或后续迭代

以下项目尚未执行，因此不得宣称已上线：

- 按 `CASDOOR_SETUP.md` 指引于真实 Casdoor 创建应用并确认 issuer、audience、JWKS 和 Gitea OAuth/OIDC 映射；
- 创建 PostgreSQL 数据库/用户，向 Vault 写入真实密钥并验证 ExternalSecret；
- ARM64 镜像构建、推送、Kubernetes apply、Pod readiness 和公网 HTTPS smoke test；
- 真实 Gitea/PostgreSQL/Casdoor 集成测试、跨用户撤权测试和恢复演练；
- Cloudflare Access 边界策略、监控、备份、PR 流程；
- MCP 跨副本 session/消息队列和 PostgreSQL advisory lock（当前部署固定单副本）；
- 多副本部署、异步任务队列、用户级 OAuth token 和 Gitea Pull Request。

当前默认 Git 写入提交到 PVC 工作区，不自动 push；服务重启后依靠 PVC 保留工作区和 Git 历史。真实部署前必须按 `DEPLOY.md` 配置 Gitea、Casdoor、Vault、PostgreSQL 和 Cloudflare。
