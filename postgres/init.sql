-- ============================================================
--  PostgreSQL 初始化 SQL 脚本
--  在部署后手动导入: psql -h postgres.data.svc.cluster.local -U appuser -d appdb -f init.sql
--  或在新数据库上直接导入
-- ============================================================

-- 扩展
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS uuid-ossp;

-- 示例: 创建一个通用用户表 (按需修改)
-- CREATE TABLE IF NOT EXISTS users (
--     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--     username VARCHAR(64) NOT NULL UNIQUE,
--     email VARCHAR(255) NOT NULL UNIQUE,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
--     updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );

-- 查看确认
SELECT current_database() AS database,
       current_user AS user,
       version() AS version;
