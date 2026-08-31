# Casdoor 配置

OpenSpec 复用通用 sso 应用 `panghu-suite`，**不需要为 OpenSpec 单独注册应用**。

- 应用：`panghu-suite`（owner `admin`，组织 `Normal-User`）
- audience（`OIDC_AUDIENCE`）：`ece3f52410b046fe0952`（即该应用的 client_id）
- issuer：`https://auth.panghuer.top`
- jwks_uri：`https://auth.panghuer.top/.well-known/jwks.json`
- 要求：JWT 必须携带可信的 `email` claim（Casdoor 默认 scope 含 email）。若某个用户在 Gitea 里无法绑定（409），检查其 Casdoor 邮箱与 Gitea 邮箱是否完全一致，以及邮箱是否对服务账号可见。

API 使用 Bearer JWT，不需要回调地址；未来 Web UI 再增加 `https://openspec.panghuer.top/*`。

将 `OIDC_ISSUER`、`OIDC_JWKS_URL`、`OIDC_AUDIENCE` 写入 `k8s/core.yaml` 的 ConfigMap（见 DEPLOYMENT_PLAN.md）。本服务只校验 JWT 公钥，暂不需要 Casdoor client secret 注入。

验证：登录 Casdoor 拿到 JWT 后，运行 `scripts/preflight.sh --jwt <JWT>`，它会检查 `aud`、`email`、`sub` 是否满足要求。
