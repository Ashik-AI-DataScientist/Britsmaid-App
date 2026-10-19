const assert=require('node:assert/strict');
const buildConfig=require('../app.config.js');
const base=require('../app.json').expo;
const original={...process.env};
let passed=0;
function test(name, fn){ try { delete process.env.EAS_BUILD;delete process.env.EXPO_PUBLIC_BACKEND_URL;delete process.env.BRITSMAID_PREVIEW_LAN;fn();passed++;console.log('PASS '+name); } finally { for(const k of ['EAS_BUILD','EXPO_PUBLIC_BACKEND_URL','BRITSMAID_PREVIEW_LAN']) { if(original[k]===undefined)delete process.env[k];else process.env[k]=original[k]; } } }
function config(){return buildConfig({config:JSON.parse(JSON.stringify(base))});}
test('native cloud build refuses an empty backend',()=>{process.env.EAS_BUILD='true';assert.throws(config,/reachable staging backend/);});
test('phone build refuses localhost',()=>{process.env.EXPO_PUBLIC_BACKEND_URL='http://127.0.0.1:8766';process.env.BRITSMAID_PREVIEW_LAN='1';assert.throws(config,/localhost/);});
test('public HTTP cannot be enabled through LAN flag',()=>{process.env.EXPO_PUBLIC_BACKEND_URL='http://example.com';process.env.BRITSMAID_PREVIEW_LAN='1';assert.throws(config,/HTTPS/);});
test('private LAN preview preserves package and scopes network exception to one host',()=>{process.env.EXPO_PUBLIC_BACKEND_URL='http://192.168.29.55:8766';process.env.BRITSMAID_PREVIEW_LAN='1';const c=config();assert.equal(c.android.package,'com.emergent.britsmaidrevshare.ixdi3x');const p=c.plugins.find(p=>Array.isArray(p)&&p[0]==='./scripts/with-preview-network.cjs');assert.equal(p[1].host,'192.168.29.55');});
console.log(`${passed} passed; 0 failed`);
