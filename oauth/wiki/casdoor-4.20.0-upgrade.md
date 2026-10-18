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
kubectl apply -f oauth/k8s/casdoor-deployment.yaml
kubectl -n oauth rollout status deployment/casdoor --timeout=300s
kubectl -n oauth get pods -l app=casdoor -o wide
```

`build.sh` 会拉取并推送 Casdoor 4.20.0 和现有 oauth2-proxy 镜像；以上 apply 只更新 Casdoor 清单。
必须确认镜像推送成功后再部署。Docker tag 使用 `4.20.0`，不带 `v`。

## 部署后验收

- 确认运行镜像、健康检查、OIDC discovery 和 JWKS；回归已有 SSO 登录及 OpenSpec 项目读取。
- 用全局管理员打开 Organizations → 目标组织 → Advanced，确认出现 Enable dynamic client registration。
- 升级本身不会开启动态注册。先核对 discovery 的 registration_endpoint 实际选择的组织；上游未指定 organization 时默认 built-in，不要直接假定是 Normal-User。
- 在确认的组织中开启并保存；核对动态应用继承的登录方式、默认 Token 格式和必要字段（特别是 email），以及刷新令牌寿命。
- 使用无缓存的客户端，不传固定 client_id，验证动态注册、浏览器授权、MCP 调用和刷新；保留已有固定应用兼容性与项目权限隔离。
- 验证通过后更新用户接入说明和 OpenSpec 任务状态。当前尚未完成线上验收。
