import crypto from 'node:crypto';
import {authenticate,subject} from './auth.mjs';
import {config} from './config.mjs';
import * as db from './db.mjs';
import * as gitea from './gitea.mjs';
import * as ws from './workspace.mjs';
import {ServiceError,badRequest,notFound,forbidden} from './errors.mjs';

const ranks={none:0,read:1,write:2,admin:3,owner:4};

const json=(res,status,body,id)=>{
  if(id) res.setHeader('x-request-id',id);
  res.writeHead(status,{'content-type':'application/json'});
  res.end(JSON.stringify(body));
};
const requestId=()=>crypto.randomUUID();

export async function payload(req){
  let raw='';
  for await(const chunk of req){
    raw+=chunk;
    if(raw.length>1048576) throw badRequest('request too large');
  }
  try{return raw?JSON.parse(raw):{};}catch{throw badRequest('invalid JSON');}
}

function actor(claims,username){return{name:username||claims.preferred_username||claims.name||claims.sub,email:claims.email||config.gitEmail};}
function requestHash(method,path,body){return crypto.createHash('sha256').update(JSON.stringify({method,path,body})).digest('hex');}

export async function projectAccess(projectRecord,claims,min){
  const username=await db.identity(subject(claims));
  if(!username) throw notFound();
  const level=await gitea.permission(projectRecord.gitea_owner,projectRecord.gitea_repository,username);
  if((ranks[level]||0)<(ranks[min]||0)) throw notFound();
  return level;
}

async function projectOperation(name,args,claims){
  const projectRecord=await db.project(args.projectId);
  if(name==='list_specs'){
    await projectAccess(projectRecord,claims,'read');
    const directory=await ws.ensureWorkspace(projectRecord);
    return{projectId:projectRecord.id,revision:await ws.currentRevision(directory),items:await ws.list(directory,'specs')};
  }
  if(name==='list_changes'){
    await projectAccess(projectRecord,claims,'read');
    const directory=await ws.ensureWorkspace(projectRecord);
    return{projectId:projectRecord.id,revision:await ws.currentRevision(directory),items:await ws.list(directory,'changes')};
  }
  if(name==='get_change'){
    await projectAccess(projectRecord,claims,'read');
    return ws.readChange(await ws.ensureWorkspace(projectRecord),args.changeId);
  }
  if(name==='create_proposal'){
    await projectAccess(projectRecord,claims,'write');
    const username=await db.identity(subject(claims));
    const result=await ws.createChange(projectRecord,args.changeId,actor(claims,username),args.expectedRevision,args.body);
    await db.audit(projectRecord.id,subject(claims),'create_change',args.requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after};
  }
  if(name==='update_proposal'){
    await projectAccess(projectRecord,claims,'write');
    const username=await db.identity(subject(claims));
    const result=await ws.updateChange(projectRecord,args.changeId,actor(claims,username),args.expectedRevision,args.body);
    await db.audit(projectRecord.id,subject(claims),'update_change',args.requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after};
  }
  if(name==='validate_change'){
    await projectAccess(projectRecord,claims,'write');
    return{projectId:projectRecord.id,id:args.changeId,valid:true,result:await ws.validateChange(projectRecord,args.changeId)};
  }
  if(name==='apply_specs'){
    await projectAccess(projectRecord,claims,'write');
    const username=await db.identity(subject(claims));
    const result=await ws.applySpecs(projectRecord,args.changeId,actor(claims,username),args.expectedRevision);
    await db.audit(projectRecord.id,subject(claims),'apply_specs',args.requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after,updates:result.updates};
  }
  if(name==='archive_change'){
    await projectAccess(projectRecord,claims,'admin');
    const username=await db.identity(subject(claims));
    const result=await ws.archiveChange(projectRecord,args.changeId,actor(claims,username),args.expectedRevision);
    await db.audit(projectRecord.id,subject(claims),'archive_change',args.requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after,archive:result.report};
  }
  throw notFound();
}

async function writeOperation(req,url,claims,args,operation){
  const sub=subject(claims);
  const key=req.headers['idempotency-key'];
  if(!key||key.length>200) throw badRequest('Idempotency-Key header is required');
  if(!args.expectedRevision) throw badRequest('If-Match header is required');
  const replay=await db.beginIdempotency(sub,args.projectId,key,requestHash(req.method,url.pathname,{expectedRevision:args.expectedRevision,body:args.body||null,operation}));
  if(replay.replay) return{status:replay.status,body:replay.response};
  try{
    const body=await projectOperation(operation,args,claims);
    const status=operation==='create_proposal'?201:200;
    await db.completeIdempotency(sub,args.projectId,key,status,body);
    return{status,body};
  }catch(error){await db.abandonIdempotency(sub,args.projectId,key).catch(()=>undefined);throw error;}
}

export async function dispatch(req,res,id=requestId()){
  const url=new URL(req.url,'http://localhost');
  const parts=url.pathname.split('/').filter(Boolean);
  if(req.method==='GET'&&url.pathname==='/healthz') return json(res,200,{status:'ok'},id);
  if(req.method==='GET'&&url.pathname==='/readyz'){
    if(!db.pool||!db.migrationReady) throw new ServiceError(503,'not_ready',db.pool?'database migration is not ready':'DATABASE_URL is not configured');
    await db.query('select 1');
    return json(res,200,{status:'ready'},id);
  }
  const claims=await authenticate(req);
  const sub=subject(claims);
  const username=claims.preferred_username||claims.name;
  await db.bindIdentity(sub,username);
  if(parts[0]!=='v1'||parts[1]!=='projects') throw notFound();
  if(req.method==='GET'&&parts.length===2) return json(res,200,{items:await db.visibleProjects(sub,gitea)},id);

  if(req.method==='POST'&&parts.length===2){
    if(!config.bootstrapSubjects.has(sub)) throw forbidden();
    const idempotencyKey=req.headers['idempotency-key'];
    if(!idempotencyKey||idempotencyKey.length>200) throw badRequest('Idempotency-Key header is required');
    const body=await payload(req);
    if(!ws.validProjectSlug(body.slug)) throw badRequest('invalid project slug');
    const replay=await db.beginProjectIdempotency(sub,idempotencyKey,requestHash(req.method,url.pathname,body));
    if(replay.replay) return json(res,replay.status,replay.response,id);
    let owner; let name; let projectPersisted=false;
    try{
      const repository=await gitea.createPrivateRepo(body.slug);
      if(!repository) throw new ServiceError(409,'repo_create_failed','Gitea repository was not created');
      owner=repository.owner?.login||repository.owner?.username||config.giteaOwner;
      name=repository.name;
      await gitea.addCollaborator(owner,name,username,'admin');
      await gitea.initializeRepository(repository,actor(claims,username));
      const record=(await db.query('insert into openspec_projects(gitea_owner,gitea_repository,default_branch,created_by) values($1,$2,$3,$4) returning *',[owner,name,repository.default_branch||'main',sub])).rows[0];
      projectPersisted=true;
      const response={id:record.id,owner:record.gitea_owner,repository:record.gitea_repository,revision:null};
      await db.completeProjectIdempotency(sub,idempotencyKey,201,response);
      return json(res,201,response,id);
    }catch(error){
      if(!projectPersisted&&owner&&name) await gitea.deleteRepo(owner,name).catch(()=>undefined);
      if(!projectPersisted) await db.abandonProjectIdempotency(sub,idempotencyKey).catch(()=>undefined);
      throw error;
    }
  }

  if(parts.length<3||!db.uuid(parts[2])) throw notFound();
  const args={projectId:parts[2],changeId:parts[4],expectedRevision:req.headers['if-match']?.replace(/^"|"$/g,''),requestId:id};
  if(req.method==='GET'&&parts[3]==='specs'&&parts.length===4) return json(res,200,await projectOperation('list_specs',args,claims),id);
  if(req.method==='GET'&&parts[3]==='specs'&&parts.length>=5){
    const record=await db.project(args.projectId);
    await projectAccess(record,claims,'read');
    const specId=parts.slice(4).join('/');
    return json(res,200,{projectId:record.id,id:specId,content:await ws.readSpec(await ws.ensureWorkspace(record),specId)},id);
  }
  if(req.method==='GET'&&parts[3]==='changes'&&parts.length===4) return json(res,200,await projectOperation('list_changes',args,claims),id);
  if(req.method==='GET'&&parts[3]==='changes'&&parts.length===5) return json(res,200,await projectOperation('get_change',args,claims),id);
  if(req.method==='POST'&&parts[3]==='changes'&&parts.length===5){
    args.body=await payload(req);
    const result=await writeOperation(req,url,claims,args,'create_proposal');
    return json(res,result.status,result.body,id);
  }
  if(req.method==='PUT'&&parts[3]==='changes'&&parts.length===5){
    args.body=await payload(req);
    const result=await writeOperation(req,url,claims,args,'update_proposal');
    return json(res,result.status,result.body,id);
  }
  if(req.method==='POST'&&parts[3]==='changes'&&parts.length===6&&parts[5]==='apply-specs'){
    const result=await writeOperation(req,url,claims,args,'apply_specs');
    return json(res,result.status,result.body,id);
  }
  if(req.method==='POST'&&parts[3]==='changes'&&parts.length===6&&parts[5]==='archive'){
    const result=await writeOperation(req,url,claims,args,'archive_change');
    return json(res,result.status,result.body,id);
  }
  if(req.method==='POST'&&parts[3]==='changes'&&parts.length===6&&parts[5]==='validate') return json(res,200,await projectOperation('validate_change',args,claims),id);
  throw notFound();
}

export async function handler(req,res){
  const id=requestId();
  try{await dispatch(req,res,id);}catch(error){
    const status=error.status||500;
    json(res,status,{error:error.code||'internal_error',message:status===404?'Not found':error.message},id);
  }
}
