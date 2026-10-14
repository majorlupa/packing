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
  return { api, read, send, context };
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
  await send(`/print/orders/${id}/label?weight=1`);
  const label = await api.request(`/print/orders/${id}/label`);
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

test('custom demo PDFs contain only template blocks, not inherited order content', async () => {
  const {api, send} = demo();
  const template = {id:'default',name:'Only my content',blocks:[{type:'text',text:'CUSTOM ONLY {{buyer_name}}'}]};
  await send('/print/document-settings', {source:'template',template});
  for (const [path,options] of [
    ['/print/custom-doc?order_id=demo-101',{}],
    ['/print/document-preview',{method:'POST',body:JSON.stringify({order_id:'demo-101',template})}]
  ]) {
    const pdf = await (await api.request(path,options)).text();
    assert.match(pdf, /CUSTOM ONLY Anna Demo/);
    assert.doesNotMatch(pdf, /SAMPLE ORDER DOCUMENT|Kubek ceramiczny|DEMO-101/);
    assert.match(pdf, /WELES \/ DEMO/);
  }
  const sales = await api.request('/print/orders/demo-101/document');
  assert.equal(sales.ok, true);
  const pdf = await sales.text();
  assert.match(pdf, /SAMPLE ORDER DOCUMENT/);
  assert.doesNotMatch(pdf, /CUSTOM ONLY/);
});

test('demo build includes every referenced local script and stylesheet including the editor', () => {
  require('node:child_process').execFileSync(process.execPath, ['tools/build-demo.cjs']);
  const html = fs.readFileSync('dist/index.html','utf8');
  for (const [,src] of html.matchAll(/(?:<script src|<link rel="stylesheet" href)="([^"]+)"/g)) {
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
    api.setParcelSize(id, size);
    assert.equal((await api.request(`/print/orders/${id}/label`, {method:'POST'})).ok, true);
    const response = await api.request(`/print/orders/${id}/label`);
    assert.equal(response.ok, true);
    assert.match(await response.text(), new RegExp(`PACZKOMAT INPOST - SIZE ${size}`));
  }
  api.setParcelSize(id, 'A');
  assert.equal((await read('/orders/')).find(order => order.id === id).shipment_id, null);
  assert.equal((await api.request(`/print/orders/${id}/label`)).status, 409);
  assert.equal((await api.request(`/print/orders/${id}/label`, {method:'POST'})).status, 200);
  api.reset();
  assert.equal((await read('/orders/')).find(order => order.id === id).parcel_size, 'A');
});

test('locker PATCH and shipment readback match the shared application contracts', async () => {
  const {api, read, send} = demo();
  assert.equal((await send('/orders/demo-102/parcel-size', {parcel_size:'B'}, 'PATCH')).parcel_size, 'B');
  await send('/print/orders/demo-102/label');
  const label = await api.request('/print/orders/demo-102/label');
  assert.match(await label.text(), /SIZE B/);
  const shipment = await read('/print/orders/demo-102/shipment');
  assert.equal(shipment.shipment_id, 'sample-demo-102');
  assert.equal(shipment.tracking_number, 'DEMO-TRACK-demo-102');
  assert.equal((await api.request('/orders/demo-102/parcel-size', {method:'PATCH',body:'{"parcel_size":"C"}'})).status,409);
});

test('label creation is JSON and idempotent; GET only downloads an existing sample', async () => {
  const {api, read, send} = demo();
  const path = '/print/orders/demo-101/label';
  assert.equal((await api.request(path)).status, 409);
  assert.equal((await read('/orders/'))[0].shipment_id, null);
  assert.equal((await api.request(`${path}?weight=0`, {method:'POST'})).status, 422);
  const created = await send(`${path}?length=30&width=20&height=15&weight=1`);
  assert.deepEqual(await send(path), created);
  assert.deepEqual(await read('/print/orders/demo-101/shipment'), created);
  const pdf = await api.request(`${path}?weight=0`);
  assert.equal(pdf.headers.get('content-type'), 'application/pdf');
  assert.match(await pdf.text(), /^%PDF-1.4/);
  api.reset();
  assert.equal((await api.request(path)).status, 409);
});

test('named templates duplicate, edit, select, delete and render the active content offline', async () => {
  const {api, read, send} = demo();
  const original = {id:'default',name:'Original',blocks:[{type:'text',text:'ORIGINAL'}]};
  await send('/print/document-settings', {source:'template',template:original});
  const copied = await send('/print/document-templates/default/duplicate', {name:'Second'});
  const id = copied.profiles.default.active_template_id;
  assert.notEqual(id, 'default');
  const template = {id,name:'Renamed',blocks:[{type:'placeholder',text:'ONLY {{ buyer.name }} {{order.id}} {{unknown}}',x:20,y:30,w:100,h:20}]};
  await send('/print/document-settings', {source:'template',template});
  const before = await read('/print/document-settings');
  const unsaved = {...template,blocks:[{type:'text',text:'UNSAVED'}]};
  const preview = await api.request('/print/document-preview', {method:'POST',body:JSON.stringify({order_id:'demo-101',template:unsaved})});
  assert.match(await preview.text(), /UNSAVED/);
  assert.deepEqual(await read('/print/document-settings'), before);
  const pdf = await (await api.request('/print/custom-doc?order_id=demo-101')).text();
  assert.match(pdf, /ONLY Anna Demo demo-101 -/);
  assert.doesNotMatch(pdf, /ORIGINAL|UNSAVED|DEMO-101|Kubek|Notes|SAMPLE ORDER DOCUMENT/);
  await send('/print/document-templates/default/select');
  assert.match(await (await api.request('/print/custom-doc?order_id=demo-101')).text(), /ORIGINAL/);
  assert.equal((await read('/print/document-settings')).templates[0].blocks[0].text, 'ORIGINAL');
  await send(`/print/document-templates/${id}/select`);
  const deleted = await send(`/print/document-templates/${id}`, undefined, 'DELETE');
  assert.equal(deleted.profiles.default.active_template_id, 'default');
  assert.equal((await api.request('/print/document-templates/default', {method:'DELETE'})).status, 422);
  assert.equal((await api.request(`/print/document-templates/${id}/select`, {method:'POST'})).status, 404);
  for (let i = 0; i < 9; i++) await send('/print/document-templates/default/duplicate');
  assert.equal((await api.request('/print/document-templates/default/duplicate', {method:'POST'})).status, 422);
  api.reset();
  assert.equal((await read('/print/document-settings')).templates.length, 1);
});

test('empty and malformed drafts fail with JSON details without changing saved templates', async () => {
  const {api, read, send} = demo();
  const before = await read('/print/document-settings');
  for (const blocks of [[], [{type:'text',text:'   '}], [{type:'text',text:'{{buyer.name + 1}}'}], [{type:'invalid'}]]) {
    const response = await api.request('/print/document-settings', {method:'POST',body:JSON.stringify({source:'template',template:{id:'default',name:'Invalid',blocks}})});
    assert.equal(response.status, 422);
    assert.equal(typeof (await response.json()).detail, 'string');
  }
  assert.deepEqual(await read('/print/document-settings'), before);
  assert.equal((await api.request('/print/document-preview', {method:'POST',body:'{'})).status, 422);
  await send('/print/document-settings', {source:'template',template:{id:'default',name:'Rule',blocks:[{type:'line'}]}});
  assert.equal((await read('/print/custom-doc/info')).available, true);
  assert.equal((await api.request('/print/custom-doc?order_id=demo-101')).ok, true);
});

test('shared JSON and PDF helpers report mock errors as toasts without token prompts or network', async () => {
  const {context} = demo();
  const nodes = {'toast-info':{textContent:'',isConnected:true},'toast-error':{textContent:'',isConnected:true}};
  const tab = {closed:false,close() { this.closed = true; }};
  Object.assign(context, {
    Headers, Intl,
    document:{getElementById:id => nodes[id] || null,querySelectorAll:() => [],documentElement:null},
    window:{open:() => tab,prompt:() => assert.fail('demo must not prompt for tokens')},
    fetch:() => assert.fail('demo must not access the network'),
    setTimeout:() => 1,clearTimeout:() => {},
  });
  const source = fs.readFileSync('frontend/static/app.js','utf8');
  vm.runInContext(source.slice(0,source.indexOf('// ---- Sidebar events ----')), context);
  assert.equal((await context.api('/orders/')).length, 5);
  for (const action of [
    () => context.api('/picking-lists',{method:'POST',body:'{"order_ids":["missing"]}'}),
    () => context.openPdf('/print/orders/demo-101/label'),
  ]) {
    let error;
    try { await action(); } catch (err) { error = err; }
    assert.ok(error);
    context.reportError('Mock failure', error);
    assert.equal(nodes['toast-error'].textContent, `Mock failure\n${error.message}`);
    assert.doesNotMatch(nodes['toast-error'].textContent, /\[object Object\]|"detail"/);
  }
  assert.equal(tab.closed, true);
});

test('template exports download one or all as JSON blobs and missing IDs return 404', async () => {
  const {api, read, send} = demo();
  const settings = await send('/print/document-templates/default/duplicate', {name:'Second'});
  const id = settings.profiles.default.active_template_id;
  for (const [path, templates, filename] of [
    ['/print/document-templates/export', settings.templates, 'packing-templates.json'],
    [`/print/document-templates/export?template_id=${encodeURIComponent(id)}`, [settings.templates[1]], `packing-template-${id}.json`],
  ]) {
    const response = await api.request(path);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'application/json');
    assert.equal(response.headers.get('content-disposition'), `attachment; filename="${filename}"`);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const blob = await response.blob(); // Same download path as document-editor.js.
    const data = JSON.parse(await blob.text());
    assert.equal(data.format, 'packing.document-templates');
    assert.equal(data.version, 1);
    assert.ok(Number.isFinite(Date.parse(data.exported_at)));
    assert.deepEqual(data.templates, templates);
    assert.deepEqual(Object.keys(data.templates[0]).sort(), ['blocks','id','name']);
  }
  for (const id of ['missing', '']) {
    assert.equal((await api.request(`/print/document-templates/export?template_id=${id}`)).status, 404);
  }
  assert.deepEqual(await read('/print/document-settings'), settings);
});

test('export/import rename round trips blocks with fresh IDs and preserves profiles', async () => {
  const {read, send} = demo();
  const template = {id:'default',name:'Insert',blocks:[{type:'text',text:'Hello {{buyer.name}}',x:20,y:30,w:100,h:20}]};
  const before = await send('/print/document-settings', {source:'template',template});
  const data = await read('/print/document-templates/export');
  for (const suffix of [2, 3]) {
    const result = await send('/print/document-templates/import', {data,on_conflict:'rename'});
    const imported = result.settings.templates.find(entry => entry.id === result.imported[0]);
    assert.notEqual(imported.id, template.id);
    assert.equal(imported.name, `Insert (${suffix})`);
    assert.deepEqual(imported.blocks, template.blocks);
    assert.deepEqual(result.settings.profiles, before.profiles);
    assert.deepEqual(await read('/print/document-settings'), result.settings);
  }
  const other = demo();
  const result = await other.send('/print/document-templates/import', {data,on_conflict:'rename'});
  assert.equal(result.settings.templates[1].name, 'Insert');
  assert.notEqual(result.imported[0], template.id);
  assert.deepEqual(result.settings.templates[1].blocks, template.blocks);
});

test('import rename truncates long names and skips existing numbered conflicts', async () => {
  const {read, send} = demo();
  const name = 'N'.repeat(100);
  await send('/print/document-settings', {source:'upload',template:{id:'default',name,blocks:[]}});
  const data = await read('/print/document-templates/export');
  for (const number of [2, 3]) {
    const result = await send('/print/document-templates/import', {data,on_conflict:'rename'});
    assert.equal(result.settings.templates.at(-1).name, `${name.slice(0,96)} (${number})`);
    assert.equal(result.settings.templates.at(-1).name.length, 100);
  }
});

test('import overwrite matches trimmed names, keeps existing ID and active template', async () => {
  const {read, send} = demo();
  await send('/print/document-settings', {source:'template',template:{id:'default',name:' Insert ',blocks:[{type:'line'}]}});
  const before = await send('/print/document-templates/default/duplicate', {name:'Active'});
  const data = await read('/print/document-templates/export?template_id=default');
  data.templates[0] = {id:'foreign-id',name:' Insert ',blocks:[{type:'text',text:'REPLACED'}]};
  data.templates.push({id:'default',name:'New',blocks:[]});
  const result = await send('/print/document-templates/import', {data,on_conflict:'overwrite'});
  assert.equal(result.imported[0], 'default');
  assert.notEqual(result.imported[1], 'default');
  assert.deepEqual(result.settings.templates[0], {...data.templates[0],id:'default',name:'Insert'});
  assert.deepEqual(result.settings.profiles, before.profiles);
  assert.deepEqual(await read('/print/document-settings'), result.settings);
});

test('invalid import files and conflicts leave all saved settings unchanged', async () => {
  const {api, read} = demo();
  const before = await read('/print/document-settings');
  const data = await read('/print/document-templates/export');
  const template = data.templates[0];
  const cases = [
    {...data,format:'wrong'}, {...data,version:2}, {...data,version:'1'}, {...data,version:true},
    {...data,exported_at:'invalid'}, {...data,unexpected:true}, {...data,templates:[]},
    {...data,templates:[template,{...template,id:'other',name:` ${template.name} `}]},
    ...[null, {...template,id:'bad id'}, {...template,name:'   '},
      {...template,name:'N'.repeat(101)}, {...template,blocks:[{type:'invalid'}]},
      {...template,blocks:[{type:'text',text:'{{buyer.name + 1}}'}]}].map(invalid => ({...data,templates:[template,invalid]})),
    {...data,templates:Array.from({length:11}, (_, i) => ({...template,id:`id-${i}`,name:`Name ${i}`}))},
  ];
  for (const body of [...cases.map(data => ({data,on_conflict:'rename'})),
    {data,on_conflict:'invalid'}, {data}, {data:null,on_conflict:'rename'}]) {
    const response = await api.request('/print/document-templates/import', {method:'POST',body:JSON.stringify(body)});
    assert.equal(response.status, 422);
    assert.equal(typeof (await response.json()).detail, 'string');
    assert.deepEqual(await read('/print/document-settings'), before);
  }
});

test('import limit failures roll back staged overwrites and additions; overwrite at ten succeeds', async () => {
  const {api, read, send} = demo();
  for (let i = 1; i < 10; i++) await send('/print/document-templates/default/duplicate', {name:`Name ${i}`});
  const before = await read('/print/document-settings');
  const data = await read('/print/document-templates/export?template_id=default');
  const changed = {...data.templates[0],blocks:[{type:'text',text:'REPLACED'}]};
  for (const on_conflict of ['rename','overwrite']) {
    const response = await api.request('/print/document-templates/import', {method:'POST',body:JSON.stringify({
      data:{...data,templates:[changed,{id:'new',name:'New',blocks:[]}]},on_conflict,
    })});
    assert.equal(response.status, 422);
    assert.deepEqual(await read('/print/document-settings'), before);
  }
  const result = await send('/print/document-templates/import', {data:{...data,templates:[changed]},on_conflict:'overwrite'});
  assert.deepEqual(result.imported, ['default']);
  assert.equal(result.settings.templates.length, 10);
  assert.deepEqual(result.settings.templates[0].blocks, changed.blocks);
  assert.deepEqual(result.settings.profiles, before.profiles);
});

test('demo chrome hides reconnect even after periodic auth updates', () => {
  assert.match(fs.readFileSync('frontend/demo/demo.css','utf8'), /\.demo-mode #sidebar #btn-auth\s*\{\s*display: none !important/);
});
