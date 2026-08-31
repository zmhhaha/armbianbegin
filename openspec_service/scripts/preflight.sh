#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# OpenSpec 服务部署/运行前预检（只读，不修改集群状态）
# 在 master（或持有 kubeconfig 的机器）上运行：
#   bash openspec_service/scripts/preflight.sh [--jwt <casdoor_jwt>]
# 退出码：0 = 全部通过；1 = 存在 FAIL。
# 可选环境变量：KUBECTL, KUBECONFIG, CASDOOR_JWT, OIDC_AUDIENCE,
#   OIDC_ISSUER, GITEA_OWNER, CHECK_USER, NAMESPACE
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
CASDOOR_JWT="${CASDOOR_JWT:-}"
EXPECTED_AUDIENCE="${OIDC_AUDIENCE:-ece3f52410b046fe0952}"   # panghu-suite client_id
OIDC_ISSUER="${OIDC_ISSUER:-https://auth.panghuer.top}"
GITEA_OWNER="${GITEA_OWNER:-openspec-service}"
NAMESPACE="${NAMESPACE:-openspec}"
CHECK_USER="${CHECK_USER:-zmh_haha}"   # 需要能看到邮箱的 Gitea 用户

PASS=0; FAIL=0; WARN=0
say(){ printf '  [%s] %s\n' "$1" "$2"; }
ok(){ say PASS "$*"; PASS=$((PASS+1)); }
bad(){ say FAIL "$*"; FAIL=$((FAIL+1)); }
warn(){ say WARN "$*"; WARN=$((WARN+1)); }
fail_here(){ echo "ERROR: $*" >&2; exit 1; }
jget(){ python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

while (($# > 0)); do
  case "$1" in
    --jwt) CASDOOR_JWT="${2:-}"; shift 2 ;;
    --check-user) CHECK_USER="${2:-}"; shift 2 ;;
    -h|--help) echo "Usage: preflight.sh [--jwt <casdoor_jwt>] [--check-user <gitea_login>]"; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
done

command -v "${KUBECTL}" >/dev/null 2>&1 || fail_here "${KUBECTL} 命令不可用"
command -v python3 >/dev/null 2>&1 || fail_here "python3 命令不可用"
command -v curl >/dev/null 2>&1 || fail_here "curl 命令不可用"

echo "== OpenSpec 预检（只读）=="

echo "--- 1. Kubernetes 访问 ---"
"${KUBECTL}" version --request-timeout=10s >/dev/null 2>&1 \
  && ok "Kubernetes API 可达" || bad "无法连接 Kubernetes API（KUBECONFIG=${KUBECONFIG}）"
"${KUBECTL}" get ns "${NAMESPACE}" >/dev/null 2>&1 \
  && ok "namespace ${NAMESPACE} 存在" || bad "namespace ${NAMESPACE} 不存在"

CM_DATA="$("${KUBECTL}" -n "${NAMESPACE}" get cm openspec-service-config -o jsonpath='{.data}' 2>/dev/null || true)"
cm() { echo "${CM_DATA}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1',''))" 2>/dev/null || true; }
deployed_issuer="$(cm OIDC_ISSUER)"; deployed_jwks="$(cm OIDC_JWKS_URL)"
deployed_aud="$(cm OIDC_AUDIENCE)"; deployed_bootstrap="$(cm BOOTSTRAP_ADMIN_SUBJECTS)"

echo "--- 2. Casdoor / OIDC ---"
if [[ -z "${deployed_issuer}" ]]; then
  bad "ConfigMap openspec-service-config 未设置 OIDC_ISSUER"
  deployed_issuer="${OIDC_ISSUER}"
fi
discovery="$(curl -fsS -m 8 "${deployed_issuer}/.well-known/openid-configuration" 2>/dev/null || true)"
if [[ -n "${discovery}" ]]; then
  disc_issuer="$(printf '%s' "${discovery}" | jget "d.get('issuer','')")"
  disc_jwks="$(printf '%s' "${discovery}" | jget "d.get('jwks_uri','')")"
  [[ "${deployed_issuer}" == "${disc_issuer}" ]] \
    && ok "issuer 与 discovery 一致 (${deployed_issuer})" \
    || warn "issuer 与 discovery 不一致: 部署=${deployed_issuer} discovery=${disc_issuer}"
  [[ "${deployed_jwks}" == "${disc_jwks}" ]] \
    && ok "jwks_uri 与 discovery 一致" \
    || warn "jwks_uri 不一致: 部署=${deployed_jwks} discovery=${disc_jwks}"
else
  bad "无法访问 Casdoor discovery: ${deployed_issuer}/.well-known/openid-configuration"
fi

[[ "${deployed_aud}" == "${EXPECTED_AUDIENCE}" ]] \
  && ok "OIDC_AUDIENCE 正确 (${deployed_aud})" \
  || bad "OIDC_AUDIENCE 应为 ${EXPECTED_AUDIENCE}，当前为 ${deployed_aud}"
if [[ -z "${deployed_bootstrap}" || "${deployed_bootstrap}" == *REPLACE* ]]; then
  bad "BOOTSTRAP_ADMIN_SUBJECTS 为空或仍是占位符: '${deployed_bootstrap}'"
else
  ok "BOOTSTRAP_ADMIN_SUBJECTS 已配置: ${deployed_bootstrap}"
fi

if [[ -n "${CASDOOR_JWT}" ]]; then
  payload="$(printf '%s' "${CASDOOR_JWT}" | cut -d. -f2)"
  claims="$(python3 -c "import base64,sys,json; s=sys.stdin.read().strip(); s+='='*(-len(s)%4); print(json.dumps(json.loads(base64.urlsafe_b64decode(s))))" <<< "${payload}" 2>/dev/null || true)"
  if [[ -n "${claims}" ]]; then
    jwt_aud="$(printf '%s' "${claims}" | python3 -c "import json,sys; a=json.load(sys.stdin).get('aud',''); print(a if isinstance(a,str) else ','.join(a))")"
    jwt_email="$(printf '%s' "${claims}" | jget "d.get('email','')")"
    jwt_sub="$(printf '%s' "${claims}" | jget "d.get('sub','')")"
    case ",${jwt_aud}," in *",${EXPECTED_AUDIENCE},"*) ok "JWT aud 含 ${EXPECTED_AUDIENCE}（实际 ${jwt_aud}）";; *) bad "JWT aud=${jwt_aud} 与期望 ${EXPECTED_AUDIENCE} 不一致（所有请求都会被 401 拒绝）";; esac
    [[ -n "${jwt_email}" ]] && ok "JWT 含 email claim: ${jwt_email}" \
      || bad "JWT 缺少 email claim（身份绑定会失败，检查 Casdoor scope/用户邮箱）"
    [[ -n "${jwt_sub}" ]] && ok "JWT sub=${jwt_sub}" \
      || bad "JWT 缺少 sub"
    case " ${deployed_bootstrap} " in *" ${jwt_sub} "*) ok "JWT sub 在 BOOTSTRAP_ADMIN_SUBJECTS 中";; *) warn "JWT sub=${jwt_sub} 不在 BOOTSTRAP_ADMIN_SUBJECTS，无法创建项目";; esac
  else
    warn "无法解码 --jwt（不是合法的三段式 JWT？），跳过 claim 校验"
  fi
else
  warn "未提供 --jwt，跳过 JWT claim 校验（建议提供以验证 aud/email/sub）"
fi

echo "--- 3. Gitea ---"
GITEA_URL="$(cm GITEA_URL)"
if ! curl -fsS -m 5 "${GITEA_URL}/api/v1/version" >/dev/null 2>&1; then
  gitea_ip="$("${KUBECTL}" -n gitops get svc gitea -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)"
  gitea_port="$("${KUBECTL}" -n gitops get svc gitea -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || true)"
  if [[ -n "${gitea_ip}" ]]; then GITEA_URL="http://${gitea_ip}:${gitea_port}"; fi
fi
GITEA_TOKEN="${GITEA_TOKEN:-$("${KUBECTL}" -n "${NAMESPACE}" get secret openspec-service-secrets -o jsonpath='{.data.GITEA_TOKEN}' 2>/dev/null | base64 -d 2>/dev/null || true)}"
if [[ -z "${GITEA_TOKEN}" ]]; then
  bad "GITEA_TOKEN 不可用（env 或 secret openspec-service-secrets 中读取为空）"
else
  me="$(curl -fsS -m 8 -H "Authorization: token ${GITEA_TOKEN}" "${GITEA_URL}/api/v1/user" 2>/dev/null || true)"
  if [[ -n "${me}" ]]; then
    ok "Gitea token 有效（login=$(printf '%s' "${me}" | jget "d.get('login','')")）"
  else
    bad "Gitea token 无效或 Gitea API 不可达（${GITEA_URL}）——检查 secret 中 GITEA_TOKEN 是否被轮换/过期"
  fi
  org="$(curl -fsS -m 8 -H "Authorization: token ${GITEA_TOKEN}" "${GITEA_URL}/api/v1/orgs/${GITEA_OWNER}" 2>/dev/null || true)"
  [[ -n "${org}" ]] && ok "Gitea 组织 ${GITEA_OWNER} 存在" \
    || bad "Gitea 组织 ${GITEA_OWNER} 不存在或对 token 不可见"
  search="$(curl -fsS -m 8 -H "Authorization: token ${GITEA_TOKEN}" "${GITEA_URL}/api/v1/users/search?q=${CHECK_USER}" 2>/dev/null || true)"
  if [[ -n "${search}" ]]; then
    email="$(printf '%s' "${search}" | python3 -c "import json,sys; d=json.load(sys.stdin); u=next((x for x in d.get('data',[]) if x.get('login')=='${CHECK_USER}'),{}); print(u.get('email') or '')")"
    if [[ -n "${email}" ]]; then
      ok "Gitea 用户 ${CHECK_USER} 邮箱对 token 可见: ${email}"
    else
      bad "Gitea 用户 ${CHECK_USER} 邮箱不可见（read:user 读不到邮箱 → 身份绑定会 409）"
    fi
  else
    bad "Gitea 用户搜索失败"
  fi
fi

echo "--- 4. Vault ---"
sealed="$("${KUBECTL}" -n vault exec vault-0 -- vault status -format=json 2>/dev/null \
  | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["sealed"]).lower())' 2>/dev/null || true)"
[[ "${sealed}" == "false" ]] && ok "Vault 未 sealed" \
  || bad "Vault sealed 或不可达（sealed=${sealed}）"
kv="$("${KUBECTL}" -n vault exec vault-0 -- vault kv get -format=json secret/openspec/service 2>/dev/null \
  | python3 -c 'import json,sys; d=json.load(sys.stdin).get("data",{}).get("data",{}); print(" ".join(sorted(d.keys())))' 2>/dev/null || true)"
for k in gitea_provision_token gitea_username database_url; do
  case " ${kv} " in *" ${k} "*) ok "Vault secret/openspec/service 含 ${k}";; *) bad "Vault secret/openspec/service 缺少 ${k}（当前有: ${kv}）";; esac
done

echo "--- 5. 部署状态 ---"
es_ready="$("${KUBECTL}" -n "${NAMESPACE}" get externalsecret openspec-service-secrets \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
[[ "${es_ready}" == "True" ]] \
  && ok "ExternalSecret openspec-service-secrets Ready" \
  || bad "ExternalSecret 未 Ready（当前=${es_ready}；常见原因：Vault 缺 database_url 或 Gitea token 已过期）"
ready="$("${KUBECTL}" -n "${NAMESPACE}" get deploy openspec-service -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
[[ "${ready:-0}" -ge 1 ]] 2>/dev/null && ok "Deployment openspec-service 就绪" \
  || bad "Deployment openspec-service 未就绪"
pvc_phase="$("${KUBECTL}" -n "${NAMESPACE}" get pvc openspec-workspaces -o jsonpath='{.status.phase}' 2>/dev/null || true)"
[[ "${pvc_phase}" == "Bound" ]] && ok "PVC openspec-workspaces Bound" \
  || bad "PVC openspec-workspaces 未 Bound（${pvc_phase}）"
"${KUBECTL}" -n data get pod postgres-0 >/dev/null 2>&1 \
  && ok "PostgreSQL postgres-0 存在" || bad "PostgreSQL postgres-0 不存在"

echo
echo "== 结果: PASS=${PASS} FAIL=${FAIL} WARN=${WARN} =="
if (( FAIL > 0 )); then echo "存在 FAIL，请先修复后再部署。"; exit 1; fi
echo "全部通过。可以继续：bash openspec_service/scripts/deploy.sh --wait"
