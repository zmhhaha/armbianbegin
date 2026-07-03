#!/bin/bash
# ============================================================
#  Generic FastAPI 构建 + 部署
#  用法:
#    1. 把你的 app 代码放到 app/ 目录
#    2. 依赖写入 requirements.txt
#    3. bash deploy.sh
# ============================================================
set -e
cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/fastapi-app:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building ${IMAGE} ==="
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .
docker push "${IMAGE}"

echo "=== Deploying ==="
kubectl apply ${K} -f k8s-deployment.yaml
sleep 10
kubectl get pods -n fastapi-app ${K}
echo ""
echo "Done: http://fastapi-app.fastapi-app.svc.cluster.local:8000"
