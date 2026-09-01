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
  const code=error instanceof ServiceError&&error.code==='invalid_session'?-32002:error instanceof ServiceError&&error.status===404?-32004:error instanceof ServiceError&&error.status===401?-32001:-32000;
  return{code,message:error instanceof ServiceError&&error.code==='invalid_session'?error.message:error.status===404?'Not found':error.message};
}

export async function mcpHandler(req,res){
  let id=null; let sessionId=req.headers['mcp-session-id']; const requestId=crypto.randomUUID();
  try{
    const claims=await authenticate(req);
    const sub=subject(claims);
    await bindClaims(claims);
    if(req.method==='GET'){
      sessionId=sessionId||crypto.randomUUID();
      if(sessions.has(sessionId)&&!sessionMatches(sessionId,sub)) throw new ServiceError(404,'invalid_session','MCP session expired or does not belong to this identity');
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
      if(sessions.has(sessionId)&&!sessionMatches(sessionId,sub)) throw new ServiceError(404,'invalid_session','MCP session expired or does not belong to this identity');
      rememberSession(sessionId,sub);
      return response(res,200,{jsonrpc:'2.0',id,result:{protocolVersion:'2025-06-18',capabilities:{tools:{}},serverInfo:{name:'openspec-service',version:'latest'}}},sessionId,requestId);
    }
    if(body.method==='notifications/initialized'||body.method==='notifications/cancelled'){
      if(sessionId&&!sessionMatches(sessionId,sub)) throw new ServiceError(404,'invalid_session','MCP session expired or does not belong to this identity');
      res.writeHead(202,{'mcp-session-id':sessionId||crypto.randomUUID(),'x-request-id':requestId});return res.end();
    }
    if(body.method==='ping') return response(res,200,{jsonrpc:'2.0',id,result:{}},sessionId,requestId);
    if(sessionId&&!sessionMatches(sessionId,sub)) throw new ServiceError(404,'invalid_session','MCP session expired or does not belong to this identity');
    if(body.method==='tools/list') return response(res,200,{jsonrpc:'2.0',id,result:{tools}},sessionId,requestId);
    if(body.method==='tools/call'){
      const name=body.params?.name; const args=body.params?.arguments||{};
      if(typeof name!=='string') throw new ServiceError(400,'invalid_params','Tool name is required');
      const requiresWriteHeaders=['create_proposal','update_proposal','apply_specs','archive_change'].includes(name);
      if(requiresWriteHeaders&&!args.expectedRevision) throw badRequest('expectedRevision is required');
      let idempotency;
      let idempotencyKey;
      if(requiresWriteHeaders){
        // 优先用客户端提供的 Idempotency-Key 头；不传时按 用户+项目+工具+参数 派生确定性键，
        // 使标准 MCP 客户端（固定请求头）也能安全重试，且不同调用互不冲突。
        idempotencyKey=(req.headers['idempotency-key']&&req.headers['idempotency-key'].length<=200)
          ? req.headers['idempotency-key']
          : crypto.createHash('sha256').update([sub,args.projectId,name,JSON.stringify(args)].join(':')).digest('hex');
        idempotency=await db.beginIdempotency(sub,args.projectId,idempotencyKey,crypto.createHash('sha256').update(JSON.stringify({name,args})).digest('hex'));
        if(idempotency.replay) return response(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(idempotency.response)}],structuredContent:idempotency.response}},sessionId,requestId);
      }
      let value;
      try{value=await callTool(name,args,claims,requestId);}
      catch(error){if(idempotency) await db.abandonIdempotency(sub,args.projectId,idempotencyKey);throw error;}
      if(idempotency) await db.completeIdempotency(sub,args.projectId,idempotencyKey,200,value);
      return response(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value}},sessionId,requestId);
    }
    // 未知方法必须返回 HTTP 200 + JSON-RPC 错误，绝不能返回 HTTP 404：
    // Codex/RMCP 会把 404 误判为 session 失效（见 openai/codex#13969）。
    return response(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found: '+body.method}},sessionId,requestId);
  }catch(error){
    const status=error.code==='invalid_session'?404:error.status===401?401:200;
    return response(res,status,{jsonrpc:'2.0',id,error:rpcError(error)},sessionId,requestId);
  }
}

export function activeSessionCount(){for(const [id,session] of sessions)if(session.expiresAt<=Date.now())sessions.delete(id);return sessions.size;}
