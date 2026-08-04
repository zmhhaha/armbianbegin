# Redis — 通用缓存/KV 存储服务

标准 Redis 7，部署在 K8s `data` 命名空间。AOF 持久化，密码由 Vault 统一管理，不落明文。

## 目录结构

```
redis/
├── k8s.yaml       # 部署清单（Namespace + ConfigMap + StatefulSet + Service）
├── deploy.sh      # 一键部署脚本
└── README.md      # 本文档
```

## 连接信息

| 项 | 值 |
|---|---|
| 集群内地址 | `redis.data.svc.cluster.local:6379` |
| 集群外地址 | `<任意节点IP>:30379`（NodePort） |
| 数据库 | 默认 0，最多 16 个库（0-15） |
| 密码 | Vault 管理，见下方「获取密码」 |

## 部署

```bash
# 1. 先写入 Vault 密码（只需一次）
kubectl exec -n vault vault-0 -- vault kv put secret/redis/app \
  REDIS_PASSWORD="你的密码"

# 2. 一键部署（自动 apply ExternalSecret + k8s.yaml）
cd redis
./deploy.sh
```

## 获取密码

密码在 Vault 中，通过 ExternalSecret 同步到 K8s Secret：

```bash
kubectl get secret -n data redis-secret \
  -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d
```

修改密码后需滚动重启生效：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/redis/app \
  REDIS_PASSWORD="新密码"
kubectl rollout restart sts/redis -n data
```

> **注意**：Redis 的密码在容器启动时由 initContainer 写入 `redis.conf`，改 Vault 密码后**必须** `rollout restart` 才会重写配置。

---

## 服务如何连接

### 方案 A：集群内 K8s 服务（推荐）

通过 ExternalSecret 把连接串注入 Deployment 环境变量。

**1. 写 Vault**（连接串含密码）：

```bash
kubectl exec -n vault vault-0 -- vault kv put secret/<你的服务>/redis \
  REDIS_URL="redis://:你的密码@redis.data.svc.cluster.local:6379/0"
```

> 注意：Redis URL 密码要放在 `redis://:` 和 `@` 之间，格式为 `redis://:<password>@<host>:<port>/<db>`。

**2. 创建 ExternalSecret**（参考 [../vault/inventory/redis-externalsecret.yaml](../vault/inventory/redis-externalsecret.yaml)）：

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: redis-secret
  namespace: <你的命名空间>
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: redis-secret
    creationPolicy: Owner
  data:
    - secretKey: url
      remoteRef:
        key: secret/data/<你的服务>/redis
        property: REDIS_URL
```

**3. Deployment 引用**：

```yaml
env:
- name: REDIS_URL
  valueFrom:
    secretKeyRef:
      name: redis-secret
      key: url
```

### 方案 B：直接用密码（开发/临时）

```bash
# 集群内
redis-cli -h redis.data.svc.cluster.local -a '<密码>'

# 集群外（任意节点）
redis-cli -h <任意节点IP> -p 30379 -a '<密码>'
```

### 连接串格式

```
redis://:<密码>@<主机>:<端口>/<数据库编号>
```

各语言的连接方式：

| 语言/框架 | 示例 |
|---|---|
| redis-cli | `redis-cli -h redis.data.svc.cluster.local -a '<密码>'` |
| Python (redis-py) | `redis://:密码@redis.data.svc.cluster.local:6379/0` |
| Node.js (ioredis) | `redis://:密码@redis.data.svc.cluster.local:6379/0` |
| Node.js (node-redis) | `redis://:密码@redis.data.svc.cluster.local:6379/0` |
| Java (Lettuce) | `redis://:密码@redis.data.svc.cluster.local:6379/0` |
| Python (redis URL) | `redis://:密码@redis.data.svc.cluster.local:6379/0` |

Python 客户端示例：

```python
import redis

r = redis.Redis(
    host="redis.data.svc.cluster.local",
    port=6379,
    password="<密码>",
    db=0,
    decode_responses=True,
)

r.set("key", "value")
print(r.get("key"))
```

---

## 配置说明（来自 redis.conf）

| 配置 | 值 | 说明 |
|---|---|---|
| `maxmemory` | 1gb | 内存上限 |
| `maxmemory-policy` | `allkeys-lru` | 超限淘汰策略：全键 LRU |
| `appendonly` | yes | AOF 持久化 |
| `appendfsync` | everysec | 每秒刷盘 |
| `databases` | 16 | 16 个逻辑库（0-15） |
| `save` | 900 1 / 300 10 / 60 10000 | RDB 快照策略（与 AOF 并存） |

## 常用运维

```bash
# 查看状态
kubectl get pods -n data -l app=redis

# 查看日志
kubectl logs -n data -l app=redis --tail=50

# 进入 redis-cli
kubectl exec -n data deploy/redis -- redis-cli -a '<密码>' ping
# → PONG

# 查看 info
kubectl exec -n data deploy/redis -- redis-cli -a '<密码>' info memory

# 查看 key
kubectl exec -n data deploy/redis -- redis-cli -a '<密码>' keys '*'

# 清空当前库
kubectl exec -n data deploy/redis -- redis-cli -a '<密码>' flushdb

# 备份（BGSAVE 生成 RDB）
kubectl exec -n data deploy/redis -- redis-cli -a '<密码>' bgsave
```

## 存储

- AOF + RDB 持久化文件存在 Ceph RBD 块存储（`storageClassName: ceph-rbd`），5Gi 动态 PVC
- StatefulSet `volumeClaimTemplates` 自动创建，Pod 重建数据不丢

## 常见问题

**Q: pod 一直 CrashLoopBackOff？**
查看 initContainer 日志：
```bash
kubectl logs -n data redis-0 -c init-config
```
常见原因是 `redis-secret` 没同步（ExternalSecret 未 apply 或 Vault 没写密钥）。

**Q: 提示 `NOAUTH Authentication required`？**
连接时没带密码。所有 `redis-cli` 调用都要 `-a '<密码>'`，或在 URL 里带密码。

**Q: 外部连不上 30379？**
NodePort 需要节点防火墙放行该端口，或者直接用集群内地址。

**Q: 密码改了但连不上？**
改 Vault 密码后要 `kubectl rollout restart sts/redis -n data`（initContainer 会重写 redis.conf），且客户端要用新密码。
