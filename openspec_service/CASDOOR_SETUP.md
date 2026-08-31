# Casdoor 配置

在 `https://auth.panghuer.top` 创建 `openspec-api` 应用，audience 使用 `openspec-api`，scope 使用 `openid profile email`。API 使用 Bearer JWT，不需要回调地址；未来 Web UI 再增加 `https://openspec.panghuer.top/*`。

Casdoor 用户名不需要与 Gitea 用户名相同，但 JWT 必须包含可信的 `email` claim。OpenSpec Service 首次绑定身份时按该邮箱在 Gitea 中精确查找用户，并保存实际 Gitea login；因此请确保 Casdoor 与 Gitea 的邮箱唯一且一致，并为服务账号 Token 开启 Gitea `read:user` 权限。

确认 Casdoor OIDC discovery 返回的 `issuer` 和 `jwks_uri` 后，写入服务运行参数（原型见 `k8s/core.yaml` 的 ConfigMap；生产以 ConfigMap/ExternalSecret 注入，见 DEPLOYMENT_PLAN.md）。client secret 不提交 Git，写入 Vault。
