import {config} from './config.mjs'; import {conflict,unavailable} from './errors.mjs';

async function api(p,opt={}) {
  if(!config.giteaToken) throw unavailable('GITEA_TOKEN is not configured');
  let r;
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),15000);
  try {
    r=await fetch(config.giteaUrl+'/api/v1'+p,{...opt,signal:controller.signal,headers:{authorization:'token '+config.giteaToken,'content-type':'application/json',...(opt.headers||{})}});
  } catch(e) { throw unavailable('Gitea API unavailable: '+(e.name==='AbortError'?'request timed out':e.message)); }
  finally { clearTimeout(timer); }
  if(r.status===404) return null;
  if(!r.ok) throw unavailable('Gitea API returned '+r.status);
  return r.status===204?null:r.json();
}
const enc=x=>encodeURIComponent(x);
export const createPrivateRepo=name=>api('/orgs/'+enc(config.giteaOwner)+'/repos',{method:'POST',body:JSON.stringify({name,private:true,auto_init:true,default_branch:'main'})});
export async function addCollaborator(owner,repository,username,permission='admin'){await api('/repos/'+enc(owner)+'/'+enc(repository)+'/collaborators/'+enc(username),{method:'PUT',body:JSON.stringify({permission})});}
export async function deleteRepo(owner,repository){await api('/repos/'+enc(owner)+'/'+enc(repository),{method:'DELETE'});}
export const user=login=>api('/users/'+enc(login));
export async function createIssue(owner,repository,{title,body}){return api('/repos/'+enc(owner)+'/'+enc(repository)+'/issues',{method:'POST',body:JSON.stringify({title,body})});}
export async function createFile(owner,repository,filePath,content,{branch='main',message='chore: initialize OpenSpec store',username=config.giteaUsername,email=config.gitEmail}={}){const body={branch,content:Buffer.from(content,'utf8').toString('base64'),message,author:{name:username,email},committer:{name:username,email}};return api('/repos/'+enc(owner)+'/'+enc(repository)+'/contents/'+filePath.split('/').map(enc).join('/'),{method:'POST',body:JSON.stringify(body)});}
export async function initializeRepository(repository,actor){const owner=repository.owner?.login||repository.owner?.username||config.giteaOwner;const name=repository.name;const branch=repository.default_branch||'main';const files=[['openspec/config.yaml','schema: spec-driven\n'],['openspec/specs/.gitkeep','\n'],['openspec/changes/.gitkeep','\n'],['openspec/changes/archive/.gitkeep','\n'],['.openspec-store/store.yaml','version: 1\nid: '+name+'\n']];for(const [file,content] of files)await createFile(owner,name,file,content,{branch,message:'chore: initialize OpenSpec store',username:actor.name,email:actor.email});return{owner,name,branch};}
export async function permission(owner,repo,user){const d=await api('/repos/'+enc(owner)+'/'+enc(repo)+'/collaborators/'+enc(user)+'/permission');if(!d)return'none';const p=d.permission||d.role||'none';return['owner','admin','write','read','none'].includes(p)?p:'none';}
export async function usernameByEmail(email){
  const value=typeof email==='string'?email.trim():'';
  if(!/^[^\s<>@\r\n]+@[^\s<>@\r\n]+$/.test(value))throw conflict('Casdoor JWT must contain a valid email for Gitea identity binding');
  const normalized=value.toLowerCase();
  const result=await api('/users/search?q='+encodeURIComponent(value)+'&limit=50');
  const users=Array.isArray(result)?result:(Array.isArray(result?.data)?result.data:Array.isArray(result?.users)?result.users:[]);
  const matches=users.filter(user=>typeof user?.email==='string'&&user.email.trim().toLowerCase()===normalized);
  if(matches.length===0)throw conflict(users.length?'Gitea user search returned no exact email match; check read:user permission and email visibility':'No Gitea user matches the Casdoor email');
  if(matches.length>1)throw conflict('Multiple Gitea users match the Casdoor email');
  const username=matches[0].login||matches[0].username;
  if(typeof username!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(username))throw conflict('Gitea user returned for the Casdoor email has an invalid username');
  return username;
}
export async function commentIssue(owner,repository,index,body){return api('/repos/'+enc(owner)+'/'+enc(repository)+'/issues/'+encodeURIComponent(String(index))+'/comments',{method:'POST',body:JSON.stringify({body})});}
export async function updateIssue(owner,repository,index,changes){return api('/repos/'+enc(owner)+'/'+enc(repository)+'/issues/'+encodeURIComponent(String(index)),{method:'PATCH',body:JSON.stringify(changes)});}
export async function addIssueLabels(owner,repository,index,labels){
  const listed=await api('/repos/'+enc(owner)+'/'+enc(repository)+'/labels?limit=100');
  const available=Array.isArray(listed)?listed:(Array.isArray(listed?.data)?listed.data:[]);
  const ids=available.filter(label=>labels.includes(label?.name)).map(label=>label.id).filter(Number.isInteger);
  if(!ids.length)return null;
  return api('/repos/'+enc(owner)+'/'+enc(repository)+'/issues/'+encodeURIComponent(String(index))+'/labels',{method:'POST',body:JSON.stringify({labels:ids})});
}
export const repo=(o,n)=>api('/repos/'+enc(o)+'/'+enc(n));
