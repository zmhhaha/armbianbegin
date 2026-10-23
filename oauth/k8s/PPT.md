# PPT 工作台：登录配置与部署

PPT 部署到 `ppt-service`，公开地址为 **https://ppt.panghuer.top**。在 Casdoor 后台创建独立应用、填写邮箱名单并准备 Vault 凭据后，用服务器部署脚本发布网站；Cloudflare Tunnel 由你在后台配置。

## 配置放在哪里

| 内容 | 唯一配置来源 |
| --- | --- |
| Casdoor issuer、client ID、回调和代理/API 认证参数 | [ppt-proxy-configmap.yaml](ppt-proxy-configmap.yaml) |
| 允许访问的精确邮箱白名单 | [ppt-owner-configmap.yaml](ppt-owner-configmap.yaml) |
| 生成填写后的公开配置 | [configure-ppt.py](configure-ppt.py) |
| 网站/代理到集群内 Casdoor HTTPS 的网络许可 | [ppt-oidc-egress.yaml](ppt-oidc-egress.yaml) |
| 密钥与数据库凭据的 Vault/ESO 映射 | [Vault 配置](../../vault/inventory/PPT-SERVICE.md) |
| Cloudflare Tunnel 入口与两端网络策略 | [Cloudflare 配置](../../cloudflare-tunnel/PPT.md) |
| 可选的 VPS Nginx/frpc 入口 | [VPS 配置](../../vps/PPT.md) |
| 站点镜像、数据库、PVC、显式迁移、回滚 | [业务部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md) |
| 后续任务模型代理与 llm-service 的边界 | [模型接入合同](../../llm-service/design/ppt-service-integration.md) |

`ppt-auth`、`ppt-oidc` 和 `ppt-owner` 三个 ConfigMap 都部署在 `ppt-service`。`ppt-auth` 通过 `envFrom` 仅给网站，并设置 `INVITATION_EMAILS_FILE=/owner/emails`；`ppt-oidc` 仅挂载给同 Pod 的 oauth2-proxy。`ppt-owner` 在网站和代理两个容器内都以完整只读目录挂载到 `/owner`，两者读取同一份 `/owner/emails`；不使用 `subPath`，以便 Kubernetes 更新文件。业务 `base/config.yaml` 只保留数据路径、执行开关等应用参数，不再存第二份 OAuth 配置。密钥不放 ConfigMap。

## 1. 在 Casdoor 后台新建独立应用

使用支持 OAuth/OIDC authorization-code 流程的独立 PPT Web 应用；服务端代理使用 client ID 与 client secret 交换 code。配置如下：

| 配置 | 值 |
| --- | --- |
| 名称 | 自定，例如 `ppt-workbench` |
| 精确 Redirect URI | `https://ppt.panghuer.top/oauth2/callback` |
| Scopes | `openid email profile` |
| Issuer | `https://auth.panghuer.top` |
| ID token 算法 | `RS256`；签名公钥由该 issuer 的 JWKS 提供 |
| 必要 claims | `iss`、`aud`、`exp`、`iat`、稳定 `sub`、`email` 和布尔值 `email_verified: true` |

保存应用后取得公开 **client ID**，client secret 存入下节 Vault。client ID 同时用于代理登录和 API 的 `aud` 校验；回调不使用通配符。确认实际 ID token 的 audience 与此 client ID 匹配，邮箱验证状态符合代理要求；不关闭 issuer、TLS、签名或邮箱验证来适配错误配置。

准入只需维护每个人在 Casdoor 中已验证的精确邮箱，不需要查找或填写 `sub`。代理按邮箱白名单允许登录，API 每次认证请求都从已验签 JWT 读取 `email`，要求 `email_verified` 为布尔值 `true`，再读取同一名单判断准入；不信任浏览器自行传入的身份头。项目归属仍绑定已验证的 `iss` 与稳定 `sub`，邮箱不是项目 owner 标识。

## 2. 配置 client ID 与邮箱白名单

编辑 [ppt-owner-configmap.yaml](ppt-owner-configmap.yaml) 中的 `ppt-owner.data.emails`，每行一个精确邮箱。与 DSH、Hermes、Pi 一样，PPT 有自己的名单：

```yaml
data:
  emails: |
    user1@example.com
    user2@example.com
```

填入实际已验证邮箱并保留仍需授权的用户；空名单拒绝所有用户。名单文件无法读取或格式无效时，API 返回 503，不沿用旧名单。无需创建 `ppt-invites.json` 或配置 subject 名单。

从本仓库根目录生成 client ID 配置（需要 Python 3.11+ 和 PyYAML）：

```sh
python oauth/k8s/configure-ppt.py \
  --client-id '后台取得的PPT-client-ID' \
  --output /secure/ppt-auth.rendered.yaml
```

工具只接收 `--client-id` 和 `--output`，同时填入代理 `client_id` 和 API `OIDC_AUDIENCE`；不生成名单、不改源模板、不写密钥、不访问集群。输出必须是尚不存在的新文件。名单单独应用 `ppt-owner-configmap.yaml`，保留你已维护的实际邮箱。认证模板中的 client placeholder 必须替换为实际值，空名单拒绝全部用户。

名单增删后应用该文件，等待 Kubernetes 将完整 ConfigMap 目录更新到两个容器；网站每次认证请求重新读取名单。无需重建镜像或配置 `sub`。当前版本首次部署必须重建并推送包含这次认证改造的站点镜像，旧 P1 镜像不具备这套名单逻辑；已经建立的连接不因修改名单立即断开。

首次由第5节的部署流程创建名单；后续维护优先修改上述源文件，再执行：

```sh
kubectl apply -f oauth/k8s/ppt-owner-configmap.yaml
```

也可用 `kubectl -n ppt-service edit configmap ppt-owner` 临时增删 `data.emails`，随后把变更同步回上述源文件并保留其他用户。不要重新应用仍为空的模板，否则会清空线上授权名单。

## 3. 在 Vault 准备凭据

按 [Vault 配置](../../vault/inventory/PPT-SERVICE.md) 准备四条独立路径：

- `secret/ppt-service/oidc`：专用 `CLIENT_SECRET`、独立 `COOKIE_SECRET`。
- `secret/ppt-service/database-runtime`：网站最小权限 `DATABASE_URL`。
- `secret/ppt-service/database-migrator`：迁移角色 `DATABASE_URL`。
- `secret/ppt-service/postgres-bootstrap`：新 PostgreSQL 的 `POSTGRES_PASSWORD`。

Cookie secret 例如使用 32 随机字节的 base64；只在安全管理环境生成和写 Vault。数据库 URL 使用 `postgresql+psycopg://`，两个应用 URL 指向新 `ppt_service` 数据库、使用不同角色。ESO 负责同步凭据；`deploy.sh` 使用专用凭据完成数据库初建或升级及角色授权检查。

## 4. Cloudflare Tunnel 配入口

在能解析、访问集群 Service 的 cloudflared 上配置 Public Hostname：

| 字段 | 值 |
| --- | --- |
| Hostname | `ppt.panghuer.top` |
| Service type | `HTTP` |
| Service URL | `ppt-site.ppt-service.svc.cluster.local:4180` |

若界面合并协议字段，填写 `http://ppt-site.ppt-service.svc.cluster.local:4180`。8000 是同 Pod 内的 loopback API，不作为 Tunnel 目标。外部访问保持 HTTPS，转发保留 Host 与 HTTPS 来源信息。仅有 DNS 记录不能使部署在集群外的 cloudflared 访问 `.svc.cluster.local`；必须先选择具备实际连通性的 Tunnel 实例。

按 [Cloudflare 说明](../../cloudflare-tunnel/PPT.md) 用实际 cloudflared namespace/Pod 标签填写并应用**两端**网络策略。不要把管理 Tunnel 的 operator 标签当作流量来源。Cloudflare Cache Rule 应对该主机全部 Bypass；PPT 的页面、资产与 API 均需认证并返回 `no-store`。不要增加 Cache Everything。若改用 VPS 链路，使用专用禁缓存模板并按 VPS 文档处理 frpc，而不同时覆盖同一主机入口。

## 5. 在服务器仓库构建和部署

服务器使用 Linux ARM64，需有 Docker、kubectl、Python 3.11+ 与 PyYAML，并能访问镜像仓库 `arm-cluster-master:5000`。先同步主仓库及 `panghu_agent` 子仓库的当前代码和公共配置，然后执行：

```sh
cd <仓库目录>/panghu_agent/ppt_service
export PPT_CLIENT_ID='<Casdoor 实际 PPT client ID>'
bash deploy.sh
```

同一命令用于首次安装和后续发布：默认构建、验证并推送站点镜像，同步四条 Vault 凭据，启动 PostgreSQL，处理数据库初建或 schema 升级，检查存储与运行权限，再发布网站。无需在 Windows 打包网页或手工上传镜像上下文。

也可先构建，再发布已有镜像：

```sh
bash build.sh
bash deploy.sh --skip-build
```

`rendered/image.txt` 保存成功推送后的 registry digest，`--skip-build` 复用该摘要。用 `PPT_SITE_IMAGE` 可显式指定完整镜像摘要。`PPT_AUTH_CONFIG` 可指定由 `configure-ppt.py` 生成的公开配置，替代 `PPT_CLIENT_ID`；后续两者均未提供时，可复用线上已有的有效公开配置。

普通部署保留已有 `ppt-owner` 名单，首次才从源文件创建；明确要替换时使用 `PPT_OWNER_CONFIG`，或按第 2 节单独应用名单。修改公开认证参数或环境变量中的 Secret 后需重启对应消费者；仅增删邮箱则等待两个容器的目录投影更新即可。

Casdoor 继续访问 `https://auth.panghuer.top`，通过现有 CoreDNS split horizon 与集群内 TLS ingress 连接；`ppt-oidc-egress.yaml` 只允许指定 `ingress-nginx` controller Pod 的 TCP443。DNS 使用业务基线许可，实际部署后核查 discovery/token/JWKS 路径及 CNI 允许和拒绝行为。

网站就绪后开放 Tunnel。完整部署前置、数据库与存储处理及故障排查见 [服务器部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md#服务器标准入口)。Pi 模型生成尚未接通，`PPT_EXECUTION_ENABLED=false` 保持关闭，生成请求仍返回 `503 execution_not_connected`。

## 6. 部署后验收

- 未登录访问 `/` 应进入登录；`/api/v1/me` 应返回 401，避免后台 API 跳登录页。
- 白名单用户完成独立 PPT 登录；名单外邮箱、未验证邮箱、缺失或非布尔 `true` 的 `email_verified` 均被拒绝。JWT 仍须包含稳定 `sub`，但无需把它配置进名单。确认真实 `aud`、RS256 和 JWKS 可用，不记录 token 内容。
- 修改 `ppt-owner.data.emails` 后等待两个容器的文件更新，验证移除用户后下一次认证请求被拒绝，空名单拒绝所有用户；名单读取或格式错误时 API 返回 503。确认原有项目仍按 `iss/sub` 隔离，不随邮箱名单变更转移归属。
- `/api/v1/me` 能返回身份与 CSRF 状态；修改请求必须带精确 Origin `https://ppt.panghuer.top` 和匹配 CSRF cookie/header，缺失或错误均被拒绝。
- `__Host-ppt` cookie 具有 Secure、HttpOnly、Path=/、SameSite=Lax，无 Domain。用实际 Casdoor claims 核查 cookie 大小。代理 cookie 最长8小时且不配置自动 refresh；API还独立检查 ID token 的 `exp`，不能把8小时当作 token 保证有效期。
- `/oauth2/sign_out` 清除本地代理会话，随后 API 401。它不会自动注销 Casdoor 的全局 SSO 会话，也不会吊销已复制的无状态 cookie；若需要全局登出，单独验证提供方登出合同。
- 带会话访问某个 `/assets/…` 成功后，使用全新未登录浏览器访问同一 URL 应被拒绝。确认 Cloudflare/VPS 不从共享缓存返回此前认证资产。
- 生成请求当前应返回 `503 execution_not_connected`；网站登录和项目管理可正常使用，Pi 模型生成接入后再单独验收。

固定 v7.8.0 的隔离协议验收工具见 [tests/oidc](../../panghu_agent/ppt_service/tests/oidc/README.md)，当前交付脚本和静态检查，尚未跑完真实代理回合。脚本使用合成 HTTPS issuer/CA、身份和 SQLite，不借用业务密钥；部署者可先运行它，再做上述真实浏览器验收。已知 JWKS 缓存允许已知 kid 暂存，不能声称删除公钥会立即撤销所有旧凭证。

2026-10-24：当前配置和部署以本文为准。[P2 结果记录](../../panghu_agent/ppt_service/deploy/oidc/RESULTS.md) 保留历史验证，其中旧 namespace 和旧脚本步骤属于当时的记录；实际登录、网络和会话结果按以上项目记录。
