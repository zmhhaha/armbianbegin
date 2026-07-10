#!/bin/bash
# ============================================================
#  Portal 通用部署脚本
#
#  用法:
#    bash deploy.sh agent      # 部署 agent 门户
#    bash deploy.sh game       # 部署 game 门户
#    bash deploy.sh main       # 部署 main 门户
#
#  命名空间约定: {app}-portal（如 agent-portal / game-portal / main-portal）
#  镜像: portal:latest（三个门户共用同一镜像）
#  index.html 通过 ConfigMap 注入
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

# ConfigMap（index.html）
INDEX_B64=$(base64 -w0 apps/${APP}/index.html)
cat > /tmp/portal-cm.yaml << CMEOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: portal-html
  namespace: ${NAMESPACE}
binaryData:
  index.html: ${INDEX_B64}
CMEOF
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
