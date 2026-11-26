/* global __dirname */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../node_modules/typescript'),React=require('../node_modules/react');
function harness(file, props, hash='', fail=false) {
  let index=0,first=true,values=[],effects=[],calls=[],messages=[],tree;
  const location={hash,pathname:'/guest-check-in'};
  const hooks={...React,useState:v=>{const i=index++;if(!(i in values))values[i]=typeof v==='function'?v():v;return[values[i],v=>{values[i]=typeof v==='function'?v(values[i]):v;}];},useRef:v=>{const i=index++;return values[i]??(values[i]={current:v});},useCallback:f=>f,useEffect:f=>{if(first)effects.push(f);}};
  const mocks={react:hooks,'react-native':{Platform:{OS:'web'},View:'View',ScrollView:'ScrollView',Pressable:'Pressable',Linking:{openURL:async url=>messages.push(url)},Share:{share:async v=>messages.push(v.message)}},'expo-image-picker':{},'@/src/ui':{...Object.fromEntries(['Button','Input','Sheet','Txt','Card','Chip','Header'].map(n=>[n,n])),useToast:()=>m=>messages.push(m)},'@/src/theme':{spacing:{},radius:{},useTheme:()=>({colors:{}})},'@/src/api':{api:{post:async (url,body)=>{calls.push({url,body});if(fail)throw Error('Wrong password');return {ok:true};}},request:async (url,options)=>{calls.push({url,options});return {guests:5,documents:[],check_in:'2026-12-01',check_out:'2026-12-03',retention_days:90};}}};
  const scope={exports:{},require:n=>{assert(n in mocks,n);return mocks[n];},window:{location,history:{replaceState:()=>{throw Error('Invitation fragment must not be removed');}}},URLSearchParams,setInterval:()=>1,clearInterval:()=>{}};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText,scope);
  const component=scope.exports.default||scope.exports.InviteSheet;
  const render=()=>{index=0;tree=component(props);first=false;return tree;};
  const nodes=()=>{let all=[];function walk(v){if(!v||typeof v!=='object')return;if(v.type)all.push(v);React.Children.toArray(v.props?.children).forEach(walk);}walk(tree);return all;};
  return {render,nodes,calls,messages,location,effects,flush:async()=>{for(const f of effects)f();await new Promise(r=>setImmediate(r));},byId:id=>nodes().find(n=>n.props.testID===id),text:()=>JSON.stringify(tree)};
}
(async()=>{
  const member={id:'member-a',name:'Synthetic member',role:'supervisor',email:'member@example.com'};
  const h=harness('src/components/InviteSheet.tsx',{invitee:member,onClose:()=>{}});h.render();
  assert(!h.text().includes('Create password'));assert(!h.byId('invite-message'));
  h.byId('invite-password-input').props.onChangeText('Chosen-password-123');h.render();
  await h.byId('invite-prepare-button').props.onPress();h.render();
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].url,'/users/member-a/verify-invite-password');assert.equal(h.calls[0].body.password,'Chosen-password-123');
  assert(h.text().includes('Password: Chosen-password-123'));assert(!h.calls.some(c=>c.url.includes('reset-password')));
  await h.byId('invite-share-button').props.onPress();assert(h.messages[0].includes('Chosen-password-123'));
  const bad=harness('src/components/InviteSheet.tsx',{invitee:member,onClose:()=>{}},'',true);bad.render();bad.byId('invite-password-input').props.onChangeText('Wrong-password-123');bad.render();await bad.byId('invite-prepare-button').props.onPress();bad.render();assert(!bad.byId('invite-share-button'));assert(bad.messages.includes('Wrong password'));
  const created=harness('src/components/InviteSheet.tsx',{invitee:{...member,password:'Original-password-123'},onClose:()=>{}});created.render();assert(created.text().includes('Original-password-123'));assert.equal(created.calls.length,0);
  const second=harness('src/components/InviteSheet.tsx',{invitee:{...member,id:'member-b'},onClose:()=>{}});second.render();assert(!second.text().includes('Chosen-password-123'));assert(!second.byId('invite-share-button'));
  for(let open=0;open<3;open++){
    const guest=harness('app/guest-check-in.tsx',{},'#invite=synthetic-booking-token');guest.render();await guest.flush();guest.render();
    assert.equal(guest.calls[0].options.authorization,'synthetic-booking-token');assert.equal(guest.location.hash,'#invite=synthetic-booking-token');assert(!guest.text().includes('Invitation code'));assert(guest.text().includes('Stay:'));
    // Effect replay must still have the original fragment available.
    await guest.flush();assert(guest.calls.every(c=>c.options.authorization==='synthetic-booking-token'));
  }
  const missing=harness('app/guest-check-in.tsx',{});missing.render();await missing.flush();missing.render();assert.equal(missing.calls.length,0);assert(missing.text().includes('complete guest upload link'));assert(!missing.text().includes('Invitation code'));
  console.log('PASS invitation flows: current-password verification, failed verification, creation sharing, member isolation, guest first open/reload/forward, effect replay and missing-link guidance');
})().catch(e=>{console.error(e);process.exitCode=1;});
