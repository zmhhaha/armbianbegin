#!/usr/bin/env bash
# Initialize Gitea in the existing PostgreSQL Pod (no local psql required).
# Usage:
#   export GITEA_DB_PASSWORD='dedicated Gitea database password'
#   bash ./init-db.sh
# Optional: POSTGRES_POD, POSTGRES_ADMIN_USER, POSTGRES_ADMIN_DB,
#           GITEA_DB_NAME and GITEA_DB_USER.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
POSTGRES_POD="${POSTGRES_POD:-postgres-0}"
POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-appuser}"
POSTGRES_ADMIN_DB="${POSTGRES_ADMIN_DB:-appdb}"
GITEA_DB_NAME="${GITEA_DB_NAME:-gitea}"
GITEA_DB_USER="${GITEA_DB_USER:-gitea}"
: "${GITEA_DB_PASSWORD:?GITEA_DB_PASSWORD must be set}"

command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 1; }
kubectl -n data get pod "${POSTGRES_POD}" >/dev/null
postgres_password="$(kubectl -n data get secret postgres-secret -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)"

run_psql() {
  kubectl -n data exec -i "${POSTGRES_POD}" -- env PGPASSWORD="${postgres_password}" \
    psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "${POSTGRES_ADMIN_USER}" "$@"
}

printf '%s\n' "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', '${GITEA_DB_USER}', :'gitea_password') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${GITEA_DB_USER}') \\gexec" \
  "ALTER ROLE ${GITEA_DB_USER} WITH LOGIN PASSWORD :'gitea_password';" \
  "SELECT format('CREATE DATABASE %I OWNER %I', '${GITEA_DB_NAME}', '${GITEA_DB_USER}') WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${GITEA_DB_NAME}') \\gexec" \
  | run_psql --dbname="${POSTGRES_ADMIN_DB}" --set="gitea_password=${GITEA_DB_PASSWORD}" >/dev/null

run_psql --dbname="${GITEA_DB_NAME}" < "${script_dir}/migrations/001_extensions.sql"
echo "Gitea database '${GITEA_DB_NAME}' is ready."
