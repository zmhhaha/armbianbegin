#!/bin/bash
# ============================================================
#  Cloudflare Tunnel Operator 一键部署
#  从 .token 读取 token，创建 Secret，部署 Operator + CRD
# ============================================================
set -e
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

[ -f "../../cluster_config.sh" ] && source "../../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/cf-tunnel-operator:latest"
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

# ---- 1. 读取 tunnel token ----
TOKEN_FILE="${script_dir}/../.token"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "ERROR: .token 文件不存在！"
    echo "  请将 Cloudflare Tunnel token 写入 ${TOKEN_FILE}（一行纯文本）"
    exit 1
fi
TUNNEL_TOKEN=$(grep -v '^#' "$TOKEN_FILE" | head -1 | tr -d '[:space:]')
if [ -z "$TUNNEL_TOKEN" ]; then
    echo "ERROR: .token 文件为空或只有注释"
    exit 1
fi
echo "Token loaded (${#TUNNEL_TOKEN} chars)"

# ---- 2. 构建 cloudflared 镜像（operator 会用它创建 tunnel pod）----
echo ""
echo "=== Building cloudflared-k8s ==="
CF_IMAGE="${REGISTRY}/cloudflared-k8s:latest"
cd ..
docker build --build-arg REGISTRY="${REGISTRY}" -t "${CF_IMAGE}" -f Dockerfile .
docker push "${CF_IMAGE}"
cd operator

# ---- 3. 构建 Operator 镜像 ----
echo ""
echo "=== Building ${IMAGE} ==="
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" .
docker push "${IMAGE}"

# ---- 3. 创建 token Secret（供 Tunnel CR 引用）----
echo ""
echo "=== Creating token secret ==="
kubectl create secret generic cf-tunnel-token \
    --from-literal=token="${TUNNEL_TOKEN}" \
    --namespace default \
    --dry-run=client -o yaml $K | kubectl apply $K -f -

# ---- 4. 部署 CRD + RBAC + Operator ----
echo "=== Deploying Operator ==="
kubectl apply $K -f crds.yaml
kubectl apply $K -f rbac.yaml
kubectl apply $K -f deployment.yaml

sleep 10
echo ""
kubectl get pods -n cf-tunnel-operator $K

echo ""
echo "============================================"
echo "  Operator deployed!"
echo "  Create a tunnel: kubectl apply -f example-tunnel.yaml"
echo "============================================"
