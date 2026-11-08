/* global __dirname */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('../node_modules/typescript');
const cache = new Map();
function load(name) {
  const key = name.replace('@/src/', '').replace('./', '');
  if (!['booking-finance', 'expense-presentation'].includes(key)) throw new Error(`Unexpected report dependency: ${name}`);
  if (cache.has(key)) return cache.get(key);
  const scope = { exports: {}, require: load };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, `../src/${key}.ts`), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, scope);
  cache.set(key, scope.exports);
  return scope.exports;
}
module.exports = load('expense-presentation');

module.exports.finance = load("booking-finance");
