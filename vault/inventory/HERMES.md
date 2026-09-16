# Hermes Vault

沿用 vault-backend ClusterSecretStore，由 hermes-externalsecret.yaml 创建三个 Secret：

| Vault CLI 路径 | 字段 |
|---|---|
| secret/hermes/model | Hermes 模型、搜索供应商密钥对应的原生环境变量 |
| secret/hermes/oidc | OAUTH2_PROXY_CLIENT_ID、OAUTH2_PROXY_CLIENT_SECRET、OAUTH2_PROXY_COOKIE_SECRET |
| secret/hermes/auth | HUBLOG_SERVICE_TOKENS，JSON 字符串，仅包含 Hermes 自己的 Token |

非敏感运行配置、issuer、域名、白名单和原生研究配置全部位于 ConfigMap，不再创建研究配置 Secret。
在已认证管理端，从 Git 之外权限为 0600 的 JSON 文件写入：

```bash
vault kv put secret/hermes/model @/secure/hermes-model.json
vault kv put secret/hermes/oidc @/secure/hermes-oidc.json
```

KV 命令路径不含 data/；ExternalSecret 沿用仓库 secret/data/* 约定。现有 Vault policy 需允许这些路径。
Hublog 侧用既有生成脚本创建独立 service:hermes 身份，将哈希映射合并到 secret/hublog/auth，不能覆盖其他机器人。
沿用已有 hublog-bot-auth ExternalSecret，不新建竞争对象。
Cookie 密钥使用随机 32 字节 base64。明文只挂载到 publisher，不进入模型/网页容器。
模型/OAuth envFrom 更新需要重启网页，新 Job 自动读取最新值。轮换需先登记有效新哈希再切换发布 Token。
旧版研究配置 Secret 如已存在，迁移到 ConfigMap 后由管理员清理；本次不自动删除。

## 独立管理机器人配置

content_agents 保留 `secret/content-agents/auth`；Hermes 单独使用 `secret/hermes/auth`。
Hermes 路径的 `HUBLOG_SERVICE_TOKENS` 字段值为以下 JSON：

```json
{"hermes":{"token":"实际生成的独立Token"}}
```

也支持字符串形式 `{"hermes":"实际Token"}` 和 content_agents 的 raw_token/service_token 别名。
Secret 以文件挂载给 publisher，不通过 envFrom 扩散到研究或网页容器。
ExternalSecret 直接读取 Hermes 自己的路径，不再读取或筛选 content_agents 的映射。
这仅是消费侧配置，Hublog 校验侧仍必须登记同一 Token 的 SHA-256 哈希。
使用现有脚本生成，输出含敏感信息，只在受保护的管理终端操作：

```bash
bash panghu_chat/hublog/scripts/generate-hermes-token.sh
```

把 SERVICE_TOKEN 写入上述 envelope，将输出的 hermes 哈希条目合并到
`secret/hublog/auth` 的 HUBLOG_SERVICE_TOKENS，保留所有已有条目。
若已将 Hermes Token 写入 content-agents/auth，将同一个 Token 复制到 secret/hermes/auth，无需重新生成或改变 Hublog 哈希。
确认新 Secret 同步成功后，仅移除 content-agents/auth 中多余的 hermes 条目，保留其他机器人；不要删除 Hublog 校验侧的 hermes 哈希。
这次发布器 JSON 格式不变，只需应用新版 ExternalSecret。旧 Vault 路径不会自动删除。

```bash
kubectl apply -f vault/inventory/hermes-externalsecret.yaml
kubectl -n hermes annotate externalsecret hermes-hublog force-sync="$(date +%s)" --overwrite
kubectl -n hermes wait --for=condition=Ready externalsecret/hermes-hublog --timeout=180s
```

Ready 表示同步完成，仍需确认 Hermes 映射确有非空 hermes 条目；缺失条目时发布器会拒绝发布。
