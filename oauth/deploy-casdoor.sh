#!/usr/bin/env bash
set -euo pipefail

# Existing Casdoor installation: apply only its entry config and Deployment/Service.
# MySQL, app.conf and SSO credentials are managed separately.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
kubectl apply -f "${SCRIPT_DIR}/k8s/casdoor-entry-configmap.yaml"
kubectl apply -f "${SCRIPT_DIR}/k8s/casdoor-deployment.yaml"
# nginx.conf uses subPath; changing its ConfigMap requires a new Pod.
kubectl -n oauth rollout restart deployment/casdoor
kubectl -n oauth rollout status deployment/casdoor --timeout=300s
kubectl -n oauth get pods -l app=casdoor -o wide
