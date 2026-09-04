#!/usr/bin/env bash
set -Eeuo pipefail

# Register a dedicated OpenSpec store for an application repository.
# The application source may remain in GitHub; this project is the Git-backed
# specs/changes store consumed by OpenSpec Service.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd -- "${SERVICE_DIR}/.." && pwd)"

BASE_URL="${BASE_URL:-https://openspec.panghuer.top}"
PROJECT_SLUG="${PROJECT_SLUG:-armbianbegin}"
PROJECT_FILE="${PROJECT_FILE:-${REPO_ROOT}/.openspec-project.json}"
CASDOOR_JWT="${CASDOOR_JWT:-$(cat /tmp/casdoor.jwt 2>/dev/null || true)}"

usage() {
  cat <<'EOF'
Usage: ./scripts/register-project.sh [options]

Register or discover an OpenSpec project for this application repository.

Options:
  --slug VAL       Gitea/OpenSpec repository slug (default: armbianbegin)
  --base-url VAL   OpenSpec Service URL (default: https://openspec.panghuer.top)
  --project-file VAL
                   Where to save the non-secret project mapping
  -h, --help       Show this help

Environment overrides: CASDOOR_JWT, PROJECT_SLUG, BASE_URL, PROJECT_FILE
The JWT is read from CASDOOR_JWT or /tmp/casdoor.jwt and is never written to
the project file.
EOF
}

while (($# > 0)); do
  case "$1" in
    --slug) (($# >= 2)) || { echo "ERROR: --slug requires a value" >&2; exit 2; }; PROJECT_SLUG="$2"; shift ;;
    --base-url) (($# >= 2)) || { echo "ERROR: --base-url requires a value" >&2; exit 2; }; BASE_URL="$2"; shift ;;
    --project-file) (($# >= 2)) || { echo "ERROR: --project-file requires a value" >&2; exit 2; }; PROJECT_FILE="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

[[ -n "${CASDOOR_JWT}" ]] || { echo "ERROR: set CASDOOR_JWT or create /tmp/casdoor.jwt" >&2; exit 1; }
[[ "${PROJECT_SLUG}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,99}$ ]] || { echo "ERROR: invalid project slug" >&2; exit 2; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl command not found" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 command not found" >&2; exit 1; }

BASE_URL="${BASE_URL%/}"
mkdir -p "$(dirname -- "${PROJECT_FILE}")"

write_mapping() {
  local body="$1"
  python3 - "${PROJECT_FILE}" "${BASE_URL}" "${PROJECT_SLUG}" "${body}" <<'PY'
import json, os, sys
path, base_url, slug, raw = sys.argv[1:]
data = json.loads(raw)
mapping = {
    "baseUrl": base_url,
    "projectId": data["id"],
    "owner": data.get("owner", "openspec-service"),
    "repository": data.get("repository", slug),
}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(mapping, f, ensure_ascii=True, indent=2)
    f.write("\n")
os.replace(tmp, path)
print(json.dumps(mapping, ensure_ascii=True))
PY
}

auth=(-H "Authorization: Bearer ${CASDOOR_JWT}" -H 'Accept: application/json')

if [[ -f "${PROJECT_FILE}" ]]; then
  existing="$(python3 - "${PROJECT_FILE}" <<'PY'
import json, sys
try:
    data=json.load(open(sys.argv[1], encoding='utf-8'))
    if data.get('projectId'):
        print(json.dumps(data, ensure_ascii=True))
except Exception:
    pass
PY
  )"
  if [[ -n "${existing}" ]]; then
    existing_repo="$(python3 - "${existing}" <<'PY'
import json, sys
try:
    print(json.loads(sys.argv[1]).get('repository',''))
except Exception:
    pass
PY
    )"
    if [[ "${existing_repo}" != "${PROJECT_SLUG}" ]]; then
      echo "ERROR: ${PROJECT_FILE} points to repository '${existing_repo}', not '${PROJECT_SLUG}'; inspect it before continuing" >&2
      exit 1
    fi
    echo "OpenSpec project mapping already exists: ${existing}"
    exit 0
  fi
fi

echo "== Looking for visible OpenSpec project ${PROJECT_SLUG} =="
projects="$(curl -sS -f "${auth[@]}" "${BASE_URL}/v1/projects" 2>/dev/null || true)"
found="$(python3 - "${projects}" "${PROJECT_SLUG}" <<'PY'
import json, sys
try:
    data=json.loads(sys.argv[1])
    slug=sys.argv[2]
    for item in data.get('items', []):
        if item.get('repository') == slug:
            print(json.dumps(item, ensure_ascii=True))
            break
except Exception:
    pass
PY
 )"
if [[ -n "${found}" ]]; then
  write_mapping "${found}"
  echo "Existing project reused."
  exit 0
fi

echo "== Creating OpenSpec project ${PROJECT_SLUG} =="
key="register-${PROJECT_SLUG}-$(date +%s)-$$"
response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT
request_body="$(python3 -c 'import json,sys; print(json.dumps({"slug":sys.argv[1]}))' "${PROJECT_SLUG}")"
status="$(curl -sS -o "${response_file}" -w '%{http_code}' -X POST "${BASE_URL}/v1/projects" \
  "${auth[@]}" -H 'Content-Type: application/json' -H "Idempotency-Key: ${key}" \
  --data "${request_body}")"
response="$(cat "${response_file}")"
if [[ "${status}" != "201" ]]; then
  echo "ERROR: OpenSpec project creation failed (HTTP ${status})" >&2
  python3 - "${response}" <<'PY' >&2
import json, sys
try:
    d=json.loads(sys.argv[1])
    print(json.dumps({k:d.get(k) for k in ('error','message') if d.get(k)}, ensure_ascii=True))
except Exception:
    print("service returned a non-JSON response")
PY
  exit 1
fi

write_mapping "${response}"
echo "Project registered. Use the projectId above for REST/MCP calls."
