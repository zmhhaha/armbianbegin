#!/usr/bin/env bash
# 把 frpc 装回集群（集群重装 / 换 VPS 后执行一次）
#
#   bash install-frpc.sh                # 沿用现有 Secret 里的 token（若存在）
#   bash install-frpc.sh --rotate       # 重新生成 token，并提示同步更新 VPS 的 frps
#
# frpc 住在自己的命名空间 frpc ✓（共享基础设施，不占业务命名空间的配额）
# 目标命名空间若要放行 frpc，各加一条 frpc-ingress（见 README「新增一个对外服务」）
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

NS=frpc
SECRET=frpc-config
VPS_IP="${VPS_IP:-62.234.50.20}"
DASH_HOST="${DASH_HOST:-dsh.panghuer.top}"
ROTATE=0
[[ "${1:-}" == "--rotate" ]] && ROTATE=1

log(){ printf '\n\033[1;34m== %s\033[0m\n' "$*"; }

log "创建命名空间与基础策略"
kubectl apply -f k8s/frpc.yaml --dry-run=client -o name >/dev/null 2>&1 || true
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

if [[ $ROTATE -eq 1 || -z "$(kubectl -n "$NS" get secret "$SECRET" -o jsonpath='{.data.frpc\.toml}' 2>/dev/null)" ]]; then
  TOKEN="$(openssl rand -hex 24)"
  log "生成新 token 并写入 Secret $NS/$SECRET"
  kubectl -n "$NS" create secret generic "$SECRET" --from-file=frpc.toml=/dev/stdin <<EOF
serverAddr = "$VPS_IP"
serverPort = 7000
auth.method = "token"
auth.token = "$TOKEN"
transport.tls.enable = true
loginFailExit = false
log.to = "console"
log.level = "info"

[[proxies]]
name = "dsh-web"
type = "http"
customDomains = ["$DASH_HOST"]
localIP = "dsh-web.dsh.svc.cluster.local"
localPort = 4180
EOF
  if [[ $ROTATE -eq 1 ]]; then
    log "★ 记得把同一把 token 写到 VPS："
    echo "  sudo sed -i 's|^auth.token = .*|auth.token = \"$TOKEN\"|' /etc/frp/frps.toml && sudo systemctl restart frps"
  fi
else
  log "Secret $NS/$SECRET 已存在，沿用其中 token（要换用 --rotate）✓"
fi

log "应用 k8s/frpc.yaml（Namespace + default-deny + Deployment + frpc-egress）"
kubectl apply -f k8s/frpc.yaml

log "等待就绪"
kubectl -n "$NS" rollout status deployment/frpc --timeout=120s || true
kubectl -n "$NS" get pod -l app=frpc | sed 's/^/  /'
log "完成 ✓（日志里应看到 login to server success / start proxy success）"
echo "  kubectl -n $NS logs -l app=frpc -c frpc --tail=20"