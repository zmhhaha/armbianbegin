# Hermes Vault

沿用 vault-backend ClusterSecretStore，由 hermes-externalsecret.yaml 创建三个 Secret：

| Vault CLI 路径 | 字段 |
|---|---|
| secret/hermes/model | Hermes 模型、搜索供应商密钥对应的原生环境变量 |
| secret/hermes/oidc | OAUTH2_PROXY_CLIENT_ID、OAUTH2_PROXY_CLIENT_SECRET、OAUTH2_PROXY_COOKIE_SECRET |
| secret/hermes/hublog | token |

非敏感运行配置、issuer、域名、白名单和原生研究配置全部位于 ConfigMap，不再创建研究配置 Secret。
在已认证管理端，从 Git 之外权限为 0600 的 JSON 文件写入：

```bash
vault kv put secret/hermes/model @/secure/hermes-model.json
vault kv put secret/hermes/oidc @/secure/hermes-oidc.json
vault kv put secret/hermes/hublog @/secure/hermes-hublog.json
```

KV 命令路径不含 data/；ExternalSecret 沿用仓库 secret/data/* 约定。现有 Vault policy 需允许这些路径。
Hublog 侧用既有生成脚本创建独立 service:hermes 身份，将哈希映射合并到 secret/hublog/auth，不能覆盖其他机器人。
沿用已有 hublog-bot-auth ExternalSecret，不新建竞争对象。
Cookie 密钥使用随机 32 字节 base64。明文只挂载到 publisher，不进入模型/网页容器。
模型/OAuth envFrom 更新需要重启网页，新 Job 自动读取最新值。轮换需先登记有效新哈希再切换发布 Token。
旧版研究配置 Secret 如已存在，迁移到 ConfigMap 后由管理员清理；本次不自动删除。
