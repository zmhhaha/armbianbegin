import crypto from 'node:crypto';
import {authenticate,subject} from './auth.mjs';
import {projectAccess} from './rest.mjs';
import * as db from './db.mjs';
import * as gitea from './gitea.mjs';
import * as ws from './workspace.mjs';
import {bindClaims} from './identity.mjs';
import {notFound,badRequest,ServiceError} from './errors.mjs';

const sessions=new Map();
const sessionTtlMs=60*60*1000;
const maxSessions=1024;
function rememberSession(id,sub){
  if(!sessions.has(id)&&sessions.size>=maxSessions)throw new ServiceError(503,'session_limit','MCP session limit reached');
  sessions.set(id,{sub,expiresAt:Date.now()+sessionTtlMs});
}
function sessionMatches(id,sub){
  const session=sessions.get(id);
  if(!session)return false;
  if(session.expiresAt<=Date.now()){sessions.delete(id);return false;}
  session.expiresAt=Date.now()+sessionTtlMs;
  return session.sub===sub;
}
const tools=[
  {name:'list_projects',description:'List projects visible to the authenticated user',inputSchema:{type:'object',properties:{},additionalProperties:false}},
  {name:'list_specs',description:'List specs in a project',inputSchema:{type:'object',required:['projectId'],properties:{projectId:{type:'string'}},additionalProperties:false}},
  {name:'list_changes',description:'List changes in a project',inputSchema:{type:'object',required:['projectId'],properties:{projectId:{type:'string'}},additionalProperties:false}},
  {name:'get_change',description:'Get a change in a project',inputSchema:{type:'object',required:['projectId','changeId'],properties:{projectId:{type:'string'},changeId:{type:'string'}},additionalProperties:false}},
  {name:'create_proposal',description:'Create an OpenSpec change from user-provided artifacts',inputSchema:{type:'object',required:['projectId','changeId','expectedRevision'],properties:{projectId:{type:'string'},changeId:{type:'string'},expectedRevision:{type:'string'},files:{type:'object',additionalProperties:{type:'string'}}},additionalProperties:false}},
  {name:'update_proposal',description:'Update user-provided artifacts in an existing OpenSpec change',inputSchema:{type:'object',required:['projectId','changeId','expectedRevision','files'],properties:{projectId:{type:'string'},changeId:{type:'string'},expectedRevision:{type:'string'},files:{type:'object',additionalProperties:{type:'string'}}},additionalProperties:false}},
  {name:'validate_change',description:'Validate an OpenSpec change',inputSchema:{type:'object',required:['projectId','changeId'],properties:{projectId:{type:'string'},changeId:{type:'string'}},additionalProperties:false}},
  {name:'apply_specs',description:'Apply change deltas to the project main specs without archiving the change',inputSchema:{type:'object',required:['projectId','changeId','expectedRevision'],properties:{projectId:{type:'string'},changeId:{type:'string'},expectedRevision:{type:'string'}},additionalProperties:false}},
  {name:'archive_change',description:'Archive a completed change and update the project main specs',inputSchema:{type:'object',required:['projectId','changeId','expectedRevision'],properties:{projectId:{type:'string'},changeId:{type:'string'},expectedRevision:{type:'string'}},additionalProperties:false}}
];

export async function callTool(name,args,claims,requestId){
  if(name==='list_projects') return db.visibleProjects(subject(claims),gitea);
  if(!args?.projectId||!db.uuid(args.projectId)) throw badRequest('valid projectId is required');
  const projectRecord=await db.project(args.projectId);
  if(['get_change','create_proposal','update_proposal','validate_change','apply_specs','archive_change'].includes(name)&&!ws.validChangeId(args.changeId)) throw badRequest('invalid change id');
  if(name==='list_specs'){await projectAccess(projectRecord,claims,'read');const directory=await ws.ensureWorkspace(projectRecord);return{projectId:projectRecord.id,revision:await ws.currentRevision(directory),items:await ws.list(directory,'specs')};}
  if(name==='list_changes'){await projectAccess(projectRecord,claims,'read');const directory=await ws.ensureWorkspace(projectRecord);return{projectId:projectRecord.id,revision:await ws.currentRevision(directory),items:await ws.list(directory,'changes')};}
  if(name==='get_change'){await projectAccess(projectRecord,claims,'read');return ws.readChange(await ws.ensureWorkspace(projectRecord),args.changeId);}
  if(name==='create_proposal'){
    await projectAccess(projectRecord,claims,'write');
    const username=await db.identity(subject(claims));
    const result=await ws.createChange(projectRecord,args.changeId,{name:username,email:claims.email},args.expectedRevision,args);
    await db.audit(projectRecord.id,subject(claims),'create_change',requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after};
  }
  if(name==='update_proposal'){
    await projectAccess(projectRecord,claims,'write');
    const username=await db.identity(subject(claims));
    const result=await ws.updateChange(projectRecord,args.changeId,{name:username,email:claims.email},args.expectedRevision,args);
    await db.audit(projectRecord.id,subject(claims),'update_change',requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after};
  }
  if(name==='validate_change'){await projectAccess(projectRecord,claims,'write');return{projectId:projectRecord.id,id:args.changeId,valid:true,result:await ws.validateChange(projectRecord,args.changeId)};}
  if(name==='apply_specs'){
    await projectAccess(projectRecord,claims,'write');
    const username=await db.identity(subject(claims));
    const result=await ws.applySpecs(projectRecord,args.changeId,{name:username,email:claims.email},args.expectedRevision);
    await db.audit(projectRecord.id,subject(claims),'apply_specs',requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after,updates:result.updates};
  }
  if(name==='archive_change'){
    await projectAccess(projectRecord,claims,'admin');
    const username=await db.identity(subject(claims));
    const result=await ws.archiveChange(projectRecord,args.changeId,{name:username,email:claims.email},args.expectedRevision);
    await db.audit(projectRecord.id,subject(claims),'archive_change',requestId,result.before,result.after);
    return{projectId:projectRecord.id,id:args.changeId,revision:result.after,archive:result.report};
  }
  throw notFound();
}

function response(res,status,body,sessionId,requestId){
  res.statusCode=status;
  res.setHeader('x-request-id',requestId||crypto.randomUUID());
  res.setHeader('content-type','application/json');
  if(sessionId) res.setHeader('mcp-session-id',sessionId);
  res.end(JSON.stringify(body));
}
function rpcError(error){
  const code=error instanceof ServiceError&&error.status===404?-32004:error instanceof ServiceError&&error.status===401?-32001:-32000;
  return{code,message:error.status===404?'Not found':error.message};
}

export async function mcpHandler(req,res){
  let id=null; let sessionId=req.headers['mcp-session-id']; const requestId=crypto.randomUUID();
  try{
    const claims=await authenticate(req);
    const sub=subject(claims);
    await bindClaims(claims);
    if(req.method==='GET'){
      sessionId=sessionId||crypto.randomUUID();
      if(sessions.has(sessionId)&&!sessionMatches(sessionId,sub)) throw new ServiceError(401,'invalid_session','MCP session does not belong to this identity');
      rememberSession(sessionId,sub);
      res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-cache','connection':'keep-alive','mcp-session-id':sessionId,'x-request-id':requestId});
      res.write('event: endpoint\ndata: /mcp\n\n');
      return res.end();
    }
    let raw='';
    for await(const chunk of req){raw+=chunk;if(raw.length>1048576)throw badRequest('request too large');}
    let body;
    try{body=raw?JSON.parse(raw):{};}catch{throw new ServiceError(400,'invalid_json','Invalid JSON');}
    id=body.id??null;
    if(body.jsonrpc!=='2.0'||typeof body.method!=='string') throw new ServiceError(400,'invalid_request','Invalid JSON-RPC request');
    if(body.method==='initialize'){
      sessionId=sessionId||crypto.randomUUID();
      if(sessions.has(sessionId)&&!sessionMatches(sessionId,sub)) throw new ServiceError(401,'invalid_session','MCP session does not belong to this identity');
      rememberSession(sessionId,sub);
      return response(res,200,{jsonrpc:'2.0',id,result:{protocolVersion:'2025-06-18',capabilities:{tools:{}},serverInfo:{name:'openspec-service',version:'0.1.1'}}},sessionId,requestId);
    }
    if(body.method==='notifications/initialized'){
      if(sessionId&&!sessionMatches(sessionId,sub)) throw new ServiceError(401,'invalid_session','MCP session does not belong to this identity');
      res.writeHead(202,{'x-request-id':requestId});return res.end();
    }
    if(sessionId&&!sessionMatches(sessionId,sub)) throw new ServiceError(401,'invalid_session','MCP session does not belong to this identity');
    if(body.method==='tools/list') return response(res,200,{jsonrpc:'2.0',id,result:{tools}},sessionId,requestId);
    if(body.method==='tools/call'){
      const name=body.params?.name; const args=body.params?.arguments||{};
      if(typeof name!=='string') throw new ServiceError(400,'invalid_params','Tool name is required');
      const requiresWriteHeaders=['create_proposal','update_proposal','apply_specs','archive_change'].includes(name);
      if(requiresWriteHeaders){
        if(!req.headers['idempotency-key']||req.headers['idempotency-key'].length>200) throw badRequest('Idempotency-Key header is required');
        if(!args.expectedRevision) throw badRequest('expectedRevision is required');
      }
      let idempotency;
      if(requiresWriteHeaders){
        const key=req.headers['idempotency-key'];
        idempotency=await db.beginIdempotency(sub,args.projectId,key,crypto.createHash('sha256').update(JSON.stringify({name,args})).digest('hex'));
        if(idempotency.replay) return response(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(idempotency.response)}],structuredContent:idempotency.response}},sessionId,requestId);
      }
      let value;
      try{value=await callTool(name,args,claims,requestId);}
      catch(error){if(idempotency) await db.abandonIdempotency(sub,args.projectId,req.headers['idempotency-key']);throw error;}
      if(idempotency) await db.completeIdempotency(sub,args.projectId,req.headers['idempotency-key'],200,value);
      return response(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value}},sessionId,requestId);
    }
    throw new ServiceError(404,'method_not_found','Unsupported MCP method: '+body.method);
  }catch(error){
    const status=error.status===401?401:error.status===404?404:400;
    return response(res,status,{jsonrpc:'2.0',id,error:rpcError(error)},sessionId,requestId);
  }
}

export function activeSessionCount(){for(const [id,session] of sessions)if(session.expiresAt<=Date.now())sessions.delete(id);return sessions.size;}
