import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

const run=promisify(execFile);
const root=await fs.mkdtemp(path.join(os.tmpdir(),'openspec-service-test-'));
process.env.WORKSPACE_ROOT=root;
if(process.platform==='win32'){
  process.env.OPENSPEC_BIN=path.resolve('node_modules/.bin/openspec.CMD');
  process.env.PATH=path.dirname(process.execPath)+';'+process.env.PATH;
}
const ws=await import('../src/workspace.mjs');

async function git(directory,args){return run('git',['-C',directory,...args]);}
let fixtureNumber=0;
async function fixture(){
  const id='fixture-'+(++fixtureNumber);
  const directory=path.join(root,id);
  await fs.mkdir(path.join(directory,'openspec','specs'),{recursive:true});
  await fs.mkdir(path.join(directory,'openspec','changes','archive'),{recursive:true});
  await fs.writeFile(path.join(directory,'openspec','config.yaml'),'schema: spec-driven\n');
  await git(directory,['init','-q']);
  await git(directory,['-c','user.name=test','-c','user.email=test@example.com','add','.']);
  await git(directory,['-c','user.name=test','-c','user.email=test@example.com','commit','-qm','init']);
  const revision=(await git(directory,['rev-parse','HEAD'])).stdout.trim();
  return{id,directory,project:{id,gitea_owner:'openspec',gitea_repository:'test',default_branch:'main'},revision};
}

test('validates project and change identifiers',()=>{
  assert.equal(ws.validProjectSlug('project-a'),true);
  assert.equal(ws.validProjectSlug('Project-A'),false);
  assert.equal(ws.validProjectSlug('project_a'),false);
  assert.equal(ws.validChangeId('change_1'),true);
  assert.equal(ws.validChangeId('archive'),false);
});

test('creates bounded artifacts and records a Git revision',async()=>{
  const f=await fixture();
  const result=await ws.createChange(f.project,'add-login',{name:'alice',email:'alice@example.com'},f.revision,{files:{'proposal.md':'# Proposal\n','specs/auth/spec.md':'## ADDED Requirements\n'}});
  assert.notEqual(result.after,f.revision);
  assert.equal(await fs.readFile(path.join(f.directory,'openspec','changes','add-login','proposal.md'),'utf8'),'# Proposal\n');
  assert.equal(await fs.readFile(path.join(f.directory,'openspec','changes','add-login','specs','auth','spec.md'),'utf8'),'## ADDED Requirements\n');
  const commit=(await git(f.directory,['log','-1','--format=%an <%ae>'])).stdout.trim();
  assert.equal(commit,'alice <alice@example.com>');
});

test('rejects traversal and duplicate changes without leaving files',async()=>{
  const f=await fixture();
  await assert.rejects(ws.createChange(f.project,'safe-change',{name:'alice'},f.revision,{files:{'../escape.md':'nope'}}),error=>error.code==='bad_request');
  await ws.createChange(f.project,'safe-change',{name:'alice'},f.revision,{files:{'proposal.md':'ok'}});
  const next=(await git(f.directory,['rev-parse','HEAD'])).stdout.trim();
  await assert.rejects(ws.createChange(f.project,'safe-change',{name:'alice'},next,{files:{'proposal.md':'again'}}),error=>error.code==='conflict');
  assert.equal(await fs.stat(path.join(f.directory,'openspec','changes','safe-change','proposal.md')).then(()=>true),true);
  assert.equal(await fs.access(path.join(f.directory,'escape.md')).then(()=>true).catch(()=>false),false);
});

test('lists nested specs and excludes the archive directory',async()=>{
  const f=await fixture();
  await fs.mkdir(path.join(f.directory,'openspec','specs','identity','login'),{recursive:true});
  await fs.writeFile(path.join(f.directory,'openspec','specs','identity','login','spec.md'),'# Login\n');
  await fs.mkdir(path.join(f.directory,'openspec','changes','active-change'),{recursive:true});
  await fs.mkdir(path.join(f.directory,'openspec','changes','Archive'),{recursive:true});
  assert.deepEqual(await ws.list(f.directory,'specs'),['identity/login']);
  assert.deepEqual(await ws.list(f.directory,'changes'),['active-change']);
});

test('does not read a spec through a symlink outside the workspace',async()=>{
  if(process.platform==='win32')return;
  const f=await fixture();
  const outside=path.join(root,'outside-secret');
  await fs.mkdir(outside,{recursive:true});
  await fs.writeFile(path.join(outside,'spec.md'),'not for this project\n');
  await fs.symlink(outside,path.join(f.directory,'openspec','specs','escape'));
  await assert.rejects(ws.readSpec(f.directory,'escape'),error=>error.code==='not_found');
});

test('archives a validated change, updates the main spec, and records the actor',async()=>{
  const f=await fixture();
  await fs.mkdir(path.join(f.directory,'openspec','specs','identity'),{recursive:true});
  await fs.writeFile(path.join(f.directory,'openspec','specs','identity','spec.md'),'# Identity\n\n## Purpose\nUsers authenticate securely.\n\n## Requirements\n\n### Requirement: Existing login\nThe system SHALL accept a login.\n\n#### Scenario: Login works\n- **WHEN** credentials are valid\n- **THEN** access is granted\n');
  await git(f.directory,['-c','user.name=test','-c','user.email=test@example.com','add','.']);
  await git(f.directory,['-c','user.name=test','-c','user.email=test@example.com','commit','-qm','add main spec']);
  const before=(await git(f.directory,['rev-parse','HEAD'])).stdout.trim();
  await ws.createChange(f.project,'add-login',{name:'alice',email:'alice@example.com'},before,{files:{'proposal.md':'# Proposal\n','tasks.md':'- [x] done\n','specs/identity/spec.md':'## MODIFIED Requirements\n\n### Requirement: Existing login\nThe system SHALL accept a Casdoor login.\n\n#### Scenario: Login works\n- **WHEN** credentials are valid\n- **THEN** access is granted\n'}});
  const changeRevision=(await git(f.directory,['rev-parse','HEAD'])).stdout.trim();
  const change=await ws.readChange(f.directory,'add-login');
  assert.deepEqual(change.files.sort(),['.openspec.yaml','proposal.md','specs/identity/spec.md','tasks.md']);
  assert.equal(change.artifacts['proposal.md'],'# Proposal\n');
  assert.deepEqual(change.taskStatus,{total:1,completed:1,remaining:0});
  const updated=await ws.updateChange(f.project,'add-login',{name:'alice',email:'alice@example.com'},changeRevision,{files:{'design.md':'# Design\n'}});
  assert.notEqual(updated.after,changeRevision);
  assert.equal((await ws.readChange(f.directory,'add-login')).artifacts['design.md'],'# Design\n');
  const result=await ws.archiveChange(f.project,'add-login',{name:'alice',email:'alice@example.com'},updated.after);
  assert.notEqual(result.after,changeRevision);
  assert.equal(result.report.archive.change,'add-login');
  assert.equal('path' in result.report.archive,false);
  assert.match(await fs.readFile(path.join(f.directory,'openspec','specs','identity','spec.md'),'utf8'),/Casdoor login/);
  assert.equal(await fs.access(path.join(f.directory,'openspec','changes','add-login')).then(()=>true).catch(()=>false),false);
  const archived=await fs.readdir(path.join(f.directory,'openspec','changes','archive'));
  assert.equal(archived.length,1);
  const commit=(await git(f.directory,['log','-1','--format=%an <%ae>'])).stdout.trim();
  assert.equal(commit,'alice <alice@example.com>');
});
