#!/usr/bin/env bash
# Agent/Gradio oauth2-proxy 重新部署命令：
#   bash deploy-agent-proxy.sh daofaziran-agent
#   bash deploy-agent-proxy.sh fofawubian-agent
#   bash deploy-agent-proxy.sh game-review-agent
#   bash deploy-agent-proxy.sh research-agent
#   bash deploy-agent-proxy.sh scientific-agent
#   bash deploy-agent-proxy.sh txt2img
#   bash deploy-agent-proxy.sh yimaneili-agent
#   bash deploy-agent-proxy.sh zhenzhuzhida-agent
#   bash deploy-agent-proxy.sh zhongkuifumo-agent
#
# 不传参数时默认重新部署 research-agent。
set -euo pipefail

target="${1:-research-agent}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${target}" == "txt2img" ]]; then
    kubectl apply -f "${script_dir}/txt2img-proxy-configmap.yaml"
else
    sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/proxy-configmap.yaml" | kubectl apply -f -
fi
sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/proxy-deployment.yaml" | kubectl apply -f -

kubectl rollout status "deployment/oauth2-proxy-${target}" -n oauth --timeout=180s
