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

// Channel rows must explain every deduction without counting booking expenses as taxes.
for (const misc of [0,.01,100]) {
 const b={...detailed,financials:{...f,misc_amount:misc}};
 const row={ota:'Direct',gross:10500,commission:1000,net:8900-misc,bookings:1,nights:1};
 const breakdown=helpers.otaBreakdown(row,[b]);
 assert.equal(breakdown.taxesAndCommission,1600);
 assert.equal(breakdown.bookingExpenses,misc);
 assert.equal(helpers.finance.money(row.gross-breakdown.taxesAndCommission-breakdown.bookingExpenses),row.net);
 const html=scope.exports.settlementHtml({month:'2026-10',by_ota:[row],bookings:[b],owner_share_percent:70,britsmaid_share_percent:30});
 const section=html.split('<h3>Revenue by OTA</h3>')[1].split('<h3>Booking-by-booking')[0];
 assert(section.includes('Taxes &amp; commission'));
 assert(section.includes('Revenue available to split'));
 assert(section.includes('INR 1600.00'));
 assert.equal(section.includes('<th class="r">Other booking expenses</th>'),misc>0);
 assert(!section.includes('>Net</th>') && !section.includes('>Commission</th>'));
}
assert.equal(helpers.otaBreakdown({ota:'Direct',gross:1000,net:900},[legacy]).taxesAndCommission,100);
console.log('PASS OTA reconciliation for taxes, commission, zero/paise/positive booking expenses and older saved rows');

// Independently allocated add-ons must stay visible and escaped in owner PDFs.
for (const ownerAmount of [null, 235]) {
 const extra={title:'Extra <guest>',guest_name:'Synthetic guest',service_date:'2026-11-23',status:'received',amount:1000,tax:50,fee:10,owner_percent:25,owner_amount:ownerAmount,notes:'Approved <note>'};
 const s={month:'2026-11',nights:0,occupancy_percent:0,by_ota:[{ota:'Additional revenue',gross:1000,net:940,bookings:0,nights:0}],bookings:[],owner_share_percent:70,britsmaid_share_percent:30,gross:1000,net_revenue:940,owner_share:235,britsmaid_share:705,additional_revenue:[extra],additional_totals:{gross:1000,deductions:60}};
 const before=JSON.stringify(s),html=scope.exports.settlementHtml(s);
 assert(html.includes('Extra &lt;guest&gt;') && html.includes('Approved &lt;note&gt;'));
 assert(html.includes('Additional revenue taxes / collection fees'));
 assert(html.includes('Owner allocation (rental and add-ons)'));
 assert(html.includes('Britsmaid allocation'));
 assert.equal(JSON.stringify(s),before);
 assert(!html.includes('undefined'));
}
console.log('PASS additional-revenue PDF allocation, deductions, escaping and immutable records');

// Owner add-on allocations include both amounts and effective rates, in the requested column order.
for (const [allocation, expected] of [[{owner_percent:25,owner_amount:null},'25%'],[{owner_percent:70,owner_amount:235},'25%']]) {
 const item={title:'Shared add-on',amount:1000,tax:50,fee:10,status:'received',...allocation};
 const html=scope.exports.settlementHtml({month:'2026-11',by_ota:[],bookings:[],additional_revenue:[item]});
 const table=html.split('<table class="additional-revenue">')[1].split('</table>')[0];
 assert(table.indexOf('>Gross</th>')<table.indexOf('>Tax / fee</th>') && table.indexOf('>Tax / fee</th>')<table.indexOf('>Allocation</th>'));
 assert(table.includes('Owner: INR 235.00 ('+expected+')') && table.includes('Britsmaid: INR 705.00 (75%)'));
 assert(!html.includes('individually') && !html.includes('Only received revenue'));
}
for (const item of [{amount:100,owner_percent:0},{amount:100,owner_percent:70,owner_amount:0},{amount:.01,owner_percent:.01},{amount:100,tax:100,owner_percent:70}]) {
 const html=scope.exports.settlementHtml({month:'2026-11',by_ota:[],bookings:[],additional_revenue:[{title:'PRIVATE',...item}]});
 assert(!html.includes('<h3>Additional revenue</h3>') && !html.includes('PRIVATE'));
}
console.log('PASS add-on column order, amount/rate allocations, zero-share omission and concise wording');
