/* global __dirname */
// Isolated frontend request tests; no browser, network or real credentials.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('../node_modules/typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/api.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
function client(fetch) {
  const context = { exports: {}, process: { env: { EXPO_PUBLIC_BACKEND_URL: '' } }, window: { location: { origin: 'http://demo.local' } }, fetch, AbortController, setTimeout, clearTimeout };
  vm.runInNewContext(compiled, context);
  return context.exports;
}
const response = (status, body) => ({ ok: status >= 200 && status < 300, status, text: async () => typeof body === 'string' ? body : JSON.stringify(body), blob: async () => ({}) });
const tests = [
 ['stale successful response is not delivered to a different login',async()=>{let c;c=client(async()=>{c.setToken('new-user');return response(200,{private:'old-user'});});c.setToken('old-user');await assert.rejects(c.api.get('/owner/dashboard'),/session changed/);}],
 ['stale unauthorized response does not sign out the new login',async()=>{let c,called=false;c=client(async()=>{c.setToken('new-user');return response(401,{detail:'Old token expired'});});c.setToken('old-user');c.setUnauthorizedHandler(()=>{called=true;});await assert.rejects(c.api.get('/cleaning'),/session changed/);assert.equal(called,false);}],
 ['private document blob is discarded after account switch',async()=>{let c;c=client(async()=>{c.setToken('new-user');return response(200,{});});c.setToken('old-user');await assert.rejects(c.authenticatedBlob('/guest-ids/synthetic/image'),/session changed/);}],
 ['account switch during file preparation never uploads with the new login',async()=>{let posts=0;const c=client(async()=>{posts++;return response(200,{id:'m'});});c.setToken('old-synthetic-user');const epoch=c.getAuthEpoch();c.setToken('different-synthetic-user');await assert.rejects(c.request('/upload',{method:'POST',body:{},expectedAuthEpoch:epoch}),/session changed/);assert.equal(posts,0);}],
 ['same-origin API fallback', async () => { let url; const c = client(async u => { url=u; return response(200, []); }); await c.api.get('/cleaning'); assert.equal(url, 'http://demo.local/api/cleaning'); }],
 ['validation error names the field', async () => { const c=client(async()=>response(422,{detail:[{loc:['body','guest_name'],msg:'Required'}]})); await assert.rejects(c.api.post('/guest/documents'),/guest_name Required/); }],
 ['expired session triggers sign-out', async () => { let called=false; const c=client(async()=>response(401,{detail:'Expired'})); c.setToken('dummy'); c.setUnauthorizedHandler(()=>{called=true;}); await assert.rejects(c.api.get('/cleaning')); assert.equal(called,true); }],
 ['wrong password does not trigger global sign-out', async()=>{let called=false; const c=client(async()=>response(401,{detail:'Wrong password'})); c.setToken('dummy'); c.setUnauthorizedHandler(()=>{called=true;}); await assert.rejects(c.api.post('/auth/login')); assert.equal(called,false);}],
 ['offline error gives a recovery instruction', async()=>{const c=client(async()=>{throw new TypeError('Failed to fetch');}); await assert.rejects(c.api.get('/cleaning'), /connection|offline|internet|try again/i);}],
 ['HTML server outage is not shown as markup', async()=>{const c=client(async()=>response(502,'<html><body>Internal upstream failure</body></html>')); await assert.rejects(c.api.get('/cleaning'),e=>!e.message.includes('<html>') && /try again|unavailable|server/i.test(e.message));}],
 ['invalid success JSON is reported as an error', async()=>{const c=client(async()=>response(200,'<html>Maintenance</html>')); await assert.rejects(c.api.get('/owner/dashboard'));}],
 ['requests have a timeout signal', async()=>{let options;const c=client(async(u,o)=>{options=o;return response(200,[]);});await c.api.get('/cleaning');assert.ok(options.signal,'No timeout/cancellation signal supplied');}],
 ['private image authorization failure triggers sign-out',async()=>{let called=false;const c=client(async()=>response(401,{}));c.setUnauthorizedHandler(()=>{called=true;});await assert.rejects(c.authenticatedBlob('/guest-ids/dummy/image'));assert.equal(called,true);}]
];
(async()=>{
 const results=[];
 for(const [name,test] of tests){try{await test();results.push({name,status:'passed'});}catch(e){results.push({name,status:'failed',message:e.message});}}
 fs.mkdirSync(require("node:path").join(__dirname,"../../test_reports/edge-audit"),{recursive:true});
 fs.writeFileSync(require('node:path').join(__dirname,'../../test_reports/edge-audit/frontend-api.json'),JSON.stringify(results,null,2));
 for(const r of results) console.log(`${r.status.toUpperCase()}: ${r.name}`);
 console.log(`${results.filter(r=>r.status==='passed').length} passed; ${results.filter(r=>r.status==='failed').length} failed`);
 process.exitCode=results.some(r=>r.status==='failed')?1:0;
})();
