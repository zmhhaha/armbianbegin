import assert from 'node:assert/strict';
import test from 'node:test';

process.env.GITEA_SCRIPT_PROFILES='openspec-bootstrap-v1,openspec-validate-v1';
const {buildProjectRequest,projectRequestEntryHtml,projectRequestFormHtml}=await import('../src/project-form.mjs?form-test');

test('builds a canonical Gitea issue body from form data',()=>{
  const result=buildProjectRequest({displayName:'My app',slug:'my-app',sourceUrl:'https://github.com/example/my-app',ref:'main',scriptProfileId:'openspec-bootstrap-v1',description:'Initial project'},{requesterUsername:'xmx'});
  assert.equal(result.title,'[project-request] My app');
  assert.match(result.body,/openspec-project-request:v1/);
  assert.match(result.body,/"slug": "my-app"/);
  assert.equal(result.request.initialPermission,'admin');
  assert.equal(result.request.requesterUsername,'xmx');
});

test('rejects unsupported form fields and unsafe values',()=>{
  assert.throws(()=>buildProjectRequest({displayName:'x',slug:'x',sourceUrl:'https://github.com/a/b',command:'rm -rf /'}));
  assert.throws(()=>buildProjectRequest({displayName:'x',slug:'x',sourceUrl:'https://github.com/a/b',scriptProfileId:'unknown'}));
});

test('renders login and authenticated form pages',()=>{
  const entry=projectRequestEntryHtml();
  assert.match(entry,/\/project-requests\/login/);
  // 退役守卫：给人取长期 JWT 的旧入口 /token 不应再出现在任何页面里。
  assert.doesNotMatch(entry,/\/token/);
  const page=projectRequestFormHtml('jwt-value');
  assert.match(page,/\/v1\/project-requests/);
  assert.match(page,/jwt-value/);
});
