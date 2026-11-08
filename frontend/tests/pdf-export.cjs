/* global __dirname */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
const ts = require('../node_modules/typescript');
const transpile = name => ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', name), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
async function run() {
  let printed = 0, nativeHtml, shared, previewHtml;
  const platform = { OS: 'web' };
  const scope = { exports: {}, require: name => {
    if (name === 'react-native') return { Platform: platform };
    if (name === 'expo-print') return { printAsync: () => { printed++; }, printToFileAsync: async ({html}) => { nativeHtml = html; return {uri: 'native.pdf'}; } };
    if (name === 'expo-sharing') return {isAvailableAsync: async () => true, shareAsync: async uri => { shared = uri; }};
    if (name === './pdf-web') return { previewWebPdf: async html => { previewHtml = html; }};
    return {};
  }};
  vm.runInNewContext(transpile('pdf.ts'), scope);
  const html = '<!doctype html><html><body>Complete statement ledger</body></html>';
  await scope.exports.sharePdf(html);
  assert.equal(previewHtml, html); assert.equal(printed, 0);
  platform.OS = 'android'; await scope.exports.sharePdf(html);
  assert.equal(nativeHtml, html); assert.equal(shared, 'native.pdf');

  let framePrinted = 0, appPrinted = 0, focused = false;
  const nodes = [];
  function element(tag) {
    const e = {tag, style: {}, children: [], setAttribute(k,v) {this[k]=v;}, append(...items) { this.children.push(...items); }, addEventListener() {}, remove() {this.removed=true;}, focus() {focused=this;}};
    if(tag === 'iframe') {e.contentDocument={fonts:{ready:Promise.resolve()}};e.contentWindow={focus(){},print(){framePrinted++;}};}
    nodes.push(e);return e;
  }
  const document = {getElementById: () => null, activeElement:{focus(){focused=true;}}, createElement:element, body:{append(e){setImmediate(()=>e.children.find(n=>n.tag==='iframe').onload());}}};
  const web = {exports:{},document,setTimeout,clearTimeout,window:{print(){appPrinted++;}}};
  vm.runInNewContext(transpile('pdf-web.ts'),web);
  await web.exports.previewWebPdf(html);
  const frame = nodes.find(n=>n.tag==='iframe'), buttons=nodes.filter(n=>n.tag==='button');
  assert.equal(frame.srcdoc,html);assert.equal(frame.sandbox,'allow-same-origin allow-modals');
  assert.equal(buttons[0].disabled,false);assert.equal(focused,buttons[0]);
  buttons[0].onclick();assert.equal(framePrinted,1);assert.equal(appPrinted,0);
  buttons[1].onclick();assert.equal(nodes[0].removed,true);
  console.log('PASS PDF export: exact generated HTML reaches isolated preview; frame prints instead of app; close restores focus; native PDF sharing preserved');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
