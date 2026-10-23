# PPT 工作台的 Vault 配置

本清单用于 `ppt-service-test` 隔离环境；2026-10-23 只交付声明，没有向 Vault 写值，也没有创建 ExternalSecret 或 Kubernetes Secret。应用部署、数据库角色和迁移顺序见 [P1 部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md) 与 [运行合同](../../panghu_agent/ppt_service/deploy/k8s/CONTRACT.md)。

## 配置归属

敏感值由 Vault 管理，映射集中在 [ppt-service-externalsecret.yaml](ppt-service-externalsecret.yaml)。非敏感 Casdoor issuer、client ID、回调域名、代理规则集中在 [OAuth 配置](../../oauth/k8s/ppt-proxy-configmap.yaml) 和 [配置说明](../../oauth/k8s/PPT.md)。允许访问的精确邮箱白名单单独放在 [ppt-owner-configmap.yaml](../../oauth/k8s/ppt-owner-configmap.yaml) 的 `ppt-owner.data.emails`，每行一个邮箱，不需配置 `sub`，也不放入 Vault；公开站点固定为 `https://ppt.panghuer.top`。Cloudflare 配置见 [Cloudflare 说明](../../cloudflare-tunnel/PPT.md)，frpc/VPS Nginx 转发见 [VPS 说明](../../vps/PPT.md)、[frpc 路由](../../vps/k8s/routes/ppt-service.toml) 和 [Nginx 模板](../../vps/nginx/ppt-service.conf.template)。业务部署只引用这些配置与下表 Secret 的明确键，不从公共服务目录复制密钥，不用 `envFrom` 扩散凭据。模型路由属于 `llm-service/`；本次不添加模型别名或调用方。Casdoor 后台、Cloudflare 和实际部署由用户配置，本轮不索取或读取真实 client、白名单用户身份或凭据。

## 路径和消费者

| Vault CLI 路径 | Vault 字段 | Kubernetes Secret / 键 | 唯一消费者 |
| --- | --- | --- | --- |
| `secret/ppt-service/test/oidc` | `CLIENT_SECRET`、`COOKIE_SECRET` | `ppt-oidc` / `client-secret`、`cookie-secret` | `ppt-site` Pod 的 `oauth2-proxy` 容器 |
| `secret/ppt-service/test/database-runtime` | `DATABASE_URL` | `ppt-database-runtime` / `DATABASE_URL` | `ppt-site` Pod 的 `site` 容器 |
| `secret/ppt-service/test/database-migrator` | `DATABASE_URL` | `ppt-database-migrator` / `DATABASE_URL` | 显式迁移 Job |
| `secret/ppt-service/test/postgres-bootstrap` | `POSTGRES_PASSWORD` | `ppt-postgres-bootstrap` / `POSTGRES_PASSWORD` | 新建的独立 PostgreSQL 容器 |

这四个 Secret 都位于 `ppt-service-test`，每个由同名 ExternalSecret 以 `creationPolicy: Owner` 管理。清单没有 Namespace、Secret 明文、`dataFrom.extract` 或模型供应商凭据。首次使用前检查同名 Secret 的 owner，避免接管其他部署的对象。尚未准备齐全的路径或空值不能当作已配置完成。

Vault CLI 使用不含 `data/` 的路径；ExternalSecret 的 `remoteRef.key` 使用仓库约定的 `secret/data/...`。沿用现有 `ClusterSecretStore/vault-backend`，它的服务账号负责读 Vault，应用和迁移 Job 不需要 Vault token 或 Kubernetes API token。每个静态 `remoteRef` 只读取表中的字段；公共 ClusterSecretStore 的 ESO 管理身份本身不是 namespace 级凭据隔离，不能把容器之间的投射范围描述为 Vault ACL 的强隔离。若以后收窄 ESO policy，必须保留这四个数据路径所需的 read 权限并另行验证同步。

## 凭据准备

标准服务器流程在 `panghu_agent/ppt_service` 执行 `bash deploy.sh --prepare`：先准备 `postgres-bootstrap` 路径即可同步初始化 Secret 并启动独立 PostgreSQL，不要求 client ID 或站点镜像。其余三个路径尚未 Ready 不妨碍此阶段。首次完整部署前准备全部四条凭据；runtime/migrator URL 使用各自计划的新角色密码，随后 `bash deploy.sh --init-db` 从这两个专用 Secret 在内存解析 URL，经新 PG 的本地管理通道创建全新 `ppt_migrator`、`ppt_runtime` 和 `ppt_service` 并设置密码。检测到任一角色或库已存在、或部分初始化状态时拒绝，不覆盖或自动修复；后续部署不再传 `--init-db`。

ExternalSecret 仍然只同步字符串，数据库变更来自部署者显式选择的初始化步骤；Secret Ready 不代表角色或数据库已存在。原人工 SQL 流程保留为维护/恢复参考，不与脚本初始化重复执行。完整命令与新空 CephFS `state` 的人工准备见 [服务器部署说明](../../panghu_agent/ppt_service/deploy/k8s/README.md#服务器标准入口)。

两份应用 URL 都必须使用已安装的 psycopg 驱动和独立数据库地址：

```text
postgresql+psycopg://ppt_runtime:<URL编码后的密码>@ppt-postgres.ppt-service-test.svc.cluster.local:5432/ppt_service
postgresql+psycopg://ppt_migrator:<URL编码后的密码>@ppt-postgres.ppt-service-test.svc.cluster.local:5432/ppt_service
```

密码中的保留字符需要 URL 编码。把完整 URL 存入各自 `DATABASE_URL`，不在 ESO 模板里直接拼接未编码密码。`POSTGRES_USER=ppt_bootstrap`、`POSTGRES_DB=ppt_test` 仅用于新 PostgreSQL 的初始化/维护；不得把 bootstrap 登录提供给站点、Worker 或迁移 Job，不复用现有 `data/postgres` 的 appuser 或凭据。数据库数据目录已有内容时，修改 `POSTGRES_PASSWORD` 环境变量不会自动改变库内角色密码。

OIDC 使用专属 PPT Casdoor 应用。其公开 client ID 同时用于代理 client ID 和站点受众校验，由 OAuth 配置集中管理；这里仅保存该应用的 client secret。Cookie secret 由管理端生成独立随机密钥，需满足实际 oauth2-proxy v7.8.0 的解码后密钥长度要求，例如 32 个随机字节的 base64 编码；不复用其他站点的 cookie secret。issuer、回调地址、允许邮箱不属于此 Secret。JWT 的稳定 `sub` 由应用读取，用于与 issuer 一起绑定项目归属，无需管理员录入名单。

经认证的管理员可从 Git 工作区之外的 0600 JSON 文件写入**新路径**，避免在命令行参数、终端或日志里出现值：

```bash
vault kv put secret/ppt-service/test/oidc @/secure/ppt-test-oidc.json
vault kv put secret/ppt-service/test/database-runtime @/secure/ppt-test-database-runtime.json
vault kv put secret/ppt-service/test/database-migrator @/secure/ppt-test-database-migrator.json
vault kv put secret/ppt-service/test/postgres-bootstrap @/secure/ppt-test-postgres-bootstrap.json
```

每份 JSON 的字段严格对应表格。此命令示例不是本次执行记录；已存在路径做部分轮换时使用 `kv patch`，不得用遗漏字段的 `kv put` 覆盖整个记录。管理端不应通过输出真实 Secret、Pod 环境、数据库 URL 或 Vault 记录来检查结果。

## 启用和轮换

`deploy.sh --prepare` 会在创建 Namespace 后应用本清单并主动同步初始化 Secret；人工准备时，Namespace 已创建且 bootstrap Vault 路径已准备后，也可先应用整份清单。未准备的其他路径暂时显示未同步，随后补齐；启动 PostgreSQL 只需要 bootstrap Secret Ready，运行迁移需要 migrator Secret 与实际角色就绪，启动网站需要 runtime 和 OIDC Secret 以及全部前置条件就绪。可以只检查同步状态：

```bash
kubectl -n ppt-service-test get externalsecret \
  ppt-oidc ppt-database-runtime ppt-database-migrator ppt-postgres-bootstrap
kubectl -n ppt-service-test describe secret ppt-oidc
kubectl -n ppt-service-test describe secret ppt-database-runtime
kubectl -n ppt-service-test describe secret ppt-database-migrator
kubectl -n ppt-service-test describe secret ppt-postgres-bootstrap
```

清单的定时刷新间隔为1小时。初次建库后补齐 runtime/migrator 或 OIDC Vault 路径时，可先主动触发对应 ExternalSecret 同步，再等待 Ready：

```bash
kubectl -n ppt-service-test annotate externalsecret \
  ppt-database-runtime ppt-database-migrator ppt-oidc \
  force-sync="$(date +%s)" --overwrite
```

`describe secret` 只用于核对键名、字节数和 owner，不使用 `-o yaml` 或解码输出。ESO 同步更新不刷新既有容器的环境变量；OIDC 密钥轮换后需按部署流程重启该测试站点，cookie secret 改动会使现有会话失效。数据库密码轮换需先协调库内密码与 Vault 值，再仅重启对应消费者；不可用重启 PostgreSQL 代替数据库密码变更。新的迁移 Job 获取最新值，不为刷新凭据重跑已成功的迁移。

## 模型授权边界

本次 P2 网站登录和公共配置不启用 Pi 模型执行，不申请 `LLM_TOKEN_PPT_*`，不创建 `llm-token` Secret。站点、迁移、PostgreSQL 和 Worker 均不接收供应商 key 或网关长期 caller token。Casdoor client secret 仅给 OAuth sidecar，bootstrap 登录仅给 PostgreSQL；站点仅接收自己的 runtime 数据库登录，迁移仅接收 migrator 登录，Worker 不接收数据库凭据。

已有 Pi 部署交接要求长期上游凭据只给可信任务代理，Worker 只得绑定 project/job/attempt/fencing/phase、期限与预算的任务 token；撤销任务必须中断模型流。公共 `llm-trusted` 路由的存在不能代替这层任务授权。

当前 `worker/model_proxy.py` 的 `ProxyConfig` 强制 HTTPS 上游，默认使用 `https://custom-llm-proxy.panghuer.top/v1` 和 Responses。集群内 `http://llm-service.llm.svc.cluster.local/v1` 无法通过该现有校验。以后接入网关必须先确认可信代理的实际部署合同，验证受控 HTTPS/网络路径、固定模型/别名语义、Responses 参数及输出预算，再单独登记 caller 和只给代理的 Secret；不能仅替换 URL、放松 HTTPS 校验或给 Worker 长期网关令牌。详见 [Pi K8s 交接](../../panghu_agent/ppt_service/K8S_DEPLOYMENT_HANDOFF.md) 和 [llm-service 调用方规范](../../llm-service/INTEGRATION.md)。
