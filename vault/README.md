# Vault + External Secrets Operator — 统一配置管理

## 概述

本目录为 `armbianbegin` 项目引入了 **HashiCorp Vault** 作为集中式密钥管理平台，
配合 **External Secrets Operator (ESO)** 自动同步到 Kubernetes Secret。

### 解决的问题

- Secret 散落在各个子系统的 YAML 文件中，手动管理容易出错
- 大量明文密码和 placeholder（如 `"123456"`、`"change-me-..."`）
- 部署前需要手动编辑 YAML 文件填入真实值
- 密钥没有审计日志，不知道谁在什么时候改了哪个密钥

### 架构

```
Vault Web UI (8200端口)         ──►  集中管理所有密钥
         │
         ▼
External Secrets Operator        ──►  定期同步到 K8s Secret
         │
         ▼
各 Deployment / Pod               ──►  引用同名 Secret，无需修改
```

**关键设计**: Vault 文件夹**不修改现有工程代码**。
现有 Deployment 仍然引用 `agent-secret`、`oauth2-proxy-secret` 等同名 Secret，
ESO 自动覆盖这些 Secret 的内容，对 Pod 完全透明。

---

## 文件结构

```
vault/
├── README.md                  ← 本文件
├── deploy.sh                  ← 一键部署脚本
├── rules.migrate.md           ← Secret 迁移完整指南
│
├── helm-values/
│   ├── vault-values.yaml      ← Vault Helm 配置（单节点 + 文件存储）
│   └── eso-values.yaml        ← ESO Helm 配置（轻量单副本）
│
├── k8s/
│   ├── namespace.yaml         ← vault + external-secrets 命名空间
│   ├── pvc.yaml               ← Vault 数据持久卷（10Gi Ceph RBD）
│   ├── cluster-secret-store.yaml ← ESO → Vault 连接配置
│   └── example-external-secret.yaml ← ExternalSecret 示例（oauth/agent/email）
│
├── scripts/
│   ├── init-vault.sh          ← Vault 初始化（K8s auth, policy, role）
│   ├── unseal.sh              ← Vault 解封辅助脚本
│   └── seed-secrets.sh        ← 将现有密钥写入 Vault（交互式）
│
└── inventory/                 ← 各组件迁移追踪
    ├── 00-oauth.md
    ├── 01-email-service.md
    ├── 02-panghu-agent.md
    └── 03-gitops.md
```

---

## 快速开始

### 前提条件

- Kubernetes 集群（kubeadm v1.31.2，ARM64）
- Helm 已安装（`debian_begin.sh` 中已装）
- kubectl 可访问集群（kubeconfig: `/etc/kubernetes/super-admin.conf`）

### Step 1: 一键部署

```bash
cd /path/to/project
bash vault/deploy.sh --seed
```

该命令会:
1. ✅ 拉取 Vault 和 ESO 镜像并推送到私有仓库
2. ✅ 通过 Helm 部署 Vault（单节点）
3. ✅ 通过 Helm 部署 External Secrets Operator
4. ✅ 创建 ClusterSecretStore
5. ✅ 初始化 Vault（K8s auth、policy、role）
6. ✅ 引导输入各个组件的密钥

### Step 2: 访问 Vault UI

```bash
kubectl port-forward -n vault svc/vault 8200:8200
# 浏览器打开 http://localhost:8200
# 使用 root token 登录
```

### Step 3: 创建 ExternalSecret 开始同步

```bash
# 按示例创建 ExternalSecret
kubectl apply -f vault/k8s/example-external-secret.yaml

# 验证同步
kubectl get secret -n oauth oauth2-proxy-secret
kubectl get externalsecret -n oauth oauth2-proxy-secret
```

### ⚠️ KV v2 路径规则

Vault KV v2 引擎的路径有一个容易混淆的地方：

| 操作 | 写法 | 解释 |
|------|------|------|
| `vault kv put` **写入** | `vault kv put secret/hello key=val` | 命令**自动加** `data/` |
| `vault kv get` **读取** | `vault kv get secret/data/hello` | 必须写 `data/` |
| ExternalSecret `remoteRef.key` | `secret/data/hello` | 必须写 `data/` |

**常见错误**：`vault kv put secret/data/hello key=val` → 实际路径变成 `secret/data/data/hello`，ESO 读不到数据。

**正确用法**：
```bash
# 写入（命令自动加 data/）
kubectl exec -n vault vault-0 -- vault kv put secret/test hello=world

# 读取（手动加 data/）
kubectl exec -n vault vault-0 -- vault kv get secret/data/test
```
```

### Vault 重启后解封

```bash
bash vault/scripts/unseal.sh
```

---

## 关键路径约定

所有密钥按以下层级组织：

```
secret/data/<namespace>/<app-name>/<key>
```

| Vault 路径 | 对应 Secret |
|---|---|
| `secret/data/oauth/oauth2-proxy/*` | `oauth2-proxy-secret` |
| `secret/data/oauth/mysql/*` | Casdoor MySQL 密码 |
| `secret/data/email-service/smtp/*` | `email-secret` |
| `secret/data/research-agent/api/*` | `agent-secret` |
| `secret/data/scientific-agent/api/*` | `agent-secret` |
| `secret/data/gitops/gitea/*` | Gitea 密钥 |
| `secret/data/gitops/drone/*` | Drone 密钥 |
| `secret/data/infra/registry/*` | 镜像仓库 TLS |
| `secret/data/infra/ceph/*` | Ceph 认证 |

---

## 运维操作

### 手动写入一个密钥

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/data/oauth/oauth2-proxy \
  COOKIE_SECRET="$(openssl rand -hex 16)" \
  OIDC_CLIENT_ID="my-client" \
  OIDC_CLIENT_SECRET="my-secret"
```

### 读取一个密钥

```bash
kubectl exec -n vault vault-0 -- vault kv get secret/data/oauth/oauth2-proxy
```

### 列出所有密钥

```bash
kubectl exec -n vault vault-0 -- vault kv list secret/data/oauth/
```

### 删除一个密钥

```bash
kubectl exec -n vault vault-0 -- vault kv delete secret/data/oauth/oauth2-proxy
```

---

## 安全建议

1. **立即备份并删除本地凭证**
   ```bash
   gpg --symmetric vault-credentials/vault-init.json
   rm -rf vault-credentials/
   ```

2. **启用审计日志**
   ```bash
   kubectl exec -n vault vault-0 -- vault audit enable file \
     file_path=/vault/logs/audit.log
   ```

3. **定期轮换密钥**（在 Vault UI 中修改后，ESO 自动同步）

4. **Vault 重启后需手动解封**：使用 `vault/scripts/unseal.sh`

---

## 限制和后续优化

- **单节点非 HA**：当前资源受限，使用文件存储而非 Raft HA
- **无 TLS**：Vault 在集群内部访问，对外层由 Cloudflare Tunnel 保护
- **ConfigMap 管理**：非敏感配置手动维护，ESO（当前版本 v2.7.0）CRD 不支持 template.kind ConfigMap
- **自动解封**：未来可考虑 Transit Auto-Unseal 或 KMS 方案
