#!/bin/bash
# ============================================================
#  oauth2-proxy + Casdoor — 拉取镜像并推送到私有 registry
#
#  用法:
#    ./build.sh              # 拉取 + 推送到私有 registry（默认）
#    ./build.sh --push       # 拉取 + 推送（默认行为）
#    ./build.sh --deploy     # 拉取 + 推送 + 部署到 K8s
#    ./build.sh --deploy-proxy  # 部署 oauth2-proxy 到 K8s
#
#  镜像:
#    oauth2-proxy — quay.io/oauth2-proxy/oauth2-proxy (ARM64)
#    Casdoor      — casbin/casdoor (ARM64, 非 all-in-one)
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

OAUTH_TAG="${OAUTH_TAG:-v7.8.0}"
# Casdoor 用**不可变 tag**：清单 oauth/k8s/casdoor-deployment.yaml 里固定的是同一个版本，
# 两边要一起改。历史上这里默认 latest、清单也写 latest，叠加 imagePullPolicy: Always，
# 结果就是「Pod 一重启就换版本」、升级不可控。改版本与升级步骤见清单顶部注释。
CASDOOR_TAG="${CASDOOR_TAG:-v4.11.0}"

# 国内加速前缀：留空 = 用服务器 Docker daemon 的 registry-mirrors（见 debian_begin.sh 里的
# daemon.json）。这与 network-policy/build.sh、panghu_chat/hermes/build.sh 的约定一致。
# Docker Hub 在国内常年不可达，拉不动时显式指定，例如：
#   DOCKERHUB_MIRROR=https://docker.m.daocloud.io CASDOOR_TAG=v4.11.0 bash oauth/build.sh
#   QUAY_MIRROR=https://quay.m.daocloud.io bash oauth/build.sh
DOCKERHUB_MIRROR="${DOCKERHUB_MIRROR:-}"
QUAY_MIRROR="${QUAY_MIRROR:-}"

pull_and_push() {
    local official="$1" local_img="$2" name="$3"
    echo "=== [${name}] Pulling ${official} ==="
    if ! docker pull "${official}"; then
        cat >&2 <<MSG

‼️ 拉取失败：${official}

   Docker Hub / quay.io 在国内常常不可达。三种办法：

   a) 显式指定加速前缀（绕过 daemon 的 registry-mirrors，最直接）
        DOCKERHUB_MIRROR=https://docker.m.daocloud.io bash oauth/build.sh    # Docker Hub
        QUAY_MIRROR=https://quay.m.daocloud.io bash oauth/build.sh           # quay.io

   b) 改服务器 /etc/docker/daemon.json 的 registry-mirrors 后 systemctl restart docker
        （候选列表与踩过的坑见 debian_begin.sh；加速器寿命不长，坏了就换一个）

   c) 兜底：在能拉通的机器上 docker save，scp 过来 docker load，再 push 到 ${REGISTRY}

MSG
        return 1
    fi
    echo "=== [${name}] Pushing to ${local_img} ==="
    docker tag "${official}" "${local_img}"
    docker push "${local_img}"
}

pull_and_push_all() {
    local proxy_src="quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
    [[ -n "${QUAY_MIRROR}" ]] && proxy_src="${QUAY_MIRROR%/}/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
    pull_and_push "${proxy_src}" \
        "${REGISTRY}/oauth2-proxy:${OAUTH_TAG}" "oauth2-proxy"
    docker tag "${REGISTRY}/oauth2-proxy:${OAUTH_TAG}" "${REGISTRY}/oauth2-proxy:latest"
    docker push "${REGISTRY}/oauth2-proxy:latest"

    local casdoor_src="casbin/casdoor:${CASDOOR_TAG}"
    [[ -n "${DOCKERHUB_MIRROR}" ]] && casdoor_src="${DOCKERHUB_MIRROR%/}/${casdoor_src}"
    pull_and_push "${casdoor_src}" \
        "${REGISTRY}/casdoor:${CASDOOR_TAG}" "Casdoor"
    docker tag "${REGISTRY}/casdoor:${CASDOOR_TAG}" "${REGISTRY}/casdoor:latest"
    docker push "${REGISTRY}/casdoor:latest"

    echo ""
    echo "全部镜像已推送:"
    echo "  ${REGISTRY}/oauth2-proxy:${OAUTH_TAG}"
    echo "  ${REGISTRY}/casdoor:${CASDOOR_TAG}"
}

deploy_k8s() {
    echo ""
    echo "=== 部署 Casdoor 基础服务到 K8s ==="
    kubectl apply ${K} -f k8s/namespace.yaml
    kubectl apply ${K} -f k8s/secret.yaml
    kubectl apply ${K} -f k8s/casdoor-configmap.yaml
    # 2026-09-29 修正：这里原写作 k8s/deployment.yaml，而该文件并不存在（实际叫
    # casdoor-deployment.yaml）。配合 set -e，--deploy 会中止在这一行，后面的
    # mysql.yaml / 各代理 / ExternalSecret 全都不会被 apply。
    kubectl apply ${K} -f k8s/casdoor-deployment.yaml   # Casdoor deployment
    kubectl apply ${K} -f k8s/mysql.yaml          # MySQL for Casdoor

    echo ""
    echo "=== Casdoor 基础服务已部署 ==="
}

deploy_proxy() {
    echo ""
    echo "=== 部署 oauth2-proxy 实例（research-agent + scientific-agent + daofaziran-agent + fofawubian-agent + zhongkuifumo-agent + yimaneili-agent + zhenzhuzhida-agent + zhougongjiemeng-agent + xiaotanrenjian-agent + txt2img）==="
    for target in research-agent scientific-agent daofaziran-agent fofawubian-agent zhongkuifumo-agent yimaneili-agent zhenzhuzhida-agent zhougongjiemeng-agent xiaotanrenjian-agent bingbichunqiu-agent; do
        echo "  ── 部署 ${target} ──"
        sed "s/__TARGET_NAME__/${target}/g" k8s/proxy-configmap.yaml | kubectl apply ${K} -f -
        sed "s/__TARGET_NAME__/${target}/g" k8s/proxy-deployment.yaml | kubectl apply ${K} -f -
    done

    # txt2img-proxy 使用独立的 ConfigMap（FastAPI 8000 端口）
    echo "  ── 部署 txt2img ──"
    kubectl apply ${K} -f k8s/txt2img-proxy-configmap.yaml
    sed "s/__TARGET_NAME__/txt2img/g" k8s/proxy-deployment.yaml | kubectl apply ${K} -f -

    echo ""
    echo "=== 同步 oauth2-proxy-secret 从 Vault ==="
    if [ -f "../vault/inventory/oauth-externalsecret.yaml" ]; then
        kubectl apply ${K} -f ../vault/inventory/oauth-externalsecret.yaml
        echo "  ExternalSecret 已应用"
    else
        echo "  ⚠️ vault/inventory/oauth-externalsecret.yaml 未找到，跳过"
        echo "  请确保 Vault 已部署，或在 apply 后手动创建 Secret"
    fi

    echo ""
    echo "=== oauth2-proxy 实例已部署 ==="
}

case "${1:-}" in
    --deploy)
        pull_and_push_all
        deploy_k8s
        deploy_proxy

        sleep 10
        kubectl get pods -n oauth ${K}

        echo ""
        echo "============================================"
        echo "  OAuth 认证服务已部署！"
        echo ""
        echo "  oauth2-proxy 实例:"
        echo "    research-agent:    http://oauth2-proxy-research-agent.oauth.svc.cluster.local:4180"
        echo "    scientific-agent:  http://oauth2-proxy-scientific-agent.oauth.svc.cluster.local:4180"
        echo "    daofaziran-agent:  http://oauth2-proxy-daofaziran-agent.oauth.svc.cluster.local:4180"
        echo "    fofawubian-agent:  http://oauth2-proxy-fofawubian-agent.oauth.svc.cluster.local:4180"
        echo "    zhongkuifumo-agent:  http://oauth2-proxy-zhongkuifumo-agent.oauth.svc.cluster.local:4180"
        echo "    yimaneili-agent:     http://oauth2-proxy-yimaneili-agent.oauth.svc.cluster.local:4180"
        echo "    zhenzhuzhida-agent:  http://oauth2-proxy-zhenzhuzhida-agent.oauth.svc.cluster.local:4180"
        echo "    zhougongjiemeng-agent: http://oauth2-proxy-zhougongjiemeng-agent.oauth.svc.cluster.local:4180"
        echo "    xiaotanrenjian-agent: http://oauth2-proxy-xiaotanrenjian-agent.oauth.svc.cluster.local:4180"
        echo "    txt2img:           http://oauth2-proxy-txt2img.oauth.svc.cluster.local:4180"
        echo ""
        echo "  下一步:"
        echo "    1. 访问 https://auth.panghuer.top 配置 OAuth 提供商"
        echo "    2. 在 Casdoor 中创建 oauth2-proxy 应用"
        echo "      回调 URL: https://research-agent.panghuer.top/oauth2/callback"
        echo "                https://scientific-agent.panghuer.top/oauth2/callback"
        echo "                https://daofaziran-agent.panghuer.top/oauth2/callback"
        echo "                https://fofawubian-agent.panghuer.top/oauth2/callback"
        echo "                https://zhongkuifumo-agent.panghuer.top/oauth2/callback"
        echo "                https://yimaneili-agent.panghuer.top/oauth2/callback"
        echo "                https://zhenzhuzhida-agent.panghuer.top/oauth2/callback"
        echo "                https://zhougongjiemeng-agent.panghuer.top/oauth2/callback"
        echo "                https://xiaotanrenjian-agent.panghuer.top/oauth2/callback"
        echo "                https://bingbichunqiu-agent.panghuer.top/oauth2/callback"
        echo "                https://txt2img.panghuer.top/oauth2/callback"
        echo "    3. 更新 secret.yaml 中 OIDC_CLIENT_ID/SECRET"
        echo "    4. 确保 tunnel-routes.yaml 已更新指向 oauth2-proxy"
        echo "============================================"
        ;;
    --deploy-proxy)
        deploy_proxy
        ;;
    --push|"")
        pull_and_push_all
        ;;
    --help)
        echo "用法: $0 [--push|--deploy|--deploy-proxy]"
        echo ""
        echo "  (无参数)        拉取 oauth2-proxy + Casdoor 镜像并推送到私有 registry（默认）"
        echo "  --push          拉取 oauth2-proxy + Casdoor 镜像并推送到私有 registry"
        echo "  --deploy        拉取镜像 + 部署 Casdoor + 部署 oauth2-proxy 多个实例"
        echo "  --deploy-proxy  仅部署/更新 oauth2-proxy 实例（research-agent + scientific-agent + daofaziran-agent + fofawubian-agent + zhongkuifumo-agent + yimaneili-agent + zhenzhuzhida-agent + zhougongjiemeng-agent + xiaotanrenjian-agent + txt2img）"
        echo ""
        echo "  oauth2-proxy 实例:"
        echo "    research-agent:     oauth2-proxy-research-agent.oauth.svc.cluster.local:4180"
        echo "    scientific-agent:   oauth2-proxy-scientific-agent.oauth.svc.cluster.local:4180"
        echo "    daofaziran-agent:   oauth2-proxy-daofaziran-agent.oauth.svc.cluster.local:4180"
        echo "    fofawubian-agent:   oauth2-proxy-fofawubian-agent.oauth.svc.cluster.local:4180"
        echo "    zhongkuifumo-agent:  oauth2-proxy-zhongkuifumo-agent.oauth.svc.cluster.local:4180"
        echo "    yimaneili-agent:     oauth2-proxy-yimaneili-agent.oauth.svc.cluster.local:4180"
        echo "    zhenzhuzhida-agent:  oauth2-proxy-zhenzhuzhida-agent.oauth.svc.cluster.local:4180"
        echo "    zhougongjiemeng-agent: oauth2-proxy-zhougongjiemeng-agent.oauth.svc.cluster.local:4180"
        echo "    xiaotanrenjian-agent: oauth2-proxy-xiaotanrenjian-agent.oauth.svc.cluster.local:4180"
        echo "    txt2img:            oauth2-proxy-txt2img.oauth.svc.cluster.local:4180"
        ;;
    *)
        echo "用法: $0 [--push|--deploy|--deploy-proxy|--help]"
        echo ""
        echo "  组件:"
        echo "    oauth2-proxy : quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
        echo "    Casdoor      : casbin/casdoor:${CASDOOR_TAG}"
        echo ""
        echo "  oauth2-proxy 实例:"
        echo "    research-agent:     oauth2-proxy-research-agent.oauth.svc.cluster.local:4180"
        echo "    scientific-agent:   oauth2-proxy-scientific-agent.oauth.svc.cluster.local:4180"
        echo "    daofaziran-agent:   oauth2-proxy-daofaziran-agent.oauth.svc.cluster.local:4180"
        echo "    fofawubian-agent:   oauth2-proxy-fofawubian-agent.oauth.svc.cluster.local:4180"
        echo "    zhongkuifumo-agent:  oauth2-proxy-zhongkuifumo-agent.oauth.svc.cluster.local:4180"
        echo "    yimaneili-agent:     oauth2-proxy-yimaneili-agent.oauth.svc.cluster.local:4180"
        echo "    zhenzhuzhida-agent:  oauth2-proxy-zhenzhuzhida-agent.oauth.svc.cluster.local:4180"
        echo "    zhougongjiemeng-agent: oauth2-proxy-zhougongjiemeng-agent.oauth.svc.cluster.local:4180"
        echo "    xiaotanrenjian-agent: oauth2-proxy-xiaotanrenjian-agent.oauth.svc.cluster.local:4180"
        echo "    txt2img:            oauth2-proxy-txt2img.oauth.svc.cluster.local:4180"
        ;;
esac
