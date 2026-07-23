#!/bin/bash
# ============================================================
#  Vault Kubernetes Auth 修复脚本
#  用途: Vault 重启后 ESO 无法登录 Vault（403 permission denied）
#        时，刷新 auth/kubernetes/config 的 token_reviewer_jwt。
#
#  原理:
#    - Vault 的 K8s auth 需要一个有 system:auth-delegator 权限的
#      SA 的 JWT 作为 token_reviewer_jwt，用于调用 TokenReview API。
#    - 使用 kubectl create token 生成的 JWT 默认 1 小时过期，
#      而 Kubernetes SA token Secret（kubernetes.io/service-account-token）
#      不会过期。
#    - 本脚本会为 vault SA 和 external-secrets SA 各创建一个长期
#      有效的 token Secret，并用 vault 的 token 作为 reviewer。
#
#  用法:
#    bash scripts/fix-eso-auth.sh              # 修复 ESO 连接
#    bash scripts/fix-eso-auth.sh --check-only  # 仅检查状态
#    bash scripts/fix-eso-auth.sh --force       # 强制刷新 token
#
#  适用场景:
#    - ClusterSecretStore vault-backend 报 InvalidProviderConfig
#    - ESO 日志报: unable to log in with Kubernetes auth: permission denied
#    - Vault 解封后所有 ExternalSecret 报 "ClusterSecretStore is not ready"
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

VAULT_NS="vault"
VAULT_POD="vault-0"
ESO_NS="external-secrets"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

SA_TOKEN_SECRET_ESO="external-secrets-token"
SA_TOKEN_SECRET_VAULT="vault-token"

# ── 颜色 ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC}  $*"; }

# ── 仅检查模式 ──
check_only() {
    echo ""
    echo "=== ESO 连接状态检查 ==="

    echo ""
    echo "1️⃣  ClusterSecretStore 状态:"
    STORE_STATUS=$(kubectl get clustersecretstore vault-backend -o yaml | grep -E "Reason:|Message:" | head -4)
    echo "$STORE_STATUS"

    echo ""
    echo "2️⃣  Vault 状态:"
    VAULT_STATUS=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status -format=json 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Sealed: {d.get(\"sealed\")}' if d.get('sealed') is not None else '  无法连接')" 2>/dev/null || echo "  无法连接")
    echo "$VAULT_STATUS"

    echo ""
    echo "3️⃣  Vault K8s auth config 是否已配置 token_reviewer_jwt:"
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault read auth/kubernetes/config 2>&1 | grep -q "token_reviewer_jwt_set" && \
      echo "  已配置 ✅" || echo "  未配置 ❌"

    echo ""
    echo "4️⃣  ESO SA 能否登录 Vault:"
    ESO_JWT=$(kubectl get secret ${SA_TOKEN_SECRET_ESO} -n ${ESO_NS} -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)
    if [ -n "$ESO_JWT" ]; then
        kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault write auth/kubernetes/login role=eso-role jwt="$ESO_JWT" &>/dev/null && \
          echo "  登录成功 ✅" || echo "  登录失败 ❌"
    else
        echo "  ESO token secret 不存在 ❌"
    fi

    echo ""
    echo "5️⃣  ExternalSecret 同步状态:"
    kubectl get externalsecret -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,REASON:.status.conditions[0].reason,MESSAGE:.status.conditions[0].message' 2>/dev/null | \
      awk 'NR==1 || NR>1 && ($3!="Synced" && $3!="SecretSynced")'

    echo ""
    return 0
}

ensure_sa_token_secret() {
    local sa_name="$1"
    local ns="$2"
    local secret_name="$3"

    if ! kubectl get secret "${secret_name}" -n "${ns}" &>/dev/null; then
        info "为 SA ${ns}/${sa_name} 创建长期 token Secret..."
        kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${secret_name}
  namespace: ${ns}
  annotations:
    kubernetes.io/service-account.name: ${sa_name}
type: kubernetes.io/service-account-token
EOF
        sleep 3
    fi
}

fix_auth() {
    info "确保长期 token Secret 存在..."
    ensure_sa_token_secret "vault" "${VAULT_NS}" "${SA_TOKEN_SECRET_VAULT}"
    ensure_sa_token_secret "external-secrets" "${ESO_NS}" "${SA_TOKEN_SECRET_ESO}"

    echo ""
    info "获取 vault SA JWT（用作 token_reviewer）..."
    VAULT_JWT=$(kubectl get secret "${SA_TOKEN_SECRET_VAULT}" -n "${VAULT_NS}" -o jsonpath='{.data.token}' | base64 -d)

    echo ""
    info "更新 Vault K8s auth config..."
    kubectl exec -n "${VAULT_NS}" "${VAULT_POD}" -- vault write auth/kubernetes/config \
      kubernetes_host="https://kubernetes.default.svc.cluster.local:443" \
      token_reviewer_jwt="${VAULT_JWT}"

    echo ""
    info "验证 ESO SA 登录 Vault..."
    ESO_JWT=$(kubectl get secret "${SA_TOKEN_SECRET_ESO}" -n "${ESO_NS}" -o jsonpath='{.data.token}' | base64 -d)
    if kubectl exec -n "${VAULT_NS}" "${VAULT_POD}" -- vault write auth/kubernetes/login role=eso-role jwt="${ESO_JWT}" &>/dev/null; then
        echo "  ESO SA 登录成功 ✅"
    else
        echo "  ESO SA 登录失败 ❌"
        exit 1
    fi

    echo ""
    info "重启 ESO Pod..."
    kubectl rollout restart deployment -n "${ESO_NS}" external-secrets
    echo "  等待 ESO 就绪..."
    sleep 10

    echo ""
    info "强制所有 ExternalSecret 重新同步..."
    SECRETS=$(kubectl get externalsecret -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}')
    echo "${SECRETS}" | while read -r ns name; do
        kubectl annotate externalsecret "${name}" -n "${ns}" force-sync=$(date +%s) --overwrite &>/dev/null || true
    done
    sleep 5

    echo ""
    info "验证同步状态..."
    kubectl get externalsecret -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,REASON:.status.conditions[0].reason,MESSAGE:.status.conditions[0].message'
}

# ============================================================
#  入口
# ============================================================
case "${1:-}" in
    --check-only|-c)
        check_only
        ;;
    --force|-f)
        fix_auth
        ;;
    --help|-h)
        echo "用法: $0 [--check-only|--force|--help]"
        echo ""
        echo "  (无参数)  检查 + 修复（如果没恢复）"
        echo "  --check-only  仅检查不做修改"
        echo "  --force       强制刷新 token 并重启 ESO"
        ;;
    *)
        echo "=== Vault K8s Auth 修复工具 ==="
        echo ""
        check_only
        echo ""
        # 如果未修复，自动运行修复
        STORE_OK=$(kubectl get clustersecretstore vault-backend -o yaml | grep -c "Valid" 2>/dev/null || true)
        ESO_OK=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault write auth/kubernetes/login \
          role=eso-role jwt="$(kubectl get secret external-secrets-token -n ${ESO_NS} -o jsonpath='{.data.token}' 2>/dev/null | base64 -d)" &>/dev/null && echo "ok" || echo "")
        if [ -z "${ESO_OK}" ] || [ "${STORE_OK}" -eq 0 ]; then
            echo ""
            warn "检测到异常，自动修复中..."
            fix_auth
        else
            info "一切正常，无需修复 ✅"
        fi
        ;;
esac
