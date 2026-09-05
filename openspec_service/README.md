# OpenSpec Service

MVP HTTP API and Kubernetes deployment assets for the OpenSpec store on the Armbian cluster.

Design docs: `DEVELOPMENT_DESIGN.md`（总体设计）、`MULTI_TENANCY.md`（多租户隔离）、`DEPLOYMENT_PLAN.md`（部署方案）。
See `DEPLOY.md` for deployment. Vault 和 Cloudflare 清单分别在 `../vault/inventory/` 和 `../cloudflare-tunnel/operator/`。Casdoor 配置见 `CASDOOR_SETUP.md`。构建和部署脚本见 `scripts/build.sh` 和 `scripts/deploy.sh`。

`ARMBIANBEGIN_PROJECT.md` 和 `scripts/register-project.sh` 用于将本仓库关联到独立的 OpenSpec projectId；项目规格库与应用源码仓库分离。

新项目登记请参阅 [`PROJECT_REGISTRATION.md`](PROJECT_REGISTRATION.md)。

Gitea 工单审批自动创建项目请参阅 [`PROJECT_REQUEST_APPROVAL.md`](PROJECT_REQUEST_APPROVAL.md)。

项目申请入口：`https://openspec.panghuer.top/project-requests`。

Agent 接入见 `MCP_INTEGRATION.md`；跑通过程遇到的问题与解决见 `TROUBLESHOOTING.md`。
