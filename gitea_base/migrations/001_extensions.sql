-- Gitea database bootstrap extensions.
-- Gitea creates and upgrades its own tables when the server starts.
-- The wrapper executes psql inside the PostgreSQL Pod:
--   export GITEA_DB_PASSWORD='dedicated Gitea database password'
--   bash ./init-db.sh
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
