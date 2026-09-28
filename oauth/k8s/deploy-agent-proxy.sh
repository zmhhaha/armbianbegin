#!/usr/bin/env bash
# Agent/Gradio oauth2-proxy 重新部署命令：
#   bash deploy-agent-proxy.sh daofaziran-agent
#   bash deploy-agent-proxy.sh fofawubian-agent
#   bash deploy-agent-proxy.sh game-review-agent
#   bash deploy-agent-proxy.sh literature-downloader
#   bash deploy-agent-proxy.sh research-agent
#   bash deploy-agent-proxy.sh scientific-agent
#   bash deploy-agent-proxy.sh txt2img
#   bash deploy-agent-proxy.sh yimaneili-agent
#   bash deploy-agent-proxy.sh zhenzhuzhida-agent
#   bash deploy-agent-proxy.sh zhongkuifumo-agent
#   bash deploy-agent-proxy.sh zhougongjiemeng-agent
#   bash deploy-agent-proxy.sh xiaotanrenjian-agent
#   bash deploy-agent-proxy.sh bingbichunqiu-agent
#
# 不传参数时默认重新部署 research-agent。
#
# 第二个参数是 upstream，不传则沿用历史默认值 ui.<target>:7860：
#   bash deploy-agent-proxy.sh bingbichunqiu-agent \
#     http://baijiazhengming-ui.baijiazhengming.svc.cluster.local:7860
# 共享运行时（百家争鸣）就是这么把八个人格的代理都指到同一个 UI 的 —— 代理名字不变，
# 所以 Cloudflare 后台与 Casdoor 回调都不用动。
set -euo pipefail

target="${1:-research-agent}"
upstream="${2:-http://ui.${target}.svc.cluster.local:7860}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${target}" == "txt2img" ]]; then
    kubectl apply -f "${script_dir}/txt2img-proxy-configmap.yaml"
else
    sed -e "s/__TARGET_NAME__/${target}/g" -e "s|__UPSTREAM__|${upstream}|g" \
        "${script_dir}/proxy-configmap.yaml" | kubectl apply -f -
fi
sed "s/__TARGET_NAME__/${target}/g" "${script_dir}/proxy-deployment.yaml" | kubectl apply -f -

# 必加：oauth2-proxy 在**启动时**读 alpha-config。只改 ConfigMap 的话 Deployment 的
# spec 没变，apply 不会触发滚动更新，Pod 会一直用着旧 upstream —— 表现是
# 「ConfigMap 看是对的、日志里却在 dial 一个早就删掉的旧地址」，浏览器拿到 502。
# （2026-09-28 实测踩过：七个代理都停在 ui.<target>，只有更早重启过的那个是好的。）
kubectl rollout restart "deployment/oauth2-proxy-${target}" -n oauth
kubectl rollout status "deployment/oauth2-proxy-${target}" -n oauth --timeout=180s
