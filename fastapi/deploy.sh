#!/bin/bash
# ============================================================
#  FastAPI Agent 一键部署
#  用法: bash deploy.sh
# ============================================================
set -e
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/fastapi-agent:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building ${IMAGE} ==="
# build context 为工程根目录，Dockerfile 在 fastapi/
cd ..
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" -f fastapi/Dockerfile .
cd fastapi
docker push "${IMAGE}"

echo "=== Deploying to K8s ==="
kubectl apply ${K} -f k8s-deployment.yaml

echo "=== Waiting ==="
sleep 15
kubectl get pods -n fastapi-agent ${K}
echo ""
echo "Done! Internal: http://fastapi-agent.fastapi-agent.svc.cluster.local:8000"
echo "API docs:    http://<node-ip>:30080/docs  (via ingress-nginx)"
