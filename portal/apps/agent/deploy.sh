#!/bin/bash
# ============================================================
#  Agent Portal 部署
#  构建镜像 → ConfigMap 注入 → K8s apply
# ============================================================
set -e
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo "=== Building portal image ==="
docker build -t arm-cluster-master:5000/portal:latest .
docker push arm-cluster-master:5000/portal:latest

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
