# Secret 迁移规则和指南

本文件列出了项目中的哪些 Secret/ConfigMap 需要迁移到 Vault，
以及迁移的优先级、步骤和方法。

---

## 迁移优先级

| 优先级 | 组件 | 原因 |
|--------|------|------|
| **P0** | OAuth (oauth2-proxy) | 明文写有 placeholder，影响认证安全 |
| **P0** | Panghu Agent | 包含真实 API Key，需加密存储 |
| **P0** | Email Service | SMTP 密码暴露 |
| **P1** | Gitea / Drone CI | CI/CD 系统密钥 |
| **P1** | Hive / MySQL | 数据库密码明文硬编码 |
| **P2** | Ceph | 存储系统认证 |
| **P2** | 私有镜像仓库 | TLS 证书 |
| **P3** | 大数据组件 ConfigMap | 非敏感配置，手动维护 |

---

## 详细清单

### OAuth 认证

| 项目 | 路径 | 当前值 |
|------|------|--------|
| `COOKIE_SECRET` | `oauth/k8s/secret.yaml` | `change-me-generate-with-openssl-rand-base64-32` |
| `OIDC_CLIENT_ID` | `oauth/k8s/secret.yaml` | `oauth2-proxy-client-id` |
| `OIDC_CLIENT_SECRET` | `oauth/k8s/secret.yaml` | `oauth2-proxy-client-secret` |
| `OIDC_ISSUER_URL` | `oauth/k8s/secret.yaml` | `https://auth.panghuer.top` |
| `ALLOWED_DOMAINS` | `oauth/k8s/secret.yaml` | `*` |
| Casdoor DB 密码 | `oauth/k8s/mysql.yaml` | `casdoor123` |

**Vault 路径**: `secret/data/oauth/oauth2-proxy/*`, `secret/data/oauth/mysql/*`

**迁移方法**:
1. 从 Vault UI 或 `seed-secrets.sh` 写入真实值
2. 在 `oauth/k8s/` 下创建对应的 `ExternalSecret.yaml`
3. 验证 `kubectl get secret -n oauth oauth2-proxy-secret`

---

### Panghu Agent

| 项目 | 路径 | 当前值 |
|------|------|--------|
| `OPENAI_API_KEY` | `panghu_agent/k8s/secret.yaml` | `sk-your-api-key-here` |
| `CUSTOM_API_KEY` | `panghu_agent/k8s/secret.yaml` | `sk-your-api-key-here` |
| `PROVIDER` | `panghu_agent/k8s/configmap.yaml`（手动维护） | `custom` |
| `CUSTOM_API_BASE` | `panghu_agent/k8s/configmap.yaml`（手动维护） | `http://0.0.0.0` |
| `CUSTOM_MODEL` | `panghu_agent/k8s/configmap.yaml`（手动维护） | `deepseek-v4-pro` |

**Vault 路径**: `secret/data/research-agent/api/*`, `secret/data/scientific-agent/api/*`

**注意**: 有 2 个 namespace（`research-agent`, `scientific-agent`），需分别处理。

---

### Email Service

| 项目 | 路径 | 当前值 |
|------|------|--------|
| `SMTP_FROM` | `email-service/k8s-deployment.yaml` | `your-email@qq.com` |
| `SMTP_USER` | `email-service/k8s-deployment.yaml` | `your-email@qq.com` |
| `SMTP_PASS` | `email-service/k8s-deployment.yaml` | `your-smtp-auth-code` |

**Vault 路径**: `secret/data/email-service/smtp/*`

---

### Gitea / Drone CI

| 项目 | 路径 | 当前值 |
|------|------|--------|
| `DRONE_GITEA_CLIENT_SECRET` | `gitea_base/drone-env.yaml` | 明文 `gto_vhnq34...` |
| `DRONE_RPC_SECRET` | `gitea_base/drone-env.yaml` | 明文 `5298dbe4c4...` |
| Gitea 密钥 | `gitea_base/gitea-env.yaml` | 需查看 |

**Vault 路径**: `secret/data/gitops/gitea/*`, `secret/data/gitops/drone/*`

---

### Hive / MySQL

| 项目 | 路径 | 当前值 |
|------|------|--------|
| MySQL root 密码 | `hive_base/mysql-statefulset.yaml` | `123456` |
| MySQL database | `hive_base/mysql-statefulset.yaml` | `hive_metastore` |
| MySQL user | `hive_base/mysql-statefulset.yaml` | `hadoop` |
| MySQL 密码 | `hive_base/mysql-statefulset.yaml` | `1234` |

**Vault 路径**: `secret/data/hive/mysql/*`

---

### Ceph

| 项目 | 路径 | 当前值 |
|------|------|--------|
| `userID` + `userKey` | `ceph/ceph-secret.yaml` | 由 `ceph auth get-key` 生成 |

**Vault 路径**: `secret/data/infra/ceph/*`

---

### 私有镜像仓库 TLS

| 项目 | 路径 | 当前值 |
|------|------|--------|
| TLS cert/key | `debian_begin.sh` 中创建 | 自签名证书 |

**Vault 路径**: `secret/data/infra/registry/*`

---

## 非敏感 ConfigMap（手动维护，不走 ESO 管理）

以下为非敏感配置，手动维护，不走 Vault + ESO 管理，原因见 `wiki/deployment-guide.md` 问题 8。

- `oauth/k8s/casdoor-configmap.yaml` — Casdoor 配置（URL、DB 连接等）
- `oauth/k8s/proxy-configmap.yaml` — oauth2-proxy 配置
- `email-service/k8s-deployment.yaml` — 部分 SMTP 配置
- `panghu_agent/k8s/configmap.yaml` — Provider/Model 配置
- Hadoop/HBase/Hive/ZK ConfigMaps — 集群地址等

---

## 迁移流程

每个组件的迁移遵循 4 步流程：

```
Step 1: 写入 Vault ──── Step 2: 创建 ExternalSecret ──── Step 3: 验证 ──── Step 4: 清理
```

### Step 1: 写入 Vault
```
# 手动方式（推荐首次使用）
kubectl exec -n vault vault-0 -- vault kv put secret/data/oauth/oauth2-proxy \
  COOKIE_SECRET="$(openssl rand -base64 32)" \
  OIDC_CLIENT_ID="xxxx" \
  OIDC_CLIENT_SECRET="xxxx"

# 或使用种子脚本（交互式）
bash vault/scripts/seed-secrets.sh
```

### Step 2: 创建 ExternalSecret
在对应组件的 `k8s/` 目录下创建 `external-secret.yaml`，参考 `vault/k8s/example-external-secret.yaml`。

### Step 3: 验证
```
kubectl get externalsecret -n <ns> <name>
kubectl get secret -n <ns> <secret-name> -o yaml
# 确认 data 字段已填充（base64 值）
```

### Step 4: 清理
从 YAML 文件中移除明文字段，替换为注释说明 "由 ESO 从 Vault 同步"。

---

## ⚠️  安全提醒

1. **永远不要将真实密钥提交到 Git**。所有 placeholder 值和示例值已通过 `.gitignore` 或注释标记
2. Vault 初始化后，root token 和 unseal keys **必须离线存储**（GPG 加密后保存）
3. 建议设置 Vault 审计日志: `vault audit enable file file_path=/vault/logs/audit.log`
4. Vault 重启后需要重新解封，建议设置自动化解封脚本
