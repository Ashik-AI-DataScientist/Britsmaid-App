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
  const nodes = [], events = {};
  function element(tag) {
    const e = {tag, style: {}, children: [], setAttribute(k,v) {this[k]=v;}, append(...items) { this.children.push(...items); }, addEventListener() {}, remove() {this.removed=true;}, focus() {focused=this;}};
    if(tag === 'iframe') {e.contentDocument={title:'Owner statement',body:{innerHTML:'<h1>Complete statement ledger</h1>'},querySelectorAll:()=>[{textContent:'@page{size:A4 portrait}'}],fonts:{ready:Promise.resolve()}};e.contentWindow={focus(){},print(){framePrinted++;}};}
    nodes.push(e);return e;
  }
  const document = {title:'Britsmaid',getElementById: () => null, activeElement:{focus(){focused=true;}}, createElement:element, head:{append(){}},body:{append(e){if(e.children.some(n=>n.tag==='iframe')) setImmediate(()=>e.children.find(n=>n.tag==='iframe').onload());}}};
  let failPrint = false;
  const web = {exports:{},document,setTimeout,clearTimeout,window:{focus(){},print(){if(failPrint) throw Error('unavailable');appPrinted++;},addEventListener:(key,fn)=>{events[key]=fn;},removeEventListener:(key)=>{delete events[key];}}};
  vm.runInNewContext(transpile('pdf-web.ts'),web);
  await web.exports.previewWebPdf(html);
  const frame = nodes.find(n=>n.tag==='iframe'), buttons=nodes.filter(n=>n.tag==='button');
  assert.equal(frame.srcdoc,html);assert.equal(frame.sandbox,'allow-same-origin allow-modals');
  assert.equal(buttons[0].disabled,false);assert.equal(focused,buttons[0]);
  buttons[0].onclick();assert.equal(appPrinted,1);assert.equal(framePrinted,0);
  const root=nodes.find(n=>n.id==='britsmaid-print-document'),style=nodes.find(n=>n.tag==='style');
  assert.equal(root.innerHTML,'<h1>Complete statement ledger</h1>');assert.equal(root.style.display,'none');
  assert.equal(style.media,'print');assert(style.textContent.includes('body>:not(#britsmaid-print-document){display:none!important}'));
  assert.equal(document.title,'Owner statement');events.afterprint();assert(root.removed && style.removed);assert.equal(document.title,'Britsmaid');
  failPrint=true;buttons[0].onclick();assert.match(nodes.find(n=>n.tag==='span').textContent,/try again/);assert.equal(document.title,'Britsmaid');
  failPrint=false;buttons[0].onclick();buttons[1].onclick();assert(nodes.filter(n=>n.id==='britsmaid-print-document').every(n=>n.removed));
  assert.equal(nodes[0].removed,true);assert.equal(document.title,'Britsmaid');
  console.log('PASS PDF export: full report in isolated top-level print flow; preview/application excluded; print error, afterprint and close cleanup; native sharing preserved');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
