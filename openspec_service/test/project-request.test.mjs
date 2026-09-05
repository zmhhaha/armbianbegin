import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';

process.env.GITEA_WEBHOOK_SECRET='test-webhook-secret';
process.env.GITEA_SCRIPT_PROFILES='openspec-bootstrap-v1,openspec-validate-v1';
const {verifyWebhookSignature,parseProjectRequest,isApprovalEvent,repositoryMatches}=await import('../src/project-request.mjs?request-test');

test('verifies Gitea webhook HMAC signatures',()=>{
  const body='{"action":"label_updated"}';
  const signature=crypto.createHmac('sha256',process.env.GITEA_WEBHOOK_SECRET).update(body).digest('hex');
  assert.equal(verifyWebhookSignature(body,signature),true);
  assert.equal(verifyWebhookSignature(body,'0'.repeat(64)),false);
});

test('parses and validates a project request block',()=>{
  const request=parseProjectRequest(`<!-- openspec-project-request:v1
{"displayName":"My app","slug":"my-app","sourceUrl":"https://github.com/example/my-app.git","ref":"main","scriptProfileId":"openspec-bootstrap-v1","initialPermission":"admin"}
-->`);
  assert.deepEqual(request,{version:1,displayName:'My app',slug:'my-app',sourceUrl:'https://github.com/example/my-app',ref:'main',scriptProfileId:'openspec-bootstrap-v1',initialPermission:'admin'});
});

test('rejects unsafe project request values',()=>{
  assert.throws(()=>parseProjectRequest('<!-- openspec-project-request:v1 {"slug":"my-app","sourceUrl":"http://github.com/example/my-app"} -->'));
  assert.throws(()=>parseProjectRequest('<!-- openspec-project-request:v1 {"slug":"my_app","sourceUrl":"https://github.com/example/my-app"} -->'));
  assert.throws(()=>parseProjectRequest('<!-- openspec-project-request:v1 {"slug":"my-app","sourceUrl":"https://github.com/example/my-app","scriptProfileId":"arbitrary-shell"} -->'));
});

test('recognizes only approved labels in the configured request repository',()=>{
  const payload={action:'label_updated',repository:{name:'project-requests',owner:{login:'openspec-service'}},issue:{number:3,labels:[{name:'status:approved'}]}};
  assert.equal(repositoryMatches(payload),true);
  assert.equal(isApprovalEvent('issues',payload),true);
  assert.equal(isApprovalEvent('issue_comment',payload),false);
});
