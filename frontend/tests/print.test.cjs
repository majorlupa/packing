const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('frontend/static/app.js', 'utf8');
// openPdf now reports its blocked-popup error through the translation catalog,
// so run it together with the real catalog + helpers rather than a stub.
const catalogSource = source.slice(
  source.indexOf('// ---- i18n catalog ----'),
  source.indexOf('async function promptForAccessToken'),
);
const openPdfSource = source.slice(source.indexOf('async function openPdf('), source.indexOf('\nlet state ='));
const functionSource = `${catalogSource}\n${openPdfSource}`;

function setup(response, blocked = false, creationError = null) {
  const calls = [];
  const tab = { location: { replace(url) { calls.push(['navigate', url]); } }, close() { calls.push(['close']); } };
  const context = {
    window: { open() { calls.push(['open']); return blocked ? null : tab; } },
    apiFetch: async () => { calls.push(['fetch']); return response; },
    api: async () => { calls.push(['create']); if (creationError) throw creationError; },
    URL: { createObjectURL: () => 'blob:label', revokeObjectURL() {} },
    setTimeout() {},
  };
  vm.createContext(context);
  vm.runInContext(functionSource, context);
  return { calls, run: () => context.openPdf('/label'), label: () => context.openPdf('/label', {}, () => context.api('/label', { method: 'POST' })) };
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
  const { label, calls } = setup({}, true);
  await assert.rejects(label, /przeglądar/i);
  assert.deepEqual(calls, [['open']]);
});

test('label creation starts synchronously after popup reservation and before PDF download', async () => {
  const { label, calls } = setup({ ok: true, blob: async () => ({}) });
  const pending = label();
  assert.deepEqual(calls, [['open'], ['create']]);
  await pending;
  assert.deepEqual(calls, [['open'], ['create'], ['fetch'], ['navigate', 'blob:label']]);
});

test('failed label creation closes popup without downloading', async () => {
  const { label, calls } = setup({}, false, new Error('Creation failed'));
  await assert.rejects(label, /Creation failed/);
  assert.deepEqual(calls, [['open'], ['create'], ['close']]);
});

test('failed PDF download after creation closes popup', async () => {
  const { label, calls } = setup({ ok: false, json: async () => ({ detail: 'Download failed' }) });
  await assert.rejects(label, /Download failed/);
  assert.deepEqual(calls, [['open'], ['create'], ['fetch'], ['close']]);
});
