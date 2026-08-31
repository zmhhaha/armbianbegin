import fs from 'node:fs/promises';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {config} from './config.mjs';
import {badRequest,conflict,unavailable,notFound} from './errors.mjs';

const run=promisify(execFile);
const require=createRequire(import.meta.url);
const openspecEntry=require.resolve('@fission-ai/openspec');
const specsApply=await import(pathToFileURL(path.join(path.dirname(openspecEntry),'core','specs-apply.js')).href);
const locks=new Map();
const windowsOpenSpecScript=process.platform==='win32'&&/\.(?:cmd|bat)$/i.test(config.openspecBin)
  ? path.join(path.dirname(openspecEntry),'..','bin','openspec.js')
  : null;
const safe=x=>typeof x==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(x);
// 从 OpenSpec 输出中抹掉本地路径等信息，避免泄露给客户端（成功与失败路径都调用）。
function redactOpenSpecOutput(text){
  try{
    const obj=JSON.parse(String(text));
    if(obj&&typeof obj==='object'){
      if(obj.root)delete obj.root;
      if(obj.archive&&typeof obj.archive==='object'&&'path' in obj.archive)delete obj.archive.path;
    }
    return JSON.stringify(obj);
  }catch{return String(text);}
}
const kebab=x=>typeof x==='string'&&/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(x)&&x.length<=100;
const validChange=x=>safe(x)&&x.toLowerCase()!=='archive';
export const validChangeId=validChange;
export const validProjectSlug=kebab;
const maxArtifactBytes=512*1024;

function dir(id){if(!safe(id)) throw badRequest('invalid workspace id');return path.join(config.workspaceRoot,id);}
function gitEnv(){if(!config.giteaToken)return{};return{GIT_CONFIG_COUNT:'1',GIT_CONFIG_KEY_0:'http.extraHeader',GIT_CONFIG_VALUE_0:'Authorization: Basic '+Buffer.from(config.giteaUsername+':'+config.giteaToken).toString('base64')};}
function gitIdentity(actor){const name=typeof actor?.name==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(actor.name)?actor.name:config.gitUser;const email=typeof actor?.email==='string'&&/^[^\s<>@\r\n]+@[^\s<>@\r\n]+$/.test(actor.email)?actor.email:config.gitEmail;return{name,email};}
async function git(directory,args){return run('git',['-C',directory,...args],{env:{...process.env,...gitEnv()},timeout:20000});}
async function assertClean(directory,paths){const status=(await git(directory,['status','--porcelain','--',...paths])).stdout.trim();if(status)throw conflict('workspace has uncommitted changes');}
async function commit(directory,message,actor){const identity=gitIdentity(actor);await git(directory,['-c','user.name='+identity.name,'-c','user.email='+identity.email,'add','-A','--','openspec']);const status=(await git(directory,['status','--porcelain','--','openspec'])).stdout.trim();if(!status)return currentRevision(directory);await git(directory,['-c','user.name='+identity.name,'-c','user.email='+identity.email,'commit','-m',message]);return currentRevision(directory);}
async function runOpenSpec(args,options={}){
  if(windowsOpenSpecScript){
    try{await fs.access(windowsOpenSpecScript);return run(process.execPath,[windowsOpenSpecScript,...args],options);}catch(error){if(error.code!=='ENOENT')throw error;}
  }
  const shell=process.platform==='win32'&&/\.(?:cmd|bat)$/i.test(config.openspecBin);
  return run(config.openspecBin,args,{...options,shell});
}

export async function ensureWorkspace(projectRecord){
  const directory=dir(projectRecord.id);
  await fs.mkdir(config.workspaceRoot,{recursive:true});
  try{await fs.access(path.join(directory,'.git'));}
  catch{
    if(!config.giteaToken) throw unavailable('GITEA_TOKEN is not configured');
    await run('git',['clone',config.giteaUrl+'/'+projectRecord.gitea_owner+'/'+projectRecord.gitea_repository+'.git',directory],{env:{...process.env,...gitEnv()},timeout:60000}).catch(error=>{throw unavailable('Gitea clone failed: '+error.message);});
  }
  return directory;
}
export async function currentRevision(directory){return(await git(directory,['rev-parse','HEAD'])).stdout.trim();}
const maxTreeEntries=2048;
async function collectFiles(current,prefix=[],depth=0,files=[]){if(depth>32)throw badRequest('workspace tree is too deep');const entries=(await fs.readdir(current,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name));for(const entry of entries){const next=path.join(current,entry.name);if(entry.isDirectory())await collectFiles(next,[...prefix,entry.name],depth+1,files);else if(entry.isFile())files.push([...prefix,entry.name].join('/'));if(files.length>maxTreeEntries)throw badRequest('too many files in change');}return files;}
async function collectSpecIds(current,prefix=[],depth=0,ids=[]){if(depth>32)throw badRequest('workspace tree is too deep');const entries=(await fs.readdir(current,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name));for(const entry of entries){const next=path.join(current,entry.name);if(entry.isDirectory()&&safe(entry.name))await collectSpecIds(next,[...prefix,entry.name],depth+1,ids);else if(entry.isFile()&&entry.name==='spec.md'&&prefix.length>0)ids.push(prefix.join('/'));if(ids.length>maxTreeEntries)throw badRequest('too many specs in project');}return ids;}
async function containedDirectory(container,target){const containerReal=await fs.realpath(container);const targetStat=await fs.lstat(target);if(!targetStat.isDirectory()||targetStat.isSymbolicLink())throw notFound();const targetReal=await fs.realpath(target);if(targetReal!==containerReal&&!targetReal.startsWith(containerReal+path.sep))throw notFound();return targetReal;}
export async function list(directory,relative){const target=path.join(directory,'openspec',relative);try{const safeTarget=await containedDirectory(directory,target);if(relative==='specs')return collectSpecIds(safeTarget);const entries=(await fs.readdir(safeTarget,{withFileTypes:true})).filter(entry=>entry.isDirectory()&&safe(entry.name)&&(relative!=='changes'||entry.name.toLowerCase()!=='archive'));return entries.map(entry=>entry.name).sort();}catch(error){if(error.code==='ENOENT')throw notFound();throw error;}}
function safePathId(id){if(typeof id!=='string'||id.length===0)return false;const segments=id.split('/');return segments.length>0&&segments.every(s=>safe(s));}
async function readContainedFile(root,target,container){try{const containerReal=await fs.realpath(container);const rootStat=await fs.lstat(root);if(!rootStat.isDirectory()||rootStat.isSymbolicLink())throw notFound();const rootReal=await fs.realpath(root);if(rootReal!==containerReal&&!rootReal.startsWith(containerReal+path.sep))throw notFound();const targetStat=await fs.lstat(target);if(!targetStat.isFile()||targetStat.isSymbolicLink())throw notFound();const targetReal=await fs.realpath(target);if(targetReal!==rootReal&&!targetReal.startsWith(rootReal+path.sep))throw notFound();return await fs.readFile(targetReal,'utf8');}catch(error){if(error.code==='ENOENT'||error.code==='EISDIR')throw notFound();throw error;}}
export async function readSpec(directory,id){if(!safePathId(id))throw badRequest('invalid spec id');const specsRoot=path.join(directory,'openspec','specs');return readContainedFile(specsRoot,path.join(specsRoot,...id.split('/'),'spec.md'),directory);}
function taskStatus(content){const tasks=content.split(/\r?\n/).filter(line=>/^\s*[-*+]\s*\[[ xX]\](?:\s|$)/.test(line));const completed=tasks.filter(line=>/^\s*[-*+]\s*\[[xX]\](?:\s|$)/.test(line)).length;return{total:tasks.length,completed,remaining:tasks.length-completed};}
async function readChangeArtifacts(target,files){const artifacts={};const omitted=[];let total=0;for(const relative of files){if(!/\.(?:md|ya?ml|json)$/i.test(relative)){omitted.push(relative);continue;}const full=path.join(target,...relative.split('/'));const size=(await fs.stat(full)).size;if(size>maxArtifactBytes||total+size>4*1024*1024){omitted.push(relative);continue;}artifacts[relative]=await fs.readFile(full,'utf8');total+=size;}return{artifacts,omitted};}
export async function readChange(directory,id){if(!validChange(id))throw badRequest('invalid change id');const target=path.join(directory,'openspec','changes',id);try{const safeTarget=await containedDirectory(path.join(directory,'openspec','changes'),target);const files=await collectFiles(safeTarget);const {artifacts,omitted}=await readChangeArtifacts(safeTarget,files);const status=artifacts['tasks.md']?taskStatus(artifacts['tasks.md']):{total:0,completed:0,remaining:0};return{id,files,artifacts,omitted,taskStatus:status,revision:await currentRevision(directory)};}catch(error){if(error.code==='ENOENT')throw notFound();throw error;}}

export async function withProjectLock(id,fn){
  const previous=locks.get(id)||Promise.resolve();
  let release; const current=new Promise(resolve=>{release=resolve;}); locks.set(id,current);
  await previous;
  try{return await fn();}finally{release();if(locks.get(id)===current)locks.delete(id);}
}

function artifactPath(changeRoot,relative){
  if(typeof relative!=='string'||relative.length===0||relative.includes('\\')||path.posix.isAbsolute(relative)) throw badRequest('invalid artifact path');
  const segments=relative.split('/');
  if(segments.some(segment=>!segment||segment==='.'||segment==='..'||!/^[A-Za-z0-9._-]+$/.test(segment))) throw badRequest('invalid artifact path');
  const allowed=relative==='proposal.md'||relative==='design.md'||relative==='tasks.md'||(segments[0]==='specs'&&segments.length>=3&&segments.at(-1)==='spec.md');
  if(!allowed) throw badRequest('artifact path is outside the change');
  const root=path.resolve(changeRoot);
  const target=path.resolve(root,...segments);
  if(target!==root&& !target.startsWith(root+path.sep)) throw badRequest('artifact path is outside the change');
  return target;
}

function normalizeArtifacts(body){
  const files=body?.files??body?.artifacts??{};
  if(files===null||typeof files!=='object'||Array.isArray(files)) throw badRequest('files must be an object');
  const entries=Object.entries(files);
  if(entries.length>32) throw badRequest('too many artifact files');
  let total=0;
  for(const [relative,content] of entries){
    if(typeof content!=='string') throw badRequest('artifact content must be a string');
    const size=Buffer.byteLength(content,'utf8'); total+=size;
    if(size>maxArtifactBytes||total>4*1024*1024) throw badRequest('artifact content is too large');
    artifactPath('change',relative);
  }
  return entries;
}

export async function validateChange(projectRecord,changeId){
  const directory=await ensureWorkspace(projectRecord);
  if(!validChange(changeId)) throw badRequest('invalid change id');
  try{
    const result=await runOpenSpec(['validate',changeId,'--json'],{cwd:directory,env:{...process.env,OPENSPEC_TELEMETRY:'0',...gitEnv()},timeout:60000});
    const parsed=JSON.parse(result.stdout);
    if(parsed&&typeof parsed==='object'&&parsed.root)delete parsed.root; // 不向客户端泄露本地 workspace 路径（与 archive 一致）
    return parsed;
  }catch(error){throw Object.assign(new Error(redactOpenSpecOutput(error.stdout||error.stderr||error.message)),{status:422,code:'validation_failed'});}
}

export async function applySpecs(projectRecord,changeId,actor,expected){
  return withProjectLock(projectRecord.id,async()=>{
    const directory=await ensureWorkspace(projectRecord);
    const before=await currentRevision(directory);
    if(expected&&expected!==before) throw Object.assign(new Error('revision mismatch'),{status:409,code:'revision_conflict'});
    if(!validChange(changeId)) throw badRequest('invalid change id');
    await assertClean(directory,['openspec']);
    const changeDir=path.join(directory,'openspec','changes',changeId);
    const mainSpecsDir=path.join(directory,'openspec','specs');
    await validateChange(projectRecord,changeId);
    const updates=await specsApply.findSpecUpdates(changeDir,mainSpecsDir);
    if(updates.length===0) throw badRequest('change contains no delta specs');
    const built=[];
    for(const update of updates) built.push({update,result:await specsApply.buildUpdatedSpec(update,changeId,{silent:true})});
    const snapshots=[];
    for(const item of built){
      if(item.result.rebuilt===undefined) throw badRequest('OpenSpec did not produce an updated spec');
      try{snapshots.push({target:item.update.target,content:await fs.readFile(item.update.target,'utf8')});}
      catch(error){if(error.code==='ENOENT')snapshots.push({target:item.update.target});else throw error;}
    }
    try{
      for(const item of built) await specsApply.writeUpdatedSpec(item.update,item.result.rebuilt,item.result.counts,{silent:true});
      const after=await commit(directory,'chore: apply specs from '+changeId,actor);
      return{before,after,updates:built.map(item=>({id:item.update.id,counts:item.result.counts,warnings:item.result.warnings}))};
    }catch(error){
      await git(directory,['reset','--','openspec']).catch(()=>undefined);
      for(const snapshot of snapshots.slice().reverse()){
        if(snapshot.content===undefined)await fs.rm(snapshot.target,{force:true}).catch(()=>undefined);
        else await fs.writeFile(snapshot.target,snapshot.content).catch(()=>undefined);
      }
      throw error;
    }
  });
}

export async function archiveChange(projectRecord,changeId,actor,expected){
  return withProjectLock(projectRecord.id,async()=>{
    const directory=await ensureWorkspace(projectRecord);
    const before=await currentRevision(directory);
    if(expected&&expected!==before) throw Object.assign(new Error('revision mismatch'),{status:409,code:'revision_conflict'});
    if(!validChange(changeId)) throw badRequest('invalid change id');
    await assertClean(directory,['openspec']);
    try{
      const result=await runOpenSpec(['archive',changeId,'--yes','--json'],{cwd:directory,env:{...process.env,OPENSPEC_TELEMETRY:'0',...gitEnv()},timeout:120000});
      const after=await commit(directory,'chore: archive change '+changeId,actor);
      let report;
      try{report=JSON.parse(result.stdout);}catch{report={archive:result.stdout.trim()};}
      if(report&&typeof report==='object'){
        if(report.root)delete report.root;
        if(report.archive&&typeof report.archive==='object'&&'path' in report.archive)delete report.archive.path;
      }
      return{before,after,report};
    }catch(error){
      if(error.code==='ERR_CHILD_PROCESS_STDIO_MAXBUFFER') throw unavailable('OpenSpec archive output exceeded the limit');
      const detail=redactOpenSpecOutput(error.stdout||error.stderr||error.message);
      throw Object.assign(new Error(detail),{status:422,code:'archive_failed'});
    }
  });
}

export async function createChange(projectRecord,id,actor,expected,body={}){
  return withProjectLock(projectRecord.id,async()=>{
    const directory=await ensureWorkspace(projectRecord);
    const before=await currentRevision(directory);
    if(expected&&expected!==before) throw Object.assign(new Error('revision mismatch'),{status:409,code:'revision_conflict'});
    if(!validChange(id)) throw badRequest('invalid change id');
    const target=path.join(directory,'openspec','changes',id);
    const relativeTarget=path.relative(directory,target);
    const artifacts=normalizeArtifacts(body);
    let committed=false;
    let createdTarget=false;
    try{
      await fs.mkdir(target,{recursive:false});
      createdTarget=true;
      await fs.writeFile(path.join(target,'.openspec.yaml'),'schema: spec-driven\n',{flag:'wx'});
      for(const [relative,content] of artifacts){const file=artifactPath(target,relative);await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,content,{flag:'wx'});}
      await git(directory,['add',relativeTarget]);
      const identity=gitIdentity(actor);
      await git(directory,['-c','user.name='+identity.name,'-c','user.email='+identity.email,'commit','-m','chore: create change '+id]);
      committed=true;
      return{before,after:await currentRevision(directory)};
    }catch(error){
      if(createdTarget&&!committed){await git(directory,['reset','--',relativeTarget]).catch(()=>undefined);await fs.rm(target,{recursive:true,force:true}).catch(()=>undefined);}
      if(error.code==='EEXIST') throw conflict('change already exists');
      throw error;
    }
  });
}

export async function updateChange(projectRecord,id,actor,expected,body={}){
  return withProjectLock(projectRecord.id,async()=>{
    const directory=await ensureWorkspace(projectRecord);
    const before=await currentRevision(directory);
    if(expected&&expected!==before) throw Object.assign(new Error('revision mismatch'),{status:409,code:'revision_conflict'});
    if(!validChange(id)) throw badRequest('invalid change id');
    const target=path.join(directory,'openspec','changes',id);
    const relativeTarget=path.relative(directory,target);
    const artifacts=normalizeArtifacts(body);
    if(artifacts.length===0) throw badRequest('at least one artifact is required');
    const changesRoot=path.join(directory,'openspec','changes');
    await containedDirectory(directory,changesRoot);
    await containedDirectory(changesRoot,target);
    await assertClean(directory,['openspec']);
    const snapshots=[];
    for(const [relative] of artifacts){
      const file=artifactPath(target,relative);
      try{await fs.mkdir(path.dirname(file),{recursive:true});const rootReal=await fs.realpath(target);const parentReal=await fs.realpath(path.dirname(file));if(parentReal!==rootReal&&!parentReal.startsWith(rootReal+path.sep))throw badRequest('artifact path is outside the change');}
      catch(error){if(error.code==='ENOENT')throw badRequest('invalid artifact path');throw error;}
      try{const fileStat=await fs.lstat(file);if(!fileStat.isFile()||fileStat.isSymbolicLink())throw badRequest('artifact path is not a regular file');snapshots.push({file,content:await fs.readFile(file,'utf8')});}
      catch(error){if(error.code==='ENOENT')snapshots.push({file});else throw error;}
    }
    try{
      for(const [relative,content] of artifacts)await fs.writeFile(artifactPath(target,relative),content);
      await git(directory,['add',relativeTarget]);
      const identity=gitIdentity(actor);
      await git(directory,['-c','user.name='+identity.name,'-c','user.email='+identity.email,'commit','-m','chore: update change '+id]);
      return{before,after:await currentRevision(directory)};
    }catch(error){
      await git(directory,['reset','--',relativeTarget]).catch(()=>undefined);
      for(const snapshot of snapshots.slice().reverse()){
        if(snapshot.content===undefined)await fs.rm(snapshot.file,{force:true}).catch(()=>undefined);
        else await fs.writeFile(snapshot.file,snapshot.content).catch(()=>undefined);
      }
      throw error;
    }
  });
}
