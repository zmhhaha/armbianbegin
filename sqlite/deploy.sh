#!/bin/bash
# ============================================================
#  SQLite Data Service 部署
#  独立镜像，不依赖其他服务
# ============================================================
set -e
cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/sqlite:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building ${IMAGE} ==="
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .

# push via arm-cluster-master registry
docker push "${IMAGE}"

echo "=== Deploying ==="
kubectl apply ${K} -f k8s.yaml

sleep 8
kubectl get pods -n data ${K}
echo ""
echo "Done! http://sqlite.data.svc.cluster.local:8000"
echo "  GET  /health   → 健康检查"
echo "  GET  /tables   → 表列表"
echo "  POST /query    → SELECT {\"sql\":\"...\"}"
echo "  POST /execute  → INSERT/UPDATE/DELETE"
echo "  GET  /backup   → 下载数据库文件"
