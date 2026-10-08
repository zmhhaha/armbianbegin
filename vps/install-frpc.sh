#!/usr/bin/env bash
# 把 frpc 装回集群（集群重装 / 换 VPS 后执行一次）
#
#   sudo 不需要 —— 用当前 kubectl 上下文即可：
#     bash install-frpc.sh                     # 沿用现有 Secret 里的 token（若存在）
#     bash install-frpc.sh --rotate            # 重新生成 token，并提示同步更新 VPS 的 frps
#
# 设计文档：../docs/vps-ingress-design.md    运维手册：README.md
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

NS=dsh
SECRET=frpc-config
VPS_IP="${VPS_IP:-62.234.50.20}"
DASH_HOST="${DASH_HOST:-dsh.panghuer.top}"
ROTATE=0
[[ "${1:-}" == "--rotate" ]] && ROTATE=1

log(){ printf '\n\033[1;34m== %s\033[0m\n' "$*"; }

if [[ $ROTATE -eq 1 || -z "$(kubectl -n "$NS" get secret "$SECRET" -o jsonpath='{.data.frpc\.toml}' 2>/dev/null)" ]]; then
  TOKEN="$(openssl rand -hex 24)"
  log "生成新 token（48 位十六进制）并写入 Secret $SECRET"
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
  log "Secret $SECRET 已存在，沿用其中的 token（要换用 --rotate）✓"
fi

log "应用 vps/k8s/frpc.yaml"
kubectl apply -f k8s/frpc.yaml

log "等待就绪"
kubectl -n "$NS" rollout status deployment/frpc --timeout=120s || true
kubectl -n "$NS" get pod -l app=frpc | sed 's/^/  /'
log "完成 ✓（日志里应看到 login to server success）"
echo "  kubectl -n $NS logs -l app=frpc -c frpc --tail=20"