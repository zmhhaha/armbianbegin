#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"

kubectl apply -f "${SCRIPT_DIR}/k8s.yaml"
kubectl set image deployment/rag-service -n data \
  rag-service="${REGISTRY}/rag-service:latest"
kubectl rollout restart deployment/rag-service -n data
kubectl rollout status deployment/rag-service -n data --timeout=300s
