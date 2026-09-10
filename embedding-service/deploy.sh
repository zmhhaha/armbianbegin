#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
kubectl apply -f "${SCRIPT_DIR}/k8s.yaml"
kubectl rollout status deployment/embedding-service -n data --timeout=300s
