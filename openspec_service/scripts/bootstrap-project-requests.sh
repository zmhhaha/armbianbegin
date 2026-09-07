#!/usr/bin/env bash
set -Eeuo pipefail

# Create the dedicated Gitea issue repository and its approval webhook.
# This is an operator setup script; it does not poll issues.

: "${GITEA_TOKEN:?Set GITEA_TOKEN}"
: "${GITEA_WEBHOOK_SECRET:?Set GITEA_WEBHOOK_SECRET}"

GITEA_URL="${GITEA_URL:-https://gitea.panghuer.top}"
GITEA_OWNER="${GITEA_OWNER:-openspec-service}"
REQUEST_REPOSITORY="${REQUEST_REPOSITORY:-project-requests}"
WEBHOOK_URL="${WEBHOOK_URL:-http://openspec-service.openspec.svc.cluster.local:8080/webhooks/gitea}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../gitea/project-requests/ISSUE_TEMPLATE/project-request.md"

command -v curl >/dev/null 2>&1 || { echo 'ERROR: curl command not found' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo 'ERROR: python3 command not found' >&2; exit 1; }

GITEA_URL="${GITEA_URL%/}"
api(){ curl -fsS -m 20 -H "Authorization: token ${GITEA_TOKEN}" -H 'Content-Type: application/json' "$@"; }
json_file(){ python3 - "$@"; }

repo_path="/repos/${GITEA_OWNER}/${REQUEST_REPOSITORY}"
if ! api "${GITEA_URL}/api/v1${repo_path}" >/dev/null 2>&1; then
  api -X POST "${GITEA_URL}/api/v1/orgs/${GITEA_OWNER}/repos" \
    --data "$(python3 - "${REQUEST_REPOSITORY}" <<'PY'
import json,sys
print(json.dumps({'name':sys.argv[1],'private':True,'auto_init':True,'default_branch':'main','description':'OpenSpec project creation requests'}))
PY
    )" >/dev/null
fi

create_label(){
  local name="$1" color="$2" description="$3"
  api -X POST "${GITEA_URL}/api/v1${repo_path}/labels" \
    --data "$(python3 - "${name}" "${color}" "${description}" <<'PY'
import json,sys
print(json.dumps({'name':sys.argv[1],'color':sys.argv[2],'description':sys.argv[3]}))
PY
    )" >/dev/null 2>&1 || true
}
create_label 'status:pending' 'bfdadc' 'Waiting for administrator review'
create_label 'status:approved' '2da44e' 'Approved; webhook provisions the project'
create_label 'status:failed' 'cf222e' 'Provisioning failed; remove approved and retry'

template_b64="$(python3 - "${TEMPLATE_FILE}" <<'PY'
import base64,sys
with open(sys.argv[1],'rb') as f: print(base64.b64encode(f.read()).decode())
PY
)"
api -X PUT "${GITEA_URL}/api/v1${repo_path}/contents/.gitea/ISSUE_TEMPLATE/project-request.md" \
  --data "$(python3 - "${template_b64}" <<'PY'
import json,sys
print(json.dumps({'branch':'main','content':sys.argv[1],'message':'chore: add OpenSpec project request template'}))
PY
  )" >/dev/null 2>&1 || true

# Keep the granular issue sub-events enabled: the approval webhook fires as an
# "issue_label" task whose X-Gitea-Event header is "issues".
events_json="$(python3 - <<'PY'
import json,sys
print(json.dumps(['issues','issue_assign','issue_label','issue_milestone','issue_comment']))
PY
)"

list_hooks() { api "${GITEA_URL}/api/v1${repo_path}/hooks?limit=50" 2>/dev/null || true; }
hook_url_missing() {
  python3 - "$1" "${WEBHOOK_URL}" <<'PY'
import json,sys
try:
    hooks=json.loads(sys.argv[1])
    url=sys.argv[2]
    print('false' if any((h.get('config') or {}).get('url') == url for h in hooks if isinstance(h,dict)) else 'true')
except Exception:
    print('true')
PY
}
hook_id() {
  python3 - "$1" "${WEBHOOK_URL}" <<'PY'
import json,sys
try:
    hooks=json.loads(sys.argv[1])
    url=sys.argv[2]
    for h in hooks:
        if isinstance(h,dict) and (h.get('config') or {}).get('url')==url:
            print(h.get('id')); break
except Exception:
    pass
PY
}
hook_json() {
  python3 - "${WEBHOOK_URL}" "${GITEA_WEBHOOK_SECRET}" "${events_json}" <<'PY'
import json,sys
print(json.dumps({'active':True,'events':json.loads(sys.argv[3]),'config':{'url':sys.argv[1],'content_type':'json','secret':sys.argv[2]}}))
PY
}

hooks="$(list_hooks)"
if [[ "$(hook_url_missing "${hooks}")" == "true" ]]; then
  api -X POST "${GITEA_URL}/api/v1${repo_path}/hooks" \
    --data "$(python3 - "${WEBHOOK_URL}" "${GITEA_WEBHOOK_SECRET}" "${events_json}" <<'PY'
import json,sys
print(json.dumps({'type':'gitea','active':True,'events':json.loads(sys.argv[3]),'config':{'url':sys.argv[1],'content_type':'json','secret':sys.argv[2]}}))
PY
    )" >/dev/null
  hooks="$(list_hooks)"
fi

# Idempotently resync an existing hook's secret and events to the current
# GITEA_WEBHOOK_SECRET. Otherwise, after the secret is rotated in Vault, Gitea
# keeps signing with the old value and the service rejects every delivery with
# 401 invalid_webhook_signature. Safe to re-run at any time.
hook_id="$(hook_id "${hooks}")"
if [[ -n "${hook_id}" ]]; then
  api -X PATCH "${GITEA_URL}/api/v1${repo_path}/hooks/${hook_id}" \
    --data "$(hook_json)" >/dev/null
fi

echo "Project request repository is ready: ${GITEA_URL}/${GITEA_OWNER}/${REQUEST_REPOSITORY}"
echo "Webhook target: ${WEBHOOK_URL}"
