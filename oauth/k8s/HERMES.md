# Hermes OAuth

当前上游 dashboard 对公开域名强制原生认证，不能仅依赖外层代理。
`hermes-dashboard-auth` ConfigMap 设置公开 URL 与内置 self_hosted OIDC 插件。
Hermes 容器从现有 hermes-oidc Secret 映射客户端 ID/密钥，不复制凭据到 ConfigMap。
Casdoor 同一应用须同时登记两个回调：
- `https://hermes.panghuer.top/oauth2/callback`（外层代理）
- `https://hermes.panghuer.top/auth/callback`（Hermes 自身）
保留外层精确邮箱白名单，可能出现第二次登录跳转，Casdoor 已有会话可用于 SSO。
不要改写 Host/Origin 或关闭检查来绕过原生认证。

原生配置在 `hermes-proxy-configmap.yaml`：发行者复用 `https://auth.panghuer.top`，
回调固定 `https://hermes.panghuer.top/oauth2/callback`，上游 `127.0.0.1:9119`。
代理容器定义在 `panghu_chat/hermes/k8s/core.yaml`，与 Hermes 同 Pod。
内网镜像复用 `arm-cluster-master:5000/oauth2-proxy:v7.8.0`。

唯一待填写项是 `hermes-owner.data.emails` 的本人已验证邮箱。空值默认拒绝访问，不能改为通配邮箱域。
客户端 ID、客户端密钥、Cookie 密钥通过 Vault 同步的 hermes-oidc Secret 注入。
Casdoor 需注册独立应用回调并开启 MFA，确认 email_verified 声明有效。

通过 Hermes deploy.sh 统一 apply；没有额外参数文件或模板渲染。
OAuth/白名单/凭据更新后重启 `deployment/hermes-web -n hermes`。
服务器需验证登录、错误用户拒绝、WebSocket 及退出撤销行为；本次未测试。
