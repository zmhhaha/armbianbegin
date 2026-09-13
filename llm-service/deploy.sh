#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/llm-service:latest"
VAULT_MANIFEST="${ROOT_DIR}/vault/inventory/llm-service-externalsecret.yaml"

if [[ "${1:-}" != "--skip-build" ]]; then
    REGISTRY="${REGISTRY}" bash "${SCRIPT_DIR}/build.sh" --push
fi

echo "=== Ensuring namespace ==="
# ExternalSecret 先于 k8s.yaml 应用，命名空间必须先存在
kubectl create namespace llm --dry-run=client -o yaml | kubectl apply -f -

echo "=== Applying Vault ExternalSecret ==="
kubectl apply -f "${VAULT_MANIFEST}"
# 用 metadata get 只检查路径存在，不读取任何令牌值（值不进日志）
if kubectl -n vault exec vault-0 -- vault kv metadata get secret/llm-service/callers >/dev/null 2>&1; then
    kubectl -n llm wait --for=condition=Ready externalsecret/llm-service-secret --timeout=120s
else
    echo "[llm-service] WARNING: Vault secret/llm-service/callers 未配置（调用方令牌）；" >&2
    echo "             服务会起来但所有调用方都会拿到 401。先按 llm-service-externalsecret.yaml 顶部的说明写入。" >&2
fi

echo "=== Applying llm-service resources ==="
sed "s|arm-cluster-master:5000/llm-service:latest|${IMAGE}|g" "${SCRIPT_DIR}/k8s.yaml" | kubectl apply -f -

# latest 不变更 Deployment 模板，必须显式重启才能拉到新镜像
kubectl -n llm rollout restart deployment/llm-service
kubectl -n llm rollout status deployment/llm-service --timeout=300s

echo "=== Status ==="
kubectl -n llm get deploy,svc,pod -l app=llm-service -o wide
echo "Internal endpoint: http://llm-service.llm.svc.cluster.local"
