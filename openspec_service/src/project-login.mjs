import crypto from 'node:crypto';
import {config} from './config.mjs';
import {projectRequestFormHtml} from './project-form.mjs';

// GET /project-requests/login —— 项目申请网页表单的登录管道。
//
// 浏览器打开 -> 302 到 Casdoor 授权（授权码 + PKCE）-> 回调带 code ->
// 服务端换 access_token -> 渲染带 token 的申请表单。
//
// ⚠️ 这是原来 `GET /token` 拆分后留下的**项目申请专用**那一半。另一半（给人取长期 JWT、
// 页面里印 claude/codex mcp add 用法）已随「标准 MCP 客户端走 OAuth 2.1 自动授权」退役，
// 归档在 oauth/token-dispenser/。别再把这个路由当成取 JWT 的入口。
//
// 用的是 MCP 专用应用（CASDOOR_MCP_CLIENT_ID）：2026-10-02 实测**不需要 client_secret**，
// 所以服务端不再持有任何 Casdoor 机密。
// 它签发的 token 其 aud = 该 client_id，已包含在 OIDC_AUDIENCE 里。

const pendingStates=new Map();
function issueState(){
  const s=crypto.randomUUID();
  // PKCE：verifier 只存在服务端内存里（单副本部署），challenge 随授权请求发出。
  const verifier=crypto.randomBytes(32).toString('base64url');
  pendingStates.set(s,{exp:Date.now()+10*60*1000,verifier});
  return{state:s,verifier};
}
function consumeState(s){
  if(typeof s!=='string'||s.length===0)return null;
  const e=pendingStates.get(s);
  if(!e||e.exp<Date.now())return null;
  pendingStates.delete(s);
  return e;
}

export async function projectLoginHandler(req,res){
  const url=new URL(req.url,'http://localhost');
  const redirectUri=`${config.publicBaseUrl}/project-requests/login`;
  const send=(status,body)=>{res.writeHead(status,{'content-type':'text/html; charset=utf-8'});return res.end(body);};
  if(!url.searchParams.has('code')){
    const {state,verifier}=issueState();
    const challenge=crypto.createHash('sha256').update(verifier).digest('base64url');
    const authorize=`${config.oidcIssuer}/login/oauth/authorize?client_id=${encodeURIComponent(config.casdoorMcpClientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=openid%20profile%20email&state=${state}&code_challenge=${challenge}&code_challenge_method=S256`;
    res.writeHead(302,{location:authorize});
    return res.end();
  }
  const code=url.searchParams.get('code');const state=url.searchParams.get('state');
  const stateInfo=consumeState(state);
  if(!stateInfo) return send(400,'<p>state 校验失败，请重新打开 <a href="/project-requests">项目申请</a>。</p>');
  let data;
  try{
    const r=await fetch(`${config.oidcIssuer}/api/login/oauth/access_token`,{
      method:'POST',
      headers:{'content-type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({grant_type:'authorization_code',client_id:config.casdoorMcpClientId,code,redirect_uri:redirectUri,code_verifier:stateInfo.verifier})
    });
    data=await r.json();
  }catch(e){return send(502,'<p>连接 Casdoor 失败：'+e.message+'</p>');}
  const token=data?.access_token;
  if(!token) return send(400,'<p>换取 token 失败：'+(data?.error_description||data?.error||'unknown')+'。请重新打开 <a href="/project-requests">项目申请</a>。</p>');
  return send(200,projectRequestFormHtml(token));
}
