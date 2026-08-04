# PostgreSQL — 通用数据库服务

标准 PostgreSQL 16，部署在 K8s `data` 命名空间。密码由 Vault 统一管理，不落明文。

## 目录结构

```
postgres/
├── k8s.yaml       # 部署清单（Namespace + ConfigMap + PVC + StatefulSet + Service）
├── deploy.sh      # 一键部署脚本
├── init.sql       # 初始化 SQL（扩展 + 建表示例）
└── README.md      # 本文档
```

## 连接信息

| 项 | 值 |
|---|---|
| 集群内地址 | `postgres.data.svc.cluster.local:5432` |
| 集群外地址 | `<任意节点IP>:30432`（NodePort） |
| 默认数据库 | `appdb` |
| 默认用户 | `appuser` |
| 密码 | Vault 管理，见下方「获取密码」 |

## 部署

```bash
# 1. 先写入 Vault 密码（只需一次）
kubectl exec -n vault vault-0 -- vault kv put secret/postgres/app \
  POSTGRES_PASSWORD="你的密码"

# 2. 一键部署（自动 apply ExternalSecret + k8s.yaml）
cd postgres
./deploy.sh
```

## 获取密码

密码在 Vault 中，通过 ExternalSecret 同步到 K8s Secret：

```bash
kubectl get secret -n data postgres-secret \
  -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d
```

修改密码后需滚动重启生效：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/postgres/app \
  POSTGRES_PASSWORD="新密码"
kubectl rollout restart sts/postgres -n data
```

---

## 服务如何连接

### 方案 A：集群内 K8s 服务（推荐）

通过 ExternalSecret 把连接串注入 Deployment 环境变量，密码不落明文。

**1. 写 Vault**（连接串含密码）：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/<你的服务>/db \
  DB_URL="postgresql://appuser:你的密码@postgres.data.svc.cluster.local:5432/appdb"
```

**2. 创建 ExternalSecret**（参考 [../vault/inventory/postgres-externalsecret.yaml](../vault/inventory/postgres-externalsecret.yaml)）：

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: db-secret
  namespace: <你的命名空间>
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: db-secret
    creationPolicy: Owner
  data:
    - secretKey: url
      remoteRef:
        key: secret/data/<你的服务>/db
        property: DB_URL
```

**3. Deployment 引用**：

```yaml
env:
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: db-secret
      key: url
```

### 方案 B：直接用密码（开发/临时）

```bash
# 集群内
psql -h postgres.data.svc.cluster.local -U appuser -d appdb

# 集群外（任意节点）
psql -h <任意节点IP> -p 30432 -U appuser -d appdb
# 提示输密码时粘贴 Vault 里的值
```

### 连接串格式

```
postgresql://<用户>:<密码>@<主机>:<端口>/<数据库>
```

各语言的连接串写法：

| 语言/框架 | 示例 |
|---|---|
| Node.js (pg) | `postgres://appuser:密码@postgres.data.svc.cluster.local:5432/appdb` |
| Python (psycopg2) | `postgresql://appuser:密码@postgres.data.svc.cluster.local:5432/appdb` |
| Python (SQLAlchemy) | `postgresql+psycopg2://appuser:密码@postgres.data.svc.cluster.local:5432/appdb` |
| Java (JDBC) | `jdbc:postgresql://postgres.data.svc.cluster.local:5432/appdb` |
| Drizzle (Node) | `postgresql://appuser:密码@postgres.data.svc.cluster.local:5432/appdb` |

---

## 建库

`appuser` 是普通用户，建库需要超级用户 `postgres`：

```bash
# 用 postgres 超级用户建库并授权给 appuser
kubectl exec -n data deploy/postgres -- psql -U postgres \
  -c "CREATE DATABASE school_of_one OWNER appuser;"

# 建完检查
kubectl exec -n data deploy/postgres -- psql -U appuser -d school_of_one -c '\l'
```

## 初始化扩展

```bash
kubectl exec -n data deploy/postgres -- psql -U appuser -d appdb \
  -f <(cat init.sql)   # 或直接 cp 进 pod
```

或简化（扩展装到当前库）：

```bash
kubectl exec -n data deploy/postgres -- psql -U appuser -d appdb -c \
  "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

## 常用运维

```bash
# 查看状态
kubectl get pods -n data -l app=postgres

# 查看日志
kubectl logs -n data -l app=postgres --tail=50

# 进入 psql
kubectl exec -n data deploy/postgres -- psql -U appuser -d appdb

# 备份
kubectl exec -n data deploy/postgres -- pg_dump -U appuser -d appdb > backup.sql

# 恢复
cat backup.sql | kubectl exec -n data deploy/postgres -- psql -U appuser -d appdb

# 重置密码后重启
kubectl rollout restart sts/postgres -n data
```

## 存储

- 数据存在 Ceph RBD 块存储（`storageClassName: ceph-rbd`），10Gi 动态 PVC
- StatefulSet `volumeClaimTemplates` 自动创建，Pod 重建数据不丢

## 常见问题

**Q: pod 一直 Pending？**
检查 PVC 是否 Bound：
```bash
kubectl get pvc -n data
```

**Q: 外部连不上 30432？**
NodePort 需要节点防火墙放行该端口，或者直接用集群内地址。

**Q: 密码改了但连不上？**
改 Vault 密码后要 `kubectl rollout restart sts/postgres -n data`，且服务端要用新密码。
