#!/bin/bash
# ============================================================
#  Portal 通用部署脚本
#
#  用法:
#    bash deploy.sh agent      # 部署 agent 门户
#    bash deploy.sh game       # 部署 game 门户
#    bash deploy.sh main       # 部署 main 门户
#    bash deploy.sh chat       # 部署 Panghu Chat 门户
#    bash deploy.sh tool       # 部署工具门户（含 OpenSpec MCP 接入文档页）
#
#  命名空间约定: {app}-portal（如 agent-portal / game-portal / main-portal / chat-portal）
#  镜像: portal:latest（各门户共用同一镜像）
#  apps/<app>/ 下的**全部文件**都打进 ConfigMap portal-html（不只是一个 index.html）
# ============================================================
set -e
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

APP="${1:?用法: bash deploy.sh <app>}"
NAMESPACE="${APP}-portal"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== 部署 Portal: ${APP} (namespace: ${NAMESPACE}) ==="

# 构建镜像
echo "  📦 构建镜像..."
docker build -t arm-cluster-master:5000/portal:latest -f Dockerfile .
docker push arm-cluster-master:5000/portal:latest

# 创建命名空间
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml $K | kubectl apply $K -f -

# ConfigMap（apps/<app>/ 下的全部文件）
{
  echo "apiVersion: v1"
  echo "kind: ConfigMap"
  echo "metadata:"
  echo "  name: portal-html"
  echo "  namespace: ${NAMESPACE}"
  echo "binaryData:"
  for f in apps/${APP}/*; do
    [ -f "$f" ] || continue
    echo "  $(basename "$f"): $(base64 -w0 "$f")"
  done
} > /tmp/portal-cm.yaml
kubectl apply $K -f /tmp/portal-cm.yaml

# k8s 资源
TMPL="k8s.yaml"
[ "${APP}" = "main" ] && TMPL="k8s.main.yaml"
sed "s/__APP__/${APP}/g" "${TMPL}" | kubectl apply $K -f -

# 重启
kubectl rollout restart deploy/portal -n ${NAMESPACE} $K

sleep 5
kubectl get pods -n ${NAMESPACE} $K | grep portal
echo ""
echo "=== Done! ${APP} portal 已部署 ==="
