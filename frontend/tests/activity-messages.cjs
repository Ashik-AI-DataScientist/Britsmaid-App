/* global __dirname */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../node_modules/typescript'),React=require('../node_modules/react');
function load(file,mocks={}){
  const scope={exports:{},require:n=>{if(n in mocks)return mocks[n];if(n.startsWith('.'))return load(path.join(path.dirname(file),n+'.ts'),mocks);throw Error('Unexpected dependency '+n);},URL,URLSearchParams};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText,scope);return scope.exports;
}
const {guestUploadMessage}=load('src/guest-invitation.ts');
const url='https://app.britsmaid.in/guest-check-in#invite=synthetic-a_123';
const stay={id:'booking-a',guest_name:'Synthetic Lead',property_name:'BM-001 Divya Villa',check_in:'2026-12-30',check_out:'2027-01-02'};
const text=guestUploadMessage(stay,url);
for(const fragment of ['Hi Synthetic Lead','BM-001 Divya Villa','30 Dec 2026','2 Jan 2027','all IDs yourself','forward this message','No app or login',url])assert(text.includes(fragment),fragment);
assert.equal(text.split(url).length,2);assert.equal(stay.guest_name,'Synthetic Lead');
assert(guestUploadMessage({...stay,guest_name:''},url).startsWith('Hi there,'));
for(const bad of ['invitation-code-only','https://app.britsmaid.in/guest-check-in','https://app.britsmaid.in/login#invite=x','javascript:alert(1)'])assert.throws(()=>guestUploadMessage(stay,bad));

// Exercise the actual guest admin screen's generation, sharing and opening handlers.
let i=0,values=[],messages=[],opened=[],posts=[];
const react={...React,useState:v=>{const index=i++;if(!(index in values))values[index]=typeof v==='function'?v():v;return [values[index],next=>values[index]=next];},useEffect:()=>{}};
const ui=Object.fromEntries(['Badge','Button','Card','ErrorState','Header','Input','Loading','Txt'].map(n=>[n,n]));ui.useToast=()=>()=>{};
const mocks={react,'react-native':{View:'View',ScrollView:'ScrollView',Text:'Text',Image:'Image',Modal:'Modal',Platform:{OS:'web'},Share:{share:async v=>messages.push(v.message)},Linking:{openURL:async u=>opened.push(u)}},'expo-router':{useLocalSearchParams:()=>({booking_id:stay.id})},'@tanstack/react-query':{useQuery:({queryKey})=>({data:queryKey[0]==='guest-bookings'?[stay]:[],refetch:async()=>{},isLoading:false,isError:false})},'@/src/api':{api:{post:async route=>{posts.push(route);return {url};}}},'@/src/ui':ui,'@/src/theme':{spacing:{}},'@/src/format':load('src/format.ts'),'@/src/guest-invitation':{guestUploadMessage}};
const Screen=load('app/guests.tsx',mocks).default;
let tree;function render(){i=0;tree=Screen();}function button(title){let found;function walk(v){if(!v||typeof v!=='object')return;if(v.type==='Button'&&v.props.title===title)found=v;React.Children.toArray(v.props?.children).forEach(walk);}walk(tree);assert(found,title);return found.props;}
(async()=>{
  render();await button('Get guest upload link').onPress();render();
  assert.equal(posts[0],'/bookings/booking-a/guest-link');
  await button('Share message & link').onPress();assert.equal(messages[0],text);
  await button('Open upload form').onPress();assert.equal(opened[0],url);

  const handlers={},shown=[],destinations=[];
  const scope={self:{addEventListener:(n,f)=>handlers[n]=f,registration:{showNotification:async(title,options)=>shown.push({title,...options})}},clients:{openWindow:async u=>destinations.push(u)}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../public/admin-push.js'),'utf8'),scope);
  let pending;const waitUntil=p=>pending=p;
  const destination='/booking/'+'a'.repeat(24);
  handlers.push({data:{json:()=>({title:'Booking recorded · BM-001 Divya Villa',details:'Stay: 1 Dec – 3 Dec 2026 · Activity: 26 Nov, 23:00 IST',body:'legacy fallback',url:destination,tag:'one'})},waitUntil});await pending;
  assert(shown[0].title.includes('BM-001'));assert(shown[0].body.includes('Stay:'));assert.equal(shown[0].data.url,destination);
  handlers.notificationclick({notification:{close:()=>{},data:{url:destination}},waitUntil});await pending;assert.equal(destinations[0],destination);
  for(const bad of ['https://attacker.invalid','//attacker.invalid','/login','/booking/../settings','javascript:alert(1)']){
    handlers.notificationclick({notification:{close:()=>{},data:{url:bad}},waitUntil});await pending;assert.equal(destinations.at(-1),'/notifications');
  }
  handlers.push({data:{json:()=>({body:'Older payload'})},waitUntil});await pending;assert.equal(shown.at(-1).title,'Britsmaid activity');assert.equal(shown.at(-1).body,'Older payload');
  console.log('PASS guest share message includes exact booking context/full fragment link; real screen shares message and opens raw link; contextual push, safe destination and legacy payload checks');
})().catch(e=>{console.error(e);process.exitCode=1;});
