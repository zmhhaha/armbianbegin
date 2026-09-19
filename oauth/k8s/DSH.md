# DSH OAuth

配置源为 `dsh-proxy-configmap.yaml`，由 `panghu_chat/dsh/k8s/web.yaml` 以 ConfigMap 卷挂载进 `dsh-web` Pod 的 oauth2-proxy 容器。与 Hermes 一样使用 INI（`--config=/oauth/oauth2-proxy.cfg`），不是命令行参数。

代理与 DSH 网页同 Pod：oauth2-proxy 上游为认证适配层 `127.0.0.1:3081`，适配层转发到 DSH 的 `127.0.0.1:3080`。只有 OAuth 的 4180 端口通过 Service 暴露。

## 两层认证

外层 oauth2-proxy **不是唯一入口认证**。DSH 保留自己的 launch token 兑换与 authority-bound cookie；首次登录流程是：

1. 在 Casdoor 完成 OIDC（本 ConfigMap 负责这一层，精确邮箱白名单）。
2. 适配层用浏览器 Cookie 请求本地 `/oauth2/auth`，检查返回的邮箱仍在 `/owner/emails` 白名单内；不信任浏览器传入的身份头。
3. 访问 `/` 时，若 DSH 返回原生认证 401，适配层在回环连接中兑换启动 Token，将 DSH 原生 Cookie 加上 `Secure` 后返回，并跳转到干净的 `/`。用户无需读取 Kubernetes 日志或拼接 Token URL。

启动包装器只在内存中保留当前 DSH 进程打印的启动 Token，并抑制含 Token 的日志。它不读取 Kubernetes API、不把 Token 写入 ConfigMap/Vault/文件，也不自行签发 DSH Cookie。DSH 子进程退出时包装器退出，由 Kubernetes 重建；启动探针检查适配层和原生服务都可用。原生 Cookie 过期后刷新根页面即可重新兑换，API 和 WebSocket 不会自动重放业务请求。

因此 Casdoor **只需登记一个回调** `https://dsh.panghuer.top/oauth2/callback`——与 Hermes 不同，DSH 的原生认证不是 OIDC，不要为它编造第二个回调或 OIDC 客户端配置。

- 在 Casdoor 建**独立应用**（不要复用 panghu-suite 或其他服务的应用），开启 MFA，确认 `email` 与 `email_verified` 声明可信。
- 不要加入 `--email-domain=*`、不要跳过邮箱验证、不要使用匿名跳过路由。
- launch token 不得进入任何 manifest、PR、路由配置或常规访问日志；确认 Cloudflare 与代理侧都不记录带 query 的 URL。详见 `panghu_chat/dsh/docs/boundaries.md`。

## 白名单与 Cookie

- `dsh-owner.data.emails` 是**唯一待填写项**，填本人已验证邮箱。空值默认拒绝访问，不能改成通配邮箱域。
- 会话 Cookie 为独立的 `__Host-dsh`，不设置父域。`__Host-` 前缀强制要求 Secure + `Path=/` + 无 Domain 三条同时成立，本配置三条都满足；改动时不要只改其中一条。
- 客户端 ID、客户端密钥、Cookie 密钥都通过 Vault 同步的 `dsh-oidc` Secret 注入，**不复制到本 ConfigMap**。

## 原生 Cookie 与安全边界

适配层给原生 Cookie 补充 `Secure`，保留 HttpOnly、SameSite 和公网 Host 绑定。已核对安装版本 `0.1.5-rc.2` 的根 URL 兑换代码；没有关闭原生认证、Host/Origin 校验。错误 Host/Origin、跨站请求及客户端 Token 查询参数均被拒绝；OAuth 检查不可用时拒绝访问。`set_xauthrequest = true` 用于让内部 `/oauth2/auth` 返回邮箱；`request_logging = false` 避免旧 Token URL 落入 OAuth 访问日志。

此适配层只处理网页登录，不是命令沙箱。同 Pod 内的恶意进程仍在信任边界内，远程项目执行隔离仍必须单独完成。既有 WebSocket 建立后不会持续向 IdP 检查撤销；Cookie 或账户变更不能被描述成现有连接立即断开。

## 部署与轮换

先重新构建包含 `auth/` 包装器的新镜像，再通过 `panghu_chat/dsh/deploy.sh` 一并部署。旧镜像没有 3081 监听器，不能仅修改 OAuth upstream。回滚时镜像入口、探针和 OAuth upstream 必须作为一组回滚。

```bash
bash build.sh               # 必须先构建并推送新镜像
bash deploy.sh --dry-run     # 只打印 apply 顺序
bash deploy.sh               # 真正部署
```

邮箱白名单支持免重启更新：修改 `dsh-owner` ConfigMap 后，等待 Kubernetes 将文件更新到 Pod，适配层在每次 HTTP 请求和 WebSocket 建连认证时重新读取 `/owner/emails`。空名单拒绝所有用户，文件读取失败返回 503，不沿用旧名单。已建立的 WebSocket 不会因名单修改立即断开。

首次启用这一功能需要构建并部署新镜像，此后修改名单无需重启。仍需同步仓库配置，避免后续部署覆盖名单。

envFrom 凭据轮换后，仍须重启网页：

```bash
kubectl -n dsh rollout restart deployment/dsh-web
kubectl -n dsh rollout status deployment/dsh-web --timeout=300s
```

## 服务器验收

需验证：本人可登录、其他账号被拒绝、错误 Host/Origin 被拒、注销与撤销后的连接行为、WebSocket 升级与重连、以及**外层 OAuth 与 DSH 原生认证叠加后 Cookie 的实际 `Set-Cookie` 行为**。

本地 `node --test panghu_chat/dsh/auth/adapter.test.mjs` 已覆盖兑换、拒绝、流式转发和 WebSocket；真实 Casdoor 浏览器跳转、原生 Cookie、镜像重建后的恢复仍需服务器验收，本次未自动部署。
