const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const definitions = source.slice(0, source.indexOf('// ---- Sidebar events ----'));

function setup(lang = 'pl') {
  const nodes = { 'toast-info': { textContent: '', isConnected: true }, 'toast-error': { textContent: '', isConnected: true } };
  const timers = new Map();
  let timerId = 0;
  const tab = { closed: false, close() { this.closed = true; } };
  const document = { getElementById: id => nodes[id] || null, querySelectorAll: () => [], documentElement: null };
  const context = vm.createContext({
    document, Headers, Intl,
    window: { open: () => tab },
    setTimeout(fn, delay) { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(definitions, context);
  context.setLanguage(lang);
  return { context, nodes, timers, tab };
}

for (const lang of ['pl', 'en']) {
  test(`network failures use a translated message (${lang})`, async () => {
    const { context } = setup(lang);
    context.fetch = async () => { throw new Error('RAW connection diagnostic'); };
    await assert.rejects(() => context.api('/test'), err => err.message === context.t('common.requestFailed'));
  });

  test(`JSON API, PDF and upload parser localize structured errors (${lang})`, async () => {
    const { context, tab } = setup(lang);
    for (const code of ['allegro.not_authorized', 'common.allegro_unreachable', 'allegro.request_failed']) {
      const response = { ok: false, headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ detail: { code, message: 'Server language ignored' } }) };
      context.apiFetch = async () => response;
      const expected = context.t(code);
      await assert.rejects(() => context.api('/test'), err => err.message === expected);
      await assert.rejects(() => context.openPdf('/test'), err => err.message === expected);
      assert.equal((await context.responseError(response)).message, expected);
      assert.equal(tab.closed, true);
    }
  });

  test(`malformed API/PDF/upload errors use localized generic fallback (${lang})`, async () => {
    const { context } = setup(lang);
    const expected = context.t('common.requestFailed');
    for (const payload of [null, {}, { detail: {} }, { detail: ['validation'] }, { detail: 42 }, { detail: { code: 'unknown', message: {} } }, { detail: ' ' }]) {
      assert.equal(context.apiErrorMessage(payload), expected);
    }
    const response = { ok: false, status: 502, statusText: 'Bad Gateway', headers: new Headers({ 'content-type': 'text/html' }), json: async () => { throw new SyntaxError('HTML'); } };
    context.apiFetch = async () => response;
    await assert.rejects(() => context.api('/test'), err => err.message === expected);
    await assert.rejects(() => context.openPdf('/test'), err => err.message === expected);
    assert.equal((await context.responseError(response)).message, expected);
  });
}

test('legacy text and unknown structured code preserve readable backend messages', () => {
  const { context } = setup();
  assert.equal(context.apiErrorMessage({ detail: 'Readable error' }), 'Readable error');
  assert.equal(context.apiErrorMessage({ message: 'Readable error' }), 'Readable error');
  assert.equal(context.apiErrorMessage({ detail: { code: 'new.code', message: 'Readable error' } }), 'Readable error');
});

test('info and error toasts replace each other, reset dismissal and do not steal focus', () => {
  const { context, nodes, timers } = setup();
  context.showToast(() => context.t('day.noneReady'));
  assert.equal(nodes['toast-info'].textContent, context.t('day.noneReady'));
  assert.equal(nodes['toast-error'].textContent, '');
  assert.equal([...timers.values()][0].delay, 5000);
  context.setLanguage('en');
  assert.equal(nodes['toast-info'].textContent, context.t('day.noneReady'));
  context.reportError(context.t('common.errorPrefix'), new Error('<script>unsafe</script>'));
  assert.equal(nodes['toast-info'].textContent, '');
  assert.equal(nodes['toast-error'].textContent, 'Error\n<script>unsafe</script>');
  assert.equal(timers.size, 1);
  const timer = [...timers.values()][0];
  assert.equal(timer.delay, 8000);
  timer.fn();
  assert.equal(nodes['toast-error'].textContent, '');
  context.setLanguage('pl');
  assert.equal(nodes['toast-error'].textContent, '', 'dismissed toast must not reappear on language change');
});

test('frontend has no alert calls, preserves confirmations and persistent accessible live regions', () => {
  for (const file of fs.readdirSync('frontend/static').filter(file => file.endsWith('.js'))) {
    assert.doesNotMatch(fs.readFileSync(`frontend/static/${file}`, 'utf8'), /\balert\s*\(/);
  }
  assert.match(source, /confirm\(t\('day.confirm'\)\)/);
  assert.match(source, /confirm\(t\('day.missingLabels'/);
  const html = fs.readFileSync('frontend/index.html', 'utf8');
  assert.match(html, /id="toast-info"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-atomic="true"/);
  assert.match(html, /id="toast-error"[^>]*role="alert"[^>]*aria-live="assertive"[^>]*aria-atomic="true"/);
  assert.match(source, /const err = await responseError\(res\);\s*showNote\(note, err\.message, 'error'\)/);
});
