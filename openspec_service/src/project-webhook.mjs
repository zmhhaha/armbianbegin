import crypto from 'node:crypto';
import {config} from './config.mjs';
import * as db from './db.mjs';
import * as gitea from './gitea.mjs';
import {provisionProject} from './project-provisioning.mjs';
import {isApprovalEvent,issueNumber,parseProjectRequest,repositoryMatches,verifyWebhookSignature} from './project-request.mjs';

const ranks={none:0,read:1,write:2,admin:3,owner:4};
const maxBody=1048576;

const json=(res,status,body,id)=>{
  if(id)res.setHeader('x-request-id',id);
  res.writeHead(status,{'content-type':'application/json'});
  res.end(JSON.stringify(body));
};

async function body(req){
  let raw='';
  for await(const chunk of req){raw+=chunk;if(raw.length>maxBody)throw new Error('webhook payload too large');}
  return raw;
}

function safeError(error){return String(error?.message||error||'unknown error').replace(/(token|secret|password|authorization)\s*[:=]?\s*[^\s,;]+/gi,'$1=[redacted]').slice(0,500);}

async function issueMessage(owner,repository,index,message,{close=false,label=null}={}){
  await gitea.commentIssue(owner,repository,index,message).catch(()=>undefined);
  if(label)await gitea.addIssueLabels(owner,repository,index,[label]).catch(()=>undefined);
  if(close)await gitea.updateIssue(owner,repository,index,{state:'closed'}).catch(()=>undefined);
}

export async function handleGiteaWebhook(req,res,id=crypto.randomUUID()){
  let raw;
  try{raw=await body(req);}catch(error){return json(res,413,{error:'payload_too_large',message:error.message},id);}
  let verified;
  try{verified=verifyWebhookSignature(raw,req.headers['x-gitea-signature']);}
  catch(error){return json(res,error.status||503,{error:error.code||'webhook_not_configured',message:error.message},id);}
  if(!verified)return json(res,401,{error:'invalid_webhook_signature',message:'Gitea webhook signature is invalid'},id);
  let payload;
  try{payload=JSON.parse(raw);}catch{return json(res,202,{status:'ignored',reason:'invalid_json'},id);}
  const event=String(req.headers['x-gitea-event']||'');
  if(!repositoryMatches(payload)||!isApprovalEvent(event,payload))return json(res,202,{status:'ignored'},id);
  const number=issueNumber(payload);
  const approver=payload.sender?.login||payload.sender?.username;
  const requester=payload.issue?.user?.login||payload.issue?.user?.username;
  if(!number||!approver||!requester)return json(res,202,{status:'ignored',reason:'missing_issue_actor'},id);
  const requestOwner=config.giteaRequestOwner;
  const requestRepository=config.giteaRequestRepository;
  const permission=await gitea.permission(requestOwner,requestRepository,approver);
  if((ranks[permission]||0)<ranks.admin){
    await db.auditRequest({owner:requestOwner,repository:requestRepository,issueNumber:number,actor:approver,action:'project_request_approval_denied',requestId:id,details:{permission}}).catch(()=>undefined);
    return json(res,202,{status:'ignored',reason:'approver_not_admin'},id);
  }
  let request;
  try{request=parseProjectRequest(payload.issue.body||'');}
  catch(error){
    await db.auditRequest({owner:requestOwner,repository:requestRepository,issueNumber:number,actor:approver,action:'project_request_rejected',requestId:id,details:{error:safeError(error)}}).catch(()=>undefined);
    await issueMessage(requestOwner,requestRepository,number,`项目申请未通过校验：${safeError(error)}`,{label:config.giteaFailureLabel});
    return json(res,202,{status:'rejected',reason:'invalid_request'},id);
  }
  const claimed=await db.claimProjectRequest({owner:requestOwner,repository:requestRepository,issueNumber:number,requesterUsername:requester,payload:request,approvedBy:approver});
  if(!claimed.claimed)return json(res,202,{status:claimed.request.status,requestId:claimed.request.id,projectId:claimed.request.project_id||null},id);
  const storedRequest=claimed.request.payload;
  const storedRequester=claimed.request.requester_username;
  await db.auditRequest({owner:requestOwner,repository:requestRepository,issueNumber:number,actor:approver,action:'project_request_approved',requestId:id,details:{slug:storedRequest.slug,requester:storedRequester}}).catch(()=>undefined);
  try{
    const account=await gitea.user(storedRequester);
    const result=await provisionProject({slug:storedRequest.slug,username:storedRequester,email:account?.email||config.gitEmail,createdBy:`gitea:${storedRequester}`,initialPermission:storedRequest.initialPermission});
    await db.completeProjectRequest(claimed.request.id,{status:'provisioned',projectId:result.record.id});
    const store=`${config.giteaPublicUrl}/${result.response.owner}/${result.response.repository}`;
    await issueMessage(requestOwner,requestRepository,number,`项目已自动创建。\n\n- projectId: \`${result.response.id}\`\n- OpenSpec store: ${store}\n- requester permission: ${storedRequest.initialPermission}`,{close:true});
    await db.auditRequest({owner:requestOwner,repository:requestRepository,issueNumber:number,actor:approver,action:'project_request_provisioned',requestId:id,details:{projectId:result.response.id,repository:result.response.repository}}).catch(()=>undefined);
    return json(res,202,{status:'provisioned',projectId:result.response.id,repository:result.response.repository},id);
  }catch(error){
    const message=safeError(error);
    await db.completeProjectRequest(claimed.request.id,{status:'failed',errorMessage:message}).catch(()=>undefined);
    await issueMessage(requestOwner,requestRepository,number,`项目自动创建失败，管理员可移除后重新添加 ${config.giteaApprovalLabel} 标签重试。\n\n错误：${message}`,{label:config.giteaFailureLabel});
    await db.auditRequest({owner:requestOwner,repository:requestRepository,issueNumber:number,actor:approver,action:'project_request_provision_failed',requestId:id,details:{error:message}}).catch(()=>undefined);
    return json(res,202,{status:'failed',message:'project provisioning failed'},id);
  }
}
