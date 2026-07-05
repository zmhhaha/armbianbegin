#!/bin/bash
# ============================================================
#  Agent Portal 部署 — ConfigMap 注入 index.html
#  更新页面只需改 index.html 然后重新执行此脚本
#  无需重新构建镜像
# ============================================================
set -e
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Encoding index.html → ConfigMap ==="
INDEX_B64=$(base64 -w0 index.html)

kubectl create namespace agent-portal --dry-run=client -o yaml $K | kubectl apply $K -f -

cat > /tmp/portal-cm.yaml << CMEOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: portal-html
  namespace: agent-portal
binaryData:
  index.html: ${INDEX_B64}
CMEOF
kubectl apply $K -f /tmp/portal-cm.yaml

echo "=== Deploying ==="
kubectl apply $K -f k8s.yaml

echo "=== Restarting ==="
kubectl rollout restart deploy/portal -n agent-portal $K

sleep 5
kubectl get pods -n agent-portal $K
echo ""
echo "Done! https://agent.panghuer.top"
