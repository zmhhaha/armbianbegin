import assert from 'node:assert/strict';
import test from 'node:test';

process.env.GITEA_TOKEN='test-token';
const {usernameByEmail}=await import('../src/gitea.mjs?identity-test');

function mockResponse(body,status=200){
  return {status,ok:status>=200&&status<300,json:async()=>body};
}

test('resolves the unique Gitea login by exact email',async()=>{
  const original=globalThis.fetch;
  let requested;
  globalThis.fetch=async(url)=>{requested=String(url);return mockResponse({data:[
    {login:'other',email:'other@example.com'},
    {login:'alice-gitea',email:'Alice@Example.com'}
  ]});};
  try{
    assert.equal(await usernameByEmail(' alice@example.com '),'alice-gitea');
    assert.match(requested,/\/api\/v1\/users\/search\?q=alice%40example\.com&limit=50$/);
  }finally{globalThis.fetch=original;}
});

test('rejects an email without an exact Gitea match',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async()=>mockResponse({data:[{login:'alice-gitea',email:'different@example.com'}]});
  try{await assert.rejects(usernameByEmail('alice@example.com'),error=>error.code==='conflict');}
  finally{globalThis.fetch=original;}
});

test('rejects ambiguous Gitea email matches',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async()=>mockResponse({data:[
    {login:'alice-one',email:'alice@example.com'},
    {login:'alice-two',email:'ALICE@example.com'}
  ]});
  try{await assert.rejects(usernameByEmail('alice@example.com'),error=>error.code==='conflict');}
  finally{globalThis.fetch=original;}
});
