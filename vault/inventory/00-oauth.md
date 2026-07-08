# OAuth — Secret 迁移追踪

## 状态: 🔴 未开始

## 组件信息

| 属性 | 值 |
|------|-----|
| **命名空间** | `oauth` |
| **Secret 名称** | `oauth2-proxy-secret` |
| **Vault 路径** | `secret/data/oauth/oauth2-proxy` |
| **现有文件** | `oauth/k8s/secret.yaml` |

## 需要迁移的密钥

| 密钥 | 迁移到 Vault | ExternalSecret | 原文件清理 |
|------|-------------|----------------|-----------|
| `COOKIE_SECRET` | ⏳ | ⏳ | ⏳ |
| `OIDC_CLIENT_ID` | ⏳ | ⏳ | ⏳ |
| `OIDC_CLIENT_SECRET` | ⏳ | ⏳ | ⏳ |
| `OIDC_ISSUER_URL` | ⏳ | ⏳ | ⏳ |
| `ALLOWED_DOMAINS` | ⏳ | ⏳ | ⏳ |

## 迁移步骤

- [ ] Step 1: 在 Vault 中写入真实值
- [ ] Step 2: 在 `oauth/k8s/` 下创建 `external-secret.yaml`
- [ ] Step 3: 应用并验证同步
- [ ] Step 4: 清理 `oauth/k8s/secret.yaml` 中的明文

## 备注

- oauth2-proxy-deployment.yaml 通过 `envFrom.secretRef` 引用此 Secret，迁移后无需修改 Deployment
- Casdoor MySQL 密码在 `oauth/k8s/mysql.yaml` 中，需单独处理
