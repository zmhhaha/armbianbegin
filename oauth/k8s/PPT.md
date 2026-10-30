# PPT 工作台：登录配置与部署

PPT 部署在 `ppt-service`，公开地址为 **https://ppt-service.panghuer.top**。
2026-10-30 起，所有者授权向其他用户开放反馈使用：用户通过 Casdoor 登录即可访问，
无需管理员把邮箱加入 PPT 名单。网站、API、资料、预览和下载仍需认证，项目按已验证的
`iss/sub` 分别归属。原有 `ppt-owner` 不再是准入配置，不应重新接入或挂载。

## 配置来源

| 内容 | 唯一配置来源 |
| --- | --- |
| Casdoor issuer、client ID、回调、代理/API 认证参数 | [ppt-proxy-configmap.yaml](ppt-proxy-configmap.yaml) |
| 生成填写后的公开配置 | [configure-ppt.py](configure-ppt.py) |
| 到集群内 Casdoor HTTPS 的网络许可 | [ppt-oidc-egress.yaml](ppt-oidc-egress.yaml) |
| 登录与数据库凭据的 Vault/ESO 映射 | [Vault 配置](../../vault/inventory/PPT-SERVICE.md) |
| VPS Nginx/frpc 入口与公网 DNS | [VPS 配置](../../vps/PPT.md) |
| 可选 Cloudflare Tunnel 入口 | [Cloudflare 配置](../../cloudflare-tunnel/PPT.md) |
| 网站构建、数据库、PVC 和回滚 | [业务部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md) |
| Agent 执行后端 | [Agent 部署说明](../../panghu_agent/ppt_service/deploy/agent/README.md) |

`ppt-auth` 和 `ppt-oidc` 位于 `ppt-service`。`ppt-auth` 通过 `envFrom` 给网站，
`ppt-oidc` 挂载给同 Pod 的 oauth2-proxy。代理设置 `email_domains = ["*"]`，
接受任意邮箱域名的已认证用户；不设置 `authenticated_emails_file`，API 不读取邀请文件。
密钥仍只由 Vault/ESO 提供。业务 base 不保存第二份 OAuth 配置。

## Casdoor 应用

继续使用独立 PPT Web 应用，支持 authorization-code 流程和服务端 code 交换：

| 配置 | 值 |
| --- | --- |
| 名称 | `ppt-service` |
| 精确 Redirect URI | `https://ppt-service.panghuer.top/oauth2/callback` |
| Scopes | `openid email profile` |
| Issuer | `https://auth.panghuer.top` |
| ID token 算法 | `RS256` |
| API 必要 claims | `iss`、`aud`、`exp`、`iat`、稳定 `sub` 和有效 `email` |

client ID 同时用于代理登录和 API audience 校验；不使用通配符回调。邮箱验证由 Casdoor
注册/登录策略负责，API 不额外要求 `email_verified`。移除 PPT 名单不改变 Casdoor 的
账号注册或应用登录策略，也不允许浏览器伪造身份头。

生成公开配置：

```sh
python oauth/k8s/configure-ppt.py \
  --client-id '后台取得的PPT-client-ID' \
  --output /secure/ppt-auth.rendered.yaml
```

工具只生成匹配的代理 client ID 与 API audience，不写密钥、不访问集群，输出必须为新文件。
不需要邮箱名单、subject 名单或 `PPT_OWNER_CONFIG`。渲染与部署校验会拒绝重新加入旧邀请设置。

## 凭据与入口

保留独立 `secret/ppt-service/oidc` 的 client/cookie secret，以及 runtime/migrator 数据库凭据。
已有服务升级不重建账号、不轮换 cookie secret、不迁移用户数据；数据库沿用 `data` 中的共享
PostgreSQL。首次配置按 [Vault 说明](../../vault/inventory/PPT-SERVICE.md) 准备。

现有入口是 VPS/nginx/frp，Cloudflare `A ppt-service → 62.234.50.20`、DNS only。
VPS 必须继续通过 OAuth 代理端口 4180 转发；8000 仅供同 Pod 内回环 API 使用。
PPT 全站认证内容和 API 均 `no-store`，不可使用共享缓存。选择 Tunnel 时，按上述配置来源
准备实际 Connector 的网络策略并切换 DNS，避免同名入口冲突。

Casdoor 仍访问 `https://auth.panghuer.top`，沿用集群内 TLS ingress 与精确网络许可。
本次开放账号不需要修改 Casdoor 数据库或共享应用配置。

## 服务器发布

应用源码先 Git 提交和推送，再由 Linux ARM64 服务器获取准确提交。构建、推送使用 `latest`，
发布绑定 `latest@sha256`，在镜像标签和部署注解中记录 Git revision。

```sh
cd <仓库目录>/panghu_agent/ppt_service
export PPT_CLIENT_ID='<Casdoor 实际 PPT client ID>'
bash build.sh
```

首次部署或常规部署入口及前置条件见 [服务器部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md)。
已接入 Agent/schema4 的线上服务做认证专项升级时，应基于实时配置只更新网站镜像、公开 OAuth
配置及不再使用的 owner 挂载，保留执行后端、Controller、数据库/PVC 和凭据引用。
不要使用旧配置重放覆盖已完成的 Agent 切换。

已有 `ppt-owner` ConfigMap 可暂留作为历史配置；新镜像不会读取，新清单也不挂载。
修改 OAuth ConfigMap 后需滚动网站 Pod，使代理重读文件；API 的旧邀请环境变量应一并移除。

## 部署后验证

- 未登录访问 `/` 进入登录，`/api/v1/me` 返回 401，匿名预览/下载不能获得内容。
- 使用从未加入旧名单的账号登录，应可访问身份 API、创建自己的项目。
- 无签名、错误 issuer/audience、过期令牌或无效邮箱仍拒绝。不同 `iss/sub` 不能访问彼此项目、事件或下载。
- 写操作要求精确 Origin `https://ppt-service.panghuer.top` 和匹配 CSRF cookie/header。
- `__Host-ppt` cookie 保持 Secure、HttpOnly、Path=/、SameSite=Lax，无 Domain。
- `/oauth2/sign_out` 清除本地代理会话；Casdoor 全局 SSO 会话和旧无状态 cookie 的撤销不由本次改动承诺。
- 验证代理不再设置邮箱文件、网站不读取邀请配置，且旧名单的空值或读取故障不影响正常认证。

真实代理的合成协议验证工具见 [tests/oidc](../../panghu_agent/ppt_service/tests/oidc/README.md)。
它使用独立 issuer、身份、凭据和 SQLite，不修改生产用户项目，不调用模型。

开放反馈使用不代表完整制稿质量已验收。当前 Agent 后端已启用；之前的完整流程受上游模型
`response.failed` 阻塞，制稿/修改/下载及 PowerPoint 完整验收仍须按实际结果记录。
