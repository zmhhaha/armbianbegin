#!/bin/bash
# ============================================================
#  Redis — 通用缓存/KV 存储服务 部署
#  标准 Redis 7，StatefulSet + AOF 持久化
#  前提: ExternalSecret 已 apply 到集群（见 vault/inventory/）
#        Vault 中已写入 secret/data/redis/app 密钥
# ============================================================
set -e
cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Deploying Redis ==="

# 先确保 ExternalSecret 和 Vault 密钥就绪
echo ">>> 1. Applying ExternalSecret (Vault → K8s Secret)..."
kubectl apply ${K} -f ../vault/inventory/redis-externalsecret.yaml
sleep 3

echo ">>> 2. Applying Redis resources..."
kubectl apply ${K} -f k8s.yaml

echo ""
echo "=== Waiting for pod ready ==="
kubectl wait --for=condition=ready pod -l app=redis -n data ${K} --timeout=120s

echo ""
echo "=== Status ==="
kubectl get pods -n data ${K} -l app=redis -o wide
kubectl get externalsecret -n data ${K} redis-secret

echo ""
echo "=== Done! ==="
echo "  内部连接: redis.data.svc.cluster.local:6379"
echo "  外部连接: <node-ip>:30379"
echo "  密码:     由 Vault 管理 (kubectl get secret -n data redis-secret -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)"
echo ""
echo "  连接示例 (集群内):"
echo "    redis-cli -h redis.data.svc.cluster.local -a '<password>'"
echo ""
echo "  连接示例 (集群外):"
echo '    redis-cli -h <任意节点IP> -p 30379 -a '<password>'"'"
