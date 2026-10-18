# Casdoor 4.11.0 → 4.20.0

2026-10-18：已更新仓库构建默认版本和部署镜像，等待用户手动部署；不代表线上已升级。
OpenSpec 变更：`upgrade-casdoor-enable-dcr`（armbianbegin 项目）。

## 升级目的

4.16.0 起提供组织级动态客户端注册 UI 开关，4.20.0 包含此功能。
官方发布：https://github.com/casdoor/casdoor/releases/tag/v4.20.0 。
开关实现：https://github.com/casdoor/casdoor/commit/bffa2978b91bd8c16f525866936a8ad12df715ed 。

## 手动部署

先备份实际 Casdoor 数据库、现有 Deployment，并保留 4.11.0 镜像。
Casdoor 启动可能迁移数据库；恢复时须核对 schema 兼容性，不能假定只回滚镜像即可。

从服务器上的仓库根目录执行：

```bash
git pull --ff-only
bash oauth/build.sh
bash oauth/deploy-casdoor.sh
```

`build.sh` 会拉取并推送 Casdoor 4.20.0、入口代理 nginx:1.28.0-alpine 和现有 oauth2-proxy 镜像；部署脚本只更新 Casdoor 入口 ConfigMap、Deployment 和 Service。
必须确认镜像推送成功后再部署。Docker tag 使用 `4.20.0`，不带 `v`。

## 部署后验收

- 确认运行镜像、健康检查、OIDC discovery 和 JWKS；回归已有 SSO 登录及 OpenSpec 项目读取。
- 用全局管理员打开 Organizations → 目标组织 → Advanced，确认出现 Enable dynamic client registration。
- 升级本身不会开启动态注册。先核对 discovery 的 registration_endpoint 实际选择的组织；上游未指定 organization 时默认 built-in，不要直接假定是 Normal-User。
- 在确认的组织中开启并保存；核对动态应用继承的登录方式、默认 Token 格式和必要字段（特别是 email），以及刷新令牌寿命。
- 使用无缓存的客户端，不传固定 client_id，验证动态注册、浏览器授权、MCP 调用和刷新；保留已有固定应用兼容性与项目权限隔离。
- 验证通过后更新用户接入说明和 OpenSpec 任务状态。当前尚未完成线上验收。

## Normal-User 默认动态注册入口（2026-10-19）

用户已确认升级完成、Normal-User 的动态注册开关开启，登录用户组织和邮箱正确。
此前公网探测表明：显式指定该组织通过开关校验，默认注册入口仍进入未开启的 built-in。

`casdoor-entry-configmap.yaml` 配置同 Pod 的 nginx 入口。Service 的对外端口仍是 8000，
targetPort 使用命名端口 http（新 Pod 为代理 8080，旧 Pod 为 Casdoor 8000），减少滚动切换时的端口不匹配。
代理把请求转发到同 Pod 的 Casdoor 8000：

- 仅 POST `/api/oauth/register` 且原查询参数没有 organization 时补上 `organization=Normal-User`。
- 保留显式组织参数、请求体及其他查询参数；不会自动开启其他组织的 DCR。
- 登录、令牌、发现、JWKS 和 `/api/oauth/register/{client_id}` 管理接口正常转发。
- 不记录包含 OAuth code/token 的请求 URL；保留 Host 和上游传入的 X-Forwarded-Proto。

现有内网 Ingress 无需更改；公网隧道必须转发到 `casdoor.oauth.svc.cluster.local:8000`，
不能绕过 Service 直连 Pod 的 8000，否则不会经过入口代理。发现文档中的注册地址无需改写。
ConfigMap 修改后要重启 Pod；`deploy-casdoor.sh` 已包含该步骤。首次须先完成 build.sh 推送新增 nginx 镜像。

部署后可发送不创建应用的探测：

```bash
curl -sS https://auth.panghuer.top/api/oauth/register \
  -H 'Content-Type: application/json' -d '{}'
```

预期为 HTTP 400、`invalid_redirect_uri`（缺少 redirect_uris），不再是动态注册关闭。
这只证明默认请求进入已开启的组织，不能替代新客户端注册、登录、项目权限及续期验收。
完成这些验证之前，保留固定 Client ID 接入说明，不宣称零配置已通过。

需要撤销入口适配时，先将 Service 恢复为 Casdoor 原端口：

```bash
kubectl -n oauth patch service casdoor --type=merge \
  -p '{"spec":{"ports":[{"name":"http","port":8000,"targetPort":8000,"protocol":"TCP"}]}}'
```

这不会回退 Casdoor 版本或数据库。随后同步回退仓库入口改动，避免下次部署再次启用。
