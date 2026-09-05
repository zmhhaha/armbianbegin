import {config} from './config.mjs';
import {badRequest} from './errors.mjs';
import {parseProjectRequest} from './project-request.mjs';

const allowedFields=new Set(['displayName','slug','sourceUrl','ref','scriptProfileId','description']);
const htmlEscape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

function required(value,name,max){
  if(typeof value!=='string'||value.trim().length===0||value.length>max)throw badRequest(`${name} is required and must be at most ${max} characters`);
  return value.trim();
}

export function buildProjectRequest(input={}){
  if(!input||typeof input!=='object'||Array.isArray(input))throw badRequest('JSON object is required');
  for(const key of Object.keys(input))if(!allowedFields.has(key))throw badRequest(`unsupported form field: ${key}`);
  const displayName=required(input.displayName,'displayName',120);
  const slug=required(input.slug,'slug',100);
  const sourceUrl=required(input.sourceUrl,'sourceUrl',500);
  const ref=required(input.ref||'main','ref',200);
  const scriptProfileId=required(input.scriptProfileId||[...config.scriptProfiles][0]||'','scriptProfileId',100);
  const description=input.description===undefined?'':input.description;
  if(typeof description!=='string'||description.length>4000||description.includes('\u0000'))throw badRequest('description must be at most 4000 characters');
  const data={displayName,slug,sourceUrl,ref,scriptProfileId,initialPermission:'admin'};
  const body=`<!-- openspec-project-request:v1\n${JSON.stringify(data,null,2)}\n-->\n\n## 申请说明\n\n${description.trim()||'（未填写）'}`;
  const request=parseProjectRequest(body);
  return{request,body,title:`[project-request] ${displayName}`.slice(0,200)};
}

export function projectRequestEntryHtml(){return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenSpec 项目申请</title><style>body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:640px;margin:64px auto;padding:0 20px;color:#1f2328}a{display:inline-block;padding:10px 16px;background:#0969da;color:white;border-radius:6px;text-decoration:none}p{color:#57606a;line-height:1.6}</style></head>
<body><h1>OpenSpec 项目申请</h1><p>登录 Casdoor 后填写项目申请表。提交后由管理员在 Gitea 审核。</p><a href="/token?return=/project-requests">使用 Casdoor 登录</a></body></html>`;}

export function projectRequestFormHtml(token){
  const tokenLiteral=JSON.stringify(token).replace(/</g,'\\u003c');
  const options=[...config.scriptProfiles].map(profile=>`<option value="${htmlEscape(profile)}">${htmlEscape(profile)}</option>`).join('');
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>申请 OpenSpec 项目</title><style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:760px;margin:36px auto;padding:0 20px;color:#1f2328}h1{font-size:24px}form{display:grid;gap:14px}label{font-weight:600;display:grid;gap:6px}input,select,textarea{font:inherit;padding:9px;border:1px solid #d0d7de;border-radius:6px;box-sizing:border-box;width:100%}textarea{min-height:120px;resize:vertical}button{padding:10px 16px;border:0;border-radius:6px;background:#0969da;color:white;font:inherit;cursor:pointer}button:disabled{opacity:.6}.hint{color:#57606a;font-size:13px;line-height:1.5}.result{margin-top:20px;padding:12px;border-radius:6px;background:#ddf4ff;display:none}.error{margin-top:20px;padding:12px;border-radius:6px;background:#ffebe9;color:#82071e;display:none}
</style></head><body><h1>申请 OpenSpec 项目</h1><p class="hint">填写后会生成一份 Gitea 申请工单，管理员审核通过后才会创建私有 OpenSpec 仓库。</p>
<form id="request-form"><label>项目显示名称<input name="displayName" maxlength="120" required placeholder="My application"></label>
<label>项目 slug<input name="slug" maxlength="100" pattern="[A-Za-z0-9][A-Za-z0-9.-]{0,99}" required placeholder="my-app"><span class="hint">只能使用字母、数字、点和短横线。</span></label>
<label>GitHub 公共仓库地址<input name="sourceUrl" type="url" required placeholder="https://github.com/example/my-app"></label>
<label>默认分支或 ref<input name="ref" value="main" maxlength="200" required></label>
<label>脚本 profile<select name="scriptProfileId" required>${options}</select></label>
<label>项目说明<textarea name="description" maxlength="4000" placeholder="说明项目用途、初始成员和其他需要管理员关注的事项"></textarea></label>
<button id="submit" type="submit">提交项目申请</button></form><div id="result" class="result"></div><div id="error" class="error"></div>
<script>
const token=${tokenLiteral};
const form=document.getElementById('request-form');
const button=document.getElementById('submit');
const result=document.getElementById('result');
const errorBox=document.getElementById('error');
const makeKey=()=>globalThis.crypto&&crypto.randomUUID?crypto.randomUUID():String(Date.now())+'-'+Math.random();
let key=makeKey();
form.addEventListener('submit',async event=>{
  event.preventDefault();
  button.disabled=true;
  result.style.display='none';
  errorBox.style.display='none';
  const data=Object.fromEntries(new FormData(form).entries());
  try{
    const response=await fetch('/v1/project-requests',{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(data)});
    const body=await response.json();
    if(!response.ok)throw new Error(body.message||body.error||'提交失败');
    result.replaceChildren();
    result.append('申请已提交：');
    const link=document.createElement('a');
    link.target='_blank';
    link.rel='noreferrer';
    link.href=body.issueUrl;
    link.textContent='查看 Gitea 工单 #'+body.issueNumber;
    result.append(link,'，当前状态为 pending。');
    result.style.display='block';
    form.reset();
    key=makeKey();
  }catch(error){
    errorBox.textContent=error.message;
    errorBox.style.display='block';
  }finally{
    button.disabled=false;
  }
});
</script></body></html>`;
}
