# PPT 工作台的 Vault 配置

PPT 部署使用 `ppt-service` namespace，凭据由 Vault 管理并通过 ESO 同步。准备下表四条记录后，在服务器运行 `bash deploy.sh` 完成网站及数据库的首次安装或后续升级。完整流程见 [部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md) 与 [运行合同](../../panghu_agent/ppt_service/deploy/k8s/CONTRACT.md)。

## 配置归属

敏感值由 Vault 管理，映射集中在 [ppt-service-externalsecret.yaml](ppt-service-externalsecret.yaml)。非敏感 Casdoor issuer、client ID、回调域名、代理规则集中在 [OAuth 配置](../../oauth/k8s/ppt-proxy-configmap.yaml) 和 [配置说明](../../oauth/k8s/PPT.md)。允许访问的精确邮箱白名单单独放在 [ppt-owner-configmap.yaml](../../oauth/k8s/ppt-owner-configmap.yaml) 的 `ppt-owner.data.emails`，每行一个邮箱，不需配置 `sub`，也不放入 Vault；公开站点固定为 `https://ppt-service.panghuer.top`。当前按已确认方案接入 frpc/VPS Nginx，配置见 [VPS 说明](../../vps/PPT.md)、[frpc 路由](../../vps/k8s/routes/ppt-service.toml) 和 [Nginx 模板](../../vps/nginx/ppt-service.conf.template)。公网 DNS 使用 `A ppt-service → 62.234.50.20`、DNS only，不与同名 Tunnel CNAME 并存；实际切换需单独核对。[Cloudflare Tunnel 配置](../../cloudflare-tunnel/PPT.md) 保留为可选路线。业务部署只引用这些配置与下表 Secret 的明确键，不从公共服务目录复制密钥，不用 `envFrom` 扩散凭据。模型路由属于 `llm-service/`；本次不添加模型别名或调用方。Casdoor 和 Cloudflare 由用户在后台配置。

## 路径和消费者

| Vault CLI 路径 | Vault 字段 | Kubernetes Secret / 键 | 唯一消费者 |
| --- | --- | --- | --- |
| `secret/ppt-service/oidc` | `CLIENT_SECRET`、`COOKIE_SECRET` | `ppt-oidc` / `client-secret`、`cookie-secret` | `ppt-site` Pod 的 `oauth2-proxy` 容器 |
| `secret/ppt-service/database-runtime` | `DATABASE_URL` | `ppt-database-runtime` / `DATABASE_URL` | `ppt-site` Pod 的 `site` 容器 |
| `secret/ppt-service/database-migrator` | `DATABASE_URL` | `ppt-database-migrator` / `DATABASE_URL` | 显式迁移 Job |
| `secret/ppt-service/postgres-bootstrap` | `POSTGRES_PASSWORD` | `ppt-postgres-bootstrap` / `POSTGRES_PASSWORD` | 新建的独立 PostgreSQL 容器 |

这四个 Secret 都位于 `ppt-service`，每个由同名 ExternalSecret 以 `creationPolicy: Owner` 管理。清单没有 Namespace、Secret 明文、`dataFrom.extract` 或模型供应商凭据。首次使用前检查同名 Secret 的 owner，避免接管其他部署的对象。尚未准备齐全的路径或空值不能当作已配置完成。

Vault CLI 使用不含 `data/` 的路径；ExternalSecret 的 `remoteRef.key` 使用仓库约定的 `secret/data/...`。沿用现有 `ClusterSecretStore/vault-backend`，它的服务账号负责读 Vault，应用和迁移 Job 不需要 Vault token 或 Kubernetes API token。每个静态 `remoteRef` 只读取表中的字段；公共 ClusterSecretStore 的 ESO 管理身份本身不是 namespace 级凭据隔离，不能把容器之间的投射范围描述为 Vault ACL 的强隔离。若以后收窄 ESO policy，必须保留这四个数据路径所需的 read 权限并另行验证同步。

## 凭据准备

先准备全部四条 Vault 记录。runtime/migrator URL 使用各自计划的角色密码，`bash deploy.sh` 通过 PostgreSQL 的管理连接创建全新的 `ppt_migrator`、`ppt_runtime` 和 `ppt_service`。角色密码在创建角色时一并设置，全部 bootstrap 授权成功后才写入数据库 comment 完成标记 `ppt-service-bootstrap-v1`。

重复部署只复用具有该完成标记、角色和归属均符合合同的数据库，再检查 schema 升级；不会无条件重置已有密码。缺少标记、初始化中断或状态冲突时停止并保留数据，由管理员核实，不通过手工补标记跳过检查。首次安装仍只运行普通 `bash deploy.sh`，无需额外步骤。

ExternalSecret 只负责同步字符串；角色与数据库由部署脚本管理，Secret Ready 本身不证明数据库已初始化。正常部署使用同一入口，完整命令和存储处理见 [服务器部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md#服务器标准入口)。

两份应用 URL 都必须使用已安装的 psycopg 驱动和独立数据库地址：

```text
postgresql+psycopg://ppt_runtime:<URL编码后的密码>@ppt-postgres.ppt-service.svc.cluster.local:5432/ppt_service
postgresql+psycopg://ppt_migrator:<URL编码后的密码>@ppt-postgres.ppt-service.svc.cluster.local:5432/ppt_service
```

密码中的保留字符需要 URL 编码。把完整 URL 存入各自 `DATABASE_URL`，不在 ESO 模板里直接拼接未编码密码。`POSTGRES_USER=ppt_bootstrap`、`POSTGRES_DB=postgres` 仅用于新 PostgreSQL 的初始化/维护；不得把 bootstrap 登录提供给站点、Worker 或迁移 Job，不复用现有 `data/postgres` 的 appuser 或凭据。数据库数据目录已有内容时，修改 `POSTGRES_PASSWORD` 环境变量不会自动改变库内角色密码。

OIDC 使用专属 PPT Casdoor 应用。其公开 client ID 同时用于代理 client ID 和站点受众校验，由 OAuth 配置集中管理；这里仅保存该应用的 client secret。Cookie secret 由管理端生成独立随机密钥，使用 32 个随机字节的 URL-safe Base64 编码，满足 oauth2-proxy v7.8.0 的解码后密钥长度要求；不复用其他站点的 cookie secret。issuer、回调地址、允许邮箱不属于此 Secret。JWT 的稳定 `sub` 由应用读取，用于与 issuer 一起绑定项目归属，无需管理员录入名单。

登录 Vault 后，在装有 OpenSSL 的 Bash 终端直接执行以下四条命令，无需创建 JSON 文件。只需把第一条的 `CLIENT_SECRET` 替换为专属 PPT Casdoor 应用的实际 Client Secret；Cookie 密钥和三个数据库密码自动生成。

```bash
kubectl -n vault exec -i vault-0 -- vault kv put secret/ppt-service/oidc \
  CLIENT_SECRET='替换为PPT应用的Client Secret' \
  COOKIE_SECRET="$(openssl rand -base64 32 | tr '+/' '-_')"

kubectl -n vault exec -i vault-0 -- vault kv put secret/ppt-service/database-runtime \
  DATABASE_URL="postgresql+psycopg://ppt_runtime:$(openssl rand -hex 24)@ppt-postgres.ppt-service.svc.cluster.local:5432/ppt_service"

kubectl -n vault exec -i vault-0 -- vault kv put secret/ppt-service/database-migrator \
  DATABASE_URL="postgresql+psycopg://ppt_migrator:$(openssl rand -hex 24)@ppt-postgres.ppt-service.svc.cluster.local:5432/ppt_service"

kubectl -n vault exec -i vault-0 -- vault kv put secret/ppt-service/postgres-bootstrap \
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
```

这组命令用于首次配置，执行一次即可，后续部署无需重复写入。生成的数据库密码只含十六进制字符，可直接用于 URL，无需另外编码；部署脚本会读取这些密码并自动创建角色。写入完成后，在服务器的 `panghu_agent/ppt_service` 目录设置 `PPT_CLIENT_ID` 并运行 `bash deploy.sh`。

已有数据库的密码轮换按下文“启用和轮换”处理，需要协调库内密码和 Vault 值；部分字段更新使用 `kv patch`，避免覆盖其他字段。管理端不应通过输出真实 Secret、Pod 环境、数据库 URL 或 Vault 记录来检查结果。

## 排查首次部署的凭据同步失败

如果部署在同步 Vault 凭据阶段失败，先检查：

```bash
kubectl -n ppt-service get externalsecret
kubectl -n ppt-service get events \
  --field-selector type=Warning --sort-by=.lastTimestamp
```

`SecretSyncedError` 配合事件中的 `Secret does not exist` 表示 ESO 找不到所引用的 Vault 记录。对照上表在 `secret` KV v2 引擎中创建四条记录，并核对字段名；Vault 页面中的相对路径为 `ppt-service/...`，CLI 使用 `secret/ppt-service/...`，不要把 ESO 的 `secret/data/...` 当作页面中的记录名。若记录已存在，检查实际保存路径、Vault 引擎和 ESO 的读取权限，不要改成其他服务的凭据。

正常部署需要全部四条记录。凭据同步阶段失败时尚未运行应用数据库初始化，补齐路径和字段后重新执行 `bash deploy.sh`。若同步已成功而数据库初始化报错，应先检查已有或部分创建的角色/数据库，再根据错误处理，保留数据。

## OAuth 代理因 Cookie 密钥长度错误无法启动

如果 PostgreSQL、迁移和存储 Job 都已成功，但网站 Pod 的 `oauth2-proxy` 容器反复重启，日志出现 `cookie_secret must be 16, 24, or 32 bytes ... but is 44 bytes`，检查 Cookie 密钥的编码。普通 `openssl rand -base64 32` 可能生成 `+`、`/`，导致 URL-safe Base64 解码失败，代理把它当作 44 字节原文。上面的首次写入命令用 `tr '+/' '-_'` 转为正确编码。

已完成数据库初始化时，只更新 OIDC 记录中的 Cookie 密钥，保留 Client Secret 和数据库凭据。下面通过集群内 Vault CLI 更新：

```bash
kubectl -n vault exec -i vault-0 -- vault kv patch secret/ppt-service/oidc \
  COOKIE_SECRET="$(openssl rand -base64 32 | tr '+/' '-_')"
```

然后在服务器的 `panghu_agent/ppt_service` 目录运行 `bash deploy.sh --skip-build`。部署脚本会等待新的 ESO 同步并重启网站及代理；此修复无需重建站点镜像，也不需要重新执行四条首次写入命令。Cookie 密钥变化后需重新登录。

本次曾出现 Vault 已修正、Kubernetes Secret 仍为旧值的情况。实际检查结果和恢复边界见
[2026-10-24 部署排障记录](../../panghu_agent/ppt_service/deploy/k8s/TROUBLESHOOTING.md)。

## 启用和轮换

`deploy.sh` 创建 Namespace 后应用本清单并同步所需 Secret，再启动数据库、执行迁移和发布网站。可以只检查同步状态：

```bash
kubectl -n ppt-service get externalsecret \
  ppt-oidc ppt-database-runtime ppt-database-migrator ppt-postgres-bootstrap
kubectl -n ppt-service describe secret ppt-oidc
kubectl -n ppt-service describe secret ppt-database-runtime
kubectl -n ppt-service describe secret ppt-database-migrator
kubectl -n ppt-service describe secret ppt-postgres-bootstrap
```

清单的定时刷新间隔为1小时。更新 Vault 记录后，可主动触发对应 ExternalSecret 同步，再等待 Ready：

```bash
kubectl -n ppt-service annotate externalsecret \
  ppt-database-runtime ppt-database-migrator ppt-oidc \
  force-sync="$(date +%s)" --overwrite
```

`describe secret` 只用于核对键名、字节数和 owner，不使用 `-o yaml` 或解码输出。ESO 同步更新不刷新既有容器的环境变量；OIDC 密钥轮换后需按部署流程重启站点，cookie secret 改动会使现有会话失效。数据库密码轮换需先协调库内密码与 Vault 值，再仅重启对应消费者；不可用重启 PostgreSQL 代替数据库密码变更。新的迁移 Job 获取最新值，不为刷新凭据重跑已成功的迁移。

## 模型授权边界

本次 P2 网站登录和公共配置不启用 Pi 模型执行，不申请 `LLM_TOKEN_PPT_*`，不创建 `llm-token` Secret。站点、迁移、PostgreSQL 和 Worker 均不接收供应商 key 或网关长期 caller token。Casdoor client secret 仅给 OAuth sidecar，bootstrap 登录仅给 PostgreSQL；站点仅接收自己的 runtime 数据库登录，迁移仅接收 migrator 登录，Worker 不接收数据库凭据。

已有 Pi 部署交接要求长期上游凭据只给可信任务代理，Worker 只得绑定 project/job/attempt/fencing/phase、期限与预算的任务 token；撤销任务必须中断模型流。公共 `llm-trusted` 路由的存在不能代替这层任务授权。

当前 `worker/model_proxy.py` 的 `ProxyConfig` 强制 HTTPS 上游，默认使用 `https://custom-llm-proxy.panghuer.top/v1` 和 Responses。集群内 `http://llm-service.llm.svc.cluster.local/v1` 无法通过该现有校验。以后接入网关必须先确认可信代理的实际部署合同，验证受控 HTTPS/网络路径、固定模型/别名语义、Responses 参数及输出预算，再单独登记 caller 和只给代理的 Secret；不能仅替换 URL、放松 HTTPS 校验或给 Worker 长期网关令牌。详见 [Pi K8s 交接](../../panghu_agent/ppt_service/K8S_DEPLOYMENT_HANDOFF.md) 和 [llm-service 调用方规范](../../llm-service/INTEGRATION.md)。
