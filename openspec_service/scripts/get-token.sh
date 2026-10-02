#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# 通过 Casdoor 授权码 + PKCE 换一把 OpenSpec 可用的 JWT（浏览器方式，无需 Casdoor 密码）。
#
# 2026-10-02 起改用 **MCP 专用应用**（公共客户端）：
#   - client_id 315cbdaf565b82103c6f，**不需要 client_secret**（实测不带 secret 也返回 200）
#   - redirect_uri 走 http://localhost:39399/callback（该应用登记的是 http://localhost:*，
#     这个具体地址是端到端实测通过的）
#
# 这条路径替代了原来的 `GET /token` 网页版领取器 —— 那个页面（连它印的 claude/codex mcp add
# 用法）已退役归档在 oauth/token-dispenser/；标准 MCP 客户端改走 RFC 9728 发现 + OAuth 2.1，
# 不再需要人工取 JWT。本脚本留给**脚本/命令行**用（mcp-call.sh、register-project.sh、
# smoke-test*.sh、preflight.sh 都靠它拿凭据）。
#
# 用法：
#   bash openspec_service/scripts/get-token.sh
# 输出：打印 JWT 到 stdout，同时写入 ${OUT:-/tmp/casdoor.jwt}
# ============================================================

CLIENT_ID="${CLIENT_ID:-315cbdaf565b82103c6f}"
REDIRECT_URI="${REDIRECT_URI:-http://localhost:39399/callback}"
CASDOOR_URL="${CASDOOR_URL:-https://auth.panghuer.top}"
OUT="${OUT:-/tmp/casdoor.jwt}"

VERIFIER="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="))')"
CHALLENGE="$(python3 -c 'import base64,hashlib,sys;print(base64.urlsafe_b64encode(hashlib.sha256(sys.argv[1].encode()).digest()).decode().rstrip("="))' "${VERIFIER}")"
STATE="openspec-get-token"

AUTH_URL="${CASDOOR_URL}/login/oauth/authorize?client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&response_type=code&scope=openid%20profile%20email&state=${STATE}&code_challenge=${CHALLENGE}&code_challenge_method=S256"

echo "1) 在浏览器打开下面链接（已登录 Casdoor 会自动跳转）："
echo "   ${AUTH_URL}"
echo "2) 跳转后地址栏形如："
echo "   ${REDIRECT_URI}?code=XXXX&state=${STATE}"
echo "   把【整个地址】粘贴到下面（浏览器提示无法连接是正常的，code 就在地址栏里）："
read -r -p "   callback URL: " CALLBACK_URL

read -r code state <<<"$(printf '%s' "${CALLBACK_URL}" | python3 -c "import sys,urllib.parse as u; q=u.parse_qs(u.urlparse(sys.stdin.read().strip()).query); print(q.get('code',[''])[0], q.get('state',[''])[0])")"
[[ -n "${code}" ]] || { echo "ERROR: 未能从 URL 中提取 code" >&2; exit 1; }
[[ "${state}" == "${STATE}" ]] || { echo "ERROR: state 不匹配（期望 ${STATE}，收到 ${state}）" >&2; exit 1; }

resp="$(curl -s -m 15 -X POST "${CASDOOR_URL}/api/login/oauth/access_token" \
  -d "grant_type=authorization_code" \
  -d "client_id=${CLIENT_ID}" \
  -d "code=${code}" \
  -d "redirect_uri=${REDIRECT_URI}" \
  -d "code_verifier=${VERIFIER}")"
token="$(printf '%s' "${resp}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")"
[[ -n "${token}" ]] || { echo "ERROR: 交换失败：$(printf '%s' "${resp}" | head -c 200)" >&2; exit 1; }

printf '%s\n' "${token}" | tee "${OUT}"
echo "== 已写入 ${OUT}。下一步："
echo "CASDOOR_JWT=\"\$(cat ${OUT})\" bash openspec_service/scripts/preflight.sh --jwt \"\$(cat ${OUT})\""
