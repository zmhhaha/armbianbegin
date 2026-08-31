import {createRemoteJWKSet,jwtVerify} from 'jose'; import {config} from './config.mjs'; import {unauthorized,unavailable} from './errors.mjs';
const keys=config.oidcJwksUrl?createRemoteJWKSet(new URL(config.oidcJwksUrl)):null;
export async function authenticate(req,probe=false){if(probe)return{sub:'probe',preferred_username:'probe'};if(!keys||!config.oidcIssuer)throw unavailable('OIDC is not configured');const h=req.headers.authorization||'';if(!h.startsWith('Bearer '))throw unauthorized();try{return(await jwtVerify(h.slice(7),keys,{issuer:config.oidcIssuer,audience:config.oidcAudience})).payload;}catch(e){throw unauthorized(`Invalid bearer token: ${e.message}`);}}
export function subject(c){if(!c?.sub||typeof c.sub!=='string')throw unauthorized('JWT sub is required');return c.sub;}
