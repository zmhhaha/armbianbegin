import crypto from 'node:crypto';
import {config} from './config.mjs';

// GET /token —— 网页版 JWT 领取器。
// 用户浏览器打开 -> 302 到 Casdoor 授权 -> 回调带 code -> 服务端换 access_token -> 渲染 JWT 页面。
// 需要：panghu-suite 应用 redirect_uris 白名单包含 `${publicBaseUrl}/token`；
//       服务持有 CASDOOR_CLIENT_SECRET（从 Vault 注入）。

const pendingStates=new Map();
function issueState(){const s=crypto.randomUUID();pendingStates.set(s,{exp:Date.now()+10*60*1000});return s;}
function consumeState(s){if(typeof s!=='string'||s.length===0)return false;const e=pendingStates.get(s);if(!e||e.exp<Date.now())return false;pendingStates.delete(s);return true;}

function decodeExp(token){
  try{
    const p=token.split('.')[1]||'';const pad=p+'='.repeat((4-p.length%4)%4);
    const payload=JSON.parse(Buffer.from(pad,'base64url').toString('utf8'));
    return payload.exp?new Date(payload.exp*1000).toISOString():'';
  }catch{return '';}
}

function html(token){
  const exp=decodeExp(token);
  const c=JSON.stringify(token).slice(1,-1); // 供 JS 使用，同时避免注入
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenSpec 访问令牌</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:720px;margin:40px auto;padding:0 16px;color:#1f2328}
h1{font-size:22px} .box{border:1px solid #d0d7de;border-radius:8px;padding:16px;margin:12px 0}
label{font-weight:600;display:block;margin-bottom:6px}
textarea{width:100%;min-height:120px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;box-sizing:border-box}
button{margin-top:8px;padding:6px 14px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;cursor:pointer}
code{background:#f6f8fa;padding:2px 5px;border-radius:4px;font-size:12px}
.hint{color:#57606a;font-size:13px}
.warn{color:#9a6700;font-size:13px}
</style></head><body>
<h1>OpenSpec 访问令牌</h1>
<p class="hint">此令牌用于 Codex / Claude Code 连接 <code>https://openspec.panghuer.top/mcp</code>。
你有权访问哪些项目，由你在 Gitea <code>openspec-service</code> 组里的权限决定。</p>
<div class="box"><label>Bearer JWT ${exp?`（约 ${exp} 到期）`:''}</label>
<textarea id="t" readonly onclick="this.select()">${token}</textarea><br>
<button onclick="navigator.clipboard.writeText(document.getElementById('t').value);this.textContent='已复制'">复制</button></div>
<div class="box"><label>Claude Code</label><code>claude mcp add --transport http openspec https://openspec.panghuer.top/mcp --header "Authorization: Bearer <token>"</code></div>
<div class="box"><label>Codex CLI</label><code>codex mcp add openspec --transport streamable-http https://openspec.panghuer.top/mcp --header "Authorization: Bearer <token>"</code></div>
<p class="warn">⚠️ 令牌等于你的身份，不要发到聊天、日志或公开仓库。</p>
</body></html>`;
}

export async function tokenHandler(req,res){
  const url=new URL(req.url,'http://localhost');
  const redirectUri=`${config.publicBaseUrl}/token`;
  const send=(status,body)=>{res.writeHead(status,{'content-type':'text/html; charset=utf-8'});return res.end(body);};
  if(!config.casdoorClientSecret) return send(503,'<h1>未配置 CASDOOR_CLIENT_SECRET</h1><p>请联系管理员在 Vault 中配置 casdoor_client_secret 后重启服务。</p>');
  if(!url.searchParams.has('code')){
    const state=issueState();
    const authorize=`${config.oidcIssuer}/login/oauth/authorize?client_id=${encodeURIComponent(config.casdoorClientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=openid%20profile%20email&state=${state}`;
    res.writeHead(302,{location:authorize});
    return res.end();
  }
  const code=url.searchParams.get('code');const state=url.searchParams.get('state');
  if(!consumeState(state)) return send(400,'<p>state 校验失败，请重新打开 <a href="/token">/token</a>。</p>');
  let data;
  try{
    const r=await fetch(`${config.oidcIssuer}/api/login/oauth/access_token`,{
      method:'POST',
      headers:{'content-type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({grant_type:'authorization_code',client_id:config.casdoorClientId,client_secret:config.casdoorClientSecret,code,redirect_uri:redirectUri})
    });
    data=await r.json();
  }catch(e){return send(502,'<p>连接 Casdoor 失败：'+e.message+'</p>');}
  const token=data?.access_token;
  if(!token) return send(400,'<p>换取 token 失败：'+(data?.error_description||data?.error||'unknown')+'。请重新打开 <a href="/token">/token</a>。</p>');
  return send(200,html(token));
}
