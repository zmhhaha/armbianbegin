# PPT 工作台：P2 登录配置与部署交接

入口已确认使用 **https://ppt.panghuer.top**。本轮交付代码、配置模板和验收工具；Casdoor 应用、Cloudflare Tunnel 和实际部署由你配置。当前未上线，专用 client 和邮箱白名单留空；完整真实 SSO 验收仍待部署后执行。

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

`ppt-auth`、`ppt-oidc` 和 `ppt-owner` 三个 ConfigMap 都部署在 `ppt-service-test`。`ppt-auth` 通过 `envFrom` 仅给网站，并设置 `INVITATION_EMAILS_FILE=/owner/emails`；`ppt-oidc` 仅挂载给同 Pod 的 oauth2-proxy。`ppt-owner` 在网站和代理两个容器内都以完整只读目录挂载到 `/owner`，两者读取同一份 `/owner/emails`；不使用 `subPath`，以便 Kubernetes 更新文件。业务 `base/config.yaml` 只保留数据路径、执行开关等应用参数，不再存第二份 OAuth 配置。密钥不放 ConfigMap。

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

工具只接收 `--client-id` 和 `--output`，同时填入代理 `client_id` 和 API `OIDC_AUDIENCE`；不生成名单、不改源模板、不写密钥、不访问集群。输出必须是尚不存在的新文件。名单单独应用 `ppt-owner-configmap.yaml`。原模板保持 client placeholder 和空名单，直接拿模板上线不会允许任何人访问。

名单增删后应用该文件，等待 Kubernetes 将完整 ConfigMap 目录更新到两个容器；网站每次认证请求重新读取名单。无需重建镜像或配置 `sub`。当前版本首次部署必须重建并推送包含这次认证改造的站点镜像，旧 P1 镜像不具备这套名单逻辑；已经建立的连接不因修改名单立即断开。

首次由第5节的部署流程创建名单；后续维护优先修改上述源文件，再执行：

```sh
kubectl apply -f oauth/k8s/ppt-owner-configmap.yaml
```

也可用 `kubectl -n ppt-service-test edit configmap ppt-owner` 临时增删 `data.emails`，随后把变更同步回上述源文件并保留其他用户。不要重新应用仍为空的模板，否则会清空线上授权名单。

## 3. 在 Vault 准备凭据

按 [Vault 配置](../../vault/inventory/PPT-SERVICE.md) 准备四条独立路径：

- `secret/ppt-service/test/oidc`：专用 `CLIENT_SECRET`、独立 `COOKIE_SECRET`。
- `secret/ppt-service/test/database-runtime`：网站最小权限 `DATABASE_URL`。
- `secret/ppt-service/test/database-migrator`：迁移角色 `DATABASE_URL`。
- `secret/ppt-service/test/postgres-bootstrap`：新 PostgreSQL 的 `POSTGRES_PASSWORD`。

Cookie secret 例如使用 32 随机字节的 base64；只在安全管理环境生成和写 Vault。数据库 URL 使用 `postgresql+psycopg://`，两个应用 URL 指向新 `ppt_service` 数据库、使用不同角色。ESO 同步字符串，不会替你创建角色或完成数据库授权。

## 4. Cloudflare Tunnel 配入口

在能解析、访问集群 Service 的 cloudflared 上配置 Public Hostname：

| 字段 | 值 |
| --- | --- |
| Hostname | `ppt.panghuer.top` |
| Service type | `HTTP` |
| Service URL | `ppt-site.ppt-service-test.svc.cluster.local:4180` |

若界面合并协议字段，填写 `http://ppt-site.ppt-service-test.svc.cluster.local:4180`。8000 是同 Pod 内的 loopback API，不作为 Tunnel 目标。外部访问保持 HTTPS，转发保留 Host 与 HTTPS 来源信息。仅有 DNS 记录不能使部署在集群外的 cloudflared 访问 `.svc.cluster.local`；必须先选择具备实际连通性的 Tunnel 实例。

按 [Cloudflare 说明](../../cloudflare-tunnel/PPT.md) 用实际 cloudflared namespace/Pod 标签填写并应用**两端**网络策略。不要把管理 Tunnel 的 operator 标签当作流量来源。Cloudflare Cache Rule 应对该主机全部 Bypass；PPT 的页面、资产与 API 均需认证并返回 `no-store`。不要增加 Cache Everything。若改用 VPS 链路，使用专用禁缓存模板并按 VPS 文档处理 frpc，而不同时覆盖同一主机入口。

## 5. 在服务器仓库构建和部署

以下命令由部署者在自己的 Linux ARM64 服务器执行，本轮没有执行 `apply` 或上线。服务器需有 Docker、kubectl、Python 3.11+ 与 PyYAML；kubectl 指向目标集群，并能管理 `ppt-service-test` 的资源与专用凭据。`deploy.sh` 默认使用 `/etc/kubernetes/super-admin.conf`，其他获准配置通过 `KUBECONFIG` 指定。构建主机与各节点须能访问 `arm-cluster-master:5000` 镜像仓库；构建需要获取 Node/Python 基础镜像和锁定依赖，无需宿主机 Node/pnpm 或旧 API 开发镜像。先把当前代码及仓库内公共配置同步到服务器，再进入：

```sh
cd <仓库目录>/panghu_agent/ppt_service
```

### 首次准备

1. 按前面各节在 Casdoor 后台创建专属应用、编辑独立邮箱名单，并在 Vault 准备四条凭据。两份 `DATABASE_URL` 先使用各自计划的新角色密码；角色由下述初始化步骤创建，Secret Ready 本身不会创建角色。只想先启动 PG 和准备卷时，可暂时只准备 `postgres-bootstrap` 路径。
2. 执行准备阶段：

   ```sh
   bash deploy.sh --prepare
   ```

   它不构建、不要求 client ID 或站点镜像，只准备 namespace、基础清单和 ESO，同步 bootstrap Secret 并启动独立 PG；已有网站副本数保留。这一步会创建两个专用 PVC，不初始化应用数据库，也不打开新的站点入口。
3. 存储管理员在**全新空的** `ppt-data` CephFS 卷内显式创建 `state`，属主 UID/GID 为 `10000:10000`、权限 `0700`，站点挂载后为 `/var/lib/ppt-service/state`。没有自动准备 Job；网站不带 `fsGroup`，不能假设它可在 root 所有的 PVC 根下自行建目录。

   必须先从 `ppt-data` 的 PVC/PV/CSI 子卷定位实际管理挂载路径，确认是此新空卷且 `state` 不存在，再执行 `install -d -m 0700 -o 10000 -g 10000 <已核验的新PVC根路径>/state`。不得猜路径、递归 chown 原数据或放宽 restricted 策略来启动临时 root Pod。已有数据按 P1 preserve 恢复流程处理，不执行这个新目录步骤。
4. 补齐四条 Vault 凭据。按 Cloudflare 文档填入**实际 Connector** 身份并应用双端网络策略；在后台准备 `ppt.panghuer.top` 路由与全主机 Cache Bypass，待网站就绪再开放。脚本不会替你修改 Casdoor 或 Cloudflare 后台，也不猜测 Connector 标签。

### 首次初始化并发布

提供公开的 client ID，然后执行：

```sh
export PPT_CLIENT_ID='<替换为 Casdoor 实际 PPT client ID>'
bash deploy.sh --init-db
```

默认先调用 `build.sh`，在 ARM64 上构建前端与独立 Python 站点、验证镜像、推送 `arm-cluster-master:5000/ppt-service-site`，将实际 `repo@sha256:...` 保存到 `rendered/image.txt`，再用该 digest 部署。无需先在 Windows 构建网页或上传 `context.tar`；旧 P1 镜像不包含当前邮箱认证改造，不能复用。

`--init-db` 是**仅首次**的新库初始化开关：从专用 runtime/migrator Secret 在内存中解析两个 URL 的角色密码，使用新 PG 本地管理通道创建全新 `ppt_service` 与独立角色，再进行迁移/权限收尾。不把密码放进参数、日志或渲染文件。目标数据库、任一角色已存在或检测到部分初始化时拒绝继续，不覆盖、不自动补齐；失败后先检查实际状态，不反复重试此开关。已有数据搬迁按 P1 的备份/恢复/等值检查流程执行。

首次 client 配置也可采用第2节生成的两份 ConfigMap：

```sh
PPT_AUTH_CONFIG=/secure/ppt-auth.rendered.yaml bash deploy.sh --init-db
```

`PPT_AUTH_CONFIG` 替代现场生成；`PPT_CLIENT_ID` 则由脚本生成一致的代理 client/API audience。两者都未提供时，只有线上已有符合新邮箱模式的有效认证配置才可复用，首次安装必须提供其一。

`ppt-owner` 首次从源文件创建，已在线存在时默认保留，普通重复部署不会用空模板清掉名单。后续名单变化按第2节单独 `kubectl apply`；也可显式设置 `PPT_OWNER_CONFIG=/secure/ppt-owner.yaml`，让部署脚本应用指定名单。

### 后续发布与复用镜像

首次完成后不再传 `--init-db`：

```sh
# 默认：构建、验证、推送，再部署当前源码。
bash deploy.sh
# 单独构建并推送；digest 保存到 rendered/image.txt。
bash build.sh
# 已构建时复用上述 digest。
bash deploy.sh --skip-build
# 也可明确指定经过核对的 registry digest，优先于 image.txt。
PPT_SITE_IMAGE='arm-cluster-master:5000/ppt-service-site@sha256:<64位摘要>' \
  bash deploy.sh --skip-build
# 只查看计划，不构建、不访问集群。
bash deploy.sh --dry-run
```

`rendered/image.txt` 保存 registry digest，本地 image ID 或可变 tag 都不能代替它。该工作流构建网站，原 Worker 的镜像构建入口已移到 `build_worker.sh`，不随网站发布启用。

构建默认推送；只有显式 `bash build.sh --no-push` 才只做本地验证，此模式不留下可部署的 digest。需要更换 registry、tag 或完整镜像名时，按 `bash build.sh --help` 使用 `REGISTRY`、`IMAGE_TAG` 或 `IMAGE`；站点部署仍要求可由各节点拉取的完整 registry digest。

修改公开认证 ConfigMap 或以环境变量注入的 Secret 后需按发布流程重启网站，既有容器的环境变量不会自动更新。仅修改独立 `ppt-owner.data.emails` 时等待两个容器的目录投影更新即可，API 后续认证请求会重读名单。不要在维护时直接重放原始 `apply -k base`：其零副本、挂起等初始值与部署脚本的阶段配置不同。

集群内 Casdoor 沿用 CoreDNS split horizon，仍访问 `https://auth.panghuer.top`，TLS 在 `ingress-nginx` 终结。`ppt-oidc-egress.yaml` 只允许精确 controller Pod 的 TCP443，DNS 由业务基线许可；不放行整个公网443。现有配置曾只读核对，实际 PPT Pod 的 DNS、discovery/token/JWKS、Calico 允许/拒绝和卷权限仍需部署后验证。

网站和代理就绪后再开放 Tunnel。工作流始终保留 `PPT_EXECUTION_ENABLED=false`、test 模式与人工验收 pending；登录成功不代表 Pi 或真实模型执行已接通。

## 6. 部署后验收

- 未登录访问 `/` 应进入登录；`/api/v1/me` 应返回 401，避免后台 API 跳登录页。
- 白名单用户完成独立 PPT 登录；名单外邮箱、未验证邮箱、缺失或非布尔 `true` 的 `email_verified` 均被拒绝。JWT 仍须包含稳定 `sub`，但无需把它配置进名单。确认真实 `aud`、RS256 和 JWKS 可用，不记录 token 内容。
- 修改 `ppt-owner.data.emails` 后等待两个容器的文件更新，验证移除用户后下一次认证请求被拒绝，空名单拒绝所有用户；名单读取或格式错误时 API 返回 503。确认原有项目仍按 `iss/sub` 隔离，不随邮箱名单变更转移归属。
- `/api/v1/me` 能返回身份与 CSRF 状态；修改请求必须带精确 Origin `https://ppt.panghuer.top` 和匹配 CSRF cookie/header，缺失或错误均被拒绝。
- `__Host-ppt` cookie 具有 Secure、HttpOnly、Path=/、SameSite=Lax，无 Domain。用实际 Casdoor claims 核查 cookie 大小。代理 cookie 最长8小时且不配置自动 refresh；API还独立检查 ID token 的 `exp`，不能把8小时当作 token 保证有效期。
- `/oauth2/sign_out` 清除本地代理会话，随后 API 401。它不会自动注销 Casdoor 的全局 SSO 会话，也不会吊销已复制的无状态 cookie；若需要全局登出，单独验证提供方登出合同。
- 带会话访问某个 `/assets/…` 成功后，使用全新未登录浏览器访问同一 URL 应被拒绝。确认 Cloudflare/VPS 不从共享缓存返回此前认证资产。
- 模型执行入口仍应拒绝执行；网页登录不代表 Pi 或真实模型已接入，`deployment_mode=test`、`manual_acceptance=pending` 继续有效。

固定 v7.8.0 的隔离协议验收工具见 [tests/oidc](../../panghu_agent/ppt_service/tests/oidc/README.md)，当前交付脚本和静态检查，尚未跑完真实代理回合。脚本使用合成 HTTPS issuer/CA、身份和 SQLite，不借用业务密钥；部署者可先运行它，再做上述真实浏览器验收。已知 JWKS 缓存允许已知 kid 暂存，不能声称删除公钥会立即撤销所有旧凭证。

结果和边界见 [P2 结果记录](../../panghu_agent/ppt_service/deploy/oidc/RESULTS.md)。P2 总项保留待验，直到实际登录、网络和会话验收完成。
