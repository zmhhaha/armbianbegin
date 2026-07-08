# Email Service — Secret 迁移追踪

## 状态: 🔴 未开始

## 组件信息

| 属性 | 值 |
|------|-----|
| **命名空间** | `email-service` |
| **Secret 名称** | `email-secret` |
| **Vault 路径** | `secret/data/email-service/smtp` |
| **现有文件** | `email-service/k8s-deployment.yaml` |

## 需要迁移的密钥

| 密钥 | 迁移到 Vault | ExternalSecret | 原文件清理 |
|------|-------------|----------------|-----------|
| `SMTP_USER` | ⏳ | ⏳ | ⏳ |
| `SMTP_PASS` | ⏳ | ⏳ | ⏳ |
| `SMTP_FROM` | ⏳ | ⏳ | ⏳ |
| `SMTP_HOST` | ⏳ | ⏳ | ⏳ |
| `SMTP_PORT` | ⏳ | ⏳ | ⏳ |

## 迁移步骤

- [ ] Step 1: 在 Vault 中写入 SMTP 配置
- [ ] Step 2: 在 `email-service/` 下创建 `external-secret.yaml`（参考 `vault/k8s/example-external-secret.yaml` 中的 email 示例）
- [ ] Step 3: 应用并验证同步
- [ ] Step 4: 清理 `email-service/k8s-deployment.yaml` 中的明文默认值

## 备注

- Deployment 通过 `envFrom.secretRef` 引用 Secret，迁移后无需修改 Deployment
- 当前 Secret 的定义在 Deployment 文件中内联，而非独立 YAML 文件
