-- OpenSpec Service: project registry, identity mapping and audit only.
create extension if not exists pgcrypto;
create table if not exists openspec_projects (
  id uuid primary key default gen_random_uuid(),
  gitea_owner text not null,
  gitea_repository text not null unique,
  default_branch text not null default 'main',
  created_by text not null,
  created_at timestamptz not null default now()
);
create table if not exists openspec_identity_map (
  subject text primary key,
  gitea_username text not null unique,
  created_at timestamptz not null default now()
);
create table if not exists openspec_audit_events (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references openspec_projects(id),
  subject text not null,
  action text not null,
  request_id uuid not null,
  revision_before text,
  revision_after text,
  created_at timestamptz not null default now()
);

create index if not exists openspec_audit_project_created_idx
  on openspec_audit_events (project_id, created_at desc);

create table if not exists openspec_idempotency_keys (
  subject text not null,
  project_id uuid not null references openspec_projects(id),
  key text not null,
  request_hash text not null,
  status integer not null,
  response jsonb,
  created_at timestamptz not null default now(),
  primary key (subject, project_id, key)
);

create table if not exists openspec_project_idempotency (
  subject text not null,
  key text not null,
  request_hash text not null,
  status integer not null,
  response jsonb,
  created_at timestamptz not null default now(),
  primary key (subject, key)
);

-- In-progress keys are reclaimed by the service after 15 minutes. This index
-- keeps that recovery query cheap without changing the idempotency contract.
create index if not exists openspec_idempotency_stale_idx
  on openspec_idempotency_keys (subject, project_id, key, created_at)
  where status = 0;
create index if not exists openspec_project_idempotency_stale_idx
  on openspec_project_idempotency (subject, key, created_at)
  where status = 0;
