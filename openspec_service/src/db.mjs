import pg from 'pg'; import crypto from 'node:crypto'; import {config} from './config.mjs'; import {unavailable,notFound,conflict} from './errors.mjs'; const {Pool}=pg; export const pool=config.databaseUrl?new Pool({connectionString:config.databaseUrl,max:5}):null; export let migrationReady=false;
export async function query(text,values=[]){if(!pool)throw unavailable('DATABASE_URL is not configured');try{return await pool.query(text,values);}catch(e){throw unavailable(`PostgreSQL unavailable: ${e.message}`);}}
export async function migrate(){
  await query(`create extension if not exists pgcrypto; create table if not exists openspec_projects(id uuid primary key default gen_random_uuid(),gitea_owner text not null,gitea_repository text not null unique,default_branch text not null default 'main',created_by text not null,created_at timestamptz not null default now()); create table if not exists openspec_identity_map(subject text primary key,gitea_username text not null unique,created_at timestamptz not null default now()); create table if not exists openspec_audit_events(id uuid primary key default gen_random_uuid(),project_id uuid not null references openspec_projects(id),subject text not null,action text not null,request_id uuid not null,revision_before text,revision_after text,created_at timestamptz not null default now()); create index if not exists openspec_audit_project_created_idx on openspec_audit_events(project_id,created_at desc); create table if not exists openspec_idempotency_keys(subject text not null,project_id uuid not null references openspec_projects(id),key text not null,request_hash text not null,status integer not null,response jsonb,created_at timestamptz not null default now(),primary key(subject,project_id,key)); create table if not exists openspec_project_idempotency(subject text not null,key text not null,request_hash text not null,status integer not null,response jsonb,created_at timestamptz not null default now(),primary key(subject,key)); create index if not exists openspec_idempotency_stale_idx on openspec_idempotency_keys(subject,project_id,key,created_at) where status=0; create index if not exists openspec_project_idempotency_stale_idx on openspec_project_idempotency(subject,key,created_at) where status=0;`);
  await query(`create table if not exists openspec_project_requests(id uuid primary key default gen_random_uuid(),request_owner text not null,request_repository text not null,issue_number integer not null,requester_username text not null,payload jsonb not null,status text not null default 'pending',approved_by text,project_id uuid references openspec_projects(id),error_message text,created_at timestamptz not null default now(),updated_at timestamptz not null default now(),unique(request_owner,request_repository,issue_number)); create index if not exists openspec_project_requests_status_idx on openspec_project_requests(status,updated_at); create table if not exists openspec_request_audit_events(id uuid primary key default gen_random_uuid(),request_owner text not null,request_repository text not null,issue_number integer,actor text not null,action text not null,request_id uuid not null,details jsonb,created_at timestamptz not null default now()); create table if not exists openspec_request_idempotency(subject text not null,key text not null,request_hash text not null,status integer not null,response jsonb,created_at timestamptz not null default now(),primary key(subject,key)); create index if not exists openspec_request_idempotency_stale_idx on openspec_request_idempotency(subject,key,created_at) where status=0;`);
  migrationReady=true;
}
export async function bindIdentity(subject,username){if(typeof username!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(username))throw conflict('A stable Gitea username is required for this identity');const existing=await identity(subject);if(existing&&existing!==username)throw conflict('Casdoor identity is already bound to another Gitea username');if(!existing)await query('insert into openspec_identity_map(subject,gitea_username) values($1,$2)',[subject,username]);return username;}
export async function beginIdempotency(subject,projectId,key,requestHash){
  await query("delete from openspec_idempotency_keys where subject=$1 and project_id=$2 and key=$3 and status=0 and created_at < now() - interval '15 minutes'",[subject,projectId,key]);
  const inserted=await query('insert into openspec_idempotency_keys(subject,project_id,key,request_hash,status) values($1,$2,$3,$4,0) on conflict(subject,project_id,key) do nothing returning status,response,request_hash',[subject,projectId,key,requestHash]);
  if(inserted.rows[0]) return{replay:false};
  const existing=(await query('select status,response,request_hash from openspec_idempotency_keys where subject=$1 and project_id=$2 and key=$3',[subject,projectId,key])).rows[0];
  if(!existing) throw unavailable('Idempotency record disappeared');
  if(existing.request_hash!==requestHash) throw conflict('Idempotency-Key was already used with a different request');
  if(existing.status===0) throw conflict('A request with this Idempotency-Key is already in progress');
  return{replay:true,status:existing.status,response:existing.response};
}
export async function completeIdempotency(subject,projectId,key,status,response){await query('update openspec_idempotency_keys set status=$4,response=$5 where subject=$1 and project_id=$2 and key=$3',[subject,projectId,key,status,JSON.stringify(response)]);}
export async function abandonIdempotency(subject,projectId,key){await query('delete from openspec_idempotency_keys where subject=$1 and project_id=$2 and key=$3 and status=0',[subject,projectId,key]);}
export async function beginProjectIdempotency(subject,key,requestHash){
  await query("delete from openspec_project_idempotency where subject=$1 and key=$2 and status=0 and created_at < now() - interval '15 minutes'",[subject,key]);
  const inserted=await query('insert into openspec_project_idempotency(subject,key,request_hash,status) values($1,$2,$3,0) on conflict(subject,key) do nothing returning status,response,request_hash',[subject,key,requestHash]);
  if(inserted.rows[0]) return{replay:false};
  const existing=(await query('select status,response,request_hash from openspec_project_idempotency where subject=$1 and key=$2',[subject,key])).rows[0];
  if(!existing) throw unavailable('Project idempotency record disappeared');
  if(existing.request_hash!==requestHash) throw conflict('Idempotency-Key was already used with a different request');
  if(existing.status===0) throw conflict('A request with this Idempotency-Key is already in progress');
  return{replay:true,status:existing.status,response:existing.response};
}
export async function completeProjectIdempotency(subject,key,status,response){await query('update openspec_project_idempotency set status=$3,response=$4 where subject=$1 and key=$2',[subject,key,status,JSON.stringify(response)]);}
export async function abandonProjectIdempotency(subject,key){await query('delete from openspec_project_idempotency where subject=$1 and key=$2 and status=0',[subject,key]);}
export async function beginRequestIdempotency(subject,key,requestHash){
  await query("delete from openspec_request_idempotency where subject=$1 and key=$2 and status=0 and created_at < now() - interval '15 minutes'",[subject,key]);
  const inserted=await query('insert into openspec_request_idempotency(subject,key,request_hash,status) values($1,$2,$3,0) on conflict(subject,key) do nothing returning status,response,request_hash',[subject,key,requestHash]);
  if(inserted.rows[0])return{replay:false};
  const existing=(await query('select status,response,request_hash from openspec_request_idempotency where subject=$1 and key=$2',[subject,key])).rows[0];
  if(!existing)throw unavailable('Request idempotency record disappeared');
  if(existing.request_hash!==requestHash)throw conflict('Idempotency-Key was already used with a different request');
  if(existing.status===0)throw conflict('A request with this Idempotency-Key is already in progress');
  return{replay:true,status:existing.status,response:existing.response};
}
export async function completeRequestIdempotency(subject,key,status,response){await query('update openspec_request_idempotency set status=$3,response=$4 where subject=$1 and key=$2',[subject,key,status,JSON.stringify(response)]);}
export async function abandonRequestIdempotency(subject,key){await query('delete from openspec_request_idempotency where subject=$1 and key=$2 and status=0',[subject,key]);}
export async function identity(subject){const r=await query('select gitea_username from openspec_identity_map where subject=$1',[subject]);return r.rows[0]?.gitea_username||null;}
export async function insertProject({owner,repository,defaultBranch='main',createdBy}){return(await query('insert into openspec_projects(gitea_owner,gitea_repository,default_branch,created_by) values($1,$2,$3,$4) returning *',[owner,repository,defaultBranch,createdBy])).rows[0];}
export async function project(id){const r=await query('select * from openspec_projects where id=$1',[id]);if(!r.rows[0])throw notFound();return r.rows[0];}
export async function claimProjectRequest({owner,repository,issueNumber,requesterUsername,payload,approvedBy}){
  const inserted=await query('insert into openspec_project_requests(request_owner,request_repository,issue_number,requester_username,payload,approved_by) values($1,$2,$3,$4,$5,$6) on conflict(request_owner,request_repository,issue_number) do nothing returning *',[owner,repository,issueNumber,requesterUsername,JSON.stringify(payload),approvedBy]);
  const current=inserted.rows[0]||(await query('select * from openspec_project_requests where request_owner=$1 and request_repository=$2 and issue_number=$3',[owner,repository,issueNumber])).rows[0];
  if(!current)throw unavailable('Project request record disappeared');
  if(current.status==='provisioned')return{claimed:false,request:current};
  const claimed=await query("update openspec_project_requests set status='provisioning',approved_by=$2,updated_at=now() where id=$1 and (status in ('pending','failed') or (status='provisioning' and updated_at < now() - interval '15 minutes')) returning *",[current.id,approvedBy]);
  return{claimed:Boolean(claimed.rows[0]),request:claimed.rows[0]||current};
}
export async function completeProjectRequest(id,{status,projectId=null,errorMessage=null}){return(await query('update openspec_project_requests set status=$2,project_id=$3,error_message=$4,updated_at=now() where id=$1 returning *',[id,status,projectId,errorMessage])).rows[0];}
export async function auditRequest({owner,repository,issueNumber=null,actor,action,requestId,details={}}){await query('insert into openspec_request_audit_events(request_owner,request_repository,issue_number,actor,action,request_id,details) values($1,$2,$3,$4,$5,$6,$7)',[owner,repository,issueNumber,actor,action,requestId,JSON.stringify(details)]);}
export async function visibleProjects(subject,gitea){const username=await identity(subject);if(!username)return[];const rows=(await query('select * from openspec_projects order by created_at desc')).rows;const result=[];for(const p of rows){const permission=await gitea.permission(p.gitea_owner,p.gitea_repository,username);if(permission!=='none')result.push({id:p.id,owner:p.gitea_owner,repository:p.gitea_repository,permission});}return result;}
export async function audit(projectId,actor,action,requestId,before,after){await query('insert into openspec_audit_events(project_id,subject,action,request_id,revision_before,revision_after) values($1,$2,$3,$4,$5,$6)',[projectId,actor,action,requestId,before||null,after||null]);}
export function uuid(v){return typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v);} export const newUuid=()=>crypto.randomUUID();
