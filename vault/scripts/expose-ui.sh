#!/bin/bash
# ============================================================
#  暴露 Vault UI 到局域网 — 将 Service 改为 NodePort
#
#  用法:
#    bash scripts/expose-ui.sh                    # 使用随机 NodePort
#    bash scripts/expose-ui.sh 31200              # 指定固定端口
#    bash scripts/expose-ui.sh --cluster          # 改回 ClusterIP（取消暴露）
#
#  访问地址:
#    http://<集群任一节点IP>:<NodePort>
#    例如: http://192.168.137.101:31200
#
#  注意:
#    - Vault 当前为 tls_disable=true（HTTP），仅限内网访问
#    - 不要将 8200/31200 端口暴露到公网！
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

VAULT_NS="vault"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

# ============================================================
#  获取 Master IP
# ============================================================
MASTER_IP=""
if [ -f "../cluster_config.sh" ]; then
    source "../cluster_config.sh"
    MASTER_IP="${MASTER_IP:-}"
fi
if [ -z "${MASTER_IP}" ]; then
    MASTER_IP=$(kubectl get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo "192.168.137.101")
fi

# ============================================================
#  检查当前 Service 类型
# ============================================================
CURRENT_TYPE=$(kubectl get svc vault -n ${VAULT_NS} $K -o jsonpath='{.spec.type}' 2>/dev/null || echo "ClusterIP")
echo "当前 Service 类型: ${CURRENT_TYPE}"

# ============================================================
#  处理 --cluster 参数（改回 ClusterIP）
# ============================================================
if [ "${1:-}" = "--cluster" ]; then
    echo "=== 改回 ClusterIP（取消局域网暴露）==="
    kubectl patch svc vault -n ${VAULT_NS} $K -p '{"spec":{"type":"ClusterIP"}}'
    echo "  已改回 ClusterIP"
    echo "  Vault 仅在集群内部可访问: http://vault.${VAULT_NS}.svc.cluster.local:8200"
    exit 0
fi

# ============================================================
#  改为 NodePort
# ============================================================
echo ""
echo "=== 将 Vault Service 改为 NodePort ==="

kubectl patch svc vault -n ${VAULT_NS} $K -p '{"spec":{"type":"NodePort"}}'

# ============================================================
#  如果指定了固定端口，应用
# ============================================================
FIXED_PORT="${1:-}"
if [ -n "${FIXED_PORT}" ]; then
    echo ""
    echo "=== 设置固定 NodePort: ${FIXED_PORT} ==="
    kubectl patch svc vault -n ${VAULT_NS} $K --type='json' \
        -p="[{\"op\":\"replace\",\"path\":\"/spec/ports/0/nodePort\",\"value\":${FIXED_PORT}}]"
fi

# ============================================================
#  获取最终端口信息
# ============================================================
echo ""
echo "=== Vault Service 信息 ==="
kubectl get svc vault -n ${VAULT_NS} $K

NODE_PORT=$(kubectl get svc vault -n ${VAULT_NS} $K -o jsonpath='{.spec.ports[?(@.port==8200)].nodePort}')

echo ""
echo "============================================"
echo "  Vault UI 已可通过以下地址访问："
echo ""
echo "  http://${MASTER_IP}:${NODE_PORT}"
echo ""
echo "  其他网段节点也可以访问（替换 IP 即可）："
echo "  http://nanopct4-server1:${NODE_PORT}"
echo "  http://orangepi5-max-server1:${NODE_PORT}"
echo ""
echo "  登录：使用 root token"
echo ""
echo "  如需取消暴露："
echo "  bash scripts/expose-ui.sh --cluster"
echo "============================================"
