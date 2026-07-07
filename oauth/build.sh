#!/bin/bash
# ============================================================
#  oauth2-proxy + Casdoor — 拉取镜像并推送到私有 registry
#
#  用法:
#    ./build.sh              # 拉取全部镜像到本地
#    ./build.sh --push       # 拉取 + 推送到私有 registry
#    ./build.sh --deploy     # 拉取 + 推送 + 部署到 K8s
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
CASDOOR_TAG="${CASDOOR_TAG:-latest}"

pull_and_push() {
    local official="$1" local_img="$2" name="$3"
    echo "=== [${name}] Pulling ${official} ==="
    docker pull "${official}"
    echo "=== [${name}] Pushing to ${local_img} ==="
    docker tag "${official}" "${local_img}"
    docker push "${local_img}"
}

pull_and_push_all() {
    pull_and_push "quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}" \
        "${REGISTRY}/oauth2-proxy:${OAUTH_TAG}" "oauth2-proxy"
    docker tag "${REGISTRY}/oauth2-proxy:${OAUTH_TAG}" "${REGISTRY}/oauth2-proxy:latest"
    docker push "${REGISTRY}/oauth2-proxy:latest"

    pull_and_push "casbin/casdoor:${CASDOOR_TAG}" \
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
    echo "=== 部署到 K8s ==="
    kubectl apply ${K} -f k8s/namespace.yaml
    kubectl apply ${K} -f k8s/secret.yaml
    kubectl apply ${K} -f k8s/configmap.yaml
    kubectl apply ${K} -f k8s/casdoor-configmap.yaml
    kubectl apply ${K} -f k8s/proxy-deployment.yaml
    kubectl apply ${K} -f k8s/deployment.yaml

    sleep 10
    kubectl get pods -n oauth ${K}

    echo ""
    echo "============================================"
    echo "  OAuth 认证服务已部署！"
    echo ""
    echo "  Casdoor:"
    echo "    内部地址: http://casdoor.oauth.svc.cluster.local:8000"
    echo "    公网地址: https://auth.panghuer.top"
    echo "    默认账户: admin / 123456"
    echo ""
    echo "  oauth2-proxy:"
    echo "    内部地址: http://oauth2-proxy.oauth.svc.cluster.local:4180"
    echo ""
    echo "  下一步:"
    echo "    1. 访问 https://auth.panghuer.top 配置 OAuth 提供商"
    echo "    2. 在 Casdoor 中创建 oauth2-proxy 应用"
    echo "    3. 更新 secret.yaml 中 OIDC_CLIENT_ID/SECRET"
    echo "    4. 切换 research-ui TunnelRoute → oauth2-proxy.oauth:4180"
    echo "============================================"
}

case "${1:-}" in
    --deploy)
        pull_and_push_all
        deploy_k8s
        ;;
    --push)
        pull_and_push_all
        ;;
    *)
        echo "用法: $0 [--push|--deploy]"
        echo ""
        echo "  组件:"
        echo "    oauth2-proxy : quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
        echo "    Casdoor      : casbin/casdoor:${CASDOOR_TAG}"
        ;;
esac
