#!/usr/bin/env bash
# 部署方式：在集群控制节点的 armbianbegin/oauth/k8s 目录执行 bash deploy-hublog-proxy.sh。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

kubectl get namespace oauth >/dev/null
kubectl get namespace hublog >/dev/null
kubectl -n oauth get secret oauth2-proxy-secret >/dev/null
kubectl -n hublog get service hublog-api >/dev/null

kubectl apply -f "${SCRIPT_DIR}/hublog-proxy-configmap.yaml"
# Hublog only: anonymous read access is limited to UUID share pages and the
# corresponding read-only APIs. The generic agent template stays protected.
sed \
  -e 's/__TARGET_NAME__/hublog/g' \
  -e '/--ssl-insecure-skip-verify=true/a\
          - "--skip-auth-route=^/share/[0-9a-fA-F-]{36}/?$"\
          - "--skip-auth-route=^/api/v1/shares/[0-9a-fA-F-]{36}(/comments)?([?].*)?$"\
          - "--skip-auth-route=^/assets/share[.](css|js)([?].*)?$"\
          - "--skip-auth-route=^/assets/hublog-mark-v10-cat-mouth-no-whiskers[.]svg([?].*)?$"' \
  "${SCRIPT_DIR}/proxy-deployment.yaml" | kubectl apply -f -
kubectl rollout restart deployment/oauth2-proxy-hublog -n oauth
kubectl rollout status deployment/oauth2-proxy-hublog -n oauth --timeout=180s

kubectl -n oauth get deployment,service -l app=oauth2-proxy-hublog
echo "Hublog SSO proxy ready: oauth2-proxy-hublog.oauth.svc.cluster.local:4180"
echo "Casdoor callback must include: https://hublog.panghuer.top/oauth2/callback"
