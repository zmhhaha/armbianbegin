#!/usr/bin/env bash
set -euo pipefail

target="${1:-research-agent}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/proxy-configmap.yaml" | kubectl apply -f -
sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/proxy-deployment.yaml" | kubectl apply -f -

kubectl rollout status "deployment/oauth2-proxy-${target}" -n oauth --timeout=180s
