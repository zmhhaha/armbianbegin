# DSH Vault

沿用 `vault-backend` ClusterSecretStore，由 `dsh-externalsecret.yaml` 创建两个 Secret：

| Vault CLI 路径 | 字段 | 目标 Secret | 挂载位置 |
|---|---|---|---|
| `secret/dsh/model` | DSH 模型/搜索供应商密钥对应的原生环境变量；全部提取 | `dsh-model` | **仅** web 容器的 `envFrom` |
| `secret/dsh/oidc` | `OAUTH2_PROXY_CLIENT_ID`、`OAUTH2_PROXY_CLIENT_SECRET`、`OAUTH2_PROXY_COOKIE_SECRET` | `dsh-oidc` | **仅** oauth2-proxy 容器 |

非敏感配置（模型端点与 ID、Cordis 策略覆盖、域名、工具白名单、插件静态许可清单、资源默认值）全部放 ConfigMap，不进 Vault。

在已认证管理端，从 Git 之外权限为 0600 的 JSON 文件写入：

```bash
vault kv put secret/dsh/model @/secure/dsh-model.json
vault kv put secret/dsh/oidc @/secure/dsh-oidc.json
```

KV 命令路径不含 `data/`；ExternalSecret 沿用仓库 `secret/data/*` 约定。现有 Vault policy 需允许这两个路径。

## 尚未创建的路径

`secret/dsh/runner`（项目作用域的传输凭据）**暂未创建**。原因：传输方式（官方 SSH provider 还是自定义 provider）尚未确定，凭据的字段形状未定，提前建一个字段未知的 Vault 路径会让部署者无从填写。等 `panghu_chat/dsh/plugins/runner/` 的结论出来后再补 `dsh-runner` ExternalSecret 与本文档条目。

同理，`DSH_HOME/.credentials.yaml` 里的浏览器会话签名授权是 DSH **原生生成**的持久运行时密钥，**不由 Vault 管理**。它的备份必须加密并限制访问；如果要求所有密钥都进 Vault，需要一个凭据提供者适配器，那是额外工作。

## 轮换

- 模型与 OIDC 的 `envFrom` 更新需要重启网页：

```bash
kubectl -n dsh rollout restart deployment/dsh-web
```

- Cookie 密钥使用随机 32 字节 base64。改动 `OAUTH2_PROXY_COOKIE_SECRET` 会让所有现有会话失效。
- 凭据只挂到对应容器：模型密钥只进 web 容器，OAuth 密钥只进代理容器。**两者都不进项目容器**，项目容器的 NetworkPolicy 也不允许它访问这些服务的地址。

## 清理

旧版本遗留的、已被 ConfigMap 取代的 Secret 由管理员手工清理；本仓库的部署脚本不自动删除任何 Secret。
