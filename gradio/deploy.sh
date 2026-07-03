#!/bin/bash
# ============================================================
#  Gradio Agent UI 一键部署
#  用法: bash deploy.sh
# ============================================================
set -e
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/gradio-agent:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building ${IMAGE} ==="
cd ..
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" -f gradio/Dockerfile .
cd gradio
docker push "${IMAGE}"

echo "=== Deploying to K8s ==="
kubectl apply ${K} -f k8s-deployment.yaml

echo "=== Waiting ==="
sleep 15
kubectl get pods -n gradio-agent ${K}
echo ""
echo "Done! Internal: http://gradio-agent.gradio-agent.svc.cluster.local:7860"
echo "Web UI:      http://<node-ip>:30080/gradio  (via ingress-nginx)"
