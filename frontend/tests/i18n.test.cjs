// Frontend language support: an explicit Polish/English catalog, Polish by
// default, remembered selection, and the Accept-Language contract with the
// backend. These tests load the real app.js definitions in a VM the same way
// the other frontend suites do.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const definitions = source.slice(0, source.indexOf('// ---- Sidebar events ----'));

function fakeStorage(initial = {}, options = {}) {
  const data = new Map(Object.entries(initial));
  return {
    _data: data,
    getItem(key) {
      if (options.throwOnGet) throw new Error('storage blocked');
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      if (options.throwOnSet) throw new Error('storage blocked');
      data.set(key, String(value));
    },
    removeItem(key) { data.delete(key); },
  };
}

function fakeNode(attributes = {}) {
  const attrs = new Map(Object.entries(attributes));
  return {
    title: '',
    placeholder: '',
    textContent: '',
    value: '',
    checked: false,
    disabled: false,
    getAttribute: name => (attrs.has(name) ? attrs.get(name) : null),
    setAttribute: (name, value) => { attrs.set(name, String(value)); },
    removeAttribute: name => { attrs.delete(name); },
    hasAttribute: name => attrs.has(name),
  };
}

function root(selectorMap = {}) {
  return {
    querySelectorAll(selector) { return selectorMap[selector] || []; },
  };
}

function loadApp({ storage, navigator, document, fetchImpl } = {}) {
  const context = vm.createContext({
    URLSearchParams, setTimeout, clearTimeout, Headers, Intl,
    navigator: navigator || {},
    document: document || { getElementById: () => null, querySelectorAll: () => [], documentElement: null },
    fetch: fetchImpl,
    localStorage: storage,
  });
  vm.runInContext(definitions, context);
  return context;
}

test('translation catalog defines the same keys for Polish and English', () => {
  const context = loadApp({ storage: fakeStorage() });
  const pl = vm.runInContext('Object.keys(MESSAGES.pl).sort()', context);
  const en = vm.runInContext('Object.keys(MESSAGES.en).sort()', context);
  assert.ok(pl.length > 0, 'catalog must not be empty');
  assert.deepEqual(en, pl, 'English catalog must mirror the Polish keys');

  const kinds = lang => vm.runInContext(
    `JSON.stringify(Object.fromEntries(Object.entries(MESSAGES.${lang}).map(([k, v]) => [k, Array.isArray(v) ? 'array' : typeof v])))`,
    context,
  );
  assert.equal(kinds('en'), kinds('pl'), 'value kinds must match across languages');

  const empty = vm.runInContext(
    `JSON.stringify(Object.entries(MESSAGES.pl).concat(Object.entries(MESSAGES.en)).filter(([k, v]) => v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0).map(([k]) => k))`,
    context,
  );
  assert.equal(empty, '[]', 'plural entries must define at least one form');
});

test('default language is Polish even when the browser prefers English', () => {
  const context = loadApp({
    storage: fakeStorage(),
    navigator: { language: 'en-US', languages: ['en-US', 'en'] },
  });
  assert.equal(context.getLanguage(), 'pl');
  assert.equal(context.t('nav.settings'), 'Ustawienia');
  assert.equal(context.t('nav.sync'), 'Pobierz zamówienia');
});

test('setLanguage switches messages and remembers the choice', () => {
  const storage = fakeStorage();
  const context = loadApp({ storage });
  assert.equal(context.setLanguage('en'), true);
  assert.equal(context.getLanguage(), 'en');
  assert.equal(context.t('nav.settings'), 'Settings');
  assert.equal(storage._data.get('weles.lang'), 'en');
  assert.equal(context.setLanguage('pl'), true);
  assert.equal(storage._data.get('weles.lang'), 'pl');
});

test('a remembered language is applied on start', () => {
  const context = loadApp({ storage: fakeStorage({ 'weles.lang': 'en' }) });
  assert.equal(context.getLanguage(), 'en');
  assert.equal(context.t('nav.settings'), 'Settings');
});

test('an unsupported stored language falls back to Polish', () => {
  const context = loadApp({ storage: fakeStorage({ 'weles.lang': 'de' }) });
  assert.equal(context.getLanguage(), 'pl');
});

test('setLanguage rejects unsupported codes without changing language', () => {
  const context = loadApp({ storage: fakeStorage() });
  assert.equal(context.setLanguage('fr'), false);
  assert.equal(context.getLanguage(), 'pl');
});

test('storage failures never break language selection', () => {
  const storage = fakeStorage({}, { throwOnGet: true, throwOnSet: true });
  const context = loadApp({ storage });
  assert.equal(context.getLanguage(), 'pl');
  assert.equal(context.setLanguage('en'), true);
  assert.equal(context.getLanguage(), 'en');
  assert.equal(context.t('nav.settings'), 'Settings');
});

test('plural forms follow Polish and English rules', () => {
  const context = loadApp({ storage: fakeStorage() });
  assert.equal(context.t('unit.order', { n: 1 }), 'zamówienie');
  assert.equal(context.t('unit.order', { n: 2 }), 'zamówienia');
  assert.equal(context.t('unit.order', { n: 5 }), 'zamówień');
  assert.equal(context.t('unit.order', { n: 22 }), 'zamówienia');
  context.setLanguage('en');
  assert.equal(context.t('unit.order', { n: 1 }), 'order');
  assert.equal(context.t('unit.order', { n: 3 }), 'orders');
});

test('every API request sends the selected language as Accept-Language', async () => {
  const seen = [];
  const context = loadApp({
    storage: fakeStorage(),
    fetchImpl: async (url, options) => {
      seen.push({ url, accept: options.headers.get('Accept-Language') });
      return { status: 200, ok: true, headers: { get: () => 'application/json' } };
    },
  });
  await context.apiFetch('/orders/');
  await context.apiFetch('/setup', { method: 'POST' });
  context.setLanguage('en');
  await context.apiFetch('/print/orders/one/label?size=A');
  await context.apiFetch('/orders/auth/url');
  assert.deepEqual(seen.map(s => s.accept), ['pl', 'pl', 'en', 'en']);
  assert.deepEqual(seen.map(s => s.url), [
    '/api/orders/', '/api/setup', '/api/print/orders/one/label?size=A', '/api/orders/auth/url',
  ]);
});

test('document language follows the selected language', () => {
  const document = { documentElement: {}, getElementById: () => null, querySelectorAll: () => [] };
  const context = loadApp({ storage: fakeStorage(), document });
  context.applyDocumentLanguage();
  assert.equal(document.documentElement.lang, 'pl');
  context.setLanguage('en');
  assert.equal(document.documentElement.lang, 'en');
});

test('switching language preserves queue state without re-rendering or refetching', () => {
  const fetched = [];
  const context = loadApp({
    storage: fakeStorage(),
    fetchImpl: async url => { fetched.push(url); return { status: 200, ok: true, headers: { get: () => null } }; },
  });
  vm.runInContext(`
    globalThis.__renderCalls = 0;
    renderQueue = function () { globalThis.__renderCalls++; };
    state.selectedOrderIds = new Set(['a', 'b']);
    state.packingIndex = 2;
    state.packingQueue = [{ id: 'x' }, { id: 'y' }, { id: 'z' }];
  `, context);
  context.setLanguage('en');
  assert.equal(vm.runInContext('state.packingIndex', context), 2);
  assert.equal(vm.runInContext('Array.from(state.selectedOrderIds).join(",")', context), 'a,b');
  assert.equal(vm.runInContext('globalThis.__renderCalls', context), 0);
  assert.equal(fetched.length, 0);
});

test('applying a language updates labelled text without touching field values', () => {
  const label = fakeNode({ 'data-i18n': 'nav.settings' });
  const input = fakeNode();
  input.value = '42';
  input.checked = true;
  const container = root({ '[data-i18n]': [label] });
  const context = loadApp({ storage: fakeStorage() });
  label.textContent = context.t('nav.settings');
  context.setLanguage('en', { root: container });
  assert.equal(label.textContent, 'Settings');
  assert.equal(input.value, '42');
  assert.equal(input.checked, true);
});

test('numbers and dates use the selected locale', () => {
  const context = loadApp({ storage: fakeStorage() });
  assert.equal(context.formatNumber(1234.5), '1234,5');
  assert.match(context.formatDateTime(Date.UTC(2026, 1, 1, 14, 30)), /^\d{1,2}\.\d{2}\.\d{4}/);
  context.setLanguage('en');
  assert.equal(context.formatNumber(1234.5), '1,234.5');
  assert.match(context.formatDateTime(Date.UTC(2026, 1, 1, 14, 30)), /^\d{2}\/\d{2}\/\d{4}/);
});

test('category labels translate app-owned names but never carrier data', () => {
  const context = loadApp({ storage: fakeStorage() });
  assert.equal(context.categoryLabel('Inny'), 'Inny');
  assert.equal(context.categoryLabel('Paczkomat InPost'), 'Paczkomat InPost');
  assert.equal(context.categoryLabel('Kurier InPost'), 'Kurier InPost');
  context.setLanguage('en');
  assert.equal(context.categoryLabel('Inny'), 'Other');
  assert.equal(context.categoryLabel('Kurier InPost'), 'Kurier InPost');
  assert.notEqual(context.categoryLabel('Paczkomat InPost'), 'Paczkomat InPost');
});

test('every translation key referenced by the markup and scripts exists in the catalog', () => {
  const context = loadApp({ storage: fakeStorage() });
  const html = fs.readFileSync('frontend/index.html', 'utf8');
  const keys = new Set();
  const add = text => {
    // Only literal keys: skip dynamic `data-i18n="${key}"` templates.
    const record = raw => { if (/^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$/.test(raw)) keys.add(raw); };
    for (const m of text.matchAll(/data-i18n(?:-html|-title|-placeholder|-aria)?="([^"]+)"/g)) record(m[1]);
    for (const m of text.matchAll(/\bt\(\s*'([^']+)'/g)) record(m[1]);
    for (const m of text.matchAll(/setText\([^,]+,\s*'([^']+)'/g)) record(m[1]);
  };
  add(html);
  add(source);
  assert.ok(keys.size > 50, 'the scan should find the catalog usages');
  const missing = [];
  for (const key of keys) {
    if (vm.runInContext(`MESSAGES.pl[${JSON.stringify(key)}] === undefined`, context)) missing.push(`pl:${key}`);
    if (vm.runInContext(`MESSAGES.en[${JSON.stringify(key)}] === undefined`, context)) missing.push(`en:${key}`);
  }
  assert.deepEqual(missing, [], 'referenced keys must be defined in both languages');
});

test('language selectors reflect the active language', () => {
  const select = fakeNode();
  const container = root({ '[data-lang-select]': [select] });
  const context = loadApp({ storage: fakeStorage() });
  context.syncLanguageControls(container);
  assert.equal(select.value, 'pl');
  context.setLanguage('en');
  context.syncLanguageControls(container);
  assert.equal(select.value, 'en');
});
