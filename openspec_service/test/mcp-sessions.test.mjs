import assert from 'node:assert/strict';
import test, {mock} from 'node:test';
import {exportJWK, generateKeyPair, SignJWT} from 'jose';

const hour=60*60*1000;
const minute=60*1000;
function deferred(){
  let resolve;
  const promise=new Promise(done=>{resolve=done;});
  return{promise,resolve};
}

test('MCP session lifecycle',async t=>{
  process.env.OIDC_ISSUER='https://session-auth.example.test';
  process.env.OIDC_AUDIENCE='session-test';
  process.env.OIDC_JWKS_URL='https://session-auth.example.test/jwks';
  process.env.DATABASE_URL='postgres://unused';

  mock.timers.enable({apis:['Date','setInterval'],now:Date.UTC(2026,0,1)});
  t.after(()=>{mock.restoreAll();mock.timers.reset();});

  // Track the real mocked interval and its unref call without inspecting source.
  const intervals=[];
  const setInterval=globalThis.setInterval;
  mock.method(globalThis,'setInterval',(...args)=>{
    const timer=setInterval(...args);
    const unref=mock.method(timer,'unref');
    intervals.push({delay:args[1],timer,unref});
    return timer;
  });

  const {privateKey,publicKey}=await generateKeyPair('ES256');
  const key={...await exportJWK(publicKey),kid:'session-test',alg:'ES256'};
  mock.method(globalThis,'fetch',async url=>{
    assert.equal(String(url),process.env.OIDC_JWKS_URL,'only the test JWKS may be fetched');
    return new Response(JSON.stringify({keys:[key]}),{status:200});
  });

  const db=await import('../src/db.mjs');
  let identityLookupGate;
  mock.method(db.pool,'query',async(sql,values)=>{
    assert.equal(sql,'select gitea_username from openspec_identity_map where subject=$1');
    assert.ok(['alice','bob'].includes(values[0]));
    if(identityLookupGate){
      const gate=identityLookupGate;
      identityLookupGate=undefined;
      gate.entered.resolve();
      await gate.released.promise;
    }
    return{rows:[{gitea_username:values[0]}]};
  });
  t.after(()=>db.pool.end());

  const tokens={};
  for(const sub of ['alice','bob']){
    tokens[sub]=await new SignJWT({sub})
      .setProtectedHeader({alg:'ES256',kid:'session-test'})
      .setIssuer(process.env.OIDC_ISSUER)
      .setAudience(process.env.OIDC_AUDIENCE)
      .setExpirationTime('30d')
      .sign(privateKey);
  }

  const {mcpHandler,activeSessionCount}=await import('../src/mcp.mjs');
  let requestId=0;
  async function request(method,{sessionId,user='alice',body}={}){
    const headers={};
    if(user)headers.authorization=`Bearer ${tokens[user]}`;
    if(sessionId!==undefined)headers['mcp-session-id']=sessionId;
    const req={method,url:'/mcp',headers,async *[Symbol.asyncIterator](){
      if(body!==undefined)yield JSON.stringify(body);
    }};
    const res={statusCode:200,headers:{},body:''};
    res.setHeader=(name,value)=>{res.headers[name.toLowerCase()]=value;return res;};
    res.writeHead=(status,values={})=>{
      res.statusCode=status;
      for(const [name,value] of Object.entries(values))res.setHeader(name,value);
      return res;
    };
    res.write=body=>{res.body+=body;return true;};
    res.end=(body='')=>{res.body+=body;return res;};
    await mcpHandler(req,res);
    return res;
  }
  const rpc=(method,sessionId,user='alice')=>request('POST',{
    sessionId,user,body:{jsonrpc:'2.0',id:++requestId,method}
  });
  async function initialize(){
    const res=await rpc('initialize');
    assert.equal(res.statusCode,200);
    assert.ok(JSON.parse(res.body).result,res.body);
    assert.ok(res.headers['mcp-session-id']);
    return res.headers['mcp-session-id'];
  }
  function invalidSession(res){
    assert.equal(res.statusCode,404,res.body);
    assert.equal(JSON.parse(res.body).error.code,-32002);
  }
  t.beforeEach(()=>{
    // Isolate cases through the public cleanup function; no session-map hooks.
    mock.timers.setTime(Date.now()+hour+minute);
    assert.equal(activeSessionCount(),0);
  });

  await t.test('rejects a 1025th active session and reclaims expired entries before creating',async()=>{
    for(let i=0;i<1024;i++)await initialize();
    assert.equal(activeSessionCount(),1024);
    const full=await rpc('initialize');
    assert.match(JSON.parse(full.body).error.message,/MCP session limit reached/);
    assert.equal(activeSessionCount(),1024);

    // setTime does not run intervals: admission must perform its own cleanup.
    mock.timers.setTime(Date.now()+hour);
    await initialize();
    assert.equal(activeSessionCount(),1);
  });

  await t.test('DELETE releases a full-table slot and a closed ID cannot be reused',async()=>{
    const first=await initialize();
    for(let i=1;i<1024;i++)await initialize();
    const closed=await request('DELETE',{sessionId:first});
    assert.equal(closed.statusCode,204);
    assert.equal(closed.body,'');
    assert.equal(activeSessionCount(),1023);
    await initialize();
    assert.equal(activeSessionCount(),1024);

    for(const method of ['tools/list','ping','initialize'])invalidSession(await rpc(method,first));
    invalidSession(await request('GET',{sessionId:first}));
    invalidSession(await request('DELETE',{sessionId:first}));
    assert.equal(activeSessionCount(),1024);
  });

  await t.test('an in-flight GET or initialize cannot revive a concurrently deleted ID',async()=>{
    for(const method of ['GET','initialize']){
      const session=await initialize();
      const gate={entered:deferred(),released:deferred()};
      identityLookupGate=gate;
      const pending=method==='GET'
        ?request('GET',{sessionId:session})
        :rpc('initialize',session);
      await gate.entered.promise;
      try{
        const closed=await request('DELETE',{sessionId:session});
        assert.equal(closed.statusCode,204);
        assert.equal(activeSessionCount(),0);
      }finally{
        gate.released.resolve();
      }
      await pending;
      invalidSession(await rpc('tools/list',session));
      assert.equal(activeSessionCount(),0,`${method} must not reinsert the deleted session`);
    }
  });

  await t.test('DELETE requires an authenticated owner and an existing unexpired session',async()=>{
    const missing=await request('DELETE');
    assert.equal(missing.statusCode,400);
    invalidSession(await request('DELETE',{sessionId:'unknown'}));
    const session=await initialize();
    assert.equal((await request('DELETE',{sessionId:session,user:null})).statusCode,401);
    invalidSession(await request('DELETE',{sessionId:session,user:'bob'}));
    assert.equal(activeSessionCount(),1);
    assert.ok(JSON.parse((await rpc('tools/list',session)).body).result);

    mock.timers.setTime(Date.now()+hour);
    invalidSession(await request('DELETE',{sessionId:session}));
    assert.equal(activeSessionCount(),0);
  });

  await t.test('requests from another identity neither delete nor renew the owner session',async()=>{
    const session=await initialize();
    const createdAt=Date.now();
    mock.timers.setTime(createdAt+hour-1);
    for(const method of ['tools/list','ping','initialize']){
      invalidSession(await rpc(method,session,'bob'));
    }
    invalidSession(await request('GET',{sessionId:session,user:'bob'}));
    invalidSession(await request('DELETE',{sessionId:session,user:'bob'}));
    assert.equal(activeSessionCount(),1,'the owner session must survive rejected requests');

    mock.timers.setTime(createdAt+hour);
    invalidSession(await rpc('tools/list',session));
    assert.equal(activeSessionCount(),0,'rejected requests must not extend its expiry');
  });

  await t.test('ping validates the session and renews it for another idle hour',async()=>{
    const session=await initialize();
    const createdAt=Date.now();
    mock.timers.setTime(createdAt+hour-1);
    const ping=await rpc('ping',session);
    assert.equal(ping.statusCode,200);
    assert.deepEqual(JSON.parse(ping.body).result,{});
    mock.timers.setTime(createdAt+hour+1);
    const list=await rpc('tools/list',session);
    assert.equal(list.statusCode,200);
    assert.ok(JSON.parse(list.body).result.tools.length);
    invalidSession(await rpc('ping','unknown'));

    mock.timers.setTime(Date.now()+hour);
    invalidSession(await rpc('ping',session));
  });

  await t.test('unknown IDs cannot create sessions through GET or initialize',async()=>{
    invalidSession(await rpc('initialize','unknown'));
    invalidSession(await request('GET',{sessionId:'unknown'}));
    assert.equal(activeSessionCount(),0);
  });

  await t.test('the 60-second unreferenced timer removes idle sessions without traffic',async()=>{
    const cleanup=intervals.filter(interval=>interval.delay===minute);
    assert.equal(cleanup.length,1);
    assert.equal(cleanup[0].unref.mock.callCount(),1);
    await initialize();
    const createdAt=Date.now();
    mock.timers.tick(hour+minute);

    // Rewind Date before inspecting: activeSessionCount cannot itself prune an
    // entry created at this instant, so zero proves the timer already did so.
    mock.timers.setTime(createdAt);
    assert.equal(activeSessionCount(),0);
  });

  await t.test('tools/list remains compatible with requests that omit a session ID',async()=>{
    const list=await rpc('tools/list');
    assert.equal(list.statusCode,200);
    assert.ok(JSON.parse(list.body).result.tools.length);
    assert.equal(activeSessionCount(),0);
  });
});
