/* global __dirname */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const ts = require('../node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/cleaning-status.ts'), 'utf8');
const scope = {exports:{}};
vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText, scope);
const {cleaningDayStatus, refreshCleaningViews, CLEANING_COMPLETE_COLOR} = scope.exports;
assert.equal(cleaningDayStatus([]), undefined);
assert.equal(cleaningDayStatus([{status:'cancelled'}]), undefined);
assert.equal(cleaningDayStatus([{status:'completed'}, {status:'cancelled'}]), 'completed');
for (const status of ['pending','in_progress','awaiting_review']) {
  for (const tasks of [[{status}, {status:'completed'}], [{status:'completed'}, {status}]]) {
    assert.equal(cleaningDayStatus(tasks), 'pending');
  }
}
assert.equal(cleaningDayStatus([{status:'completed'}, {status:'completed'}]), 'completed');
const views = new Map(['cleaning','dashboard','properties','property','owner-dashboard','calendar','finance'].map(key=>[key,false]));
refreshCleaningViews({invalidateQueries:({queryKey})=>views.set(queryKey[0],true)});
assert.deepEqual([...views].filter(([,stale])=>!stale).map(([key])=>key), ['finance']);
assert.equal(CLEANING_COMPLETE_COLOR, '#7C3AED');
console.log('PASS cleaning: cancelled/mixed tasks, order independence, completion colour and all dependent views refresh');
