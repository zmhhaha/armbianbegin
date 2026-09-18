# DSH Vault

沿用 `vault-backend` ClusterSecretStore，由 `dsh-externalsecret.yaml` 创建四个 Secret：

| Vault CLI 路径 | 字段 | 目标 Secret | 挂载位置 |
|---|---|---|---|
| `secret/dsh/model` | DSH 模型/搜索供应商密钥对应的原生环境变量；全部提取 | `dsh-model` | **仅** web 容器的 `envFrom` |
| `secret/dsh/oidc` | `OAUTH2_PROXY_CLIENT_ID`、`OAUTH2_PROXY_CLIENT_SECRET`、`OAUTH2_PROXY_COOKIE_SECRET` | `dsh-oidc` | **仅** oauth2-proxy 容器 |
| `secret/dsh/ssh` | `id_ed25519`、`id_ed25519.pub`、`ssh_host_ed25519_key`、`ssh_host_ed25519_key.pub`、`known_hosts` | `dsh-ssh-client`（`dsh` 命名空间）<br>`dsh-ssh-host`（`dsh-runners` 命名空间） | 私钥按侧拆分，见下 |

非敏感配置（模型端点与 ID、Cordis 策略覆盖、域名、工具白名单、插件静态许可清单、资源默认值）全部放 ConfigMap，不进 Vault。

在已认证管理端，从 Git 之外权限为 0600 的 JSON 文件写入：

```bash
vault kv put secret/dsh/model @/secure/dsh-model.json
vault kv put secret/dsh/oidc @/secure/dsh-oidc.json
```

KV 命令路径不含 `data/`；ExternalSecret 沿用仓库 `secret/data/*` 约定。现有 Vault policy 需允许这三个路径。

## SSH 传输密钥对

一对 ed25519 密钥承载网页到项目容器的传输。**两半都从同一个 Vault 路径读**，但拆成两个 ExternalSecret，按"哪一侧可以持有"划分：

| Secret | 内容 | 谁能读 |
|---|---|---|
| `dsh-ssh-client`（ns `dsh`） | `id_ed25519`、`known_hosts` | 仅网页 Pod |
| `dsh-ssh-host`（ns `dsh-runners`） | `ssh_host_ed25519_key`、`.pub`、`authorized_keys` | 仅项目容器 |

`authorized_keys` 是 `id_ed25519.pub` 的重命名映射（`secretKey` + `remoteRef.property`），所以信任关系在 Vault 里只写一次，两边不可能漂移。**不要**把客户端私钥也放进 `dsh-runners`，也不要把主机私钥放进 `dsh`——那正是这套拆分要避免的。

生成与写入（全部在 Git 之外）：

```bash
ssh-keygen -t ed25519 -N '' -C dsh-client -f /secure/dsh-client
ssh-keygen -t ed25519 -N '' -C dsh-host   -f /secure/dsh-host

# known_hosts 固定项目容器的主机密钥。别名 dsh-runner-<project> 由
# config/ssh_config 展开成 <别名>.dsh-runners.svc.cluster.local，所以这份
# 可以在项目容器启动之前就生成好。
printf '[dsh-runner-<project>.dsh-runners.svc.cluster.local]:2222 %s\n' \
  "$(cut -d' ' -f1,2 /secure/dsh-host.pub)" > /secure/known_hosts

kubectl exec -n vault vault-0 -- vault kv put secret/dsh/ssh \
  id_ed25519=@/secure/dsh-client \
  id_ed25519.pub=@/secure/dsh-client.pub \
  ssh_host_ed25519_key=@/secure/dsh-host \
  ssh_host_ed25519_key.pub=@/secure/dsh-host.pub \
  known_hosts=@/secure/known_hosts
```

`dsh-ssh` 要求严格主机密钥校验，所以**换掉主机密钥就必须同时换 `known_hosts`**，否则连接会被拒——这是设计上的失败即停，不是故障。

## 不进 Vault 的密钥

`DSH_HOME/.credentials.yaml` 里的浏览器会话签名授权是 DSH **原生生成**的持久运行时密钥，**不由 Vault 管理**。它的备份必须加密并限制访问；如果要求所有密钥都进 Vault，需要一个凭据提供者适配器，那是额外工作。

`DSH_SSH_HELPER_HASH` 也不是密钥，但同样不进 Git：它是 runner 镜像里 helper 的摘要，由 `build.sh` 从镜像读回写进 `rendered/helper.sha256`，`deploy.sh` 再注入 `dsh-ssh-runtime` ConfigMap。

## 轮换

- 模型与 OIDC 的 `envFrom` 更新需要重启网页：

```bash
kubectl -n dsh rollout restart deployment/dsh-web
```

- Cookie 密钥使用随机 32 字节 base64。改动 `OAUTH2_PROXY_COOKIE_SECRET` 会让所有现有会话失效。
- 凭据只挂到对应容器：模型密钥只进 web 容器，OAuth 密钥只进代理容器。**两者都不进项目容器**，项目容器的 NetworkPolicy 也不允许它访问这些服务的地址。
- **SSH 密钥对**：轮换要两边同时做，否则网页侧会连不上，或者更糟——用旧密钥继续连。顺序是：先在 Vault 写入新的 `secret/dsh/ssh`（含配套的 `known_hosts`）→ 重启两个 ExternalSecret → 重启项目容器（重新落位主机密钥）→ 重启网页。中途连不上是预期的，不要用放宽校验来绕过。

## 清理

旧版本遗留的、已被 ConfigMap 取代的 Secret 由管理员手工清理；本仓库的部署脚本不自动删除任何 Secret。
