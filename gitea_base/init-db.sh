#!/usr/bin/env bash
# Initialize the logical Gitea database in the existing PostgreSQL service.
# Usage inside the cluster:
#   export PGHOST=postgres.data.svc.cluster.local PGPORT=5432
#   export PGUSER=appuser PGPASSWORD='existing PostgreSQL admin password'
#   export GITEA_DB_PASSWORD='dedicated Gitea database password'
#   bash ./init-db.sh
#
# Usage from outside the cluster (run port-forward first):
#   kubectl -n data port-forward svc/postgres 15432:5432
#   export PGHOST=127.0.0.1 PGPORT=15432
#   bash ./init-db.sh
# Required: PGHOST, PGPORT, PGUSER, PGPASSWORD (admin credentials),
#           GITEA_DB_PASSWORD (password for the dedicated gitea role).
set -euo pipefail

: "${PGHOST:=postgres.data.svc.cluster.local}"
: "${PGPORT:=5432}"
: "${PGUSER:?PGUSER must be a PostgreSQL administrator}"
: "${PGPASSWORD:?PGPASSWORD must be set}"
: "${GITEA_DB_PASSWORD:?GITEA_DB_PASSWORD must be set}"
GITEA_DB_NAME="${GITEA_DB_NAME:-gitea}"
GITEA_DB_USER="${GITEA_DB_USER:-gitea}"

export PGHOST PGPORT PGUSER PGPASSWORD

psql --dbname=postgres --set=ON_ERROR_STOP=1 \
  --set=gitea_user="${GITEA_DB_USER}" \
  --set=gitea_password="${GITEA_DB_PASSWORD}" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'gitea_user') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'gitea_user', :'gitea_password');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'gitea_user', :'gitea_password');
  END IF;
END
$$;
SQL

if ! psql --dbname=postgres --tuples-only --no-align \
    --set=db_name="${GITEA_DB_NAME}" \
    -c "SELECT 1 FROM pg_database WHERE datname = :'db_name'" | grep -qx 1; then
  createdb --owner="${GITEA_DB_USER}" "${GITEA_DB_NAME}"
fi

psql --dbname="${GITEA_DB_NAME}" --set=ON_ERROR_STOP=1 \
  -f "$(cd "$(dirname "$0")" && pwd)/migrations/001_extensions.sql"

echo "Gitea database '${GITEA_DB_NAME}' is ready."
