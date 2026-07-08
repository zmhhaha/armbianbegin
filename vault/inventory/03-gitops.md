# GitOps (Gitea + Drone CI) — Secret 迁移追踪

## 状态: 🔴 未开始

## 组件信息

### Gitea

| 属性 | 值 |
|------|-----|
| **命名空间** | `gitops` |
| **现行配置** | `gitea_base/gitea-env.yaml`（ConfigMap） |
| **Vault 路径** | `secret/data/gitops/gitea` |

### Drone CI

| 属性 | 值 |
|------|-----|
| **命名空间** | `gitops` |
| **现行配置** | `gitea_base/drone-env.yaml`（ConfigMap，含明文密码） |
| **Vault 路径** | `secret/data/gitops/drone` |

## 需要迁移的密钥

| 密钥 | 迁移到 Vault | ExternalSecret | 原文件清理 |
|------|-------------|----------------|-----------|
| `DRONE_GITEA_CLIENT_SECRET` | ⏳ | ⏳ | ⏳ |
| `DRONE_RPC_SECRET` | ⏳ | ⏳ | ⏳ |
| `GITEA_SECRET_KEY` | ⏳ | ⏳ | ⏳ |
| `GITEA_INTERNAL_TOKEN` | ⏳ | ⏳ | ⏳ |
| `GITEA_OAUTH2_JWT_SECRET` | ⏳ | ⏳ | ⏳ |

## 迁移步骤

- [ ] Step 1: 在 Vault 中写入 Drone + Gitea 密钥
- [ ] Step 2: 创建 ExternalSecret，目标为 `gitops` 命名空间
- [ ] Step 3: 需要修改 Deployment 引用方式（当前是 `envFrom.configMapRef` → 需改为 `envFrom.secretRef` 或 `valueFrom.secretKeyRef`）
- [ ] Step 4: 验证同步并清理明文

## 备注

- ⚠️ 当前 Gitea 和 Drone 的密钥在 ConfigMap（`gitea-env.yaml`, `drone-env.yaml`）而非 Secret 中
- 迁移可能需要修改 Deployment 的引用方式（从 `envFrom` ConfigMap 改为引用新创建的 Secret）
- 此组件迁移会更复杂，建议在 P0/P1 组件完成后进行
