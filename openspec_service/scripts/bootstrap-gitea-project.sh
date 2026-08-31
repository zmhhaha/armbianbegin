#!/usr/bin/env bash
set -euo pipefail
# Run from a trusted admin workstation. This creates the organization/repository
# used by the MVP service; the token is never written to this repository.
: "${GITEA_URL:=https://gitea.panghuer.top}"
: "${GITEA_TOKEN:?Set GITEA_TOKEN}"
: "${GITEA_OWNER:=openspec}"
: "${REPO_NAME:?Set REPO_NAME, e.g. project-a-specs}"
: "${OWNER_USERNAME:?Set OWNER_USERNAME to the Casdoor/Gitea username}"
json(){ curl -fsS -H "Authorization: token ${GITEA_TOKEN}" -H 'Content-Type: application/json' "$@"; }
json -X POST "${GITEA_URL}/api/v1/orgs" -d "{\"username\":\"${GITEA_OWNER}\",\"visibility\":\"private\"}" || true
json -X POST "${GITEA_URL}/api/v1/orgs/${GITEA_OWNER}/repos" -d "{\"name\":\"${REPO_NAME}\",\"private\":true,\"auto_init\":true,\"default_branch\":\"main\"}" || true
json -X PUT "${GITEA_URL}/api/v1/repos/${GITEA_OWNER}/${REPO_NAME}/collaborators/${OWNER_USERNAME}" -d '{"permission":"admin"}'
printf 'Repository ready: %s/%s/%s\n' "$GITEA_OWNER" "$REPO_NAME" "$OWNER_USERNAME"
