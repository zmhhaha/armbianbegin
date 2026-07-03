#!/bin/bash
# ============================================================
#  Generic Gradio 构建 + 部署
#  用法:
#    1. 编辑 app.py 写你的 Gradio 应用
#    2. 依赖写入 requirements.txt
#    3. bash deploy.sh
# ============================================================
set -e
cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/gradio-app:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building ${IMAGE} ==="
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .
docker push "${IMAGE}"

echo "=== Deploying ==="
kubectl apply ${K} -f k8s-deployment.yaml
sleep 10
kubectl get pods -n gradio-app ${K}
echo ""
echo "Done: http://gradio-app.gradio-app.svc.cluster.local:7860"
