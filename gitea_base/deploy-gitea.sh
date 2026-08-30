#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "${script_dir}"

kubectl apply -f gitops-namespace.yaml
kubectl apply -f drone-builds-namespace.yaml
kubectl apply -f ../vault/inventory/gitops-externalsecret.yaml

kubectl wait --for=condition=Ready externalsecret/gitea-secrets -n gitops --timeout=120s

kubectl apply -f gitea-env.yaml
kubectl apply -f gitea-config.yaml
kubectl apply -f gitea.yaml

kubectl rollout status statefulset/gitea -n gitops --timeout=180s
kubectl apply -f ../cloudflare-tunnel/operator/gitops-routes.yaml
