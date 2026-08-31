import http from 'node:http'; import {config} from './config.mjs'; import {migrate} from './db.mjs'; import {handler} from './rest.mjs'; import {mcpHandler} from './mcp.mjs';
const server=http.createServer(async(req,res)=>{try{if(req.url?.split('?')[0]==='/mcp'&&(req.method==='POST'||req.method==='GET'))return await mcpHandler(req,res);return await handler(req,res);}catch(e){if(!res.headersSent){res.writeHead(e.status||500,{'content-type':'application/json'});res.end(JSON.stringify({error:e.code||'internal_error',message:e.message}));}else res.destroy();}});
async function start(){try{await migrate();}catch(error){console.error(`migration failed: ${error.message}`);}server.listen(config.port,'0.0.0.0',()=>console.log(`openspec-service listening on ${config.port}`));}
start();
