#!/bin/bash
# ============================================================
#  Vault 初始化脚本
#  功能：
#    1. 等待 Vault Pod 启动
#    2. 初始化 Vault（生成 root token + unseal keys）— 仅首次
#    3. 解封 Vault — 每次重启后需要
#    4. 登录 Vault
#    5. Enable KV v2 secrets engine（默认路径 secret/）
#    6. Enable Kubernetes auth method 并配置
#    7. 创建 policy 和 role（用于 ESO 读取）
#    8. 保存凭证到安全位置
#
#  用法:
#    bash scripts/init-vault.sh              # 交互式首次初始化
#    bash scripts/init-vault.sh --reconfig    # Vault 已运行，只执行配置部分
#
#  注意:
#    - 首次使用运行一次即可
#    - 生成的 unseal keys 和 root token 会保存到
#      ./vault-credentials/ 目录，请安全保管！
#    - 如果 Vault 重新部署（Pod 重建），需要重新解封
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

VAULT_NS="vault"
VAULT_POD="vault-0"
CRED_DIR="vault-credentials"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

ESO_SA="external-secrets"
ESO_NS="external-secrets"
ESO_ROLE="eso-role"
POLICY_NAME="kv-reader"

mkdir -p "${CRED_DIR}"

# ============================================================
#  1. 等待 Vault Pod 变为 Running
#  （注意：不能用 --for=condition=Ready，因为未初始化的 Vault
#    readiness probe 返回非 0，Pod 永远不会 Ready）
# ============================================================
echo "=== 等待 Vault Pod 启动 ==="
echo "  Pod: ${VAULT_NS}/${VAULT_POD}"
for i in $(seq 1 60); do
    POD_STATUS=$(kubectl get pod ${VAULT_POD} -n ${VAULT_NS} $K -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
    if [ "${POD_STATUS}" = "Running" ]; then
        echo "  ✅ Vault Pod 已 Running（第 ${i}s）"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "  ❌ 等待超时，请检查: kubectl describe pod -n ${VAULT_NS} ${VAULT_POD}"
        exit 1
    fi
    sleep 1
done

# ============================================================
#  2. 检查 Vault 初始化 + 封禁状态
# ============================================================
echo ""
echo "=== 检查 Vault 状态 ==="
STATUS_JSON=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status -format=json 2>/dev/null || echo '{"initialized":false,"sealed":true}')
INITIALIZED=$(echo "${STATUS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('initialized',False))" 2>/dev/null || echo "false")
SEALED=$(echo "${STATUS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed',True))" 2>/dev/null || echo "true")
echo "  Initialized: ${INITIALIZED}"
echo "  Sealed: ${SEALED}"

# ============================================================
#  3. 初始化（仅首次）
# ============================================================
DO_INIT=false
if [ "${INITIALIZED}" = "False" ] || [ "${INITIALIZED}" = "false" ]; then
    DO_INIT=true
fi

ROOT_TOKEN=""
UNSEAL_KEYS=()

if [ "${DO_INIT}" = true ]; then
    echo ""
    echo "============================================"
    echo "  Vault 未初始化 — 执行初始化"
    echo "============================================"
    echo ""
    echo "=== 初始化（生成 root token + 5 个 unseal keys）==="
    INIT_OUTPUT=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault operator init \
        -key-shares=5 \
        -key-threshold=3 \
        -format=json)

    # 保存到文件
    echo "${INIT_OUTPUT}" > "${CRED_DIR}/vault-init.json"

    # 提取变量
    ROOT_TOKEN=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['root_token'])" 2>/dev/null || echo "")
    while IFS= read -r key; do
        UNSEAL_KEYS+=("$key")
    done < <(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; [print(k) for k in json.load(sys.stdin)['unseal_keys_b64']]" 2>/dev/null || true)

    if [ -z "${ROOT_TOKEN}" ]; then
        echo "ERROR: 无法提取 root token"
        exit 1
    fi

    # 打印人类可读版本
    echo ""
    echo "${INIT_OUTPUT}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('=' * 60)
print('  VAULT CREDENTIALS — 请安全保管！')
print('=' * 60)
print()
print('Root Token:')
print('  ' + data['root_token'])
print()
print('Unseal Keys (5 份，任意 3 份可解封):')
for i, k in enumerate(data['unseal_keys_b64']):
    print(f'  {i+1}. {k}')
print()
print('恢复命令:')
print('  vault operator unseal <key1>')
print('  vault operator unseal <key2>')
print('  vault operator unseal <key3>')
print()
print('登录:')
print('  vault login <root_token>')
"
    echo ""
    echo "  凭证已保存到 ${CRED_DIR}/vault-init.json"
    echo ""
    echo "  ⚠️  请立即备份此文件到安全位置！"
    echo

else
    echo ""
    echo "Vault 已初始化，跳过初始化步骤"
    echo ""

    # 尝试从保存的凭证文件读取
    if [ -f "${CRED_DIR}/vault-init.json" ]; then
        ROOT_TOKEN=$(python3 -c "import json; print(json.load(open('${CRED_DIR}/vault-init.json'))['root_token'])" 2>/dev/null || echo "")
        while IFS= read -r key; do
            UNSEAL_KEYS+=("$key")
        done < <(python3 -c "import json; [print(k) for k in json.load(open('${CRED_DIR}/vault-init.json'))['unseal_keys_b64']]" 2>/dev/null || true)
        echo "  从 ${CRED_DIR}/vault-init.json 读取了凭证"
    fi
fi

# ============================================================
#  4. 解封（需要 root token 和 unseal keys 才能继续）
# ============================================================
if [ "${SEALED}" = "True" ] || [ "${SEALED}" = "true" ]; then
    echo ""
    echo "============================================"
    echo "  Vault 已封禁 — 执行解封"
    echo "============================================"

    # 如果没有 unseal keys，提示用户输入
    if [ ${#UNSEAL_KEYS[@]} -lt 3 ]; then
        echo ""
        echo "请在 vault-credentials/vault-init.json 中查找 5 个 Unseal Keys"
        echo "输入其中 3 个来解封 Vault："
        UNSEAL_KEYS=()
        for i in 1 2 3; do
            read -s -p "  Unseal key ${i}: " KEY
            echo ""
            UNSEAL_KEYS+=("${KEY}")
        done
    fi

    echo ""
    echo "=== 解封（需要 3/5 份 key）==="
    for i in 0 1 2; do
        kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault operator unseal "${UNSEAL_KEYS[$i]}"
        echo "  Unseal key $((i+1))/3 已应用"
    done

    # 验证解封状态
    SEAL_STATUS=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status -format=json 2>/dev/null || echo '{"sealed":true}')
    SEALED_AFTER=$(echo "${SEAL_STATUS}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed',True))" 2>/dev/null || echo "true")
    if [ "${SEALED_AFTER}" = "False" ] || [ "${SEALED_AFTER}" = "false" ]; then
        echo "Vault 已成功解封！"
    else
        echo "WARNING: Vault 可能仍处于封禁状态，请检查"
    fi
else
    echo ""
    echo "Vault 已解封，跳过解封步骤"
fi

# ============================================================
#  5. 登录 Vault
# ============================================================
echo ""
echo "=== 登录 Vault ==="

# 如果还没有 root token，提示输入
if [ -z "${ROOT_TOKEN}" ]; then
    read -s -p "  请输入 Root Token: " ROOT_TOKEN
    echo ""
fi

if [ -n "${ROOT_TOKEN}" ]; then
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault login "${ROOT_TOKEN}"
    echo "  登录成功"
else
    echo "  ⚠️  没有 Root Token，跳过后续配置"
    echo "  可稍后手动运行: kubectl exec -n vault vault-0 -- vault login <root_token>"
    echo "  然后重新运行: bash scripts/init-vault.sh --reconfig"
    exit 0
fi

# ============================================================
#  6. Enable KV v2 Secrets Engine
# ============================================================
echo ""
echo "=== 启用/检查 KV v2 Secrets Engine（secret/）==="
KV_LIST=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault secrets list -format=json 2>/dev/null || echo '{}')
KV_EXISTS=$(echo "${KV_LIST}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if any(k.startswith('secret/') for k in d) else 'false')" 2>/dev/null || echo "false")

if [ "${KV_EXISTS}" = "false" ]; then
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault secrets enable -path=secret kv-v2
    echo "  ✅ KV v2 已启用（路径: secret/）"
else
    echo "  ✅ KV v2 已存在，跳过"
fi

# ============================================================
#  7. Enable 并配置 Kubernetes Auth
# ============================================================
echo ""
echo "=== 配置 Kubernetes Auth ==="
AUTH_LIST=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault auth list -format=json 2>/dev/null || echo '{}')
K8S_AUTH_EXISTS=$(echo "${AUTH_LIST}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if any('kubernetes' in k for k in d) else 'false')" 2>/dev/null || echo "false")

if [ "${K8S_AUTH_EXISTS}" = "false" ]; then
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault auth enable kubernetes
    echo "  ✅ Kubernetes auth 已启用"
else
    echo "  ✅ Kubernetes auth 已存在，跳过"
fi

# 配置 K8s 连接
K8S_HOST="https://kubernetes.default.svc.cluster.local:443"
echo "=== 配置 Vault 连接 K8s API Server ==="
echo "  Kubernetes Host: ${K8S_HOST}"

# 获取 vault 自身的 SA token
VAULT_SA_TOKEN=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- cat /var/run/secrets/kubernetes.io/serviceaccount/token 2>/dev/null || echo "")
if [ -z "${VAULT_SA_TOKEN}" ]; then
    echo "  ⚠️  无法获取 Vault SA token，使用 disable_local_ca_jwt=true"
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- \
        vault write auth/kubernetes/config \
        kubernetes_host="${K8S_HOST}" \
        disable_local_ca_jwt=true
else
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- \
        vault write auth/kubernetes/config \
        kubernetes_host="${K8S_HOST}" \
        token_reviewer_jwt="${VAULT_SA_TOKEN}"
fi
echo "  ✅ K8s auth 配置完成"

# ============================================================
#  8. 创建 Policy
# ============================================================
echo ""
echo "=== 创建 Policy: ${POLICY_NAME} ==="
kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- sh -c "cat > /tmp/policy.hcl << 'EOF'
path \"secret/data/*\" {
  capabilities = [\"read\", \"list\"]
}
path \"secret/metadata/*\" {
  capabilities = [\"read\", \"list\"]
}
EOF"

kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault policy write "${POLICY_NAME}" /tmp/policy.hcl 2>/dev/null && \
    echo "  ✅ Policy '${POLICY_NAME}' 已创建" || \
    echo "  ✅ Policy '${POLICY_NAME}' 已存在，已覆盖"

# ============================================================
#  9. 创建 Role（绑定 ESO 的 ServiceAccount）
# ============================================================
echo ""
echo "=== 创建 Role: ${ESO_ROLE} ==="
kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- \
    vault write "auth/kubernetes/role/${ESO_ROLE}" \
    bound_service_account_names="${ESO_SA}" \
    bound_service_account_namespaces="${ESO_NS}" \
    policies="${POLICY_NAME}" \
    ttl="24h" 2>/dev/null && \
    echo "  ✅ Role '${ESO_ROLE}' 已创建（绑定 SA ${ESO_NS}/${ESO_SA}）" || \
    echo "  ✅ Role '${ESO_ROLE}' 已存在，已覆盖"

# ============================================================
#  10. 验证
# ============================================================
echo ""
echo "============================================"
echo "  Vault 初始化配置完成！"
echo "============================================"
echo ""
echo "  Vault Status:"
kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status 2>/dev/null | grep -E "(Sealed|Version|Cluster)" || true

echo ""
echo "  Auth Methods:"
kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault auth list 2>/dev/null | grep -E "(kubernetes|token)" || true

echo ""
echo "  Secrets Engines:"
kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault secrets list 2>/dev/null | grep "secret/" || true

if [ -f "${CRED_DIR}/vault-init.json" ]; then
    echo ""
    echo "  凭证已保存到: ${CRED_DIR}/"
    echo "    - vault-init.json（完整 JSON）"
    echo ""
    echo "  ⚠️  安全警告："
    echo "    请立即将 ${CRED_DIR}/ 目录备份到安全位置并删除本地的副本！"
    echo "    建议: gpg --symmetric vault-credentials/vault-init.json"
    echo "          然后 rm -rf vault-credentials/"
fi

echo ""
echo "  后续操作:"
echo "    1. 写入种子密钥: bash scripts/seed-secrets.sh"
echo "    2. 部署 ESO: bash deploy.sh --eso-only （或 helm 安装）"
echo "    3. 创建 ClusterSecretStore: kubectl apply -f k8s/cluster-secret-store.yaml"
echo "    4. 创建 ExternalSecret 同步到 K8s"
echo "============================================"
