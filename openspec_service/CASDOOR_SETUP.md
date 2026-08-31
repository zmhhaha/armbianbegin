# Casdoor 配置

在 `https://auth.panghuer.top` 创建 `openspec-api` 应用，audience 使用 `openspec-api`，scope 使用 `openid profile email`。API 使用 Bearer JWT，不需要回调地址；未来 Web UI 再增加 `https://openspec.panghuer.top/*`。

确认 Casdoor OIDC discovery 返回的 `issuer` 和 `jwks_uri` 后，写入服务运行参数（原型见 `k8s/core.yaml` 的 ConfigMap；生产以 ConfigMap/ExternalSecret 注入，见 DEPLOYMENT_PLAN.md）。client secret 不提交 Git，写入 Vault。
