const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const functionSource = source.slice(source.indexOf('async function openPdf('), source.indexOf('\nlet state ='));

function setup(response, blocked = false) {
  const calls = [];
  const tab = { location: { replace(url) { calls.push(['navigate', url]); } }, close() { calls.push(['close']); } };
  const context = {
    window: { open() { calls.push(['open']); return blocked ? null : tab; } },
    apiFetch: async () => { calls.push(['fetch']); return response; },
    URL: { createObjectURL: () => 'blob:label', revokeObjectURL() {} },
    setTimeout() {},
  };
  vm.createContext(context);
  vm.runInContext(functionSource, context);
  return { calls, run: () => context.openPdf('/label') };
}

test('opens the print tab before waiting for label generation', async () => {
  const { run, calls } = setup({ ok: true, blob: async () => ({}) });
  await run();
  assert.deepEqual(calls, [['open'], ['fetch'], ['navigate', 'blob:label']]);
});

test('closes print tab and reports API error', async () => {
  const { run, calls } = setup({ ok: false, json: async () => ({ detail: 'Missing Allegro address' }) });
  await assert.rejects(run, /Missing Allegro address/);
  assert.deepEqual(calls, [['open'], ['fetch'], ['close']]);
});

test('blocked popup does not create an unseen shipment', async () => {
  const { run, calls } = setup({}, true);
  await assert.rejects(run, /przeglądar/i);
  assert.deepEqual(calls, [['open']]);
});
