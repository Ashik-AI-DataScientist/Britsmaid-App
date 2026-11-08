/* global __dirname */
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm'), assert=require('node:assert/strict');
const ts=require('../node_modules/typescript'), helpers=require('./report-helpers.cjs');
const scope={exports:{}, require:name=> name==='@/src/booking-finance'?helpers.finance:name==='@/src/expense-presentation'?helpers:name==='@/src/format'?{inr:n=>`INR ${Number(n).toFixed(2)}`,fmtDate:d=>d,monthLabel:m=>m}:name==='@/src/api'?{LOGO_URL:'logo'}:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/pdf.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,scope);
const legacy={guest_name:'Older <Guest>',ota:'Direct',check_in:'2026-10-01',check_out:'2026-10-02',amount:10000.03,ota_commission:1000,net_revenue:9000.03};
const f=helpers.finance.newFinancials();f.gst.percent=5;f.platform_fee.percent=10;f.platform_tax.percent=1;f.misc_amount=100;f.misc_title='Linen & repair';f.misc_notes='Approved <note>';
const t=helpers.finance.bookingMath(10500,f);
f.gst.amount=t.gst;f.platform_fee.amount=t.fee;f.platform_tax.amount=t.tax;
const detailed={...legacy,guest_name:'Detailed booking',amount:10500,net_revenue:t.net,financials:f};
let cases=0;
for(const split of [0,.5,30,50,70,99.5,100]) for(const paid of [false,true]) for(const bookings of [[legacy],[detailed],[legacy,detailed],[]]) {
 const s={property_name:'SYNTHETIC property',owner_name:'Test owner',month:'2026-10',nights:0,occupancy_percent:0,by_ota:[],bookings,owner_share_percent:split,britsmaid_share_percent:100-split,owner_payout:100.01,owner_tds:2.04,owner_tds_percent:2,payout:paid?{amount:90.02,paid_on:'2026-11-05',method:'Bank transfer',reference:'REF<&',receipt_number:'SAMPLE-001',notes:'Saved & checked'}:null};
 const before=JSON.stringify(s),html=scope.exports.settlementHtml(s);
 assert.equal(html.includes('Payout status: PAID'),paid);
 assert.equal(html.includes('Payout pending:'),!paid);
 if(paid) {assert(html.includes('REF&lt;&amp;'));assert(html.includes('Saved &amp; checked'));assert(html.includes('differs from the current calculated payout'));assert(html.includes('INR 90.02'));}
 if(bookings.includes(legacy)) {assert(html.includes('Older &lt;Guest&gt;'));assert(html.includes('Tax details were not recorded'));assert(html.includes('INR 1000.00'));assert(html.includes('INR 9000.03'));}
 if(bookings.includes(detailed)) {assert(html.includes('INR 8800.00'));assert(html.includes('Linen &amp; repair'));assert(html.includes('Approved &lt;note&gt;'));}
 assert.equal(JSON.stringify(s),before);assert(!html.includes('undefined'));cases++;
}
const legacyForm=helpers.finance.newFinancials(6419.53);
assert.equal(helpers.finance.bookingMath(37564,legacyForm).net,31144.47);
assert.equal(helpers.finance.bookingMath(37564,legacyForm).fee,6419.53);
console.log(`PASS ${cases} uniform detailed PDF cases: older/new/mixed/empty bookings, split boundaries, pending/paid reference and notes, mismatched payment, escaped data and immutable input`);
