// Language switching must rewrite live UI in place. These tests drive the real
// app.js functions with a small DOM that mirrors two behaviours the browser
// has and the buggy code depended on:
//   * assigning textContent drops every child node (this is what destroyed the
//     courier badge when the category label was translated), and
//   * an unhandled raw upstream error must never be swapped for catalog text.
// Raw API data is never translated; only app-owned text follows the language.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const definitions = source.slice(0, source.indexOf('// ---- Sidebar events ----'));
// setupMessage() sits after the auto-executing sidebar block, so it is loaded
// on its own alongside the definitions (the same slicing the print suite uses).
const setupSource = source.slice(
  source.indexOf('function setupMessage'),
  source.indexOf('\nasync function boot('),
);

class ClassList {
  constructor() { this.items = new Set(); }
  add(...names) { names.forEach(name => this.items.add(name)); }
  remove(...names) { names.forEach(name => this.items.delete(name)); }
  toggle(name, force) {
    const on = force === undefined ? !this.items.has(name) : Boolean(force);
    if (on) this.items.add(name); else this.items.delete(name);
    return on;
  }
  contains(name) { return this.items.has(name); }
}

class El {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.dataset = {};
    this.classList = new ClassList();
    this.listeners = {};
    this.parentNode = null;
    this.isConnected = true;
    this.disabled = false;
    this.checked = false;
    this.value = '';
    this.files = [];
    this.style = {};
    this._text = '';
    this._html = '';
  }

  get textContent() {
    return this.children.length ? this.children.map(child => child.textContent).join('') : this._text;
  }

  // Real DOM semantics: assigning textContent replaces every child node. This
  // is exactly why a badge child under a data-i18n node disappeared.
  set textContent(value) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._text = value === null || value === undefined ? '' : String(value);
  }

  get innerHTML() { return this._html; }

  set innerHTML(html) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._text = '';
    this._html = String(html);
    this.controls = new Map();
    for (const match of this._html.matchAll(/<\w+\b[^>]*\bid="([^"]+)"/g)) {
      const tag = match[0];
      const node = new El();
      node.disabled = /\bdisabled\b/.test(tag);
      node.checked = /\bchecked\b/.test(tag);
      const value = tag.match(/\bvalue="([^"]*)"/);
      if (value) node.value = value[1];
      this.controls.set('#' + match[1], node);
    }
    this.radios = [...this._html.matchAll(/<input\b[^>]*\bname="parcel-size"[^>]*>/g)].map(radio => {
      const node = new El('input');
      node.value = radio[0].match(/\bvalue="([^"]+)"/)[1];
      node.checked = /\bchecked\b/.test(radio[0]);
      return node;
    });
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name.startsWith('data-')) {
      this.dataset[name.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(value);
    }
  }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  hasAttribute(name) { return this.attributes.has(name); }
  removeAttribute(name) { this.attributes.delete(name); }

  appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
  dispatch(type, extra = {}) {
    const event = { target: this, preventDefault() {}, stopPropagation() {}, ...extra };
    const results = (this.listeners[type] || []).map(handler => handler(event));
    return results.length === 1 ? results[0] : results;
  }
  click() { return this.dispatch('click'); }

  remove() {
    if (this.parentNode) {
      const index = this.parentNode.children.indexOf(this);
      if (index >= 0) this.parentNode.children.splice(index, 1);
    }
    this.parentNode = null;
    this.isConnected = false;
  }

  after(node) {
    const parent = this.parentNode;
    if (!parent) return;
    const index = parent.children.indexOf(this);
    parent.children.splice(index + 1, 0, node);
    node.parentNode = parent;
  }

  descendants() {
    const out = [];
    const walk = node => { for (const child of node.children) { out.push(child); walk(child); } };
    walk(this);
    return out;
  }

  querySelectorAll(selector) {
    if (selector === 'input[name="parcel-size"]') return this.radios || [];
    const nodes = this.descendants();
    if (selector.startsWith('.')) {
      const cls = selector.slice(1);
      return nodes.filter(node => node.classList.contains(cls));
    }
    const attribute = selector.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attribute) {
      const [, name, value] = attribute;
      return nodes.filter(node => node.hasAttribute(name) && (value === undefined || node.getAttribute(name) === value));
    }
    return [];
  }

  querySelector(selector) {
    if (selector.startsWith('#')) {
      this.controls = this.controls || new Map();
      if (!this.controls.has(selector)) this.controls.set(selector, new El());
      return this.controls.get(selector);
    }
    const found = this.querySelectorAll(selector)[0];
    if (found) return found;
    this._autos = this._autos || new Map();
    if (!this._autos.has(selector)) this._autos.set(selector, new El());
    return this._autos.get(selector);
  }

  focus() {}
  select() {}
}

function makeDocument(registry) {
  return {
    documentElement: {},
    getElementById: id => registry.get(id) || null,
    createElement: tag => new El(tag),
    querySelector: selector => registry.get('@' + selector) || null,
    querySelectorAll: () => [],
  };
}

function loadContext({ document: doc, extra = {} } = {}) {
  const context = vm.createContext({
    URLSearchParams, Intl, FormData, clearTimeout, setTimeout: () => 0,
    navigator: { clipboard: { writeText: async () => {} } },
    document: doc,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    ...extra,
  });
  vm.runInContext(definitions, context);
  return context;
}

// ---- Courier badge survives the category relabel ----

test('courier badge survives a language switch and the label still translates', () => {
  const body = new El('ul');
  const pendingItem = new El('li');
  body.appendChild(pendingItem);

  const counts = {};
  for (const key of ['pending', 'picking', 'packing', 'done']) counts[`count-${key}`] = new El();
  const registry = new Map(Object.entries(counts));
  registry.set('@[data-queue="pending"]', pendingItem);

  const context = loadContext({ document: makeDocument(registry) });
  context.testOrders = [
    { id: '1', status: 'pending', delivery_type: 'inpost_locker' },
    { id: '2', status: 'pending', delivery_type: 'inpost_locker' },
  ];
  vm.runInContext('state.orders = testOrders;', context);

  context.updateBadges();
  const subnav = body.children.find(child => child.id === 'courier-subnav');
  assert.ok(subnav, 'the courier sub-navigation is created');
  const li = subnav.children[0];
  assert.equal(li.children.length, 2, 'the item holds a label and a badge');

  const [label, badge] = li.children;
  assert.equal(label.getAttribute('data-i18n'), 'category.locker');
  assert.equal(label.textContent, 'Paczkomat InPost');
  assert.equal(badge.textContent, '2');
  assert.equal(li.getAttribute('data-i18n'), null, 'the key must not sit on the li');

  context.setLanguage('en', { root: body });
  assert.equal(label.textContent, 'InPost parcel locker', 'the category label is translated');
  assert.equal(li.children.length, 2, 'the badge child is not destroyed by the switch');
  assert.equal(li.children[1].textContent, '2', 'the badge keeps its count');
});

// ---- State banner ----

test('quarantine banner follows the language and survives dynamicText.clear()', () => {
  const banner = new El();
  const context = loadContext({ document: makeDocument(new Map([['state-banner', banner]])) });

  context.renderStateBanner({ quarantined: 3 });
  assert.equal(banner.textContent, '⚠ 3 rekordy pominięto — dane nie przechodzą walidacji.');

  // renderQueue() clears dynamicText on every view rebuild; the banner must not
  // be bound there or it would freeze after the first navigation.
  vm.runInContext('dynamicText.clear();', context);
  context.setLanguage('en');
  assert.equal(banner.textContent, '⚠ 3 records were skipped — they failed validation.');
});

test('banner fallback and backend detail follow the language without translating raw data', () => {
  const banner = new El();
  const context = loadContext({ document: makeDocument(new Map([['state-banner', banner]])) });

  context.renderStateBanner({ ok: false });
  assert.equal(banner.textContent, '⚠ Problem ze stanem aplikacji.');
  context.setLanguage('en');
  assert.equal(banner.textContent, '⚠ There is a problem with the application state.');

  context.renderStateBanner({ ok: false, message: 'Soubor je poškozený' });
  assert.equal(banner.textContent, '⚠ There is a problem with the application state. Soubor je poškozený');
  context.setLanguage('pl');
  assert.equal(banner.textContent, '⚠ Problem ze stanem aplikacji. Soubor je poškozený',
    'the backend detail is kept verbatim while the prefix switches');
});

// ---- Setup status line ----

test('setup status messages follow the language but raw errors stay verbatim', () => {
  const message = new El();
  const context = loadContext({ document: makeDocument(new Map([['setup-message', message]])) });
  vm.runInContext(setupSource, context);

  vm.runInContext("setupMessage(() => t('setup.tokenCopied'));", context);
  assert.equal(message.textContent, 'Token skopiowany. Zachowaj go w bezpiecznym miejscu.');
  context.setLanguage('en');
  assert.equal(message.textContent, 'Token copied. Keep it in a safe place.');

  vm.runInContext("setupMessage('Connection refused');", context);
  assert.equal(message.textContent, 'Connection refused');
  assert.equal(message.hasAttribute('data-i18n'), false, 'raw text detaches from the catalog');
  context.setLanguage('pl');
  assert.equal(message.textContent, 'Connection refused', 'raw errors are never translated');
});

// ---- Settings notes ----

function settingsContext() {
  const panel = new El();
  const context = loadContext({ document: makeDocument(new Map()) });
  context.testApi = async (path, options = {}) => {
    if (path === '/print/invoice-settings' && !options.method) {
      return { show_buyer_name: true, free_text: '' };
    }
    if (path === '/print/custom-doc/info') return { available: false };
    if (path === '/print/invoice-settings' && options.method === 'POST') {
      if (context.rejectInvoice) throw new Error('upstream down');
      return {};
    }
    return {};
  };
  vm.runInContext('api = testApi;', context);
  return { panel, context };
}

test('settings success note follows the language while a raw error does not', async () => {
  const { panel, context } = settingsContext();
  await context.renderSettingsDocuments(panel);
  const save = panel.querySelector('#invoice-settings-save');
  const note = panel.querySelector('#invoice-settings-note');

  await save.dispatch('click');
  assert.equal(note.textContent, '✓ Zapisano');
  context.setLanguage('en');
  assert.equal(note.textContent, '✓ Saved', 'the success note is re-rendered on switch');

  context.rejectInvoice = true;
  await save.dispatch('click');
  assert.equal(note.textContent, '✗ upstream down');
  context.setLanguage('pl');
  assert.equal(note.textContent, '✗ upstream down', 'a raw upstream error is never translated');
});

test('shipping success note follows the language', async () => {
  const panel = new El();
  const context = loadContext({ document: makeDocument(new Map()) });
  context.testApi = async (path, options = {}) => {
    if (path === '/print/shipment-settings' && !options.method) return { sender: {}, package: {} };
    return {};
  };
  vm.runInContext('api = testApi;', context);

  await context.renderSettingsShipping(panel);
  await panel.querySelector('#shipping-save').dispatch('click');
  const note = panel.querySelector('#shipping-note');
  assert.equal(note.textContent, '✓ Zapisano');
  context.setLanguage('en');
  assert.equal(note.textContent, '✓ Saved');
});

// ---- Pending label generation ----

test('a generating label keeps busy text, disabled state and form values across a switch', () => {
  const content = new El();
  const context = loadContext({ document: makeDocument(new Map([['content', content]])) });
  vm.runInContext('openPdf = () => new Promise(() => {});', context);

  context.testOrders = [{
    id: 'o1', status: 'packing', delivery_type: 'inpost_locker', courier: 'Allegro Paczkomaty InPost',
    buyer_name: 'Buyer', buyer_address: 'Address', allegro_id: 'X', items: [{ name: 'P', quantity: 1 }],
    parcel_size: 'B', shipment_id: null, tracking_number: null,
  }];
  vm.runInContext(`
    state.shipmentSettings = { package: { length: 30, width: 20, height: 15, weight: 1 } };
    state.orders = testOrders;
    state.packingQueue = testOrders;
    state.packingIndex = 0;
  `, context);
  context.renderPackingCard(content);

  const view = content.querySelector('#packing-view');
  const radios = view.querySelectorAll('input[name="parcel-size"]');
  assert.equal(radios.length, 3, 'the parcel-size options are rendered');
  const button = view.querySelector('#btn-label');
  assert.equal(button.disabled, false);

  button.dispatch('click'); // never resolves: the label stays "generating"
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, 'Generowanie etykiety…');

  context.setLanguage('en', { root: view });
  assert.equal(button.disabled, true, 'the button stays disabled while generating');
  assert.equal(button.textContent, 'Generating label…', 'the busy text follows the language');
  assert.equal(radios.find(radio => radio.checked).value, 'B', 'the parcel-size choice is untouched');
});
