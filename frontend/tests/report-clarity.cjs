/* global __dirname */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const ts = require('../node_modules/typescript');
const presentation = require('./report-helpers.cjs');
const scope = { exports: {}, require: name => name === '@/src/expense-presentation' ? presentation : name === '@/src/format' ? { inr:n=>`INR ${n}`,fmtDate:d=>d,monthLabel:m=>m } : name === '@/src/api' ? {LOGO_URL:'logo'} : {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/pdf.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
let count=0;
for (const before of [0,.01,.03,4000,100000]) for (const after of [0,.01,.03,2000,100000]) for (const costShare of [0,30,50,100]) for (const split of [0,1,30,70,99,100]) {
  const round=n=>Math.round((n+Number.EPSILON)*100)/100;
  const ownerCost=round(after*costShare/100),bmCost=round(after-ownerCost),net=84000-before,ownerBase=round(net*split/100),bmBase=round(net-ownerBase),balance=round(ownerBase-ownerCost),tds=round(Math.max(balance,0)*.02),payout=round(balance-tds);
  const items=[null,{amount:null},{amount:0},...(before?[{id:'before',amount:before,type:'pre_split',title:'<script>bad()</script>',notes:'Repair & approved'}]:[]),...(after?[{id:'after',amount:after,type:'other',title:'Shared expense',allocation:{owner_amount:ownerCost,britsmaid_amount:bmCost,owner_percent:costShare,britsmaid_percent:100-costShare}}]:[])];
  const s={gross:100000,ota_commission:10000,gst_total:5000,platform_tax:1000,pre_split_deductions:before,expense_before_total:before,expense_after_total:after,expense_reference_total:0,owner_after_expenses:ownerCost,britsmaid_after_expenses:bmCost,net_revenue:net,owner_share:ownerBase,britsmaid_share:bmBase,owner_share_percent:split,britsmaid_share_percent:100-split,owner_before_tds:balance,owner_tds:tds,owner_tds_percent:2,owner_payout:payout,britsmaid_net:round(bmBase-bmCost),deduction_items:items,by_ota:[],bookings:[],month:'2026-11'};
  const original=JSON.stringify(s),p=presentation.reportPresentation(s),html=scope.exports.settlementHtml(s),receipt=scope.exports.payoutReceiptHtml({...s,calculated_payout:payout,amount:payout,paid_on:'2026-11-01'});
  assert.equal(p.totalExpenses,round(before+after));assert.equal(p.ownerAfter,ownerCost);assert.equal(p.bmAfter,bmCost);assert.equal(p.groups.length,Number(before>0)+Number(after>0));
  for(const output of [html,receipt]) {assert.equal(output.includes('Expenses before revenue split'),before>0);assert.equal(output.includes('Owner expenses after split'),ownerCost>0);assert.equal(output.includes('Britsmaid expenses after split'),bmCost>0);assert(output.includes('Other tax deductions'));assert(!output.includes('Platform tax'));assert(!output.includes('<script>bad()</script>'));if(before)assert(output.includes('&lt;script&gt;bad()&lt;/script&gt;'));assert(output.includes(`INR ${payout}`));}
  assert.equal(JSON.stringify(s),original);count++;
}
const old={owner_electricity:500,britsmaid_electricity:500,electricity_total:1000,electricity_mode:'split_half',other_deductions:50,pre_split_deductions:100,owner_payout:1234.56,deduction_items:[],by_ota:[],bookings:[],month:'2026-11'};
const oldP=presentation.reportPresentation(old);assert.equal(oldP.totalExpenses,1150);assert.equal(oldP.ownerAfter,550);assert(oldP.groups.some(g=>g.items.some(e=>e.summary)));
assert(scope.exports.settlementHtml(old).includes('INR 1234.56'));assert(scope.exports.settlementHtml(old).includes('older report'));
const empty=presentation.reportPresentation({deduction_items:[null,{amount:null},{amount:0},{amount:'bad'}]});assert.equal(empty.groups.length,0);assert.equal(empty.totalExpenses,0);
const mismatch=presentation.reportPresentation({expense_before_total:1,deduction_items:[{amount:2,type:'pre_split'}]});assert(mismatch.groups[0].mismatch);
const reference=presentation.reportPresentation({expense_reference_total:500,deduction_items:[{amount:500,type:'electricity',treatment:'reference'}]});assert.equal(reference.totalExpenses,500);assert.equal(reference.ownerAfter,0);
assert(!scope.exports.payoutReceiptHtml({by_ota:[],bookings:[],month:'2026-11',calculated_payout:50,amount:50}).includes('Britsmaid breakdown'));
console.log(`PASS ${count} report/receipt scenarios: conditional categories, full expenses vs owner contribution, split ratios, loss months, zero/paise costs, saved figures, escaping and legacy receipts`);

assert.equal(presentation.reportPresentation({britsmaid_electricity:50.17,britsmaid_other_expenses:3.6}).bmAfter,53.77);
