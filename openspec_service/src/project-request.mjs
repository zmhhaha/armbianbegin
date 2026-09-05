import crypto from 'node:crypto';
import {config} from './config.mjs';
import {badRequest,ServiceError} from './errors.mjs';

const marker=/<!--\s*openspec-project-request:v1\s*([\s\S]*?)-->/i;
const slugPattern=/^[A-Za-z0-9][A-Za-z0-9.-]{0,99}$/;
const refPattern=/^[A-Za-z0-9._/-]{1,200}$/;
const permissions=new Set(['read','write','admin']);

export function verifyWebhookSignature(raw,signature){
  if(!config.giteaWebhookSecret)throw new ServiceError(503,'webhook_not_configured','Gitea webhook secret is not configured');
  const supplied=String(signature||'').replace(/^sha256=/i,'').trim().toLowerCase();
  const expected=crypto.createHmac('sha256',config.giteaWebhookSecret).update(raw).digest('hex');
  if(!/^[0-9a-f]{64}$/.test(supplied))return false;
  return crypto.timingSafeEqual(Buffer.from(expected,'hex'),Buffer.from(supplied,'hex'));
}

function text(value,name,max){
  if(typeof value!=='string'||value.trim().length===0||value.length>max)throw badRequest(`${name} is required and must be at most ${max} characters`);
  return value.trim();
}

function sourceUrl(value){
  const raw=text(value,'sourceUrl',500);
  let url;
  try{url=new URL(raw);}catch{throw badRequest('sourceUrl must be a valid HTTPS GitHub URL');}
  if(url.protocol!=='https:'||url.hostname.toLowerCase()!=='github.com'||url.username||url.password||url.search||url.hash)throw badRequest('sourceUrl must be a public HTTPS github.com repository URL');
  const parts=url.pathname.replace(/\/$/,'').split('/').filter(Boolean);
  if(parts.length!==2||!parts.every(part=>/^[A-Za-z0-9._-]+$/.test(part)))throw badRequest('sourceUrl must use the form https://github.com/owner/repository');
  return `https://github.com/${parts[0]}/${parts[1].replace(/\.git$/i,'')}`;
}

export function parseProjectRequest(body){
  const match=marker.exec(typeof body==='string'?body:'');
  if(!match)throw badRequest('issue body must contain an openspec-project-request:v1 JSON block');
  let data;
  try{data=JSON.parse(match[1].trim());}catch{throw badRequest('project request JSON is invalid');}
  const slug=text(data.slug,'slug',100);
  if(!slugPattern.test(slug))throw badRequest('invalid project slug');
  const displayName=text(data.displayName||slug,'displayName',120);
  const ref=text(data.ref||'main','ref',200);
  if(!refPattern.test(ref)||ref.includes('..'))throw badRequest('invalid source ref');
  const scriptProfileId=data.scriptProfileId?text(data.scriptProfileId,'scriptProfileId',100):null;
  if(scriptProfileId&&!config.scriptProfiles.has(scriptProfileId))throw badRequest('script profile is not registered');
  const initialPermission=data.initialPermission||'admin';
  if(!permissions.has(initialPermission))throw badRequest('initialPermission must be read, write, or admin');
  return{version:1,slug,displayName,sourceUrl:sourceUrl(data.sourceUrl),ref,scriptProfileId,initialPermission};
}

export function isApprovalEvent(event,payload){
  if(event!=='issues'||!['label_updated','update'].includes(payload?.action))return false;
  const labels=Array.isArray(payload?.issue?.labels)?payload.issue.labels:[];
  return labels.some(label=>String(label?.name||label||'')===config.giteaApprovalLabel);
}

export function repositoryMatches(payload){
  const repo=payload?.repository;
  const owner=repo?.owner?.login||repo?.owner?.username||repo?.owner?.name;
  return owner===config.giteaRequestOwner&&repo?.name===config.giteaRequestRepository;
}

export function issueNumber(payload){
  const value=payload?.issue?.number;
  return Number.isInteger(value)&&value>0?value:null;
}
