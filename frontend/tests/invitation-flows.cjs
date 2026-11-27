/* global __dirname */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../node_modules/typescript'),React=require('../node_modules/react');
function harness(file, props, hash='', fail=false) {
  let index=0,first=true,values=[],effects=[],calls=[],messages=[],tree; const listeners={}; let responder=null;
  const location={hash,pathname:'/guest-check-in'};
  const hooks={...React,useState:v=>{const i=index++;if(!(i in values))values[i]=typeof v==='function'?v():v;return[values[i],v=>{values[i]=typeof v==='function'?v(values[i]):v;}];},useRef:v=>{const i=index++;return values[i]??(values[i]={current:v});},useCallback:f=>f,useEffect:f=>{if(first)effects.push(f);}};
  const mocks={react:hooks,'react-native':{Platform:{OS:'web'},View:'View',ScrollView:'ScrollView',Pressable:'Pressable',Linking:{openURL:async url=>messages.push(url)},Share:{share:async v=>messages.push(v.message)}},'expo-image-picker':{},'@/src/ui':{...Object.fromEntries(['Button','Input','Sheet','Txt','Card','Chip','Header'].map(n=>[n,n])),useToast:()=>m=>messages.push(m)},'@/src/theme':{spacing:{},radius:{},useTheme:()=>({colors:{}})},'@/src/api':{api:{post:async (url,body)=>{calls.push({url,body});if(fail)throw Error('Wrong password');return {ok:true};}},request:async (url,options)=>{calls.push({url,options});if(responder)return responder(url,options);return {guests:5,documents:[],check_in:'2026-12-01',check_out:'2026-12-03',retention_days:90};}}};
  const scope={exports:{},require:n=>{assert(n in mocks,n);return mocks[n];},window:{location,addEventListener:(event,fn)=>listeners[event]=fn,removeEventListener:(event)=>delete listeners[event],history:{replaceState:()=>{throw Error('Invitation fragment must not be removed');}}},URLSearchParams,FormData,Blob,setInterval:()=>1,clearInterval:()=>{}};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText,scope);
  const component=scope.exports.default||scope.exports.InviteSheet;
  const render=()=>{index=0;tree=component(props);first=false;return tree;};
  const nodes=()=>{let all=[];function walk(v){if(!v||typeof v!=='object')return;if(v.type)all.push(v);React.Children.toArray(v.props?.children).forEach(walk);}walk(tree);return all;};
  return {dispatch:event=>listeners[event]?.(),respond:fn=>responder=fn,render,nodes,calls,messages,location,effects,flush:async()=>{for(const f of effects)f();await new Promise(r=>setImmediate(r));},byId:id=>nodes().find(n=>n.props.testID===id),text:()=>JSON.stringify(tree)};
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
  const arriving=harness('app/guest-check-in.tsx',{});arriving.render();await arriving.flush();arriving.render();
  arriving.location.hash='#invite=arriving-later';arriving.dispatch('hashchange');await new Promise(r=>setImmediate(r));arriving.render();
  assert(arriving.text().includes('Stay:'));assert.equal(arriving.calls.at(-1).options.authorization,'arriving-later');
  let resolveA,resolveB;
  arriving.respond((url,options)=>new Promise(resolve=>{if(options.authorization==='booking-A')resolveA=resolve;else resolveB=resolve;}));
  arriving.location.hash='#invite=booking-A';arriving.dispatch('popstate');
  arriving.location.hash='#invite=booking-B';arriving.dispatch('pageshow');arriving.render();assert(!arriving.text().includes('Stay:'));
  const response=property_name=>({property_name,guests:2,documents:[],check_in:'2026-12-01',check_out:'2026-12-03',retention_days:90});
  resolveB(response('CURRENT BOOKING'));await new Promise(r=>setImmediate(r));arriving.render();assert(arriving.text().includes('CURRENT BOOKING'));
  resolveA(response('WRONG PREVIOUS BOOKING'));await new Promise(r=>setImmediate(r));arriving.render();assert(!arriving.text().includes('WRONG PREVIOUS BOOKING'));assert(arriving.text().includes('CURRENT BOOKING'));
  arriving.location.hash='';arriving.dispatch('focus');arriving.render();assert(!arriving.text().includes('CURRENT BOOKING'));assert(arriving.text().includes('complete guest upload link'));
  const upload=harness('app/guest-check-in.tsx',{},'#invite=upload-A');upload.render();await upload.flush();upload.render();
  upload.nodes().find(n=>n.type==='Input'&&n.props.label==='Guest full name as shown on ID').props.onChangeText('Synthetic old guest');
  upload.nodes().find(n=>n.type==='Pressable'&&n.props.accessibilityRole==='checkbox').props.onPress();upload.render();
  let finishUpload;
  upload.respond((url)=>url==='/guest/documents'?new Promise(resolve=>finishUpload=resolve):Promise.resolve(response('NEW STAY')));
  const fileHandler=upload.nodes().find(n=>n.type==='input').props.onChange;
  fileHandler({target:{files:[new File(['synthetic'],'id.jpg',{type:'image/jpeg'})],value:'id.jpg'}});
  assert.equal(upload.calls.at(-1).options.authorization,'upload-A');
  upload.location.hash='#invite=upload-B';upload.dispatch('hashchange');await new Promise(r=>setImmediate(r));upload.render();
  finishUpload({id:'synthetic'});await new Promise(r=>setImmediate(r));upload.render();
  assert(upload.text().includes('NEW STAY'));assert(!upload.text().includes('Synthetic old guest'));assert.equal(upload.messages.length,0);
  console.log('PASS invitation flows: current-password verification, failed verification, creation sharing, member isolation, guest first open/reload/forward, effect replay and missing-link guidance');
})().catch(e=>{console.error(e);process.exitCode=1;});
