// Document editor (block editor) frontend tests. They drive the real
// document-editor.js against a small DOM that mirrors the browser semantics the
// editor relies on (children, classList, data attributes, listeners, files).
// app.js definitions are loaded first so the editor can use t(), setText(),
// bindDynamicText(), api() and openPdf() exactly as in the browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const definitions = source.slice(0, source.indexOf('// ---- Sidebar events ----'));
const editorSource = fs.readFileSync('frontend/static/document-editor.js', 'utf8');

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

function matchOne(node, selector) {
  let rest = selector.trim();
  if (!rest) return false;
  const attrs = [];
  const attrRe = /\[([\w-]+)(?:=("([^"]*)"|'([^']*)'))?\]/g;
  let match;
  while ((match = attrRe.exec(rest))) {
    attrs.push([match[1], match[3] !== undefined ? match[3] : match[4] !== undefined ? match[4] : null]);
  }
  rest = rest.replace(attrRe, '');
  const idMatch = rest.match(/#([\w-]+)/);
  if (idMatch) {
    if (node.getAttribute('id') !== idMatch[1]) return false;
    rest = rest.replace(/#[\w-]+/, '');
  }
  for (const cls of rest.matchAll(/\.([\w-]+)/g)) {
    if (!node.classList.contains(cls[1])) return false;
  }
  rest = rest.replace(/\.[\w-]+/g, '').trim();
  if (rest && node.tagName !== rest.toUpperCase()) return false;
  for (const [name, value] of attrs) {
    if (value === null) { if (!node.hasAttribute(name)) return false; }
    else if (node.getAttribute(name) !== value) return false;
  }
  return true;
}

function matches(node, selector) {
  return selector.split(',').map(part => part.trim()).filter(Boolean).some(part => {
    const chain = part.split(/\s+(?![^\[]*\])/);
    if (!matchOne(node, chain.pop())) return false;
    let ancestor = node.parentNode;
    while (chain.length) {
      const expected = chain.pop();
      while (ancestor && !matchOne(ancestor, expected)) ancestor = ancestor.parentNode;
      if (!ancestor) return false;
      ancestor = ancestor.parentNode;
    }
    return true;
  });
}

class Dom {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.classList = new ClassList();
    this.listeners = {};
    this.style = {};
    this.dataset = {};
    this.isConnected = false;
    this.disabled = false;
    this.checked = false;
    this.value = '';
    this.type = '';
    this.accept = '';
    this.files = [];
    this.selectionStart = 0;
    this.selectionEnd = 0;
    this._text = '';
  }
  get textContent() {
    return this.children.length ? this.children.map(child => child.textContent).join('') : this._text;
  }
  set textContent(value) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._text = value === null || value === undefined ? '' : String(value);
  }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name.startsWith('data-')) {
      this.dataset[name.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(value);
    }
  }
  removeAttribute(name) { this.attributes.delete(name); }
  hasAttribute(name) { return this.attributes.has(name); }
  appendChild(node) { node.parentNode = this; node.isConnected = true; this.children.push(node); return node; }
  removeChild(node) {
    const index = this.children.indexOf(node);
    if (index >= 0) this.children.splice(index, 1);
    node.parentNode = null;
    node.isConnected = false;
    return node;
  }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); this.isConnected = false; }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
  dispatch(type, extra = {}) {
    const event = { target: this, preventDefault() {}, stopPropagation() {}, ...extra };
    const handlers = this.listeners[type] || [];
    const results = handlers.map(handler => handler(event));
    return results.length === 1 ? results[0] : results;
  }
  click() { return this.dispatch('click'); }
  focus() {}
  getBoundingClientRect() { return { width: 420, height: 594 }; }
  setPointerCapture(id) { this.capturedPointer = id; }
  select() {}
  descendants() {
    const out = [];
    const walk = node => { for (const child of node.children) { out.push(child); walk(child); } };
    walk(this);
    return out;
  }
  querySelectorAll(selector) { return this.descendants().filter(node => matches(node, selector)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function makeDocument() {
  return {
    documentElement: {},
    createElement: tag => new Dom(tag),
    getElementById: () => null,
    querySelectorAll: () => [],
    querySelector: () => null,
  };
}

function settingsFixture(overrides = {}) {
  return {
    version: 1,
    templates: [{ id: 'default', name: 'Custom document', blocks: [] }],
    profiles: { default: { source: 'upload', active_template_id: 'default' } },
    ...overrides,
  };
}

function loadEditor({ orders = [], windowSpy, FileReader: reader } = {}) {
  const document = makeDocument();
  const context = vm.createContext({
    document,
    URLSearchParams, Intl, setTimeout: (fn, ms) => { const timer = setTimeout(fn, ms); timer.unref(); return timer; }, clearTimeout, console,
    navigator: {},
    window: windowSpy || { confirm: () => true, open: () => ({ location: { replace() {} }, close() {} }) },
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
    FileReader: reader,
  });
  vm.runInContext(definitions, context);
  vm.runInContext(editorSource, context);
  context.testOrders = orders;
  context.onSavedCalls = [];
  context.testApi = (path, options) => new Promise((resolve, reject) => {
    context.apiCalls.push({ path, options, resolve, reject });
  });
  context.apiCalls = [];
  vm.runInContext('api = testApi;', context);
  return context;
}

function mount(context, settings, orders = []) {
  context.testContainer = new Dom();
  context.testSettings = settings;
  context.testMountOrders = orders;
  vm.runInContext(`
    DocumentEditor.mount(testContainer, {
      settings: testSettings,
      orders: testMountOrders,
      onSaved: function (saved) { onSavedCalls.push(saved); },
    });
  `, context);
  return context.testContainer;
}

function blocks(container) { return container.querySelectorAll('.editor-block'); }

test('renders source options and the active template name', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({ templates: [{ id: 'default', name: 'Weles pack slip', blocks: [] }] }));
  assert.ok(container.querySelector('[data-i18n="doc.source"]'), 'source label uses the catalog');
  const sourceInputs = container.querySelectorAll('input[name="doc-source"]');
  assert.equal(sourceInputs.length, 2);
  assert.equal(sourceInputs.find(input => input.checked).value, 'upload');
  assert.equal(container.querySelector('.editor-template-name').value, 'Weles pack slip');
  assert.equal(container.querySelector('input[name="doc-source"][value="upload"]').value, 'upload');
});

test('adding a block uses normalized defaults', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture());
  const type = container.querySelector('.editor-block-type');
  type.value = 'text';
  container.querySelector('.editor-add-block').click();
  const rendered = blocks(container);
  assert.equal(rendered.length, 1);
  assert.equal(rendered[0].getAttribute('data-type'), 'text');
  const draft = JSON.parse(vm.runInContext('JSON.stringify(DocumentEditor.draft.blocks[0])', context));
  assert.deepEqual(draft, { type: 'text', text: '', align: 'left', size: 12, show_prices: false, image: '', bold: false, x: 18, y: 18, w: 174, h: 24 });
});

test('moving blocks up and down reorders the draft', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'heading', text: 'A' }, { type: 'text', text: 'B' }] }],
  }));
  assert.deepEqual(blocks(container).map(node => node.getAttribute('data-type')), ['heading', 'text']);
  blocks(container)[0].querySelector('.editor-block-down').click();
  assert.deepEqual(blocks(container).map(node => node.getAttribute('data-type')), ['text', 'heading']);
  blocks(container)[1].querySelector('.editor-block-up').click();
  assert.deepEqual(blocks(container).map(node => node.getAttribute('data-type')), ['heading', 'text']);
  const draft = vm.runInContext('DocumentEditor.draft', context);
  assert.deepEqual(draft.blocks.map(block => block.type), ['heading', 'text']);
});

test('removing a block drops it from the draft', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'heading', text: 'A' }, { type: 'text', text: 'B' }] }],
  }));
  blocks(container)[0].querySelector('.editor-block-remove').click();
  assert.deepEqual(blocks(container).map(node => node.getAttribute('data-type')), ['text']);
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks.length', context), 1);
});

test('saving posts the source and full template and adopts the normalized response', async () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({ profiles: { default: { source: 'template', active_template_id: 'default' } } }));
  const type = container.querySelector('.editor-block-type');
  type.value = 'text';
  container.querySelector('.editor-add-block').click();
  const textarea = blocks(container)[0].querySelector('.editor-block-text');
  textarea.value = 'Hello';
  textarea.dispatch('input');
  container.querySelector('.editor-template-name').value = 'My slip';
  container.querySelector('.editor-template-name').dispatch('input');
  container.querySelector('.editor-save').click();

  const call = context.apiCalls[0];
  assert.equal(call.path, '/print/document-settings');
  assert.equal(call.options.method, 'POST');
  const body = JSON.parse(call.options.body);
  assert.equal(body.source, 'template');
  assert.deepEqual(body.template, {
    id: 'default', name: 'My slip',
    blocks: [{ type: 'text', text: 'Hello', align: 'left', size: 12, show_prices: false, image: '', bold: false, x: 18, y: 18, w: 174, h: 24 }],
  });

  const normalized = settingsFixture({
    templates: [{ id: 'default', name: 'My slip', blocks: [{ type: 'text', text: 'Hello', align: 'left', size: 12, show_prices: false, image: '' }] }],
    profiles: { default: { source: 'template', active_template_id: 'default' } },
  });
  call.resolve(normalized);
  await vm.runInContext('DocumentEditor.lastSavePromise', context);
  assert.equal(context.onSavedCalls.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(context.onSavedCalls[0])), normalized);
  assert.equal(vm.runInContext('DocumentEditor.draft.status', context), 'saved');
  assert.equal(container.querySelector('.editor-status').textContent, 'Zapisano');
});

test('preview posts the unsaved draft with the order id', async () => {
  const context = loadEditor();
  const order = { id: 'order-1' };
  const container = mount(context, settingsFixture({ profiles: { default: { source: 'template', active_template_id: 'default' } } }), [order]);
  const type = container.querySelector('.editor-block-type');
  type.value = 'text';
  container.querySelector('.editor-add-block').click();
  const textarea = blocks(container)[0].querySelector('.editor-block-text');
  textarea.value = 'Draft only';
  textarea.dispatch('input');

  let previewCall = null;
  context.apiFetch = async (path, options) => {
    previewCall = { path, options };
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, blob: async () => ({}) };
  };
  await container.querySelector('.editor-preview').click();

  assert.equal(previewCall.path, '/print/document-preview');
  assert.equal(previewCall.options.method, 'POST');
  const body = JSON.parse(previewCall.options.body);
  assert.equal(body.order_id, 'order-1');
  assert.equal(body.template.blocks[0].text, 'Draft only');
  // The request is only a preview: no save was issued.
  assert.equal(context.apiCalls.length, 0);
});

test('preview opens the print window before the request', async () => {
  const steps = [];
  const context = loadEditor({
    windowSpy: { open() { steps.push('open'); return { location: { replace: () => steps.push('navigate') }, close() {} }; } },
  });
  const container = mount(context, settingsFixture({ profiles: { default: { source: 'template', active_template_id: 'default' } } }), [{ id: 'o1' }]);
  const type = container.querySelector('.editor-block-type');
  type.value = 'customer';
  container.querySelector('.editor-add-block').click();
  context.apiFetch = async () => { steps.push('fetch'); return { ok: true, status: 200, headers: { get: () => 'application/json' }, blob: async () => ({}) }; };
  await container.querySelector('.editor-preview').click();
  assert.deepEqual(steps, ['open', 'fetch', 'navigate']);
});

test('an empty designed template cannot be saved or previewed', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({ profiles: { default: { source: 'template', active_template_id: 'default' } } }), [{ id: 'o1' }]);
  assert.equal(container.querySelector('.editor-save').disabled, true);
  assert.equal(container.querySelector('.editor-preview').disabled, true);
  assert.equal(container.querySelector('.editor-preview-note').textContent, 'Szablon jest pusty — dodaj przynajmniej jeden blok z treścią.');
});

test('preview is disabled with an explanation when there are no orders', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture(), []);
  assert.equal(container.querySelector('.editor-preview').disabled, true);
  assert.equal(container.querySelector('.editor-save').disabled, false);
  assert.match(container.querySelector('.editor-preview-note').textContent, /Brak zamówień/);
});

test('an edited draft survives a remount', () => {
  const context = loadEditor();
  const settings = settingsFixture({ profiles: { default: { source: 'upload', active_template_id: 'default' } } });
  mount(context, settings);
  const container = context.testContainer;
  const type = container.querySelector('.editor-block-type');
  type.value = 'heading';
  container.querySelector('.editor-add-block').click();
  const textarea = blocks(container)[0].querySelector('.editor-block-text');
  textarea.value = 'Saved draft';
  textarea.dispatch('input');
  container.querySelector('.editor-template-name').value = 'Draft name';
  container.querySelector('.editor-template-name').dispatch('input');

  // Simulate navigation away and back: a fresh mount with the persisted settings.
  mount(context, settingsFixture({ profiles: { default: { source: 'upload', active_template_id: 'default' } } }));
  const again = context.testContainer;
  assert.equal(again.querySelector('.editor-template-name').value, 'Draft name');
  const draft = vm.runInContext('DocumentEditor.draft', context);
  assert.equal(draft.blocks[0].text, 'Saved draft');
  assert.equal(draft.status, 'dirty');
});

test('a pending save is not duplicated across a remount', async () => {
  const context = loadEditor();
  const settings = settingsFixture({ profiles: { default: { source: 'upload', active_template_id: 'default' } } });
  mount(context, settings);
  context.testContainer.querySelector('.editor-save').click();
  assert.equal(context.apiCalls.length, 1);
  assert.equal(vm.runInContext('DocumentEditor.draft.saving', context), true);

  mount(context, settingsFixture({ profiles: { default: { source: 'upload', active_template_id: 'default' } } }));
  const container = context.testContainer;
  assert.equal(container.querySelector('.editor-save').disabled, true, 'no second save may start');
  assert.equal(container.querySelector('.editor-status').textContent, 'Zapisywanie…');
  assert.equal(context.apiCalls.length, 1);

  context.apiCalls[0].resolve(settingsFixture({ profiles: { default: { source: 'upload', active_template_id: 'default' } } }));
  await vm.runInContext('DocumentEditor.lastSavePromise', context);
  assert.equal(container.querySelector('.editor-status').textContent, 'Zapisano');
  assert.equal(container.querySelector('.editor-save').disabled, false);
});

test('language switching translates editor labels but never user text', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture());
  const type = container.querySelector('.editor-block-type');
  type.value = 'text';
  container.querySelector('.editor-add-block').click();
  const textarea = blocks(container)[0].querySelector('.editor-block-text');
  textarea.value = 'Nie tłumacz tego';
  textarea.dispatch('input');
  container.querySelector('.editor-template-name').value = 'Moja nazwa';
  container.querySelector('.editor-template-name').dispatch('input');
  assert.equal(container.querySelector('.editor-status').textContent, 'Niezapisane zmiany');

  context.setLanguage('en', { root: container });

  assert.equal(container.querySelector('.editor-status').textContent, 'Unsaved changes');
  assert.equal(textarea.value, 'Nie tłumacz tego', 'user text stays verbatim');
  assert.equal(container.querySelector('.editor-template-name').value, 'Moja nazwa');
  assert.equal(container.querySelector('.editor-add-block').textContent, 'Add block');
});

test('SVG logos are rejected before encoding', () => {
  const context = loadEditor({ FileReader: class { readAsDataURL() { throw new Error('must not encode'); } } });
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'logo', text: '', align: 'left', size: 12, show_prices: false, image: '' }] }],
  }));
  const input = blocks(container)[0].querySelector('.editor-logo-file');
  input.files = [{ type: 'image/svg+xml', size: 10, name: 'x.svg' }];
  input.dispatch('change');
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks[0].image', context), '');
  assert.match(container.querySelector('.editor-status').textContent, /SVG/);
});

test('oversize logos are rejected before encoding', () => {
  const context = loadEditor({ FileReader: class { readAsDataURL() { throw new Error('must not encode'); } } });
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'logo', text: '', align: 'left', size: 12, show_prices: false, image: '' }] }],
  }));
  const input = blocks(container)[0].querySelector('.editor-logo-file');
  input.files = [{ type: 'image/png', size: 3 * 1024 * 1024, name: 'big.png' }];
  input.dispatch('change');
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks[0].image', context), '');
  assert.match(container.querySelector('.editor-status').textContent, /2 MB/);
});

test('a PNG logo is encoded into a data URI', () => {
  const dataUri = 'data:image/png;base64,iVBORw0KGgo=';
  const context = loadEditor({
    FileReader: class {
      readAsDataURL(file) { this.result = file.result; this.onload(); }
    },
  });
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'logo', text: '', align: 'left', size: 12, show_prices: false, image: '' }] }],
  }));
  const input = blocks(container)[0].querySelector('.editor-logo-file');
  input.files = [{ type: 'image/png', size: 128, name: 'logo.png', result: dataUri }];
  input.dispatch('change');
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks[0].image', context), dataUri);
});

test('token buttons insert the placeholder at the cursor', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'text', text: 'Hi ', align: 'left', size: 12, show_prices: false, image: '' }] }],
  }));
  const block = blocks(container)[0];
  const textarea = block.querySelector('.editor-block-text');
  textarea.value = 'Hi ';
  textarea.selectionStart = 3;
  textarea.selectionEnd = 3;
  block.querySelector('.editor-token[data-token="buyer_name"]').click();
  assert.equal(textarea.value, 'Hi {{buyer_name}}');
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks[0].text', context), 'Hi {{buyer_name}}');
});

test('a template whose combined logo payload is too large cannot be saved', () => {
  const big = 'data:image/png;base64,' + 'A'.repeat(2_600_000);
  const context = loadEditor();
  const container = mount(context, settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [
      { type: 'logo', text: '', align: 'left', size: 12, show_prices: false, image: big },
      { type: 'logo', text: '', align: 'left', size: 12, show_prices: false, image: big },
    ] }],
  }), [{ id: 'o1' }]);
  assert.equal(container.querySelector('.editor-save').disabled, true);
  assert.match(container.querySelector('.editor-preview-note').textContent, /2 MB/);
  container.querySelector('.editor-save').click();
  assert.equal(context.apiCalls.length, 0, 'the request is blocked client-side');
});

test('a server validation rejection preserves the draft', async () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture());
  const type = container.querySelector('.editor-block-type');
  type.value = 'text';
  container.querySelector('.editor-add-block').click();
  const textarea = blocks(container)[0].querySelector('.editor-block-text');
  textarea.value = 'Keep me';
  textarea.dispatch('input');
  container.querySelector('.editor-save').click();
  context.apiCalls[0].reject(new Error('Nieprawidłowe pola dokumentu'));
  await vm.runInContext('DocumentEditor.lastSavePromise', context);
  assert.equal(vm.runInContext('DocumentEditor.draft.blocks[0].text', context), 'Keep me');
  assert.match(container.querySelector('.editor-status').textContent, /Nieprawidłowe pola dokumentu/);
});

test('empty drafts cannot be previewed even when upload is selected', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture(), [{id:'first'}]);
  assert.equal(container.querySelector('.editor-preview').disabled, true);
  assert.equal(container.querySelector('.editor-save').disabled, false);
});

test('token insertion never truncates a placeholder at the text limit', () => {
  const context = loadEditor();
  const container = mount(context, textSettings('x'.repeat(4000)));
  const textarea = container.querySelector('.editor-block-text');
  textarea.selectionStart = textarea.selectionEnd = 4000;
  container.querySelector('.editor-token[data-token="buyer_name"]').click();
  assert.equal(textarea.value, 'x'.repeat(4000));
  assert.equal(context.DocumentEditor.draft.blocks[0].text, textarea.value);
});

test('logo status follows language changes in place', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({templates:[{id:'default',name:'T',blocks:[{type:'logo',image:'data:image/png;base64,iVBORw0KGgo='}]}]}));
  context.setLanguage('en', {root:container});
  assert.equal(container.querySelector('.editor-logo-name').textContent, 'Logo selected');
});

test('editor controls and icon buttons have localized accessible labels', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({templates:[{id:'default',name:'T',blocks:[{type:'text',text:'Hi'},{type:'logo'}]}]}));
  const controls = ['.editor-block-text', '.editor-block-align', '.editor-block-size', '.editor-logo-file', '.editor-block-type', '.editor-block-remove'];
  controls.forEach(selector => assert.ok(container.querySelector(selector).getAttribute('aria-label'), selector));
  assert.equal(container.querySelector('.editor-block-remove').getAttribute('aria-label'), 'Usuń blok');
  context.setLanguage('en', {root:container});
  assert.equal(container.querySelector('.editor-block-remove').getAttribute('aria-label'), 'Remove block');
  assert.equal(container.querySelector('.editor-block-align').getAttribute('aria-label'), 'Alignment');
});

test('local validation messages translate without claiming a save failed', () => {
  const context = loadEditor();
  const container = mount(context, settingsFixture({templates:[{id:'default',name:'T',blocks:[{type:'logo'}]}]}));
  const input = container.querySelector('.editor-logo-file');
  input.files = [{type:'image/svg+xml',size:10}];
  input.dispatch('change');
  context.setLanguage('en', {root:container});
  assert.equal(container.querySelector('.editor-status').textContent, 'Error: SVG is not supported. Use a PNG or JPEG file.');
});

function textSettings(text = 'First') {
  return settingsFixture({
    templates: [{ id: 'default', name: 'T', blocks: [{ type: 'text', text }] }],
    profiles: { default: { source: 'template', active_template_id: 'default' } },
  });
}

test('editing a block after a successful save updates the next payload', async () => {
  const context = loadEditor();
  const container = mount(context, textSettings());
  container.querySelector('.editor-save').click();
  context.apiCalls[0].resolve(textSettings());
  await context.DocumentEditor.lastSavePromise;
  const textarea = container.querySelector('.editor-block-text');
  textarea.value = 'Second';
  textarea.dispatch('input');
  container.querySelector('.editor-save').click();
  assert.equal(JSON.parse(context.apiCalls[1].options.body).template.blocks[0].text, 'Second');
  context.apiCalls[1].resolve(textSettings('Second'));
  await context.DocumentEditor.lastSavePromise;
});

test('edits made during a pending save survive its response as unsaved changes', async () => {
  const context = loadEditor();
  const container = mount(context, textSettings());
  container.querySelector('.editor-save').click();
  const textarea = container.querySelector('.editor-block-text');
  textarea.value = 'Typed while saving';
  textarea.dispatch('input');
  context.apiCalls[0].resolve(textSettings());
  await context.DocumentEditor.lastSavePromise;
  assert.equal(context.DocumentEditor.draft.blocks[0].text, 'Typed while saving');
  assert.equal(context.DocumentEditor.draft.status, 'dirty');
});

test('preview uses the chosen order and preserves the choice across block redraws', async () => {
  const context = loadEditor();
  const orders = [{id:'first', buyer_name:'Anna'}, {id:'second', buyer_name:'Jan'}];
  const container = mount(context, textSettings(), orders);
  const select = container.querySelector('.editor-preview-order');
  assert.ok(select, 'preview has an order selector');
  select.value = 'second';
  select.dispatch('change');
  container.querySelector('.editor-add-block').click();
  assert.equal(container.querySelector('.editor-preview-order').value, 'second');
  let call;
  context.apiFetch = async (path, options) => {
    call = {path, options};
    return {ok:true, blob:async()=>({})};
  };
  await container.querySelector('.editor-preview').click();
  assert.equal(JSON.parse(call.options.body).order_id, 'second');
});

test('legacy layout migrates exact mm defaults and heading bold', () => {
  const context = loadEditor();
  mount(context, settingsFixture({ templates: [{ id: 'default', name: 'T', blocks: ['heading', 'text', 'customer', 'items', 'logo', 'placeholder', 'line'].map(type => ({type})) }] }));
  const geometry = JSON.parse(JSON.stringify(context.DocumentEditor.draft.blocks)).map(b => [b.x, b.y, b.w, b.h, b.bold]);
  assert.deepEqual(geometry, [[18,18,174,18,true],[18,42,174,24,false],[18,72,174,30,false],[18,108,174,90,false],[18,204,174,35,false],[18,245,174,24,false],[18,275,174,1,false]]);
});

test('dotted and legacy fields resolve once as safe DOM text; unknown fields warn', () => {
  const context = loadEditor();
  const container = mount(context, textSettings('{{buyer.name}}|{{buyer_name}}|{{buyer.address}}|{{order.id}}|{{order_number}}|{{items}}|{{unknown.field}}|{{toString}}|{{__proto__}}'), [{id:'internal', allegro_id:'allegro', buyer_name:'<img onerror=x>{{courier}}', buyer_address:'A & B', courier:'SECRET', items:[{name:'<script>',quantity:2}]}]);
  const content = container.querySelector('.editor-canvas-content');
  assert.equal(content.textContent, '<img onerror=x>{{courier}}|<img onerror=x>{{courier}}|A & B|internal|allegro|<script> × 2|—|—|—');
  assert.equal(content.children.length, 0);
  assert.match(container.querySelector('.editor-warnings').textContent, /unknown.field/);
  context.setLanguage('en', {root:container});
  assert.match(container.querySelector('.editor-warnings').textContent, /Unknown placeholders/);
});

test('malformed placeholder blocks save and PDF; valid unknown remains savable', () => {
  const context = loadEditor();
  const container = mount(context, textSettings('{{bad-name}}'), [{id:'first'}]);
  assert.equal(container.querySelector('.editor-save').disabled, true);
  assert.equal(container.querySelector('.editor-preview').disabled, true);
  container.querySelector('.editor-save').click();
  assert.equal(context.apiCalls.length, 0);
  const text = container.querySelector('.editor-block-text'); text.value = '{{missing}}'; text.dispatch('input');
  assert.equal(container.querySelector('.editor-save').disabled, false);
});

test('geometry properties clamp to A4 bounds and update canvas immediately', () => {
  const context = loadEditor(); const container = mount(context, textSettings());
  const x = container.querySelector('.editor-geometry-x'); x.value = '999'; x.dispatch('input');
  const y = container.querySelector('.editor-geometry-y'); y.value = '-5'; y.dispatch('input');
  const h = container.querySelector('.editor-geometry-h'); h.value = '999'; h.dispatch('input');
  const block = context.DocumentEditor.draft.blocks[0];
  assert.deepEqual([block.x,block.y,block.w,block.h],[209,0,1,297]);
  assert.equal(x.value, '209'); assert.equal(container.querySelector('.editor-canvas-block').style.height, '100%');
  const bold = container.querySelector('.editor-block-bold'); bold.checked = true; bold.dispatch('change');
  assert.equal(container.querySelector('.editor-canvas-block').style.fontWeight, '700');
});

test('real pointer drag/resize handlers snap mm, preserve drag size and cancel cleanly', () => {
  const context = loadEditor(); const container = mount(context, textSettings());
  const node = container.querySelector('.editor-canvas-block');
  node.dispatch('pointerdown', {pointerId:1,clientX:0,clientY:0,button:0});
  node.dispatch('pointermove', {pointerId:1,clientX:5,clientY:7});
  let b = context.DocumentEditor.draft.blocks[0]; assert.deepEqual([b.x,b.y,b.w,b.h],[21,22,174,24]);
  node.dispatch('pointermove', {pointerId:1,clientX:10000,clientY:10000});
  assert.deepEqual([b.x,b.y,b.w,b.h],[36,273,174,24]);
  node.dispatch('pointercancel'); node.dispatch('pointermove',{pointerId:1,clientX:0,clientY:0}); assert.equal(b.x,36);
  node.dispatch('pointerdown', {target:node.querySelector('.editor-resize'),pointerId:2,clientX:0,clientY:0});
  node.dispatch('pointermove',{pointerId:2,clientX:-400,clientY:-400}); assert.deepEqual([b.w,b.h],[1,1]);
});

test('real keyboard and header handlers select, nudge and delete without editing text', () => {
  const context = loadEditor(); const container = mount(context, textSettings());
  const node = container.querySelector('.editor-canvas-block');
  node.dispatch('keydown',{key:'ArrowRight'}); node.dispatch('keydown',{key:'ArrowDown',shiftKey:true});
  assert.deepEqual([context.DocumentEditor.draft.blocks[0].x,context.DocumentEditor.draft.blocks[0].y],[19,28]);
  node.dispatch('keydown',{key:'Delete',target:container.querySelector('.editor-block-text')}); assert.equal(context.DocumentEditor.draft.blocks.length,1);
  container.querySelector('.editor-block-head').dispatch('click'); assert.equal(context.DocumentEditor.draft.selectedIndex,0);
  node.dispatch('keydown',{key:'Delete'}); assert.equal(context.DocumentEditor.draft.blocks.length,0);
});

test('sample/current order preview updates immediately; sample disables real PDF', () => {
  const context = loadEditor(); const container = mount(context, textSettings('{{buyer.name}}'), [{id:'one',buyer_name:'Real buyer'}]);
  const select = container.querySelector('.editor-preview-order'); assert.equal(container.querySelector('.editor-canvas-content').textContent,'Real buyer');
  select.value = ''; select.dispatch('change'); assert.equal(container.querySelector('.editor-canvas-content').textContent,'Anna Kowalska');
  assert.equal(container.querySelector('.editor-preview').disabled,true);
});

test('select duplicate delete handlers use collection routes and returned active settings', async () => {
  const context = loadEditor(); const initial = textSettings();
  initial.templates.push({id:'other',name:'Other',blocks:[{type:'line'}]});
  const container = mount(context,initial); const select = container.querySelector('.editor-template-select');
  select.value = 'other'; const switching = select.dispatch('change'); await Promise.resolve();
  assert.equal(context.apiCalls[0].path,'/print/document-templates/other/select');
  const selected = {...initial,profiles:{default:{source:'template',active_template_id:'other'}}}; context.apiCalls[0].resolve(selected); await switching;
  assert.equal(context.DocumentEditor.draft.templateId,'other');
  const duplicating = container.querySelector('.editor-template-duplicate').click(); await Promise.resolve();
  assert.equal(context.apiCalls[1].path,'/print/document-templates/other/duplicate'); assert.equal(JSON.parse(context.apiCalls[1].options.body).name,'Other (copy)');
  const duplicated = {...selected,templates:[...selected.templates,{id:'copy',name:'Other (copy)',blocks:[{type:'line'}]}],profiles:{default:{source:'template',active_template_id:'copy'}}}; context.apiCalls[1].resolve(duplicated); await duplicating;
  const deleting = container.querySelector('.editor-template-delete').click(); await Promise.resolve();
  assert.equal(context.apiCalls[2].path,'/print/document-templates/copy'); assert.equal(context.apiCalls[2].options.method,'DELETE');
  context.apiCalls[2].resolve(selected); await deleting; assert.equal(context.DocumentEditor.draft.templateId,'other');
});

test('duplicate saves dirty draft first and failed save never duplicates', async () => {
  const context = loadEditor(); const container = mount(context,textSettings());
  const text = container.querySelector('.editor-block-text'); text.value='New'; text.dispatch('input');
  const duplicating = container.querySelector('.editor-template-duplicate').click();
  assert.equal(context.apiCalls[0].path,'/print/document-settings');
  context.apiCalls[0].reject(new Error('Save failed')); await duplicating;
  assert.equal(context.apiCalls.length,1); assert.equal(context.DocumentEditor.draft.blocks[0].text,'New');
});

test('collection limits and discard cancellation prevent requests', async () => {
  const context = loadEditor(); const container = mount(context,textSettings());
  assert.equal(container.querySelector('.editor-template-delete').disabled,true);
  await container.querySelector('.editor-template-delete').click(); assert.equal(context.apiCalls.length,0);
  const text = container.querySelector('.editor-block-text'); text.value='Dirty'; text.dispatch('input'); context.window.confirm=()=>false;
  const select=container.querySelector('.editor-template-select'); select.value='other'; await select.dispatch('change'); assert.equal(context.apiCalls.length,0);
  const many=textSettings(); many.templates=Array.from({length:10},(_,i)=>({id:i?'t'+i:'default',name:'T',blocks:[{type:'line'}]})); mount(context,many);
  assert.equal(context.testContainer.querySelector('.editor-template-duplicate').disabled,true);
});

test('successful duplicate saves newest text and survives pending navigation', async () => {
  const context = loadEditor(); const container = mount(context,textSettings());
  const text = container.querySelector('.editor-block-text'); text.value='Newest'; text.dispatch('input');
  const pending=container.querySelector('.editor-template-duplicate').click();
  assert.equal(container.querySelector('.editor-block-text').disabled,true);
  mount(context,textSettings());
  assert.equal(context.testContainer.querySelector('.editor-template-select').disabled,true);
  context.apiCalls[0].resolve(textSettings('Newest'));
  await context.DocumentEditor.lastSavePromise; await Promise.resolve();
  assert.equal(context.apiCalls[1].path,'/print/document-templates/default/duplicate');
  const saved=textSettings('Newest'); saved.templates.push({id:'copy',name:'T (copy)',blocks:[{type:'text',text:'Newest'}]}); saved.profiles.default.active_template_id='copy';
  context.apiCalls[1].resolve(saved); await pending;
  assert.equal(context.DocumentEditor.draft.templateId,'copy');
  assert.equal(context.testContainer.querySelector('.editor-block-text').value,'Newest');
  assert.equal(context.testContainer.querySelector('.editor-block-text').disabled,false);
});

class JsonReader {
  readAsText(file) { this.result = file.text; this.onload(); }
}

function importFile(container, text) {
  const input = container.querySelector('.editor-template-import-file');
  input.files = [{ name: 'templates.json', text }];
  input.value = 'templates.json';
  return input.dispatch('change');
}

test('export current and all use authenticated fetch paths and blob downloads', async () => {
  const context = loadEditor(); const initial = textSettings();
  initial.templates[0].id = 'special/id'; initial.profiles.default.active_template_id = 'special/id';
  const container = mount(context, initial); const calls = []; const downloads = []; const revoked = [];
  const createElement = context.document.createElement;
  context.document.createElement = tag => {
    const node = createElement(tag);
    if (tag === 'a') node.click = () => downloads.push([node.getAttribute('href'), node.getAttribute('download')]);
    return node;
  };
  context.URL.createObjectURL = blob => { assert.equal(blob.kind, 'json'); return 'blob:download'; };
  context.URL.revokeObjectURL = url => revoked.push(url);
  context.setTimeout = fn => { fn(); };
  context.apiFetch = async path => { calls.push(path); return {ok:true,blob:async()=>({kind:'json'})}; };
  await container.querySelector('.editor-template-export').click();
  await container.querySelector('.editor-template-export-all').click();
  assert.deepEqual(calls, ['/print/document-templates/export?template_id=special%2Fid', '/print/document-templates/export']);
  assert.deepEqual(downloads, [['blob:download','document-template.json'],['blob:download','document-templates.json']]);
  assert.deepEqual(revoked, ['blob:download','blob:download']);
  assert.equal(container.querySelector('a'), null);
});

test('import posts parsed JSON and conflict strategy, adopts settings and translates result', async () => {
  for (const strategy of ['rename', 'overwrite']) {
    const context = loadEditor({FileReader:JsonReader}); const container = mount(context,textSettings());
    const file = container.querySelector('.editor-template-import-file');
    assert.equal(file.hasAttribute('hidden'), true); assert.equal(file.getAttribute('accept'), '.json,application/json');
    let opened = 0; file.click = () => opened++;
    container.querySelector('.editor-template-import').click(); assert.equal(opened, 1);
    const conflict = container.querySelector('.editor-import-conflict'); assert.equal(conflict.value, 'rename');
    conflict.value = strategy; conflict.dispatch('change');
    const data = {version:1,templates:[{id:'new',name:'Imported',blocks:[{type:'line'}]}]};
    const pending = importFile(container, JSON.stringify(data)); await Promise.resolve();
    assert.equal(file.value, '');
    const call = context.apiCalls[0]; assert.equal(call.path, '/print/document-templates/import');
    assert.equal(call.options.method, 'POST'); assert.equal(call.options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(call.options.body), {data,on_conflict:strategy});
    const saved = settingsFixture({templates:data.templates,profiles:{default:{source:'template',active_template_id:'new'}}});
    call.resolve({settings:saved, imported:1}); await pending;
    assert.equal(context.DocumentEditor.draft.templateId, 'new');
    assert.equal(container.querySelector('.editor-template-name').value, 'Imported');
    assert.equal(context.onSavedCalls[0], saved);
    assert.equal(container.querySelector('.editor-status').textContent, 'Zaimportowano szablony: 1');
    context.setLanguage('en',{root:container});
    assert.equal(container.querySelector('.editor-status').textContent, 'Templates imported: 1');
    assert.equal(container.querySelector('.editor-template-export').textContent, 'Export current');
    assert.equal(container.querySelector('.editor-import-conflict').getAttribute('aria-label'), 'Import template conflicts');
  }
});

test('invalid JSON and file read errors do not call the API and translate in place', async () => {
  for (const Reader of [JsonReader, class { readAsText() { this.onerror(); } }]) {
    const context = loadEditor({FileReader:Reader}); const container = mount(context,textSettings());
    await importFile(container, '{invalid');
    assert.equal(context.apiCalls.length, 0);
    assert.equal(context.DocumentEditor.draft.blocks[0].text, 'First');
    context.setLanguage('en',{root:container});
    assert.equal(container.querySelector('.editor-status').textContent, 'Error: Invalid JSON file.');
    assert.equal(container.querySelector('.editor-template-import').disabled, false);
  }
});

test('import discard cancellation preserves draft without reading or requesting', async () => {
  let reads = 0;
  const context = loadEditor({FileReader:class { readAsText() { reads++; } }}); const container = mount(context,textSettings());
  const text = container.querySelector('.editor-block-text'); text.value = 'Dirty'; text.dispatch('input');
  let confirms = 0; context.window.confirm = () => { confirms++; return false; };
  await importFile(container, '{}');
  assert.equal(confirms, 1); assert.equal(reads, 0); assert.equal(context.apiCalls.length, 0);
  assert.equal(context.DocumentEditor.draft.blocks[0].text, 'Dirty');
});

test('import locks collection during file reading and request, including remount and failures', async () => {
  let reader;
  const context = loadEditor({FileReader:class { constructor() { reader = this; } readAsText() {} }});
  let container = mount(context,textSettings(),[{id:'order'}]);
  const pending = importFile(container, '{}');
  const assertBusy = () => {
    for (const selector of ['.editor-template-export','.editor-template-export-all','.editor-template-import','.editor-template-import-file','.editor-import-conflict','.editor-template-select','.editor-save','.editor-preview','.editor-block-text']) assert.equal(container.querySelector(selector).disabled,true,selector);
  };
  assertBusy();
  await container.querySelector('.editor-template-export').click();
  await importFile(container, '{}'); assert.equal(context.apiCalls.length, 0);
  mount(context,textSettings(),[{id:'order'}]); container = context.testContainer; assertBusy();
  reader.result = '{}'; reader.onload(); await Promise.resolve(); assertBusy();
  context.apiCalls[0].reject(new Error('Import failed')); await pending;
  assert.equal(container.querySelector('.editor-template-import').disabled,false);
  assert.equal(container.querySelector('.editor-block-text').value,'First');
  assert.match(container.querySelector('.editor-status').textContent,/Import failed/);
});

test('save in flight blocks import and exports, and export reports HTTP and blob API errors', async () => {
  const context = loadEditor({FileReader:JsonReader}); const container = mount(context,textSettings());
  container.querySelector('.editor-save').click();
  await importFile(container, '{}'); await container.querySelector('.editor-template-export').click();
  assert.equal(context.apiCalls.length, 1);
  assert.equal(container.querySelector('.editor-template-import').disabled,true);
  context.apiCalls[0].resolve(textSettings()); await context.DocumentEditor.lastSavePromise;
  context.apiFetch = async () => ({ok:false,json:async()=>({detail:'Export failed'})});
  await container.querySelector('.editor-template-export').click();
  assert.match(container.querySelector('.editor-status').textContent,/Export failed/);
  // A new clean mount clears that error before testing unsupported blob URLs.
  const fresh = loadEditor(); const freshContainer = mount(fresh,textSettings());
  fresh.URL = undefined; fresh.apiFetch = async () => ({ok:true,blob:async()=>({})});
  await freshContainer.querySelector('.editor-template-export').click();
  assert.equal(freshContainer.querySelector('.editor-template-export').disabled,false);
  assert.equal(fresh.DocumentEditor.draft.status,'error');
});

test('export saves latest dirty template before downloading and aborts on save failure', async () => {
  const context = loadEditor(); const container = mount(context,textSettings()); let exports = 0;
  context.apiFetch = async () => { exports++; return {ok:true,blob:async()=>({})}; };
  const text = container.querySelector('.editor-block-text'); text.value = 'Newest'; text.dispatch('input');
  const pending = container.querySelector('.editor-template-export').click();
  assert.equal(JSON.parse(context.apiCalls[0].options.body).template.blocks[0].text,'Newest');
  assert.equal(exports,0); context.apiCalls[0].resolve(textSettings('Newest')); await pending; assert.equal(exports,1);
  const next = container.querySelector('.editor-block-text'); next.value = 'Unsaved'; next.dispatch('input');
  const failed = container.querySelector('.editor-template-export-all').click();
  context.apiCalls[1].reject(new Error('Save failed')); await failed;
  assert.equal(exports,1); assert.equal(context.DocumentEditor.draft.blocks[0].text,'Unsaved');
});

