#!/usr/bin/env bash
# ============================================================
# Vault CLI 登录恢复脚本
#
# 部署/运行方式:
#   cd ~/armbianbegin/vault
#   bash scripts/login.sh
#   bash scripts/login.sh --interactive
#   bash scripts/login.sh --from-file /secure/path/vault-init.json
#
# 默认在 Vault Pod 内已有有效 token 时直接返回；否则从凭证文件读取
# root_token，或在交互终端中隐藏输入。Token 通过 stdin 传给 Vault CLI，
# 不写入 shell history，也不出现在 kubectl 命令参数中。
# ============================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

VAULT_NS="vault"
VAULT_POD="vault-0"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
export KUBECONFIG

CREDENTIAL_FILE=""
FORCE=false
INTERACTIVE=false

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    sed -n '2,13p' "${SCRIPT_DIR}/login.sh"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from-file)
            [[ $# -ge 2 ]] || fail "--from-file 需要指定 vault-init.json 路径"
            CREDENTIAL_FILE="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --interactive)
            INTERACTIVE=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "未知参数: $1"
            ;;
    esac
done

command -v kubectl >/dev/null 2>&1 || fail "缺少 kubectl"
command -v python3 >/dev/null 2>&1 || fail "缺少 python3"
[[ -f "${KUBECONFIG}" ]] || fail "找不到 kubeconfig: ${KUBECONFIG}"
kubectl -n "${VAULT_NS}" get pod "${VAULT_POD}" >/dev/null 2>&1 || \
    fail "Vault Pod ${VAULT_NS}/${VAULT_POD} 未找到"

status_json="$(kubectl -n "${VAULT_NS}" exec "${VAULT_POD}" -- vault status -format=json 2>/dev/null || true)"
sealed="$(printf '%s' "${status_json}" | python3 -c '
import json, sys
try:
    print(str(json.load(sys.stdin).get("sealed", True)).lower())
except Exception:
    print("true")
')"
[[ "${sealed}" == "false" ]] || fail "Vault 尚未解封，请先运行 bash scripts/unseal.sh --interactive"

if [[ "${FORCE}" == false ]] && \
   kubectl -n "${VAULT_NS}" exec "${VAULT_POD}" -- vault token lookup >/dev/null 2>&1; then
    echo "Vault CLI 已登录，token 有效"
    exit 0
fi

if [[ "${INTERACTIVE}" == false && -z "${CREDENTIAL_FILE}" && -f "vault-credentials/vault-init.json" ]]; then
    CREDENTIAL_FILE="vault-credentials/vault-init.json"
fi

ROOT_TOKEN=""
if [[ -n "${CREDENTIAL_FILE}" ]]; then
    [[ -f "${CREDENTIAL_FILE}" ]] || fail "凭证文件不存在: ${CREDENTIAL_FILE}"
    ROOT_TOKEN="$(python3 -c '
import json, sys
with open(sys.argv[1]) as stream:
    print(json.load(stream).get("root_token", ""))
' "${CREDENTIAL_FILE}")"
    [[ -n "${ROOT_TOKEN}" ]] || fail "凭证文件中没有 root_token"
    echo "正在从指定凭证文件恢复 Vault CLI 登录"
else
    [[ -t 0 ]] || fail "当前不是交互终端，请使用 --from-file 提供 vault-init.json"
    read -r -s -p '请输入 Vault Root Token: ' ROOT_TOKEN
    printf '\n'
    [[ -n "${ROOT_TOKEN}" ]] || fail "Root Token 不能为空"
fi

# Vault CLI 的 '-' 参数会从 stdin 读取 token，并将有效 token 缓存在 Pod 内。
if ! printf '%s\n' "${ROOT_TOKEN}" | \
    kubectl -n "${VAULT_NS}" exec -i "${VAULT_POD}" -- vault login -no-print - >/dev/null; then
    ROOT_TOKEN=""
    fail "Vault 登录失败，请确认使用的是 root_token，而不是 unseal key"
fi
ROOT_TOKEN=""

kubectl -n "${VAULT_NS}" exec "${VAULT_POD}" -- vault token lookup >/dev/null 2>&1 || \
    fail "Vault 登录后 token lookup 验证失败"

echo "Vault CLI 登录已恢复"
