# DSH OAuth

配置源为 `dsh-proxy-configmap.yaml`，由 `panghu_chat/dsh/k8s/web.yaml` 以 ConfigMap 卷挂载进 `dsh-web` Pod 的 oauth2-proxy 容器。与 Hermes 一样使用 INI（`--config=/oauth/oauth2-proxy.cfg`），不是命令行参数。

代理与 DSH 网页同 Pod：DSH 监听回环 `127.0.0.1:3080`，代理上游写死 `http://127.0.0.1:3080/`，因此两者必须在同一 Pod、共享 network namespace。

## 两层认证

外层 oauth2-proxy **不是唯一入口认证**。DSH 保留自己的 launch token 兑换与 authority-bound cookie；首次登录流程是：

1. 在 Casdoor 完成 OIDC（本 ConfigMap 负责这一层，精确邮箱白名单）。
2. 初次访问时通过一个已认证的 HTTPS 根 URL 兑换进程 launch token，之后由 DSH 自己的 cookie 维持会话。

因此 Casdoor **只需登记一个回调** `https://dsh.panghuer.top/oauth2/callback`——与 Hermes 不同，DSH 的原生认证不是 OIDC，不要为它编造第二个回调或 OIDC 客户端配置。

- 在 Casdoor 建**独立应用**（不要复用 panghu-suite 或其他服务的应用），开启 MFA，确认 `email` 与 `email_verified` 声明可信。
- 不要加入 `--email-domain=*`、不要跳过邮箱验证、不要使用匿名跳过路由。
- launch token 不得进入任何 manifest、PR、路由配置或常规访问日志；确认 Cloudflare 与代理侧都不记录带 query 的 URL。详见 `panghu_chat/dsh/docs/boundaries.md`。

## 白名单与 Cookie

- `dsh-owner.data.emails` 是**唯一待填写项**，填本人已验证邮箱。空值默认拒绝访问，不能改成通配邮箱域。
- 会话 Cookie 为独立的 `__Host-dsh`，不设置父域。`__Host-` 前缀强制要求 Secure + `Path=/` + 无 Domain 三条同时成立，本配置三条都满足；改动时不要只改其中一条。
- 客户端 ID、客户端密钥、Cookie 密钥都通过 Vault 同步的 `dsh-oidc` Secret 注入，**不复制到本 ConfigMap**。

## 未定项：原生 Cookie 的 Secure

DSH 的原生 cookie 在本机使用场景下**不带 `Secure`**。生产网关必须在不破坏 HttpOnly / SameSite、也不关闭 DSH 自身信任检查的前提下补上 `Secure`。上游是否提供配置开关尚未验证；若不提供，需要一个位于 OAuth 与 DSH 之间的极小回环适配层。**这一项未解决前不要放开 agent 执行。** 不要照抄 Hermes 的 `WEBSOCKETS_MAX_LINE_LENGTH`——那是 Python websockets 的设置，DSH 是 Node。

## 部署与轮换

通过 `panghu_chat/dsh/deploy.sh` 一并部署；没有独立的代理 Deployment，避免两个配置来源漂移。

```bash
bash deploy.sh --dry-run     # 只打印 apply 顺序
bash deploy.sh               # 真正部署
```

envFrom 凭据轮换或邮箱白名单修改后，必须重启网页：

```bash
kubectl -n dsh rollout restart deployment/dsh-web
kubectl -n dsh rollout status deployment/dsh-web --timeout=300s
```

## 服务器验收

需验证：本人可登录、其他账号被拒绝、错误 Host/Origin 被拒、注销与撤销后的连接行为、WebSocket 升级与重连、以及**外层 OAuth 与 DSH 原生认证叠加后 Cookie 的实际 `Set-Cookie` 行为**。

**本次未测试**：本文件与配套 manifest 未在集群上部署或验证。
