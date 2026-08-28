#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "${script_dir}"

kubectl apply -f ../vault/inventory/gitops-externalsecret.yaml
kubectl wait --for=condition=Ready externalsecret/drone-server-secrets -n gitops --timeout=120s
kubectl wait --for=condition=Ready externalsecret/drone-runner-secrets -n gitops --timeout=120s

kubectl apply -f drone-env.yaml
kubectl apply -f drone.yaml
kubectl apply -f ../cloudflare-tunnel/operator/gitops-routes.yaml

kubectl rollout status statefulset/drone-server -n gitops --timeout=180s
kubectl rollout status deployment/drone-runner -n gitops --timeout=180s
