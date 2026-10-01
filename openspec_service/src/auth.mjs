import {createRemoteJWKSet,jwtVerify} from 'jose'; import {config} from './config.mjs'; import {unauthorized,unavailable} from './errors.mjs';
const keys=config.oidcJwksUrl?createRemoteJWKSet(new URL(config.oidcJwksUrl)):null;
export async function authenticate(req,probe=false){if(probe)return{sub:'probe',preferred_username:'probe'};if(!keys||!config.oidcIssuer)throw unavailable('OIDC is not configured');const h=req.headers.authorization||'';if(!h.startsWith('Bearer '))throw unauthorized();try{return(await jwtVerify(h.slice(7),keys,{issuer:config.oidcIssuer,audience:config.oidcAudience})).payload;}catch(e){throw unauthorized(`Invalid bearer token: ${e.message}`);}}
export function subject(c){if(!c?.sub||typeof c.sub!=='string')throw unauthorized('JWT sub is required');return c.sub;}

// —— RFC 9728：本服务作为「受保护资源」，公开声明该找谁授权。必须匿名可读（路由见 rest.mjs 的公开分支）。
// resource 带路径时的 well-known 形状见 RFC 9728 §3.1：把 /.well-known/oauth-protected-resource 插在
// host 与 path 之间 —— resource=https://host/mcp → /.well-known/oauth-protected-resource/mcp。
// 根形式一并提供，作为部分客户端的兼容回退；401 挑战头里用规范正解的那一个。
export const protectedResourceMetadataUrl=()=>`${config.publicBaseUrl}/.well-known/oauth-protected-resource/mcp`;
export const bearerChallenge=()=>`Bearer resource_metadata="${protectedResourceMetadataUrl()}"`;
export function protectedResourceMetadata(){
  if(!config.oidcIssuer) throw unavailable('OIDC is not configured');
  // 故意不声明 scopes_supported：当前只校验 issuer + audience，不校验 scope。
  // 声明了却不校验，只会让客户端去申请一堆无效 scope；等 scope 门真的实现后再加。
  return{resource:`${config.publicBaseUrl}/mcp`,authorization_servers:[config.oidcIssuer],bearer_methods_supported:['header']};
}
