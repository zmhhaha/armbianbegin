import {subject} from './auth.mjs';
import * as db from './db.mjs';
import * as gitea from './gitea.mjs';

// Resolve the external identity once. The immutable sub-to-login mapping is
// then used for ACL checks even if a user later changes an email address.
export async function bindClaims(claims){
  const sub=subject(claims);
  const existing=await db.identity(sub);
  if(existing)return existing;
  const username=await gitea.usernameByEmail(claims.email);
  await db.bindIdentity(sub,username);
  return username;
}
