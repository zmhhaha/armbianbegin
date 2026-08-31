#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# 校验/修复 OpenSpec 的 Gitea 服务账号与 Vault 凭据（幂等）。
#   - 校验 Gitea token 有效性、组织存在性、用户邮箱对 token 可见
#   - 用 vault kv patch 把凭据写入 Vault（保留 database_url，避免 kv put 覆盖）
#   - 触发 ExternalSecret 同步并重启服务
# 在 master（或持有 kubeconfig 的机器）上运行：
#   GITEA_TOKEN=xxx GITEA_USERNAME=zmh_haha bash openspec_service/scripts/provision-gitea.sh
# 环境变量：
#   GITEA_URL      默认 https://gitea.panghuer.top
#   GITEA_TOKEN    必需（Gitea 用户 token，需 read:user + 仓库创建/内容/collaborator）
#   GITEA_USERNAME 必需（token 所属 Gitea 登录名，例如 zmh_haha）
#   GITEA_OWNER    默认 openspec-service
#   CHECK_USER     默认 ${GITEA_USERNAME}，用于验证邮箱可见性
#   CREATE_ORG=1   组织不存在时自动创建
# ============================================================

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd -- "${SERVICE_DIR}/.." && pwd)"
if [[ -f "${REPO_ROOT}/cluster_config.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/cluster_config.sh"
fi

KUBECTL="${KUBECTL:-kubectl}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
export KUBECONFIG
NAMESPACE="${NAMESPACE:-openspec}"

: "${GITEA_URL:=https://gitea.panghuer.top}"
: "${GITEA_OWNER:=openspec-service}"
: "${GITEA_USERNAME:?Set GITEA_USERNAME to the Gitea login the token belongs to}"
: "${GITEA_TOKEN:?Set GITEA_TOKEN}"
CHECK_USER="${CHECK_USER:-${GITEA_USERNAME}}"
CREATE_ORG="${CREATE_ORG:-0}"

command -v "${KUBECTL}" >/dev/null 2>&1 || { echo "ERROR: ${KUBECTL} 命令不可用" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 命令不可用" >&2; exit 1; }

api() { curl -fsS -m 12 -H "Authorization: token ${GITEA_TOKEN}" -H 'Content-Type: application/json' "$@"; }
jget() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

echo "== 1. 校验 Gitea token =="
me="$(api "${GITEA_URL}/api/v1/user")"
login="$(printf '%s' "${me}" | jget "d.get('login','')")"
[[ -n "${login}" ]] || { echo "ERROR: Gitea token 无效（${GITEA_URL}）" >&2; exit 1; }
echo "  ✓ token 有效，所属登录名=${login}"

echo "== 2. 确认组织 ${GITEA_OWNER} =="
if org="$(api "${GITEA_URL}/api/v1/orgs/${GITEA_OWNER}" 2>/dev/null)"; then
  echo "  ✓ 组织已存在"
else
  if [[ "${CREATE_ORG}" == "1" ]]; then
    api -X POST "${GITEA_URL}/api/v1/orgs" -d "{\"username\":\"${GITEA_OWNER}\",\"visibility\":\"private\"}" >/dev/null
    echo "  ✓ 已创建组织 ${GITEA_OWNER}"
  else
    echo "  WARN: 组织 ${GITEA_OWNER} 不存在（可设 CREATE_ORG=1 自动创建）"
  fi
fi

echo "== 3. 邮箱可见性检查 (${CHECK_USER}) =="
search="$(api "${GITEA_URL}/api/v1/users/search?q=${CHECK_USER}")"
email="$(printf '%s' "${search}" | python3 -c "import json,sys; d=json.load(sys.stdin); u=next((x for x in d.get('data',[]) if x.get('login')=='${CHECK_USER}'),{}); print(u.get('email') or '')")"
if [[ -n "${email}" ]]; then
  echo "  ✓ ${CHECK_USER} 邮箱对 token 可见: ${email}"
else
  echo "ERROR: ${CHECK_USER} 邮箱不可见，身份绑定会 409；请将该用户邮箱设为公开，或使用有 read:user 权限的 token" >&2
  exit 1
fi

echo "== 4. 同步到 Vault（kv patch，保留 database_url） =="
"${KUBECTL}" -n vault exec vault-0 -- vault kv patch secret/openspec/service \
  "gitea_provision_token=${GITEA_TOKEN}" "gitea_username=${GITEA_USERNAME}" >/dev/null
keys="$("${KUBECTL}" -n vault exec vault-0 -- vault kv get -format=json secret/openspec/service \
  | python3 -c 'import json,sys; print(" ".join(sorted(json.load(sys.stdin).get("data",{}).get("data",{}).keys())))')"
echo "  ✓ 已写入。Vault 现有键: ${keys}"

echo "== 5. 触发 ExternalSecret 同步并重启服务 =="
"${KUBECTL}" -n "${NAMESPACE}" annotate externalsecret openspec-service-secrets \
  "force-sync=$(date +%s)" --overwrite >/dev/null
"${KUBECTL}" -n "${NAMESPACE}" wait --for=condition=Ready \
  externalsecret/openspec-service-secrets --timeout=120s
"${KUBECTL}" -n "${NAMESPACE}" rollout restart deployment/openspec-service

echo "== 完成。建议随后运行 scripts/preflight.sh --jwt <JWT> 复核 =="
