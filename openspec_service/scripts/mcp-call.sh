#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
#  命令行调用 OpenSpec 的远程 MCP（streamable HTTP + JSON-RPC）
#
#  给「手上没有 MCP 客户端」的场景用：脚本、CI，或者 agent 自己要在 shell 里
#  读写 specs。协议版本 2025-06-18；认证是 Casdoor JWT（见 MCP_INTEGRATION.md §1）。
#
#  用法：
#    export CASDOOR_JWT='<Casdoor JWT>'      # 或写到 /tmp/casdoor.jwt（与其它脚本一致）
#    bash mcp-call.sh --check                # initialize + tools/list，连通性自检
#    bash mcp-call.sh --tools                # 列出工具
#    bash mcp-call.sh --call list_projects
#    bash mcp-call.sh --call list_specs --args '{"projectId":"<uuid>"}'
#
#  覆盖：MCP_URL（默认 https://openspec.panghuer.top/mcp）
#
#  约定：
#  - 凭据只从环境变量或 /tmp/casdoor.jwt 读，**不进命令行参数**（避免 ps 泄露），
#    也绝不被本脚本写入任何文件；
#  - streamable HTTP 的 session id 由服务端在 initialize 响应头里给出，本脚本在
#    同一次运行内复用（服务端是单副本、session 在内存里，跨进程无法续用）。
# ============================================================

MCP_URL="${MCP_URL:-https://openspec.panghuer.top/mcp}"
JWT="${CASDOOR_JWT:-$(cat /tmp/casdoor.jwt 2>/dev/null || true)}"
PROTOCOL_VERSION="2025-06-18"

ACTION="check"
TOOL=""
TOOL_ARGS="{}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) ACTION="check"; shift ;;
        --tools) ACTION="tools"; shift ;;
        --call)  ACTION="call"; TOOL="${2:-}"; shift 2 ;;
        --args)  TOOL_ARGS="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "未知参数: $1（可用：--check / --tools / --call <tool> [--args <json>]）" >&2; exit 2 ;;
    esac
done

[[ -n "${JWT}" ]] || {
    cat >&2 <<'EOF'
ERROR: 没有凭据。请设置 CASDOOR_JWT，或把 JWT 写到 /tmp/casdoor.jwt。

  取 JWT 的方式：
    bash openspec_service/scripts/get-token.sh
  （授权码 + PKCE，用 MCP 专用应用 315cbdaf565b82103c6f，**不需要 client_secret**）

  注意：网页版领取器 https://openspec.panghuer.top/token 已于 2026-10-02 退役 ——
  标准 MCP 客户端现在自己走 OAuth 2.1（RFC 9728 发现）。归档见 oauth/token-dispenser/。
EOF
    exit 1
}
command -v curl >/dev/null 2>&1 || { echo "ERROR: 需要 curl" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: 需要 python3" >&2; exit 1; }

[[ "${ACTION}" == "call" && -z "${TOOL}" ]] && { echo "ERROR: --call 需要一个工具名" >&2; exit 2; }

HDR_FILE="$(mktemp)"; BODY_FILE="$(mktemp)"
SESSION=""
cleanup() { rm -f "${HDR_FILE}" "${BODY_FILE}"; }
trap cleanup EXIT

# 发一次 JSON-RPC。$1 = 请求体；$2 = 期望的响应 id（空串表示通知，不解析响应）
rpc() {
    local payload="$1" want_id="$2"
    local args=(-sS -D "${HDR_FILE}" -o "${BODY_FILE}" -X POST "${MCP_URL}"
                -H "Authorization: Bearer ${JWT}"
                -H 'Content-Type: application/json'
                -H 'Accept: application/json, text/event-stream')
    [[ -n "${SESSION}" ]] && args+=(-H "Mcp-Session-Id: ${SESSION}")
    local http_code
    http_code="$(curl "${args[@]}" -d "${payload}" -w '%{http_code}')"

    if [[ -z "${SESSION}" ]]; then
        SESSION="$(python3 - "${HDR_FILE}" <<'PY'
import sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if line.lower().startswith("mcp-session-id:"):
        print(line.split(":", 1)[1].strip())
        break
PY
)"
    fi

    [[ -n "${want_id}" ]] || return 0

    python3 - "${BODY_FILE}" "${want_id}" "${http_code}" <<'PY'
import json, sys
path, want_id, http_code = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(path, encoding="utf-8", errors="replace").read()

# 响应可能是普通 JSON，也可能是 SSE（每条 data: 一个 JSON-RPC 对象）
objects = []
for line in raw.splitlines():
    line = line.strip()
    if not line:
        continue
    if line.startswith("data:"):
        line = line[5:].strip()
    try:
        objects.append(json.loads(line))
    except ValueError:
        continue
if not objects:
    try:
        objects.append(json.loads(raw))
    except ValueError:
        print(f"ERROR: 无法解析响应（HTTP {http_code}）：{raw[:400]}", file=sys.stderr)
        sys.exit(1)

for obj in objects:
    if str(obj.get("id")) == want_id or obj.get("id") is None:
        if "error" in obj:
            err = obj["error"]
            print(f"ERROR: JSON-RPC {err.get('code')}: {err.get('message')}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(obj.get("result", obj), ensure_ascii=False, indent=2))
        sys.exit(0)

print(f"ERROR: 响应里没有 id={want_id} 的结果（HTTP {http_code}）：{raw[:400]}", file=sys.stderr)
sys.exit(1)
PY
}

# 1) initialize —— 同时拿到 session id
rpc "$(python3 -c '
import json, sys
print(json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": sys.argv[1],
        "capabilities": {},
        "clientInfo": {"name": "openspec-mcp-call", "version": "1"},
    },
}))' "${PROTOCOL_VERSION}")" 1 >/dev/null

# 2) initialized 通知（无 id，服务端通常回 202/空体）
rpc '{"jsonrpc":"2.0","method":"notifications/initialized"}' ""

case "${ACTION}" in
    check)
        echo "== initialize 成功（session: ${SESSION:-无}）=="
        rpc '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' 2
        ;;
    tools)
        rpc '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' 2
        ;;
    call)
        rpc "$(python3 -c '
import json, sys
tool, args = sys.argv[1], json.loads(sys.argv[2])
print(json.dumps({
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": tool, "arguments": args},
}))' "${TOOL}" "${TOOL_ARGS}")" 2
        ;;
esac
