#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
kubectl apply -f "${SCRIPT_DIR}/k8s.yaml"
kubectl set image deployment/embedding-service -n data embedding-service="${REGISTRY:-arm-cluster-master:5000}/embedding-service:latest"
kubectl rollout restart deployment/embedding-service -n data
kubectl rollout status deployment/embedding-service -n data --timeout=300s
