/* global __dirname */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../public/install.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
function setup(standalone = false, appleStandalone = false) {
  const events = {}, actions = {}, changes = {};
  const button = { hidden: true, disabled: false, addEventListener: (type, fn) => { actions[type] = fn; } };
  const status = { textContent: '' };
  const display = { matches: standalone, addEventListener: (type, fn) => { changes[type] = fn; } };
  vm.runInNewContext(script, {
    document: { getElementById: id => id === 'install' ? button : status },
    window: { matchMedia: () => display, addEventListener: (type, fn) => { events[type] = fn; } },
    navigator: { standalone: appleStandalone },
  });
  return { events, actions, button, status, display, changes };
}
function offer(state, outcome = 'dismissed', reject = false) {
  let prompted = 0;
  state.events.beforeinstallprompt({ preventDefault() {}, prompt: async () => { prompted++; if (reject) throw Error('Not available'); }, userChoice: Promise.resolve({ outcome }) });
  return () => prompted;
}
(async () => {
  let state = setup();
  assert.equal(state.button.hidden, true); // Safari/no event: manual steps remain available.
  let count = offer(state);
  assert.equal(state.button.hidden, false);
  await state.actions.click(); await state.actions.click();
  assert.equal(count(), 1);
  assert.match(state.status.textContent, /later/);
  assert.doesNotMatch(state.status.textContent, /was installed/);
  state = setup(); count = offer(state, 'accepted');
  await state.actions.click();
  assert.match(state.status.textContent, /requested/);
  state.events.appinstalled();
  assert.equal(state.button.hidden, true);
  assert.match(state.status.textContent, /was installed/);
  state = setup(); offer(state, 'dismissed', true);
  await state.actions.click();
  assert.equal(state.button.disabled, false);
  assert.match(state.status.textContent, /browser menu/);
  for (const args of [[true, false], [false, true]]) {
    state = setup(...args); count = offer(state);
    assert.equal(state.button.hidden, true);
    await state.actions.click();
    assert.equal(count(), 0);
  }
  console.log('PASS web installation: manual fallback, cancellation/retry, accepted/installed distinction, prompt error and standalone Android/iPhone states');
})().catch(error => { console.error(error); process.exitCode = 1; });
