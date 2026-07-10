# OAuth — Secret 迁移追踪

## 状态: 🟡 进行中

## 组件信息

| 属性 | 值 |
|------|-----|
| **命名空间** | `oauth` |
| **Secret 名称** | `oauth2-proxy-secret` |
| **Vault 路径** | `secret/data/oauth/oauth2-proxy` |
| **现有文件** | `oauth/k8s/secret.yaml` |

## 需要迁移的密钥

| 密钥 | 写入 Vault | ExternalSecret | 原文件清理 |
|------|-----------|----------------|-----------|
| `COOKIE_SECRET` | ⏳ | ✅ (文件已就绪) | ⏳ |
| `OIDC_CLIENT_ID` | ⏳ | ✅ | ⏳ |
| `OIDC_CLIENT_SECRET` | ⏳ | ✅ | ⏳ |
| `OIDC_ISSUER_URL` | ✅ | ✅ | ⏳ |
| `ALLOWED_DOMAINS` | ✅ | ✅ | ⏳ |

## 迁移步骤

- [ ] Step 1: 写入真实值到 Vault
- [ ] Step 2: apply ExternalSecret
- [ ] Step 3: 验证同步
- [ ] Step 4: 清理 `oauth/k8s/secret.yaml` 中的明文

## 备注

- research-agent 和 scientific-agent 两个 oauth2-proxy 实例共用同一个 Secret
- ExternalSecret 位于 `vault/inventory/oauth-externalsecret.yaml`
