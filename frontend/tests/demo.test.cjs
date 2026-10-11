const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
function demo() {
  const context = vm.createContext({ Response, URLSearchParams });
  vm.runInContext(fs.readFileSync('frontend/demo/demo.js', 'utf8'), context);
  const api = context.WelesDemo;
  const read = async path => (await api.request(path)).json();
  const send = async (path, body, method = 'POST') => {
    const response = await api.request(path, { method, body: JSON.stringify(body) });
    assert.equal(response.ok, true, await response.clone().text());
    return response.json();
  };
  return { api, read, send };
}
test('sample orders complete the picking, packing, PDF, done and archive workflow', async () => {
  const { api, read, send } = demo();
  const orders = await read('/orders/');
  assert.equal(orders.length, 5);
  const id = orders[0].id;
  const list = await send('/picking-lists', { order_ids: [id] });
  assert.equal((await read('/orders/'))[0].status, 'picking');
  await send(`/picking-lists/${list.id}`, { name: 'Morning batch' }, 'PATCH');
  assert.equal((await read('/picking-lists'))[0].name, 'Morning batch');
  await send(`/picking-lists/${list.id}/start-packing`);
  assert.equal((await read('/orders/'))[0].status, 'packing');
  const label = await api.request(`/print/orders/${id}/label?weight=1`);
  assert.equal(label.headers.get('content-type'), 'application/pdf');
  assert.match(await label.text(), /NOT VALID FOR SHIPPING/);
  assert.equal((await read('/orders/'))[0].shipment_id, `sample-${id}`);
  await send(`/orders/${id}/done`);
  await send(`/orders/${id}/undo-done`);
  assert.equal((await read('/orders/'))[0].status, 'packing');
  await send(`/orders/${id}/done`);
  await send('/orders/zakoncz-dzien');
  assert.equal((await read('/orders/')).length, 4);
  assert.equal((await read('/orders/archive'))[0].id, id);
  assert.deepEqual(await read('/picking-lists'), []);
  api.reset();
  assert.equal((await read('/orders/')).length, 5);
  assert.deepEqual(await read('/orders/archive'), []);
});
test('reverting detaches orders and sync adds unique samples', async () => {
  const { read, send } = demo();
  const ids = (await read('/orders/')).slice(0, 2).map(order => order.id);
  const list = await send('/picking-lists', { order_ids: ids });
  await send(`/orders/${ids[0]}/revert-pending`);
  assert.deepEqual((await read('/picking-lists'))[0].order_ids, [ids[1]]);
  await send(`/picking-lists/${list.id}/revert`);
  assert.ok((await read('/orders/')).every(order => order.status === 'pending'));
  await send('/orders/sync'); await send('/orders/sync');
  assert.equal(new Set((await read('/orders/')).map(order => order.id)).size, 7);
});
test('unsupported routes and upload never fall through to a backend', async () => {
  const { api } = demo();
  for (const path of ['/setup', '/orders/auth/url', '/print/custom-doc', '/unknown']) {
    const response = await api.request(path, { method: 'POST' });
    assert.equal(response.ok, false);
  }
  assert.equal((await api.request('/picking-lists', { method: 'POST', body: '{"order_ids":["missing"]}' })).status, 400);
});
test('browser data is isolated between visitors', async () => {
  const first = demo(); const second = demo();
  await first.send('/orders/sync');
  assert.equal((await first.read('/orders/')).length, 6);
  assert.equal((await second.read('/orders/')).length, 5);
});

test('document editor saves locally and previews an unsaved personalized demo PDF', async () => {
  const { api, read, send } = demo();
  const settings = await read('/print/document-settings');
  assert.equal(settings.profiles.default.source, 'upload');
  const template = {id:'default',name:'Demo insert',blocks:[{type:'heading',text:'Hello {{buyer_name}} - {{order_number}}'}]};
  const preview = await api.request('/print/document-preview', {method:'POST',body:JSON.stringify({order_id:'demo-101',template})});
  assert.equal(preview.ok, true);
  assert.match(await preview.text(), /Hello Anna Demo - DEMO-101/);
  assert.deepEqual(await read('/print/document-settings'), settings);
  await send('/print/document-settings', {source:'template',template});
  assert.deepEqual(await read('/print/custom-doc/info'), {available:true,source:'template',upload_available:false,size:0});
  const custom = await api.request('/print/custom-doc?order_id=demo-102');
  assert.match(await custom.text(), /Hello Marek Demo - DEMO-102/);
  assert.equal((await api.request('/print/custom-doc?order_id=missing')).status, 404);
  assert.match(await (await api.request('/print/combined/demo-101')).text(), /Hello Anna Demo/);
  await send('/print/document-settings', {source:'upload',template});
  assert.equal((await read('/print/custom-doc/info')).available, false);
  assert.equal((await read('/print/document-settings')).templates[0].name, 'Demo insert');
  assert.equal((await demo().read('/print/document-settings')).templates[0].blocks.length, 0);
});

test('demo build includes every referenced local script including the editor', () => {
  require('node:child_process').execFileSync(process.execPath, ['tools/build-demo.cjs']);
  const html = fs.readFileSync('dist/index.html','utf8');
  for (const [,src] of html.matchAll(/<script src="([^"]+)"/g)) {
    assert.ok(fs.existsSync(`dist/${src}`), src);
  }
});

test('locker sizes are stored per order, validated, printed and reset', async () => {
  const { api, read } = demo();
  const orders = await read('/orders/');
  const lockers = orders.filter(order => order.courier === 'Paczkomat InPost');
  assert.equal(lockers.length, 2);
  const id = lockers[0].id;
  assert.equal(lockers[0].parcel_size, 'A');
  api.setParcelSize(id, 'B');
  assert.equal((await read('/orders/')).find(order => order.id === id).parcel_size, 'B');
  assert.equal((await read('/orders/')).find(order => order.id === lockers[1].id).parcel_size, 'A');
  assert.throws(() => api.setParcelSize(id, 'D'), /gabaryt/);
  assert.throws(() => api.setParcelSize(orders[0].id, 'B'), /gabaryt/);
  for (const size of ['A', 'B', 'C']) {
    const response = await api.request(`/print/orders/${id}/label?parcel_size=${size}`);
    assert.equal(response.ok, true);
    assert.match(await response.text(), new RegExp(`PACZKOMAT INPOST - SIZE ${size}`));
  }
  api.setParcelSize(id, 'A');
  assert.equal((await read('/orders/')).find(order => order.id === id).shipment_id, null);
  assert.equal((await api.request(`/print/orders/${id}/label?parcel_size=D`)).status, 400);
  assert.equal((await api.request(`/print/orders/${id}/label`)).status, 200);
  api.reset();
  assert.equal((await read('/orders/')).find(order => order.id === id).parcel_size, 'A');
});

test('locker PATCH and shipment readback match the shared application contracts', async () => {
  const {api, read, send} = demo();
  assert.equal((await send('/orders/demo-102/parcel-size', {parcel_size:'B'}, 'PATCH')).parcel_size, 'B');
  const label = await api.request('/print/orders/demo-102/label');
  assert.match(await label.text(), /SIZE B/);
  const shipment = await read('/print/orders/demo-102/shipment');
  assert.equal(shipment.shipment_id, 'sample-demo-102');
  assert.equal(shipment.tracking_number, 'DEMO-TRACK-demo-102');
  assert.equal((await api.request('/orders/demo-102/parcel-size', {method:'PATCH',body:'{"parcel_size":"C"}'})).status,409);
});
