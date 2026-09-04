#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# OpenSpec 端到端冒烟：建/改 change -> validate -> apply-specs -> archive
# 用法：
#   PROJECT_ID=<project-id> bash openspec_service/scripts/smoke-test-e2e.sh
# 或先执行 register-project.sh，脚本会读取仓库根目录的
# .openspec-project.json。只有显式设置 CREATE_PROJECT=1 才创建临时项目。
# JWT 来源：CASDOOR_JWT 环境变量，或 /tmp/casdoor.jwt
# ============================================================

CASDOOR_JWT="${CASDOOR_JWT:-$(cat /tmp/casdoor.jwt 2>/dev/null || true)}"
BASE_URL="${BASE_URL:-https://openspec.panghuer.top}"
PROJECT_ID="${PROJECT_ID:-}"
PROJECT_FILE="${PROJECT_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.openspec-project.json}"
CREATE_PROJECT="${CREATE_PROJECT:-0}"

[[ -n "${CASDOOR_JWT}" ]] || { echo "ERROR: 需要 CASDOOR_JWT 或 /tmp/casdoor.jwt" >&2; exit 1; }
H_AUTH="Authorization: Bearer ${CASDOOR_JWT}"
H_JSON="Content-Type: application/json"
key() { cat /proc/sys/kernel/random/uuid; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

# 合法 OpenSpec delta spec：每条 Requirement 必须至少带一个 Scenario。
SPEC_ADD_LOGIN='## ADDED Requirements

### Requirement: Login
The system SHALL accept a login.

#### Scenario: Login works
- **WHEN** credentials are valid
- **THEN** access is granted
'

if [[ -z "${PROJECT_ID}" && -f "${PROJECT_FILE}" ]]; then
  PROJECT_ID="$(python3 - "${PROJECT_FILE}" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding='utf-8'))
print(data.get('projectId',''))
PY
  )"
  [[ -n "${PROJECT_ID}" ]] || { echo "ERROR: ${PROJECT_FILE} 没有 projectId" >&2; exit 1; }
  echo "== 使用项目映射 ${PROJECT_FILE} (${PROJECT_ID}) =="
fi

if [[ -z "${PROJECT_ID}" && "${CREATE_PROJECT}" == "1" ]]; then
  slug="smoke-$(date +%s)"
  echo "== 创建临时项目 ${slug} =="
  resp="$(curl -fsS -X POST "${BASE_URL}/v1/projects" \
    -H "${H_AUTH}" -H "Idempotency-Key: $(key)" -H "${H_JSON}" -d "{\"slug\":\"${slug}\"}")"
  PROJECT_ID="$(printf '%s' "${resp}" | json "d['id']")"
  echo "  project id: ${PROJECT_ID}"
elif [[ -z "${PROJECT_ID}" ]]; then
  echo "ERROR: 未提供 PROJECT_ID，也找不到 ${PROJECT_FILE}。先执行 register-project.sh，或显式设置 CREATE_PROJECT=1。" >&2
  exit 1
else
  echo "== 使用已有项目 ${PROJECT_ID} =="
fi
B="${BASE_URL}/v1/projects/${PROJECT_ID}"
CHANGE_ID="login-$(date +%s)"

echo "== 1. list specs =="
curl -fsS -H "${H_AUTH}" "${B}/specs"; echo
REV="$(curl -fsS -H "${H_AUTH}" "${B}/specs" | json "d['revision']")"
echo "   revision=${REV}"

BODY="{\"files\":{\"proposal.md\":\"# 登录功能\n\",\"specs/auth/spec.md\":$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$SPEC_ADD_LOGIN")}}"

echo "== 2. create/update change ${CHANGE_ID} =="
resp="$(curl -s -X POST -H "${H_AUTH}" -H "Idempotency-Key: $(key)" -H "If-Match: ${REV}" -H "${H_JSON}" \
  "${B}/changes/${CHANGE_ID}" -d "${BODY}" || true)"
if printf '%s' "${resp}" | grep -q "already exists"; then
  echo "   (已存在，改用 PUT 更新)"
  curl -fsS -X PUT -H "${H_AUTH}" -H "Idempotency-Key: $(key)" -H "If-Match: ${REV}" -H "${H_JSON}" \
    "${B}/changes/${CHANGE_ID}" -d "${BODY}"; echo
else
  printf '%s\n' "${resp}"
fi

echo "== 3. validate =="
curl -fsS -X POST -H "${H_AUTH}" "${B}/changes/${CHANGE_ID}/validate"; echo

REV2="$(curl -fsS -H "${H_AUTH}" "${B}/changes" | json "d['revision']")"
echo "   revision=${REV2}"

echo "== 4. apply-specs =="
curl -fsS -X POST -H "${H_AUTH}" -H "Idempotency-Key: $(key)" -H "If-Match: ${REV2}" \
  "${B}/changes/${CHANGE_ID}/apply-specs"; echo

REV3="$(curl -fsS -H "${H_AUTH}" "${B}/changes" | json "d['revision']")"
echo "   revision=${REV3}"

echo "== 5. archive =="
curl -fsS -X POST -H "${H_AUTH}" -H "Idempotency-Key: $(key)" -H "If-Match: ${REV3}" \
  "${B}/changes/${CHANGE_ID}/archive"; echo

echo "== 6. final specs =="
curl -fsS -H "${H_AUTH}" "${B}/specs"; echo
echo "== 7. final changes =="
curl -fsS -H "${H_AUTH}" "${B}/changes"; echo
echo "== 完成 =="
