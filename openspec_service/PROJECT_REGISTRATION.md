# 新项目登记指南

本文档说明当前版本如何把一个应用项目登记到 OpenSpec Service。

当前版本的“项目”是一个独立的 Gitea 私有 OpenSpec store。应用源码可以继续放在 GitHub 或其他源码仓库中；OpenSpec Service 只管理该项目的 `specs`、`changes`、Git revision 和审计记录。

普通用户应通过项目申请表提交申请，管理员审批后由 Webhook 自动创建项目。完整流程请参阅
[`PROJECT_REQUEST_APPROVAL.md`](PROJECT_REQUEST_APPROVAL.md)。

部署表单入口后，用户直接访问 `https://openspec.panghuer.top/project-requests` 提交申请；服务会自动生成标准 Gitea Issue，用户不需要手动编写 Issue 模板。下面的脚本流程仅用于 bootstrap 管理员在没有表单或需要恢复映射文件时使用。

## 当前能力边界

登记项目会创建：

```text
Gitea: https://gitea.panghuer.top/openspec-service/<project-slug>
```

并初始化：

```text
openspec/
├── config.yaml
├── specs/
├── changes/
└── changes/archive/

.openspec-store/store.yaml
```

当前登记流程不会：

- 自动保存或同步 GitHub 源码地址；
- 读取 GitHub 私有仓库；
- 接收或保存 GitHub Personal Access Token；
- 通过 OpenSpec Service 执行任意项目脚本；
- 允许普通用户绕过管理员策略创建项目。

GitHub 源码和 OpenSpec store 是两个独立的仓库。需要执行项目构建或测试脚本时，当前仍需在源码仓库或现有 CI/CD 中手动执行。

## 前置条件

1. OpenSpec Service 已部署并且 `https://openspec.panghuer.top/healthz` 可访问。
2. 执行者拥有 Casdoor 有效 access token。
3. 执行者的 Casdoor `sub` 已配置在服务的 `BOOTSTRAP_ADMIN_SUBJECTS` 中。
4. Casdoor JWT 包含有效的 `email` claim。
5. 该邮箱在 Gitea 中对应唯一用户，且 OpenSpec 服务的 Gitea token 可以读取该用户邮箱。
6. 执行环境安装了 `bash`、`curl` 和 `python3`。

项目创建权限只授予 bootstrap 管理员。项目创建完成后，项目内的读写权限由 Gitea 仓库 ACL 决定。

## 登记新项目

以下示例将 GitHub 项目 `my-app` 登记到 OpenSpec Service。假设源码已经克隆到 `/root/my-app`。

### 1. 准备源码目录

如果源码还没有克隆到服务器：

```bash
cd /root
git clone https://github.com/example/my-app.git
```

源码目录不要求与 `armbianbegin` 同一个 Git 仓库。`.openspec-project.json` 应写入该源码仓库根目录，方便后续 Codex、Claude Code 或其他工具确定项目边界。

### 2. 获取 Casdoor JWT

推荐打开：

```text
https://openspec.panghuer.top/token
```

登录 Casdoor 后复制页面显示的 access token。也可以在命令行使用：

```bash
bash openspec_service/scripts/get-token.sh
export CASDOOR_JWT="$(cat /tmp/casdoor.jwt)"
```

JWT 只放在当前终端环境中，不要提交到 Git、写入项目映射文件或发到聊天中。

### 3. 执行登记脚本

```bash
cd /root/armbianbegin

export CASDOOR_JWT='<Casdoor access_token>'

bash openspec_service/scripts/register-project.sh \
  --slug my-app \
  --project-file /root/my-app/.openspec-project.json
```

`--slug` 必须符合以下格式：

```text
[A-Za-z0-9][A-Za-z0-9.-]{0,99}
```

例如 `my-app`、`backend-service` 和 `demo.project` 都合法；`my_app` 不合法。

脚本会先查询当前用户可见的项目。如果同名项目已经存在，脚本会复用它并重新写入映射文件；不存在时才会调用 `POST /v1/projects` 创建新项目。

### 4. 保存项目映射

成功后，脚本会在源码仓库根目录生成：

```text
/root/my-app/.openspec-project.json
```

内容类似：

```json
{
  "baseUrl": "https://openspec.panghuer.top",
  "projectId": "<project-uuid>",
  "owner": "openspec-service",
  "repository": "my-app"
}
```

该文件只包含非敏感的项目映射，不包含 JWT、密码或 Gitea token。建议将它提交到源码仓库；如果项目不希望提交，也可以保留在本地，但后续工具必须能够读取到相同的 `projectId`。

## 授权其他用户

项目创建者会被自动加入对应 Gitea 仓库的 Admin collaborator。要让其他用户访问项目，需要在 Gitea 中打开：

```text
https://gitea.panghuer.top/openspec-service/my-app/settings/collaboration
```

或者通过组织 Team 授权。

权限映射如下：

| Gitea 权限 | OpenSpec 能力 |
|---|---|
| Read | 查看 specs、changes 和 revision |
| Write | 创建、修改和校验 change，执行 `apply-specs` |
| Admin | 归档 change，以及项目管理操作 |

Casdoor 用户名和 Gitea 用户名可以不同，但两个系统的邮箱必须能够精确匹配。用户第一次调用 OpenSpec Service 时，服务会按 JWT 的 `email` 查找 Gitea login，并保存不可变的 Casdoor `sub -> Gitea username` 映射。

## 验证登记结果

### 查看 Gitea 仓库

登录 Gitea 后打开：

```text
https://gitea.panghuer.top/openspec-service/my-app
```

确认仓库为 Private，并且存在 `openspec/config.yaml`。

### 查看可见项目

```bash
export CASDOOR_JWT='<Casdoor access_token>'

curl -fsS \
  -H "Authorization: Bearer ${CASDOOR_JWT}" \
  https://openspec.panghuer.top/v1/projects | jq
```

### 读取项目 specs

```bash
PROJECT_ID='<project-uuid>'

curl -fsS \
  -H "Authorization: Bearer ${CASDOOR_JWT}" \
  "https://openspec.panghuer.top/v1/projects/${PROJECT_ID}/specs" | jq
```

返回结果中的 `revision` 是后续写入操作需要使用的 Git revision。

### 读取项目 changes

```bash
curl -fsS \
  -H "Authorization: Bearer ${CASDOOR_JWT}" \
  "https://openspec.panghuer.top/v1/projects/${PROJECT_ID}/changes" | jq
```

## 后续 OpenSpec 工作流

项目登记完成后，AI 工具或脚本必须使用 `.openspec-project.json` 中的 `projectId`，不能继续使用其他项目的 UUID。

典型流程是：

```text
list_projects
    ↓
list_specs / list_changes，获取当前 revision
    ↓
create_proposal 或 update_proposal
    ↓
validate_change
    ↓
apply_specs
    ↓
archive_change
```

MCP 地址：

```text
https://openspec.panghuer.top/mcp
```

MCP 配置和各工具的参数见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 失败处理

### `401 Unauthorized`

检查 JWT 是否过期、是否包含 `Bearer` 前缀，以及 `aud`、`iss`、`email` 和 `sub` 是否正确。重新获取 JWT 后再运行脚本。

### `403 Forbidden`

当前用户不是 `BOOTSTRAP_ADMIN_SUBJECTS` 中的项目创建管理员。需要管理员执行登记，或者由运维将该用户的 Casdoor `sub` 加入配置后滚动更新服务。

### `409 Conflict`

常见原因是项目 slug 已经存在，或者 Casdoor 邮箱对应多个 Gitea 用户。先检查 Gitea 组织仓库和用户邮箱，不要重复创建同名项目。

### `404 Not Found`

项目可能不存在，也可能当前 Gitea 用户没有该私有仓库权限。确认已登录正确的 Gitea 账号，并检查 collaborator/team 授权。

### 项目已创建但映射文件丢失

在能够访问该项目的用户环境中重新执行：

```bash
export CASDOOR_JWT='<Casdoor access_token>'

bash openspec_service/scripts/register-project.sh \
  --slug my-app \
  --project-file /root/my-app/.openspec-project.json
```

脚本会先查找已存在且当前用户可见的项目，不会重复创建 Gitea 仓库。

## 表单与管理员脚本的关系

项目申请和审批使用 [`PROJECT_REQUEST_APPROVAL.md`](PROJECT_REQUEST_APPROVAL.md) 中的表单流程。本文档中的 `register-project.sh` 仅用于 bootstrap 管理员直接创建项目，或在已有项目中恢复 `.openspec-project.json` 映射文件；普通用户不需要执行该脚本，也不需要手动编辑 Gitea Issue。

无论使用表单还是管理员脚本，都不要向 OpenSpec API 提交任意 shell 命令、GitHub token 或其他凭据。
