# armbianbegin OpenSpec 项目

`armbianbegin` 的应用源码可以继续维护在 GitHub；OpenSpec Service 使用一个独立的 Gitea 私有仓库存放该项目的 `openspec/` 规格和变更。不要把现有的 `project-a-specs` 当作 `armbianbegin` 项目。

## 一次性登记

在能够访问 OpenSpec 服务并已准备 Casdoor JWT 的环境执行：

```bash
export CASDOOR_JWT='<Casdoor access_token>'
bash openspec_service/scripts/register-project.sh
```

脚本会：

1. 查找当前用户已经可见的 `armbianbegin` 项目；
2. 如果不存在，调用 `POST /v1/projects` 创建 `openspec-service/armbianbegin` 私有仓库；
3. 将非敏感的项目映射写入仓库根目录 `.openspec-project.json`。

`POST /v1/projects` 需要 bootstrap 管理员 JWT。第一次创建完成后，项目访问权仍由 Gitea 仓库 ACL 决定。脚本不会写入或保存 JWT、密码或 Gitea Token。

## 接入后使用

读取 `.openspec-project.json` 得到 `projectId`，再通过 MCP：

```text
https://openspec.panghuer.top/mcp
```

调用 `list_specs`、`list_changes` 等工具时始终传该 `projectId`。新任务应先读取 `list_projects` 或 `.openspec-project.json`，再开始 proposal/spec/change 操作。

## 项目边界

```text
GitHub: armbianbegin 应用源码
Gitea:  openspec-service/armbianbegin OpenSpec store
API:    projectId -> Gitea 私有仓库 -> /data/workspaces/{projectId}
```

OpenSpec Service 不会直接修改 GitHub 源码，也不会对任意本地 `docs/` 文件自动执行 OpenSpec 流程。源码变更仍需通过原有 GitHub 工作流；规格变更则通过该项目的 REST/MCP API 创建、校验和归档。
