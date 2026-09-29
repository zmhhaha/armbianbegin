#!/usr/bin/env bash
# 给「一个域名一个 oauth2-proxy 实例」的服务重新部署代理：
#   bash deploy-agent-proxy.sh research-agent
#   bash deploy-agent-proxy.sh scientific-agent
#   bash deploy-agent-proxy.sh game-review-agent
#   bash deploy-agent-proxy.sh literature-downloader
#   bash deploy-agent-proxy.sh txt2img
#
# ⚠️ 八个人格（bingbichunqiu / daofaziran / fofawubian / xiaotanrenjian / yimaneili /
# zhenzhuzhida / zhongkuifumo / zhougongjiemeng）**不在这里**：2026-09-28 起他们由共享实例
# oauth2-proxy-baijiazhengming 服务（一个代理、八个域名），原来那八个 per-domain 代理已经删除。
# 别为某个人格单独跑本脚本 —— 上游 ui.<slug>-agent 已经不存在，只会造出一个指不回任何
# Service 的代理。其他家族各有自己的脚本：游戏系 deploy-game-proxy.sh，Hublog deploy-hublog-proxy.sh。
#
# 不传参数时默认重新部署 research-agent。
#
# 第二个参数是 upstream，不传则沿用历史默认值 ui.<target>:7860。共享运行时（百家争鸣）
# 就是这么建的 —— 它的 target 是 baijiazhengming：
#   bash deploy-agent-proxy.sh baijiazhengming \
#     http://baijiazhengming-ui.baijiazhengming.svc.cluster.local:7860
#
# 特例：target=baijiazhengming 是**多域名共享实例**（一个代理服务八个域名）。它的回调
# 不能写死，改用 --whitelist-domain，由 oauth2-proxy 按请求的 Host 生成回调 ——
# 写死的话，从别的域名登录会被绕到被写死的那一个。
set -euo pipefail

target="${1:-research-agent}"
upstream="${2:-http://ui.${target}.svc.cluster.local:7860}"
if [[ "${target}" == "baijiazhengming" ]]; then
    callback_arg="--whitelist-domain=.panghuer.top"
else
    callback_arg="--redirect-url=https://${target}.panghuer.top/oauth2/callback"
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${target}" == "txt2img" ]]; then
    kubectl apply -f "${script_dir}/txt2img-proxy-configmap.yaml"
else
    sed -e "s/__TARGET_NAME__/${target}/g" -e "s|__UPSTREAM__|${upstream}|g" \
        "${script_dir}/proxy-configmap.yaml" | kubectl apply -f -
fi
sed -e "s/__TARGET_NAME__/${target}/g" -e "s|__CALLBACK_ARG__|${callback_arg}|g" \
    "${script_dir}/proxy-deployment.yaml" | kubectl apply -f -

# 必加：oauth2-proxy 在**启动时**读 alpha-config。只改 ConfigMap 的话 Deployment 的
# spec 没变，apply 不会触发滚动更新，Pod 会一直用着旧 upstream —— 表现是
# 「ConfigMap 看是对的、日志里却在 dial 一个早就删掉的旧地址」，浏览器拿到 502。
# （2026-09-28 实测踩过：七个代理都停在 ui.<target>，只有更早重启过的那个是好的。）
kubectl rollout restart "deployment/oauth2-proxy-${target}" -n oauth
kubectl rollout status "deployment/oauth2-proxy-${target}" -n oauth --timeout=180s
