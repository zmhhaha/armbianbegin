#!/bin/bash
# ============================================================
#  Generic Agent UI 部署（Gradio）
#  用法: AGENT_NAME=panghu_agent bash deploy.sh
#  域名: ${AGENT_NAME}.panghuer.top
# ============================================================
set -e
cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"

AGENT_NAME="${AGENT_NAME:-panghu_agent}"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/gradio-agent:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building ${IMAGE} (agent: ${AGENT_NAME}) ==="
cd ..
docker build --build-arg REGISTRY="${REGISTRY}" --build-arg AGENT_NAME="${AGENT_NAME}" -t "${IMAGE}" -f gradio/Dockerfile .
docker push "${IMAGE}"
cd gradio

echo "=== Deploying to K8s (namespace: ${AGENT_NAME}) ==="
sed "s/__AGENT_NAME__/${AGENT_NAME}/g" k8s-deployment.yaml | kubectl apply ${K} -f -

sleep 15
kubectl get pods -n "${AGENT_NAME}" ${K}
echo ""
echo "Done! UI: https://${AGENT_NAME}.panghuer.top"
