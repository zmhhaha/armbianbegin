-- Gitea database bootstrap extensions.
-- Gitea creates and upgrades its own tables when the server starts.
-- The wrapper script can be run with:
--   export PGHOST=postgres.data.svc.cluster.local PGPORT=5432
--   export PGUSER=appuser PGPASSWORD='existing PostgreSQL admin password'
--   export GITEA_DB_PASSWORD='dedicated Gitea database password'
--   bash ./init-db.sh
-- From outside the cluster, first run:
--   kubectl -n data port-forward svc/postgres 15432:5432
--   export PGHOST=127.0.0.1 PGPORT=15432
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
