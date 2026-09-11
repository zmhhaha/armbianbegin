#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"

LLM_MANIFEST="${ROOT_DIR}/vault/inventory/rag-llm-externalsecret.yaml"
CALLERS_MANIFEST="${ROOT_DIR}/vault/inventory/rag-callers-externalsecret.yaml"

echo "=== Applying llm-service token ExternalSecret ==="
kubectl apply -f "${LLM_MANIFEST}"
if ! kubectl -n data wait --for=condition=Ready externalsecret/rag-llm-secret --timeout=120s; then
    echo "[rag-service] WARNING: rag-llm-secret 未就绪；查询会退化为只返回检索上下文，直到令牌注入。" >&2
fi

echo "=== Applying caller token ExternalSecret ==="
kubectl apply -f "${CALLERS_MANIFEST}"
if ! kubectl -n data wait --for=condition=Ready externalsecret/rag-callers-secret --timeout=120s; then
    echo "[rag-service] WARNING: rag-callers-secret 未就绪；所有调用都会返回 401，直到写入 secret/rag-service/callers。" >&2
fi

kubectl apply -f "${SCRIPT_DIR}/k8s.yaml"
kubectl set image deployment/rag-service -n data \
  rag-service="${REGISTRY}/rag-service:latest"
kubectl rollout restart deployment/rag-service -n data
kubectl rollout status deployment/rag-service -n data --timeout=300s
