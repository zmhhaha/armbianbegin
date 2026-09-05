import assert from 'node:assert/strict';
import test from 'node:test';

process.env.GITEA_SCRIPT_PROFILES='openspec-bootstrap-v1,openspec-validate-v1';
const {buildProjectRequest,projectRequestEntryHtml,projectRequestFormHtml}=await import('../src/project-form.mjs?form-test');

test('builds a canonical Gitea issue body from form data',()=>{
  const result=buildProjectRequest({displayName:'My app',slug:'my-app',sourceUrl:'https://github.com/example/my-app',ref:'main',scriptProfileId:'openspec-bootstrap-v1',description:'Initial project'});
  assert.equal(result.title,'[project-request] My app');
  assert.match(result.body,/openspec-project-request:v1/);
  assert.match(result.body,/"slug": "my-app"/);
  assert.equal(result.request.initialPermission,'admin');
});

test('rejects unsupported form fields and unsafe values',()=>{
  assert.throws(()=>buildProjectRequest({displayName:'x',slug:'x',sourceUrl:'https://github.com/a/b',command:'rm -rf /'}));
  assert.throws(()=>buildProjectRequest({displayName:'x',slug:'x',sourceUrl:'https://github.com/a/b',scriptProfileId:'unknown'}));
});

test('renders login and authenticated form pages',()=>{
  assert.match(projectRequestEntryHtml(),/\/token\?return=\/project-requests/);
  const page=projectRequestFormHtml('jwt-value');
  assert.match(page,/\/v1\/project-requests/);
  assert.match(page,/jwt-value/);
});
