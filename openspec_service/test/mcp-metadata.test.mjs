import assert from 'node:assert/strict';
import test from 'node:test';

// PRM / 挑战头只需要公开地址与 issuer，设成测试值即可，不依赖真实集群。
process.env.PUBLIC_BASE_URL='https://openspec.example.test';
process.env.OIDC_ISSUER='https://auth.example.test';
process.env.OIDC_JWKS_URL='https://auth.example.test/.well-known/jwks';
process.env.GITEA_TOKEN='test-token';
process.env.DATABASE_URL='postgres://unused';
delete process.env.BOOTSTRAP_ADMIN_SUBJECTS;

const auth=await import('../src/auth.mjs?metadata-test');
const {handler,dispatch}=await import('../src/rest.mjs?metadata-test');
const {mcpHandler}=await import('../src/mcp.mjs?metadata-test');

function fakeReq(method,url,headers={}){return{method,url,headers};}
function fakeRes(){
  const res={statusCode:200,headers:{}};
  res.setHeader=(k,v)=>{res.headers[String(k).toLowerCase()]=v;return res;};
  res.writeHead=(status,headers)=>{res.statusCode=status;for(const [k,v] of Object.entries(headers||{}))res.headers[String(k).toLowerCase()]=v;return res;};
  res.end=(body)=>{res.body=body;return res;};
  return res;
}

test('PRM 文档指向 /mcp，授权服务器是 issuer，且不声明尚未校验的 scope',()=>{
  const prm=auth.protectedResourceMetadata();
  assert.equal(prm.resource,'https://openspec.example.test/mcp');
  assert.deepEqual(prm.authorization_servers,['https://auth.example.test']);
  assert.deepEqual(prm.bearer_methods_supported,['header']);
  assert.ok(!('scopes_supported' in prm),'服务尚未校验 scope，不得声明 scopes_supported');
});

test('挑战头用的是 RFC 9728 §3.1 的路径插入式 PRM 地址',()=>{
  assert.equal(auth.protectedResourceMetadataUrl(),'https://openspec.example.test/.well-known/oauth-protected-resource/mcp');
  assert.equal(auth.bearerChallenge(),'Bearer resource_metadata="https://openspec.example.test/.well-known/oauth-protected-resource/mcp"');
});

test('PRM 两种形状都匿名可读，不需要 Authorization',async()=>{
  for(const path of ['/.well-known/oauth-protected-resource','/.well-known/oauth-protected-resource/mcp']){
    const res=fakeRes();
    await dispatch(fakeReq('GET',path),res);
    assert.equal(res.statusCode,200,`${path} 应当匿名可读`);
    assert.equal(JSON.parse(res.body).resource,'https://openspec.example.test/mcp');
    assert.equal(res.headers['www-authenticate'],undefined,'200 响应不该带挑战头');
  }
});

test('无凭据访问 /mcp 返回 401 且带 WWW-Authenticate 挑战头',async()=>{
  const res=fakeRes();
  await mcpHandler(fakeReq('POST','/mcp',{}),res);
  assert.equal(res.statusCode,401);
  assert.equal(res.headers['www-authenticate'],auth.bearerChallenge());
});

test('REST 侧无凭据与无效 token 都是 401 且带挑战头',async()=>{
  for(const headers of [{},{authorization:'Bearer not-a-jwt'}]){
    const res=fakeRes();
    await handler(fakeReq('GET','/v1/projects',headers),res);
    assert.equal(res.statusCode,401);
    assert.equal(res.headers['www-authenticate'],auth.bearerChallenge());
  }
});

test('非 401 的错误不带挑战头（避免把挑战头加错地方）',async()=>{
  const res=fakeRes();
  await handler(fakeReq('GET','/readyz'),res);
  assert.notEqual(res.statusCode,401);
  assert.equal(res.headers['www-authenticate'],undefined);
});
