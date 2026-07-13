#!/bin/bash
# ============================================================
#  PostgreSQL — 通用数据库服务 部署
#  标准 PostgreSQL 16，StatefulSet + PVC
# ============================================================
set -e
cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Deploying PostgreSQL ==="

# 先确保 ExternalSecret 和 Vault 密钥就绪
echo ">>> 1. Applying ExternalSecret (Vault → K8s Secret)..."
kubectl apply ${K} -f ../vault/inventory/postgres-externalsecret.yaml
sleep 3

echo ">>> 2. Applying PostgreSQL resources..."
kubectl apply ${K} -f k8s.yaml

echo ""
echo "=== Waiting for pod ready ==="
kubectl wait --for=condition=ready pod -l app=postgres -n data ${K} --timeout=120s

echo ""
echo "=== Status ==="
kubectl get pods -n data ${K} -l app=postgres -o wide

echo ""
echo "=== Done! ==="
echo "  内部连接: postgres.data.svc.cluster.local:5432"
echo "  外部连接: <node-ip>:30432"
echo "  数据库:   appdb"
echo "  用户:     appuser"
echo "  密码:     由 Vault 管理 (kubectl get secret -n data postgres-secret -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)"
echo ""
echo "  连接示例 (集群内):"
echo "    psql -h postgres.data.svc.cluster.local -U appuser -d appdb"
echo ""
echo "  连接示例 (集群外):"
echo '    psql -h <任意节点IP> -p 30432 -U appuser -d appdb'
