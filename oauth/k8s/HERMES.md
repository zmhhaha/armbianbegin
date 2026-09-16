# Hermes OAuth

配置源为 `hermes-proxy-container.yaml`，由 `panghu_chat/hermes/scripts/render.py` 读取并注入 Hermes Pod。
不是独立 Kubernetes 对象，不能直接 `kubectl apply`。代理必须和 dashboard 同 Pod，才能访问回环地址。
不同于其他服务的共享代理，Hermes 不复用父域 Cookie 或允许所有 Casdoor 用户登录。

非敏感配置来自 `panghu_chat/hermes/deployment.local.yaml`：
- `hostname`：默认 `hermes.panghuer.top`。
- `oidc_issuer`：Casdoor 实际 OIDC issuer，保留 TLS 校验。
- `owner_email`：仅一个已验证邮箱，渲染为 `hermes-owner` ConfigMap。
- `oauth_image`：ARM64 支持的固定镜像摘要。

在 Casdoor 创建独立应用，注册 `https://hermes.panghuer.top/oauth2/callback`，开启 MFA；确认签发的 email 和 email_verified 声明有效。
不要加入 `--email-domain=*`、跳过邮箱验证或匿名跳过路由。会话 Cookie 为独立的 `__Host-hermes`，不设置父域。
凭据来自 `vault/inventory/hermes-externalsecret.yaml` 创建的 `hermes-oidc` Secret。

通过 `panghu_chat/hermes/deploy.sh` 一并部署；没有独立代理 Deployment，避免两个配置来源发生漂移。
envFrom 凭据轮换或邮箱白名单修改后，应执行 `kubectl -n hermes rollout restart deployment/hermes-web`。
服务端验收登录、错误用户拒绝、WebSocket、退出/撤销；本次未执行测试。
