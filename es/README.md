# 单节点 Elasticsearch

本目录为 `armbianbegin` Kubernetes 集群部署单节点 Elasticsearch 的代码，面向虎博第一版全文搜索。部署方式采用 StatefulSet + Ceph RBD PVC，不引入 ECK，避免为单节点搜索服务增加额外 Operator 依赖。

## 默认参数

| 项目 | 默认值 |
| --- | --- |
| Elasticsearch | 8.15.3 |
| 镜像 | `arm-cluster-master:5000/elasticsearch:8.15.3` |
| K8s 命名空间 | `data` |
| 节点 | `orangepi5-max-server1` |
| 内存 | 2Gi JVM Heap，容器上限 4Gi |
| 数据卷 | Ceph RBD，30Gi |
| 集群名 | `hubo-search` |
| K8s 地址 | `elasticsearch.data.svc.cluster.local:9200` |
| 对外访问 | 不提供 NodePort，不通过公网暴露 |

当前节点总资源和已有工作负载决定了 Elasticsearch 不应调度到 4Gi 内存的 NanoPC 节点。若节点名称变化，修改 `k8s/statefulset.yaml` 的 `nodeSelector`。

## 文件说明

```text
es/
├── README.md
├── build.sh                       # 拉取 ARM64 镜像并推送到私有 Registry
├── deploy.sh                      # ExternalSecret、配置、Service 和 StatefulSet 部署
└── k8s/
    ├── configmap.yaml             # elasticsearch.yml
    ├── service.yaml               # ClusterIP + Headless Service
    └── statefulset.yaml           # 单节点 Elasticsearch

vault/inventory/
└── elasticsearch-externalsecret.yaml # Vault -> K8s 密码同步及部署说明
```

## 前置条件

- Kubernetes `data` 命名空间已经存在。
- `ceph-rbd` StorageClass 可用。
- Vault 和 External Secrets Operator 已部署。
- Vault KV v2 中存在 `secret/elasticsearch/app`，且包含 `ELASTIC_PASSWORD`。
- 节点 `orangepi5-max-server1` 可拉取私有 Registry 镜像。
- Elasticsearch ARM64 镜像已经推送到私有 Registry。

创建 Elasticsearch 密码时不要把密码提交到仓库：

```bash
ELASTIC_PASSWORD="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9_@#%+=' | head -c 24)"
kubectl exec -n vault vault-0 -- vault kv put secret/elasticsearch/app \
  ELASTIC_PASSWORD="${ELASTIC_PASSWORD}"
unset ELASTIC_PASSWORD
```

Vault 相关清单统一存放在 `vault` 目录。完整的创建、同步和验证步骤见
`vault/inventory/elasticsearch-externalsecret.yaml` 文件首部注释。注意：Vault CLI
写入 KV v2 时使用 `secret/elasticsearch/app`，ExternalSecret 读取时使用
`secret/data/elasticsearch/app`。

## 构建镜像

在可以访问外网 Registry 的 ARM64 节点上执行：

```bash
cd /root/armbianbegin/es
bash build.sh --push
```

可通过环境变量覆盖版本和目标 Registry：

```bash
ES_VERSION=8.15.3 REGISTRY=arm-cluster-master:5000 bash build.sh --push
```

## 部署

```bash
cd /root/armbianbegin/es
bash deploy.sh
```

部署脚本会：

1. 从 `vault/inventory/elasticsearch-externalsecret.yaml` 应用 ExternalSecret，并等待 `elasticsearch-secret` 同步。
2. 应用 Elasticsearch 配置和两个 Service。
3. 确保 StatefulSet 使用目标镜像。
4. 等待 Pod 就绪。
5. 使用 `elastic` Basic Auth 做集群健康检查。

可使用自定义镜像：

```bash
ES_IMAGE=arm-cluster-master:5000/elasticsearch:8.15.3 bash deploy.sh
```

## 访问和验证

集群内访问：

```bash
kubectl run es-curl --rm -i --restart=Never -n data \
  --image=curlimages/curl:8.10.1 -- \
  curl -fsS -u 'elastic:<password>' \
  'http://elasticsearch.data.svc.cluster.local:9200/_cluster/health'
```

常用检查：

```bash
kubectl get pods -n data -l app.kubernetes.io/name=elasticsearch
kubectl get pvc -n data -l app.kubernetes.io/name=elasticsearch
kubectl logs -n data elasticsearch-0 --tail=100
```

正常的单节点集群状态通常为 `yellow`，因为没有副本节点；这不是故障。虎博索引应将副本数设为 `0`：

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  }
}
```

## 配置说明

- Elasticsearch 开启 Basic Auth，密码只从 Vault/ExternalSecret 注入。
- HTTP TLS 在集群内部关闭，9200 只通过 ClusterIP 暴露；公网不开放 Elasticsearch。
- transport TLS 保留 Elasticsearch 8 的默认安全机制。
- `vm.max_map_count` 由特权 initContainer 设置为 `262144`。
- JVM Heap 固定为 2Gi，避免 Elasticsearch 自动占满节点内存。
- 使用 `action.destructive_requires_name: true` 防止无名称删除整个索引。
- 数据目录位于 Ceph RBD，删除 StatefulSet 不会自动删除 PVC。

## 虎博接入建议

虎博应用通过 Vault 同步的 `elasticsearch-secret` 获取 `ELASTIC_PASSWORD`，搜索 Worker 使用：

```text
ELASTICSEARCH_URL=http://elasticsearch.data.svc.cluster.local:9200
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=<从 Secret 注入>
```

ES 只作为可重建搜索索引，不作为动态和文章主库。发布、编辑、隐藏和删除事件必须异步更新索引，并保留全量重建脚本。

## 升级和恢复

升级时先构建并推送新镜像，再设置 `ES_VERSION`/`ES_IMAGE` 执行部署。单节点升级会有短暂不可用窗口：

```bash
ES_VERSION=8.16.0 bash build.sh --push
ES_IMAGE=arm-cluster-master:5000/elasticsearch:8.16.0 bash deploy.sh
```

当前没有自动快照策略。正式使用前应补充：

- Ceph RBD 快照或 Elasticsearch Snapshot Repository
- 索引模板和别名的重建脚本
- PostgreSQL Outbox 到 ES 的断点重放
- 失败索引的死信和人工重试
