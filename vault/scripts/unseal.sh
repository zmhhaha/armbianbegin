#!/bin/bash
# ============================================================
#  Vault 解封辅助脚本
#  用途: Vault Pod 重启后需要重新解封
#
#  用法:
#    bash scripts/unseal.sh                    # 交互式输入 keys
#    bash scripts/unseal.sh <key1> <key2> <key3>  # 直接传入 3 个 key
#    bash scripts/unseal.sh --from-file <file> # 从文件读取（待实现）
#
#  注意:
#    需要 3/5 个 unseal keys 的解封阈值才能生效
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

VAULT_NS="vault"
VAULT_POD="vault-0"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

# 检查 Vault Pod 是否运行
if ! kubectl get pod ${VAULT_POD} -n ${VAULT_NS} $K &>/dev/null; then
    echo "ERROR: Vault Pod ${VAULT_NS}/${VAULT_POD} 未找到"
    echo "请确保 Vault 已部署"
    exit 1
fi

# 检查是否已解封
SEAL_STATUS=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status -format=json 2>/dev/null || echo '{"sealed":false}')
SEALED=$(echo "${SEAL_STATUS}" | grep -o '"sealed":[^,}]*' | cut -d: -f2 | tr -d ' "')

if [ "${SEALED}" = "false" ]; then
    echo "Vault 已经解封，无需操作"
    exit 0
fi

# 从命令行参数获取 keys
if [ $# -ge 3 ]; then
    echo "=== 从命令行参数解封 ==="
    KEYS=("$1" "$2" "$3")
elif [ $# -eq 1 ] && [ "$1" = "--interactive" ]; then
    # 交互式输入
    echo "=== 交互式解封 ==="
    echo "请输入 3 个 unseal keys（建议从 vault-credentials/vault-init.json 获取）:"
    KEYS=()
    for i in 1 2 3; do
        read -s -p "  Unseal key ${i}: " KEY
        echo ""
        KEYS+=("${KEY}")
    done
elif [ -f "vault-credentials/vault-init.json" ]; then
    # 从保存的凭证文件读取
    echo "=== 从 vault-credentials/vault-init.json 解封 ==="
    KEYS=()
    while IFS= read -r key; do
        KEYS+=("$key")
    done < <(python3 -c "
import json
with open('vault-credentials/vault-init.json') as f:
    data = json.load(f)
for k in data['unseal_keys_b64'][:3]:
    print(k)
" 2>/dev/null || echo "")

    if [ ${#KEYS[@]} -lt 3 ]; then
        echo "WARNING: 无法从文件中读取 unseal keys"
        echo "请手动输入"
        KEYS=()
        for i in 1 2 3; do
            read -s -p "  Unseal key ${i}: " KEY
            echo ""
            KEYS+=("${KEY}")
        done
    fi
else
    echo "ERROR: 请提供 unseal keys"
    echo "用法: bash scripts/unseal.sh <key1> <key2> <key3>"
    exit 1
fi

# 执行解封
echo ""
echo "=== 开始解封 Vault ==="
for i in 0 1 2; do
    echo "  应用 unseal key $((i+1))/3..."
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault operator unseal "${KEYS[$i]}"
done

# 验证
echo ""
echo "=== 验证解封状态 ==="
kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status 2>/dev/null | grep -E "(Sealed|Version|Cluster Name|HA Cluster)" || true

SEAL_STATUS_AFTER=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status -format=json 2>/dev/null || echo '{"sealed":true}')
SEALED_AFTER=$(echo "${SEAL_STATUS_AFTER}" | grep -o '"sealed":[^,}]*' | cut -d: -f2 | tr -d ' "')

if [ "${SEALED_AFTER}" = "false" ]; then
    echo ""
    echo "  ✅ Vault 已成功解封！"
    echo ""
    echo "  后续操作:"
    echo "    1. 验证 ESO 连接: kubectl get clustersecretstore vault-backend"
    echo "    2. 验证 ExternalSecret 同步状态"
else
    echo ""
    echo "  ❌ Vault 仍处于封禁状态"
    echo "  请检查 Pod 状态: kubectl describe pod -n ${VAULT_NS} ${VAULT_POD}"
fi

# 重置token和key
# root@arm-cluster-master:~/armbianbegin/vault# kubectl exec -n vault vault-0 -- vault operator init -key-shares=5 -key-threshold=3