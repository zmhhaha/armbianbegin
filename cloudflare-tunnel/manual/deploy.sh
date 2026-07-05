#!/bin/bash
# =============================================================
#  Cloudflare Tunnel 一键部署脚本
#  用法:
#    1. 把 tunnel token 写入 .token 文件（一行纯文本）
#    2. bash deploy.sh
# =============================================================
set -e

script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

# 加载集群配置
[ -f "${script_dir}/../cluster_config.sh" ] && source "${script_dir}/../cluster_config.sh"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/cloudflared-k8s:latest"

# ============================================================
# 1. 读取 token
# ============================================================
TOKEN_FILE="${script_dir}/../.token"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "ERROR: .token 文件不存在！"
    echo "  请在 Cloudflare Zero Trust → Networks → Tunnels 中创建 Tunnel"
    echo "  将 token 粘贴到 ${TOKEN_FILE} 文件中（一行纯文本）"
    exit 1
fi
TUNNEL_TOKEN=$(grep -v '^#' "$TOKEN_FILE" | head -1 | tr -d '[:space:]')
if [ -z "$TUNNEL_TOKEN" ]; then
    echo "ERROR: .token 文件为空或只有注释"
    exit 1
fi
echo "Token loaded (${#TUNNEL_TOKEN} chars)"

# ============================================================
# 2. 构建 Docker 镜像
# ============================================================
echo ""
echo "=== Building ${IMAGE} ==="
docker build --build-arg REGISTRY="${REGISTRY}" -t "${IMAGE}" -f ../Dockerfile ..
echo "Build complete"

# ============================================================
# 3. 推送到本地 Registry
# ============================================================
echo ""
echo "=== Pushing to registry ==="
docker push "${IMAGE}"
echo "Push complete"

# ============================================================
# 4. 部署到 K8s
# ============================================================
K="--kubeconfig=/etc/kubernetes/super-admin.conf"

echo ""
echo "=== Deploying to K8s ==="

# 创建 namespace
kubectl create namespace cloudflare-tunnel --dry-run=client -o yaml $K | kubectl apply $K -f -

# 创建/更新 tunnel token Secret
kubectl create secret generic tunnel-credentials \
    --from-literal=token="${TUNNEL_TOKEN}" \
    --namespace cloudflare-tunnel \
    --dry-run=client -o yaml $K | kubectl apply $K -f -

# 应用所有 K8s 资源
kubectl apply -f namespace.yaml $K
kubectl apply -f tunnel-configmap.yaml $K 2>/dev/null || true
kubectl apply -f service.yaml $K

# 渲染 deployment 并替换镜像名
sed "s|cloudflare-tunnel-operator:latest|${IMAGE}|g" deployment.yaml | kubectl apply $K -f -

# ============================================================
# 5. 验证
# ============================================================
echo ""
echo "=== Waiting for cloudflared to start... ==="
sleep 10
kubectl get pods -n cloudflare-tunnel $K
echo ""
echo "=== Recent logs ==="
kubectl logs -n cloudflare-tunnel -l app.kubernetes.io/name=cloudflared --tail=10 $K 2>/dev/null || true

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "  Check status: kubectl get pods -n cloudflare-tunnel"
echo "  Check logs:   kubectl logs -f -n cloudflare-tunnel -l app.kubernetes.io/name=cloudflared"
echo "============================================"
