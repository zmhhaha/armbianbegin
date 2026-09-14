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
│   ├── unseal.sh              ← Vault 解封、CLI 登录和 ESO 恢复
│   ├── login.sh               ← 单独恢复 Vault CLI token
│   ├── fix-eso-auth.sh        ← 修复 Vault Kubernetes Auth / ESO
│   ├── seed-secrets.sh        ← 将现有密钥写入 Vault（交互式）
│   └── store-s3-credentials.sh ← 将 S3 凭据文件写入 Vault KV v2
│
└── inventory/                 ← 各组件迁移追踪
    ├── 00-oauth.md
    ├── 01-email-service.md
    ├── 02-panghu-agent.md
    ├── 03-gitops.md
    ├── elasticsearch-externalsecret.yaml ← Elasticsearch 密码同步及部署说明
    └── panghu-chat-s3-externalsecret.yaml ← 虎博 S3 凭据同步及部署说明
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
| `vault kv put` **写入** | `vault kv put secret/hello key=val` | 命令**自动加** `data/`，实际存到 `secret/data/hello` |
| `vault kv get` **读取** | `vault kv get secret/data/hello` | 必须手动写 `data/` |
| ExternalSecret `remoteRef.key` | `secret/data/hello` | 必须写 `data/` |

**常见错误**：`vault kv put secret/data/hello key=val` → 命令自动加 `data/`，实际路径变成 `secret/data/data/hello`，ESO 读不到数据。

**正确用法**：
```bash
# 写入（命令自动加 data/，所以路径不加 data/）
kubectl exec -n vault vault-0 -- vault kv put secret/test hello=world

# 读取（手动加 data/）
kubectl exec -n vault vault-0 -- vault kv get secret/data/test
```
```

### Vault 重启后解封

```bash
cd vault
bash scripts/unseal.sh --interactive
```

该脚本依次完成：

1. 隐藏输入 3 个 `unseal key` 并解封 Vault。
2. 隐藏输入 `root_token`，恢复 Vault Pod 内的 CLI 登录缓存。
3. 检查并按需修复 Kubernetes Auth 的 token reviewer JWT 和 ESO。

也可以从安全保管的初始化文件一次恢复：

```bash
bash scripts/unseal.sh --from-file /secure/path/vault-init.json
```

Vault 已解封但 CLI token 丢失或失效时，只运行：

```bash
bash scripts/login.sh --interactive
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
| `secret/data/elasticsearch/app/*` | `data/elasticsearch-secret` |
| `secret/data/panghu-chat/s3/*` | `panghu-chat/hubo-s3` |
| `secret/data/txt2img/ark/*` | txt2img-proxy 火山引擎视觉 CV AK/SK（`ARK_ACCESS_KEY` / `ARK_SECRET_KEY`） |
| `secret/data/txt2img/replicate/*` | txt2img-proxy Replicate API Key |
| `secret/data/txt2img/together/*` | txt2img-proxy Together AI API Key |
| `secret/data/txt2img/stability/*` | txt2img-proxy Stability AI API Key |
| `secret/data/txt2img/openai/*` | txt2img-proxy OpenAI API Key |

---

## 运维操作

### 手动写入一个密钥

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/oauth/oauth2-proxy \
  COOKIE_SECRET="$(openssl rand -hex 16)" \
  OIDC_CLIENT_ID="my-client" \
  OIDC_CLIENT_SECRET="my-secret"
```

### 读取一个密钥

```bash
kubectl exec -n vault vault-0 -- vault kv get secret/oauth/oauth2-proxy
```

### 列出所有密钥

```bash
kubectl exec -n vault vault-0 -- vault kv list secret/oauth/
```

### 删除一个密钥 —— ⚠️ 必须用 `metadata delete`

```bash
kubectl exec -n vault vault-0 -- vault kv metadata delete secret/oauth/oauth2-proxy
```

**`vault kv delete` 不等于删除。** 它只**软删除当前版本**，而 KV v2 默认
`max_versions: 0`（**无限保留历史版本**）。结果这三种查法**全部显示「已删除」**：

```bash
vault kv list secret/<path>/          # 仍列出该路径（元数据还在）
vault kv get  secret/<path>           # data: null（当前版本已软删）
vault kv metadata get secret/<path>   # 不看 versions 字段就看不出来
```

**只有 `vault kv get -version=N` 读得出来。** 2026-09-14 在 panghu_agent 侧清出 12 条这样的
路径，每条都还留着**当时 llm-service 正在使用**的那把 DeepSeek key —— 全部可读、可恢复。

**删完必须核实 `versions` 里没有存活条目**：

```bash
kubectl -n vault exec vault-0 -- vault kv metadata get -format=json secret/<path> \
  | python3 -c 'import json,sys; d=json.load(sys.stdin)["data"]; \
      print([v for v,i in d["versions"].items() if not i["deletion_time"] and not i["destroyed"]])'
```

输出 `[]` 才算真删干净。**不要只看 `kv list` 或 `kv get` 就判定已清理。**

---

## 清理残留（退役一个组件时）

凭据迁移完之后，下面四类东西**都要单独清**——它们是四个不同的位置，漏掉任何一个都会留下
可用的凭据或死配置：

| # | 位置 | 怎么清 |
|---|---|---|
| 1 | **仓库里的清单文件** | 删除 `<component>/k8s/*externalsecret.yaml` |
| 2 | **集群里的 ExternalSecret** | `kubectl delete externalsecret <name> -n <ns>` |
| 3 | **集群里它同步出的 Secret** | 若 ExternalSecret 是 `creationPolicy: Owner`，上一步会一并 GC；否则手动 `kubectl delete secret` |
| 4 | **Vault 里的源数据** | `vault kv metadata delete secret/<ns>/<app>`（见上，**不能用 `kv delete`**） |

### ⚠️ 第 1 步做完，不等于 2/3/4 做完了

这是本项目反复踩到的一类错误：**从仓库删掉 ExternalSecret 清单，集群里的 ExternalSecret 对象
仍然存在，而且仍在按 `refreshInterval` 持续同步。** 也就是说凭据还在被拉取、还在被使用。

2026-09-14 的两次实际案例：

- **panghu_game**：5 个 namespace 的 provider ExternalSecret 在仓库里早已删除，集群里
  却仍 `SecretSynced`，各渲染出一个只含 `DEEPSEEK_*` 的 Secret —— 共享 key 仍散在 5 个 namespace。
  `school-of-one/llm-secret` 同理（键名是小写 `deepseek-api-key`，很容易被大小写敏感的检索漏掉）。
- **panghu_agent**：12 条 Vault 路径只做了软删除，历史版本全在（见上）。

**核对方式（不信「我以为删了」）**：

```bash
# 2/3：全集群找残留
kubectl get externalsecret -A | grep -E '<component>|agent'
kubectl get secret -A | grep -E 'deepseek|openai|anthropic|api-key'

# 4：全 Vault 找带 provider 键的路径
kubectl -n vault exec vault-0 -- vault kv list secret/
```

### ConfigMap 不会自动清理

非敏感 ConfigMap 不走 ESO，也就不在任何「退役」流程里。三类会变成孤儿：

- **deploy 脚本创建、但 Deployment 并不挂载的**（例如 School of One 的
  `duel-judge-code` / `combo-judge-code` / `training-code`）—— 删了下次部署还会回来，
  要清得连脚本一起改
- **Job 跑完留下的**（例如 literature-downloader 的 `scihub-input-*`）—— 这类**没有
  `ownerReferences`**，Job 被删时不会级联清理
- **改架构后废弃的**（例如 `data/sqlite-server` —— 代码已烤进镜像，ConfigMap 是旧做法的残留）

**判断方法：ConfigMap 是否被任何工作负载的 `envFrom` / `env.valueFrom` / `volumes` 引用。**
不被引用的就是孤儿。

⚠️ 检查 CronJob 时要看对路径：pod spec 在 `.spec.jobTemplate.spec.template.spec`，
**不是** `.spec.template.spec`。按后者取会永远读不到 CronJob 的引用，
把所有被 CronJob 使用的资源误报成孤儿（本项目踩过）。

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
