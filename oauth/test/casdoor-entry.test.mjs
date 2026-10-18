// Run with NGINX_BIN pointing to an installed nginx executable (Windows or Linux).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {spawn, spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {test} from 'node:test';

test('Casdoor entry defaults only unscoped registration POSTs', {timeout:30000}, async () => {
  const nginx = process.env.NGINX_BIN;
  assert.ok(nginx, 'Set NGINX_BIN to run the real proxy integration test');
  const upstream = http.createServer(async (req,res) => {
    let body=''; for await (const chunk of req) body+=chunk;
    res.setHeader('content-type','application/json');
    res.end(JSON.stringify({method:req.method,url:req.url,body,host:req.headers.host,proto:req.headers['x-forwarded-proto'],authorization:req.headers.authorization}));
  });
  upstream.listen(0,'127.0.0.1'); await once(upstream,'listening');
  const reserve=http.createServer(); reserve.listen(0,'127.0.0.1'); await once(reserve,'listening');
  const port=reserve.address().port; await new Promise(r=>reserve.close(r));
  const dir=fs.mkdtempSync(path.join(process.env.TEST_TMPDIR||os.tmpdir(),'casdoor-entry-test-'));
  const prefix=dir.replaceAll('\\','/')+'/';
  fs.mkdirSync(path.join(dir,'logs'));
  let config=fs.readFileSync(new URL('../k8s/casdoor-entry-configmap.yaml',import.meta.url),'utf8')
    .split('  nginx.conf: |')[1].trimStart().split(/\r?\n/).map(l=>l.replace(/^    /,'')).join('\n');
  config=config.replace('/dev/stderr','stderr').replace('listen 8080;',`listen 127.0.0.1:${port};`)
    .replaceAll('127.0.0.1:8000',`127.0.0.1:${upstream.address().port}`)
    .replace(/\/tmp\/(nginx.pid|client_body|proxy|fastcgi|uwsgi|scgi)/g,(_,name)=>`"${prefix}${name}"`);
  fs.writeFileSync(path.join(dir,'nginx.conf'),config);
  let proc;
  try {
    const check=spawnSync(nginx,['-p',prefix,'-c','nginx.conf','-t'],{encoding:'utf8',windowsHide:true});
    assert.equal(check.status,0,check.stderr||String(check.error));
    proc=spawn(nginx,['-p',prefix,'-c','nginx.conf','-g','daemon off;'],{windowsHide:true,stdio:'ignore'});
    for(let i=0;i<50;i++){
      try{await fetch(`http://127.0.0.1:${port}/api/health`,{signal:AbortSignal.timeout(500)});break;}
      catch{if(i===49)throw new Error('nginx did not start');await new Promise(r=>setTimeout(r,100));}
    }
    const cases=[
      ['POST','/api/oauth/register','/api/oauth/register?organization=Normal-User'],
      ['POST','/api/oauth/register?trace=a%2Bb','/api/oauth/register?trace=a%2Bb&organization=Normal-User'],
      ['POST','/api/oauth/register?organization=Other','/api/oauth/register?organization=Other'],
      ['POST','/api/oauth/register?organization=','/api/oauth/register?organization='],
      ['GET','/api/oauth/register?trace=1','/api/oauth/register?trace=1'],
      ['DELETE','/api/oauth/register/client-test','/api/oauth/register/client-test'],
      ['POST','/api/login/oauth/access_token','/api/login/oauth/access_token'],
      ['GET','/login/oauth/authorize?client_id=test&code_challenge=abc','/login/oauth/authorize?client_id=test&code_challenge=abc'],
      ['GET','/.well-known/oauth-authorization-server','/.well-known/oauth-authorization-server'],
      ['GET','/.well-known/jwks','/.well-known/jwks'],
    ];
    for(const [method,url,expected] of cases){
      const body=method==='POST'?'{"client_name":"integration-test"}':undefined;
      const r=await new Promise((resolve,reject)=>{
        const req=http.request({hostname:'127.0.0.1',port,path:url,method,headers:{host:'auth.panghuer.top','x-forwarded-proto':'https',authorization:'Bearer test-only'},signal:AbortSignal.timeout(3000)},async res=>{
          try{let text='';for await(const chunk of res)text+=chunk;resolve({status:res.statusCode,data:JSON.parse(text)});}catch(error){reject(error);}
        });
        req.on('error',reject);req.end(body);
      });
      assert.equal(r.status,200,`${method} ${url}`);
      assert.deepEqual(r.data,{method,url:expected,body:body||'',host:'auth.panghuer.top',proto:'https',authorization:'Bearer test-only'});
    }
  } finally {
    if(proc){spawnSync(nginx,['-p',prefix,'-c','nginx.conf','-s','quit'],{windowsHide:true,stdio:'ignore'});}
    upstream.closeAllConnections(); await new Promise(r=>upstream.close(r));
    // Test runtime files are kept in the printed temporary directory for diagnosis.
    console.log(`nginx test runtime: ${dir}`);
  }
});
