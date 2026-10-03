const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const definitions = source.slice(0, source.indexOf('// ---- Sidebar events ----'));

// A small DOM for this card: parse the generated controls so assertions exercise
// the production template and handlers together, including card replacement.
class Element {
  constructor(attributes = '') {
    this.listeners = {};
    this.disabled = /\bdisabled\b/.test(attributes);
    this.checked = /\bchecked\b/.test(attributes);
    this.value = attributes.match(/\bvalue="([^"]*)"/)?.[1] || '';
    this.textContent = '';
    this.dataset = {};
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener(type, handler) { this.listeners[type] = handler; }
  dispatch(type) { return this.listeners[type]?.({ target: this }); }
}

class View extends Element {
  set innerHTML(html) {
    this.html = html;
    this.controls = new Map();
    for (const match of html.matchAll(/<(?:button|input|p|div)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
      this.controls.set(`#${match[2]}`, new Element(match[1]));
    }
    this.radios = [...html.matchAll(/<input\b([^>]*\bname="parcel-size"[^>]*)>/g)]
      .map(match => new Element(match[1]));
    const fieldset = html.match(/<fieldset\b([^>]*)>/);
    if (fieldset) this.controls.set('.parcel-sizes', new Element(fieldset[1]));
    this.controls.set('.pack-card', new Element());
    this.controls.set('.btn-copy', new Element());
    const status = html.match(/<p\b[^>]*id="parcel-size-status"[^>]*>([\s\S]*?)<\/p>/);
    if (status) this.controls.get('#parcel-size-status').textContent = status[1];
  }
  get innerHTML() { return this.html; }
  querySelector(selector) {
    if (selector.startsWith('input[name="parcel-size"]')) {
      const value = selector.match(/\[value="([^"]+)"\]/)?.[1];
      return this.radios.find(input => !value || input.value === value) || null;
    }
    return this.controls.get(selector) || null;
  }
  querySelectorAll(selector) {
    return selector === 'input[name="parcel-size"]' ? this.radios : [];
  }
}

class Content extends Element {
  set innerHTML(html) {
    this.html = html;
    if (this.view) this.view.isConnected = false;
    this.view = new View();
    this.view.isConnected = true;
  }
  querySelector(selector) { return selector === '#packing-view' ? this.view : null; }
}

function locker(id, overrides = {}) {
  return {
    id, allegro_id: id, buyer_name: 'Buyer', buyer_address: 'Address',
    items: [{ name: 'Product', quantity: 1 }], status: 'packing',
    delivery_type: 'inpost_locker', courier: 'Allegro Paczkomaty InPost',
    parcel_size: null, shipment_id: null, tracking_number: null, ...overrides,
  };
}

function setup(orders) {
  const content = new Content();
  const calls = [];
  const context = vm.createContext({
    document: { getElementById: id => id === 'content' ? content : null },
    URLSearchParams, setTimeout, clearTimeout,
    navigator: { clipboard: { writeText: async () => {} } },
    confirm: () => false,
    alert(message) { throw new Error(`Unexpected alert: ${message}`); },
  });
  vm.runInContext(definitions, context);
  context.testOrders = orders;
  context.testApi = (path, options) => new Promise((resolve, reject) => {
    calls.push({ path, options, resolve, reject });
  });
  vm.runInContext(`
    state.orders = testOrders;
    state.packingQueue = testOrders;
    state.currentQueue = 'packing';
    state.parcelSizeSaves = new Map();
    state.parcelSizeErrors = new Map();
    api = testApi;
    renderPackingCard(document.getElementById('content'));
  `, context);
  return {
    context, content, calls,
    view: () => content.view,
    selected: () => content.view.radios.find(input => input.checked)?.value || null,
    select(value) {
      const view = content.view;
      assert.equal(view.querySelector('.parcel-sizes').disabled, false);
      for (const input of view.radios) input.checked = input.value === value;
      return view.radios.find(input => input.value === value).dispatch('change');
    },
    next() { return content.view.querySelector('#btn-next').dispatch('click'); },
    previous() { return content.view.querySelector('#btn-prev').dispatch('click'); },
  };
}

test('an unsaved locker requires explicit selection, including A', async () => {
  const order = locker('one');
  const app = setup([order]);
  assert.equal(app.selected(), null);
  const save = app.select('A');
  assert.equal(app.calls[0].path, '/orders/one/parcel-size');
  assert.equal(app.calls[0].options.method, 'PATCH');
  assert.deepEqual(JSON.parse(app.calls[0].options.body), { parcel_size: 'A' });
  app.calls[0].resolve({ parcel_size: 'A' });
  await save;
  assert.equal(order.parcel_size, 'A');
  assert.equal(app.selected(), 'A');
});

test('pending selection survives navigation and blocks another save', async () => {
  const order = locker('one', { parcel_size: 'A' });
  const app = setup([order, locker('two')]);
  const save = app.select('B');
  assert.equal(app.view().querySelector('.parcel-sizes').disabled, true);
  app.next();
  assert.equal(app.selected(), null);
  app.previous();
  assert.equal(app.selected(), 'B');
  assert.equal(app.view().querySelector('.parcel-sizes').disabled, true);
  // Even a queued event from the replacement card cannot start a second PATCH.
  await app.view().radios.find(input => input.value === 'C').dispatch('change');
  assert.equal(app.calls.length, 1);
  app.calls[0].resolve({ parcel_size: 'B' });
  await save;
  assert.equal(app.selected(), 'B');
  assert.equal(order.parcel_size, 'B');
  assert.equal(app.view().querySelector('.parcel-sizes').disabled, false);
});

test('failed save restores prior selection and displays the error after navigation', async () => {
  const order = locker('one', { parcel_size: 'A' });
  const app = setup([order, locker('two')]);
  const save = app.select('C');
  app.next();
  app.calls[0].reject(new Error('Storage unavailable'));
  await save;
  assert.equal(app.selected(), null);
  app.previous();
  assert.equal(app.selected(), 'A');
  assert.equal(order.parcel_size, 'A');
  assert.match(app.view().querySelector('#parcel-size-status').textContent, /Storage unavailable/);
  assert.equal(app.view().querySelector('.parcel-sizes').disabled, false);
});

test('failed first selection restores an unselected locker', async () => {
  const app = setup([locker('one')]);
  const save = app.select('A');
  app.calls[0].reject(new Error('Cannot save'));
  await save;
  assert.equal(app.selected(), null);
  assert.match(app.view().querySelector('#parcel-size-status').textContent, /Cannot save/);
});

test('save completion updates refreshed order references without changing another card', async () => {
  const app = setup([locker('one'), locker('two', { parcel_size: 'C' })]);
  const save = app.select('B');
  app.context.refreshedOrders = [locker('one'), locker('two', { parcel_size: 'C' })];
  vm.runInContext(`state.orders = refreshedOrders; state.packingQueue = refreshedOrders;`, app.context);
  app.next();
  const otherView = app.view();
  app.calls[0].resolve({ parcel_size: 'B' });
  await save;
  assert.equal(app.view(), otherView);
  assert.equal(app.selected(), 'C');
  app.previous();
  assert.equal(app.selected(), 'B');
});

test('existing shipments lock parcel sizes and retain label access', () => {
  const app = setup([locker('one', { parcel_size: 'C', shipment_id: 'saved' })]);
  assert.equal(app.selected(), 'C');
  assert.equal(app.view().querySelector('.parcel-sizes').disabled, true);
  assert.equal(app.view().querySelector('#btn-label').disabled, false);
});

test('new locker labels remain disabled and couriers retain dimension fields', () => {
  const app = setup([locker('one'), locker('two', { delivery_type: 'courier', courier: 'Kurier InPost' })]);
  assert.equal(app.view().querySelector('#btn-label').disabled, true);
  assert.equal(app.view().querySelector('#dim-l'), null);
  app.next();
  assert.equal(app.view().querySelector('.parcel-sizes'), null);
  assert.equal(app.view().querySelector('#dim-l').value, '30');
  assert.equal(app.view().querySelector('#dim-wt').value, '1');
});

test('delivery categories consolidate lockers and preserve courier names', () => {
  const app = setup([locker('one')]);
  assert.equal(app.context.deliveryCategory(locker('one')), 'Paczkomat InPost');
  assert.equal(app.context.deliveryCategory({ delivery_type: 'courier', courier: 'Kurier InPost' }), 'Kurier InPost');
  assert.equal(app.context.deliveryCategory({}), 'Inny');
});

test('new locker with parcel size selected enables label button', () => {
  const app = setup([locker('one', { parcel_size: 'B' })]);
  assert.equal(app.selected(), 'B');
  assert.equal(app.view().querySelector('#btn-label').disabled, false);
});
