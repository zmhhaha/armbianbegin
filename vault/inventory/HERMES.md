# Hermes secrets

沿用现有 `vault-backend` ClusterSecretStore 和 External Secrets Operator，无需让 Hermes 直接连接 Vault。

| Vault CLI 路径 | 字段 | 目标 Secret |
|---|---|---|
| `secret/hermes/model` | Hermes 原生模型/搜索环境变量；全部提取 | `hermes-model` |
| `secret/hermes/oidc` | `OAUTH2_PROXY_CLIENT_ID`、`OAUTH2_PROXY_CLIENT_SECRET`、`OAUTH2_PROXY_COOKIE_SECRET` | `hermes-oidc` |
| `secret/hermes/research` | `config.yaml`：原生研究配置文本 | `hermes-research-config` |
| `secret/hermes/hublog` | `token`：独立机器人明文 Token | `hermes-hublog` |

在已登录 Vault 的管理端准备权限为 0600 的 JSON 文件，再执行以下示例；文件不进 Git，不将密钥直接写在命令参数中：

```bash
vault kv put secret/hermes/model @/secure/hermes-model.json
vault kv put secret/hermes/oidc @/secure/hermes-oidc.json
vault kv put secret/hermes/research @/secure/hermes-research.json
vault kv put secret/hermes/hublog @/secure/hermes-hublog.json
```

每个 JSON 为字段到字符串的映射。Cookie secret 使用 oauth2-proxy 支持的随机 32 字节 base64 密钥。
model 路径仅存供应商配置，不放 Hublog 或 OAuth 凭据。research 配置会进入研究 PVC，不包含私人聊天数据。

机器人在 Hublog 一侧还需要注册：按 `panghu_chat/hublog/README.md` 生成独立 `service:hermes` 身份，
把哈希条目合并到 `secret/hublog/auth` 的 `HUBLOG_SERVICE_TOKENS` JSON，保留所有已有机器人条目。
继续使用现有 `hublog-bot-auth-externalsecret.yaml` 同步该哈希映射，不另建竞争管理同一 Secret 的对象。

`panghu_chat/hermes/deploy.sh` 在显式 APPLY=true 时创建 namespace、应用本清单、等待四个 ExternalSecret Ready 后部署。
若此前手动创建过同名 Secret，先确认归属并备份，再决定交由 ESO 接管；不要强删凭据。
ClusterSecretStore 对应 Vault policy 需要读取 `secret/data/hermes/*`；如现有 policy 已覆盖该路径，不重复授予权限。

轮换：envFrom 的模型/OIDC 变量需要重启网页；新 Job 会读新值。发布器每次启动读取挂载 Token。
Hublog 先登记新哈希，等待同步，再更新明文 Token，确认后撤销旧哈希（以当前映射格式支持的方式操作）。
默认刷新周期五分钟，需考虑 kubelet Secret volume 更新延迟。本次未写入 Vault 或生成实际凭据。
