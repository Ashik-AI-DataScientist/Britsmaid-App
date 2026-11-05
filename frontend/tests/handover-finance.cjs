/* global __dirname */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const ts = require('../node_modules/typescript');
const scope = {exports: {}, require: name => {
  if (name === '@/src/format') return {inr: n => `INR ${n}`, fmtDate: d => d, monthLabel: m => m};
  if (name === '@/src/api') return {LOGO_URL: 'data:image/png;base64,TEST'};
  return {};
}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/pdf.ts'), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText, scope);
const deductions = [{id: 'cost', type: 'pre_split', amount: 1000, title: '<script>bad()</script>', notes: 'Shared & approved'}, {id:'owner', type:'other', amount:300, notes:'Owner requested'}];
const statement = {by_ota: [], bookings: [], month: '2026-11', property_name:'Sample', owner_name:'Sample', gross:10000, ota_commission:1000, net_revenue:8000, owner_share:5600, britsmaid_share:2400, owner_share_percent:70, britsmaid_share_percent:30, owner_payout:5300, owner_electricity:0, pre_split_deductions:1000, other_deductions:300, deduction_items:deductions};
const receipt = { ...statement, receipt_number:'TEST', amount:5300, calculated_payout:5300, paid_on:'2026-11-03', method:'Cash' };
for (const html of [scope.exports.settlementHtml(statement), scope.exports.payoutReceiptHtml(receipt)]) {
  assert(html.includes('Expenses before split'));
  assert(html.includes('INR 5300'));
  assert(html.includes('&lt;script&gt;bad()&lt;/script&gt;'));
  assert(!html.includes('<script>bad()</script>'));
  assert(html.includes('Shared &amp; approved'));
  assert(html.includes('Owner requested'));
}
// Existing snapshots without new deduction fields remain printable.
delete statement.pre_split_deductions; delete statement.deduction_items;
assert(scope.exports.settlementHtml(statement).includes('Owner payout'));
console.log('PASS statement and receipt: separate deductions, saved notes, escaped markup and old snapshots');
