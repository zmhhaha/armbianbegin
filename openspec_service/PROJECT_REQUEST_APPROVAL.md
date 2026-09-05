# Gitea 工单自动创建项目

OpenSpec Service 支持通过 Gitea Issue 提交项目创建申请。该流程使用 Gitea Webhook，在管理员添加审批标签时一次性触发，不轮询 Issue。

## 流程

```text
用户打开 OpenSpec 项目申请表并登录 Casdoor
        ↓
服务端校验表单并自动创建标准 Gitea Issue
        ↓
管理员检查申请并添加 status:approved
        ↓  Gitea Issues Webhook
OpenSpec Service 验签并确认审批人是仓库 Admin/Owner
        ↓
创建 Gitea 私有 OpenSpec store
        ↓
初始化 openspec/，建立 projectId 映射，授权申请人
        ↓
评论 projectId 和仓库地址，关闭 Issue
```

服务不会定时扫描 Gitea，也不会因为普通用户修改 Issue 或添加标签而创建项目。

## 用户提交表单

用户访问：

```text
https://openspec.panghuer.top/project-requests
```

登录 Casdoor 后填写项目显示名称、项目 slug、GitHub 公共仓库地址、默认 ref、脚本 profile 和项目说明。服务端会再次校验所有字段，用户不需要编辑 JSON，也不需要手动创建 Gitea Issue。

提交成功后，页面返回 Gitea Issue 地址和 `pending` 状态。该 Issue 是后续审批和审计记录，用户可以打开它查看进度，但不应手动修改结构化字段或添加审批标签。

## 申请仓库

申请仓库固定为：

```text
openspec-service/project-requests
```

该仓库只用于项目申请，不用于保存项目 specs、源码或凭据。仓库中的 Issue 模板位于：

```text
gitea/project-requests/ISSUE_TEMPLATE/project-request.md
```

表单提交后，服务会在 Issue 正文中写入一个受限 JSON 块：

```text
<!-- openspec-project-request:v1
{
  "displayName": "My application",
  "slug": "my-app",
  "sourceUrl": "https://github.com/example/my-app",
  "ref": "main",
  "scriptProfileId": "openspec-bootstrap-v1",
  "initialPermission": "admin"
}
-->
```

服务只接受 HTTPS `github.com` 公共仓库地址、合法 slug、合法 ref 和服务端注册的脚本 profile。Issue 中禁止填写 GitHub Token、Gitea Token、密码或任意 shell 命令。

## 首次配置

### 1. 写入 Webhook secret

生成一个随机 secret，并写入 Vault。不要把它提交到仓库：

```bash
WEBHOOK_SECRET="$(openssl rand -hex 32)"

kubectl -n vault exec vault-0 -- vault kv patch secret/openspec/service \
  gitea_webhook_secret="${WEBHOOK_SECRET}"
```

应用 ExternalSecret：

```bash
kubectl apply -f vault/inventory/openspec-service-externalsecret.yaml
```

等待：

```bash
kubectl -n openspec get externalsecret openspec-service-secrets
```

应该显示 `SecretSynced=True`。服务读取的变量名是 `GITEA_WEBHOOK_SECRET`。

### 2. 部署包含 Webhook 代码的镜像

```bash
bash openspec_service/scripts/build.sh
bash openspec_service/scripts/deploy.sh --wait
```

Webhook 使用的内部地址为：

```text
http://openspec-service.openspec.svc.cluster.local:8080/webhooks/gitea
```

这样 Gitea 在集群内可以直接访问服务，不需要让 Webhook 经过公网 Cloudflare 路由。

### 3. 创建申请仓库和 Webhook

在可以访问 Gitea API 的环境执行：

```bash
export GITEA_TOKEN='<受限 Gitea token>'
export GITEA_WEBHOOK_SECRET='<与 Vault 中完全相同的 secret>'

bash openspec_service/scripts/bootstrap-project-requests.sh
```

脚本会幂等地创建：

- 私有仓库 `openspec-service/project-requests`；
- `status:pending`、`status:approved` 和 `status:failed` 标签；
- Issue 模板；
- 只监听 `issues` 事件的 Gitea Webhook。

如果 Gitea API 从集群内部访问，脚本可以覆盖地址：

```bash
GITEA_URL='http://gitea.gitops.svc.cluster.local:3000' \
bash openspec_service/scripts/bootstrap-project-requests.sh
```

管理员需要确保申请用户可以访问 `project-requests`，但不能修改仓库 Webhook 或仓库设置。表单 API 使用用户自己的 Casdoor JWT 创建 Issue；只有该仓库的 Admin/Owner 添加 `status:approved` 才会触发创建。

## 管理员审批

1. 用户在 `https://openspec.panghuer.top/project-requests` 提交表单。
2. 管理员检查 GitHub URL、slug、ref、脚本 profile 和项目成员。
3. 管理员添加 `status:approved` 标签。
4. 服务验证 Webhook HMAC 和审批人的 Gitea 权限。
5. 成功后服务创建：

   ```text
   https://gitea.panghuer.top/openspec-service/<slug>
   ```

6. 服务把 `projectId` 和 store 地址评论到 Issue，并关闭 Issue。

服务使用 `request repository + issue number` 作为幂等键。Gitea 重复投递同一个 Webhook 时不会创建第二个仓库。

## 失败和重试

如果创建失败，服务会：

- 在数据库中记录 `failed` 状态和脱敏错误；
- 给 Issue 添加 `status:failed`；
- 保持 Issue 打开；
- 不删除已经成功持久化的项目映射。

修正申请内容或依赖问题后，管理员先移除 `status:approved`，再重新添加该标签触发重试。服务不会通过后台轮询自动重试。

## 当前边界

该 Webhook 流程当前自动完成的是 OpenSpec store 创建和项目授权。它还不会：

- clone 或同步 GitHub 源码；
- 读取 GitHub 私有仓库；
- 执行 Issue 中指定的任意脚本；
- 启动项目构建或测试 Job。

固定脚本必须继续使用服务端注册的 profile，后续再接入隔离的 Kubernetes Job runner。
