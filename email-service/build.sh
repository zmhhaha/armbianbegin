#!/bin/bash
# ============================================================
#  Email Service — 构建 + 部署脚本
#  依赖 arm-cluster-master:5000/base:latest
# ============================================================
#  用法:
#    ./build.sh              # 本地构建
#    ./build.sh --push       # 构建 + 推送
#    ./build.sh --deploy     # 构建 + 推送 + 部署到 K8s
# ============================================================
set -euo pipefail

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/email-service:latest"

cd "$(dirname "$0")"

case "${1:-}" in
  --push)
    echo "=== 构建 + 推送: ${IMAGE} ==="
    docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .
    docker push "${IMAGE}"
    echo "完成! 拉取: docker pull ${IMAGE}"
    ;;

  --deploy)
    echo "=== 构建 + 推送 + 部署: ${IMAGE} ==="
    docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .
    docker push "${IMAGE}"
    kubectl apply -f k8s-deployment.yaml
    sleep 10
    kubectl get pods -n email-service
    echo ""
    echo "服务地址: http://email.email-service.svc.cluster.local"
    echo "健康检查: kubectl exec -n email-service deploy/email -- curl -s http://localhost:8000/health"
    ;;

  *)
    echo "=== 本地构建: ${IMAGE} ==="
    docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .
    echo "完成! 运行: docker run -d -p 8000:8000 --env-file .env ${IMAGE}"
    ;;
esac

# ============================================================
# ConfigMap
# kubectl create configmap email-config -n email-service \
#   --from-literal=SMTP_HOST="smtp.163.com" \
#   --from-literal=SMTP_PORT="465" \
#   --from-literal=SMTP_FROM="panghuer001@163.com" \
#   --dry-run=client -o yaml | kubectl apply -f -

# Secret  
# kubectl create secret generic email-secret -n email-service \
#   --from-literal=SMTP_USER="panghuer001@163.com" \
#   --from-literal=SMTP_PASS="你的QQ授权码" \
#   --dry-run=client -o yaml | kubectl apply -f -
# ============================================================
