/* global __dirname */
// Render real owner/property components with synthetic data; no browser or services.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../node_modules/typescript'),React=require('../node_modules/react'),{renderToStaticMarkup}=require('../node_modules/react-dom/server');
let role='owner',pid='villa-one',mode='earnings',feeds=[],segments=['owner'];
const native=({children,testID})=>React.createElement('div',{'data-testid':testID},children);
const button=({children,title,label,testID})=>React.createElement('button',{'data-testid':testID},title||label||children);
const ui={Txt:native,Card:native,Button:button,IconButton:button,Icon:native,Loading:native,Badge:button,Chip:button,Input:()=>React.createElement('input'),Row:({label,value})=>React.createElement('div',null,label,' ',value),Header:({title,right})=>React.createElement('header',null,title,right),HomeButton:button,ErrorState:native,Empty:native,useToast:()=>()=>{},ConfirmSheet:({visible})=>visible?React.createElement('div',null,'DELETE CONFIRMATION'):null,Segmented:({options})=>React.createElement('nav',null,...options.map(o=>React.createElement('span',{key:o.value},o.label)))};
const prop=()=>({id:pid,name:'Sample '+pid,rooms:['Room 1'],location:'Sample location',owner_share_percent:70,base_rate:1000,ical_feeds:feeds,created_at:'2026-11-01'});
const expense=()=>({id:'123456789012345678901234',title:'Electricity',notes:'Full expense note',amount:200,month:'2026-11',treatment:'after_split',media_ids:['receipt-id'],allocation:{owner_amount:100,britsmaid_amount:100,owner_percent:50,britsmaid_percent:50}});
const statement=()=>({month:'2026-11',property_id:pid,owner_payout:100,nights:1,by_ota:[],bookings:[],payout:null});
const mockReact={...React,useState:initial=>[typeof initial==='function'?initial():initial,()=>{}]};
function load(relative,expanded=false){
 const mocks={react:expanded?{...mockReact,useState:initial=>[typeof initial==='boolean'?true:initial,()=>{}]}:{...mockReact,useState:initial=>[initial==='earnings'?mode:typeof initial==='function'?initial():initial,()=>{}]},
  'react-native':{LogBox:{ignoreLogs:()=>{}},View:native,ScrollView:native,RefreshControl:()=>null,Pressable:button,Platform:{OS:'web'}},
  'expo-router':{Stack:()=>React.createElement('div',{'data-testid':'router-stack'}),useSegments:()=>segments,useRouter:()=>({push:()=>{},back:()=>{}}),useLocalSearchParams:()=>({id:pid,deduction:'expense',expense_id:expense().id})},
  '@tanstack/react-query':{QueryClientProvider:native,useQuery:({queryKey})=>({data:queryKey[0]==='property'?prop():queryKey[0]==='settlement'?statement():queryKey[0]==='expenses'?[expense()]:[],refetch:()=>{},isLoading:false,isError:false}),useQueryClient:()=>({})},
  'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},
  'react-native-reanimated':{__esModule:true,default:{View:native},FadeInDown:{delay:()=>({})}},
  'expo-linear-gradient':{LinearGradient:native},
  '@/src/api':{api:{}},'@/src/auth':{AuthProvider:native,useAuth:()=>({user:{id:pid,role},logout:()=>{}})},
  '@/src/ui':ui,'@/src/theme':{colors:{surfaceSecondary:'#123456'},spacing:{sm:8,md:12,lg:16,xl:24,xs:4},radius:{pill:40,lg:20},useTheme:()=>({colors:new Proxy({},{get:()=> '#123456'})})},
  '@/src/format':{thisMonth:()=> '2026-11',todayISO:()=> '2026-11-08',fmtDate:d=>d,fmtShort:d=>d,monthLabel:m=>m,otaColor:()=> '#123456',inr:n=>String(n)},
  '@/src/components/PropertyCover':{PropertyCover:()=>React.createElement('img',{alt:'cover'})},
  '@/src/components/ExpenseEditor':{ExpenseEditor:()=>React.createElement('form',null,'EXPENSE EDITOR')},
  '@/src/components/ExpenseDetails':{ExpenseDetails:props=>React.createElement(load('src/components/ExpenseDetails.tsx',true).ExpenseDetails,props)},
  '@/src/components/MediaThumb':{MediaThumb:({id})=>React.createElement('button',null,'Attachment '+id)},
  '@/src/components/Contacts':{ContactsCard:native},
  '@/src/components/PropertyCalendar':{PropertyCalendar:({propertyId})=>React.createElement('div',{'data-property':propertyId},'Shared property calendar')},
  '@/src/components/SettlementView':{SettlementView:()=>React.createElement('div',null,'Shared detailed statement')},
  '@/src/components/Payout':{PayoutStatusCard:()=>React.createElement('div',null,'View payment status'),downloadReceipt:()=>{}},
  '@/src/app-fonts':{useAppFonts:()=>[true,null]},'@/src/query-client':{queryClient:{}},'@/src/components/error-boundary':{ErrorBoundary:native},'expo-status-bar':{StatusBar:native},'react-native-keyboard-controller':{KeyboardProvider:native},'react-native-gesture-handler':{GestureHandlerRootView:native},
  '@/src/pdf':{settlementHtml:()=>'',sharePdf:()=>{}}
 };
 const scope={React,exports:{},require:name=>{if(name in mocks)return mocks[name];throw Error('Unexpected rendering dependency '+name);}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',relative),'utf8')+(relative==='app/_layout.tsx'?'\nexport { AuthGate };':''),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText,scope);
 return scope.exports;
}
const controls=['property-edit-button','property-delete-button','property-new-booking','property-report','property-ical-sync','property-add-ical','property-edit-bottom','property-delete-bottom','property-add-bill'];
let count=0;
for(role of ['owner','admin'])for(pid of ['villa-one','villa-two'])for(feeds of [[],[{ota:'Airbnb',last_synced:null}]]){
 const html=renderToStaticMarkup(React.createElement(load('app/property/[id].tsx').default));
 for(const control of controls)assert.equal(html.includes(`data-testid="${control}"`),role==='admin'&&(control!=='property-add-ical'||feeds.length===0),control);
 assert(html.includes('Statement')&&html.includes('Full expense note')&&html.includes('Attachment receipt-id'));
 assert.equal(html.includes('EXPENSE EDITOR'),role==='admin');
 assert.equal(html.includes('Edit expense'),role==='admin');
 count++;
}
for(role of ['owner','admin'])for(const treatment of ['before_split','after_split','reference']){
 const html=renderToStaticMarkup(React.createElement(load('src/components/ExpenseDetails.tsx',true).ExpenseDetails,{item:{...expense(),treatment},onEdit:()=>{}}));
 assert(html.includes('Full expense note')&&html.includes('Attachment receipt-id'));
 assert.equal(html.includes('Edit expense'),role==='admin');assert(!html.includes('<input')&&!html.includes('<form'));
 count++;
}
role='owner';
for(pid of ['villa-one','villa-two'])for(mode of ['earnings','calendar']){
 const html=renderToStaticMarkup(React.createElement(load('app/owner/[id].tsx').default));
 for(const label of ['Earnings','Payouts','Calendar','Stays','Updates'])assert(html.includes(label));
 assert(!html.includes('Edit expense')&&!html.includes('Mark as paid')&&!html.includes('<input'));
 assert(html.includes(mode==='calendar'?`data-property="${pid}"`:'Shared detailed statement'));
 count++;
}
console.log(`PASS ${count} synthetic owner/admin renders: identical property tabs, scoped calendar, expanded expense notes and attachments, no owner edit/create/delete/sync controls or editor via query parameters`);


for(role of ['owner','admin']) for(segments of [['property','edit'],['booking','new'],['report','new'],['(admin)','calendar'],['staff'],['settings'],['invoice','new'],['owner','[id]'],['property','[id]'],['booking','[id]'],['report','settlement'],['report','[id]'],['cleaning','[id]']]) {
 const html=renderToStaticMarkup(React.createElement(load('app/_layout.tsx').AuthGate));
 const editorRoute=['edit','new'].includes(segments[1])||['(admin)','staff','settings'].includes(segments[0]);
 assert.equal(html.includes('router-stack'),role==='admin'||!editorRoute,role+' '+segments.join('/'));
}
console.log('PASS 26 route renders: owner editor/admin routes withheld before redirect; view routes remain available; admin routes retained');

