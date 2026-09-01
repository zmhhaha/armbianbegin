#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# 通过 Casdoor 授权码流程换取 OpenSpec 可用的 JWT（浏览器方式，无需 Casdoor 密码）。
#
# 前置（一次性）：panghu-suite 应用的 redirect_uris 需包含
#   https://openspec.panghuer.top/mcp
# 添加方式：
#   - Casdoor 管理员 UI：应用 → panghu-suite → Redirect URLs 增加
#     https://openspec.panghuer.top/mcp
#   - 或 DBA 执行（需重启 casdoor 刷新缓存）：
#     UPDATE application SET redirect_uris = JSON_ARRAY_APPEND(redirect_uris, '$',
#       'https://openspec.panghuer.top/mcp') WHERE name='panghu-suite';
#
# 用法：
#   bash openspec_service/scripts/get-token.sh
# 输出：打印 JWT 到 stdout，同时写入 ${OUT:-/tmp/casdoor.jwt}
# ============================================================

CLIENT_ID="${CLIENT_ID:-ece3f52410b046fe0952}"
CLIENT_SECRET="${CLIENT_SECRET:-${CASDOOR_CLIENT_SECRET:-''}}"
REDIRECT_URI="${REDIRECT_URI:-https://openspec.panghuer.top/mcp}"
CASDOOR_URL="${CASDOOR_URL:-https://auth.panghuer.top}"
OUT="${OUT:-/tmp/casdoor.jwt}"

AUTH_URL="${CASDOOR_URL}/login/oauth/authorize?client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&response_type=code&scope=openid%20profile%20email&state=openspec-token"

echo "1) 在浏览器打开下面链接（已登录 Casdoor 会自动跳转）："
echo "   ${AUTH_URL}"
echo "2) 跳转后地址栏形如："
echo "   ${REDIRECT_URI}?code=XXXX&state=openspec-token"
echo "   把【整个地址】粘贴到下面（页面显示 404/空白是正常的，code 在地址栏里）："
read -r -p "   callback URL: " CALLBACK_URL

code="$(printf '%s' "${CALLBACK_URL}" | python3 -c "import sys,urllib.parse as u; q=u.parse_qs(u.urlparse(sys.stdin.read().strip()).query); print(q.get('code',[''])[0])")"
[[ -n "${code}" ]] || { echo "ERROR: 未能从 URL 中提取 code" >&2; exit 1; }

resp="$(curl -s -m 15 -X POST "${CASDOOR_URL}/api/login/oauth/access_token" \
  -d "grant_type=authorization_code" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "code=${code}" \
  -d "redirect_uri=${REDIRECT_URI}")"
token="$(printf '%s' "${resp}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")"
[[ -n "${token}" ]] || { echo "ERROR: 交换失败：$(printf '%s' "${resp}" | head -c 200)" >&2; exit 1; }

printf '%s\n' "${token}" | tee "${OUT}"
echo "== 已写入 ${OUT}。下一步："
echo "CASDOOR_JWT=\"\$(cat ${OUT})\" bash openspec_service/scripts/preflight.sh --jwt \"\$(cat ${OUT})\""
