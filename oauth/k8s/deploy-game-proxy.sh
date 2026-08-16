#!/usr/bin/env bash
# 游戏/Nginx oauth2-proxy 重新部署命令：
#   bash deploy-game-proxy.sh guanliao
#   bash deploy-game-proxy.sh qianfu
#   bash deploy-game-proxy.sh school-of-one
#   bash deploy-game-proxy.sh shapan
#   bash deploy-game-proxy.sh tewu
#   bash deploy-game-proxy.sh xuye
#
# 不传参数时默认重新部署 tewu。
set -euo pipefail

target="${1:-tewu}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/game-proxy-configmap.yaml" | kubectl apply -f -
sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/game-proxy-deployment.yaml" | kubectl apply -f -

kubectl rollout status "deployment/oauth2-proxy-${target}" -n oauth --timeout=180s
