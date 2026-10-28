/* Browser-only sample data. Every demo request terminates here; no network fallback. */
(function (global) {
  'use strict';
  const initialOrders = () => [
    ['101', 'Anna Demo', 'Warszawa', 'InPost', [['Kubek ceramiczny — szałwia', 2, 39], ['Notes w kropki A5', 1, 24]]],
    ['102', 'Marek Demo', 'Kraków', 'Paczkomat InPost', [['Kubek ceramiczny — szałwia', 1, 39]]],
    ['103', 'Julia Demo', 'Gdańsk', 'DPD', [['Torba bawełniana', 2, 29], ['Notes w kropki A5', 1, 24]]],
    ['104', 'Piotr Demo', 'Poznań', 'DPD', [['Świeca sojowa — las', 1, 49]]],
    ['105', 'Ewa Demo', 'Wrocław', 'Paczkomat InPost', [['Notes w kropki A5', 3, 24]]],
  ].map(([id, buyer, city, courier, items]) => ({
    id: `demo-${id}`, allegro_id: `DEMO-${id}`, buyer_name: buyer,
    buyer_address: `ul. Przykładowa 1, ${city} (dane fikcyjne)`,
    courier, pickup_point: courier === 'Paczkomat InPost' ? 'DEMO01M' : null,
    delivery_type: courier === 'Paczkomat InPost' ? 'inpost_locker' : 'courier',
    parcel_size: courier === 'Paczkomat InPost' ? 'A' : null,
    status: 'pending', picking_list_id: null, shipment_id: null,
    items: items.map(([name, quantity, unit_price]) => ({ name, quantity, unit_price })),
  }));
  let orders, lists, archive, shipment, invoice, documents, counter, syncCounter;
  let tourActive = false;
  const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json', ...headers },
  });
  function reset() {
    orders = initialOrders(); lists = []; archive = []; counter = 0; syncCounter = 0;
    shipment = { sender: {}, package: { length: 30, width: 20, height: 15, weight: 1, page_size: 'A6' } };
    invoice = { free_text: 'Dziękujemy za zakup! — Weles DEMO' };
    documents = {version:1,templates:[{id:'default',name:'Mój dokument',blocks:[]}],
      profiles:{default:{source:'upload',active_template_id:'default'}}};
    const draft = global.DocumentEditor?.draft;
    if (draft) Object.assign(draft, {templateId:'default',source:'upload',name:documents.templates[0].name,blocks:[],
      status:'idle',error:'',errorKey:null,revision:draft.revision + 1});
  }
  reset();
  function detach(id) {
    lists.forEach(list => { list.order_ids = list.order_ids.filter(oid => oid !== id); });
    lists = lists.filter(list => list.order_ids.length);
  }
  function setParcelSize(id, size) {
    const order = orders.find(entry => entry.id === id);
    if (!order || order.delivery_type !== 'inpost_locker' || !['A', 'B', 'C'].includes(size)) {
      throw new Error('Wybierz gabaryt A, B lub C dla przesyłki Paczkomat InPost.');
    }
    if (order.parcel_size !== size) {
      order.parcel_size = size;
      order.shipment_id = null;
    }
    return size;
  }
  // A real, minimal PDF with an unmistakable sample watermark; no usable shipping barcode.
  function templateLines(order, template) {
    const fields = {buyer_name:order.buyer_name,buyer_address:order.buyer_address,
      order_number:order.allegro_id,date:new Date().toLocaleDateString('pl-PL'),
      courier:order.courier,pickup_point:order.pickup_point || '-',tracking_number:order.tracking_number || '-'};
    Object.assign(fields, {'buyer.name':order.buyer_name,'buyer.address':order.buyer_address,
      'order.id':order.id,'order.date':fields.date,items:order.items.map(item => `${item.name} x ${item.quantity}`).join('\n')});
    return ['SIMPLIFIED DEMO - TEXT ONLY; NO LOGOS OR FORMATTING', ...template.blocks.flatMap(block => {
      if (block.type === 'customer') return [order.buyer_name, order.buyer_address];
      if (block.type === 'items') return order.items.map(item => `${item.quantity} x ${item.name}${block.show_prices ? ` - ${item.unit_price} PLN` : ''}`);
      if (block.type === 'logo') return block.image ? ['[LOGO - available in the full application]'] : [];
      if (block.type === 'line') return ['--------------------'];
      return String(block.text || '').replace(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}/g, (_, key) => fields[key] || '-').split('\n');
    })];
  }
  function samplePdf(order, label, extra = [], customOnly = false) {
    const orderLines = customOnly ? [] : [order.allegro_id,
      ...(order.delivery_type === 'inpost_locker' ? [`PACZKOMAT INPOST - SIZE ${order.parcel_size}`] : []),
      ...order.items.map(item => `${item.quantity} x ${item.name}`)];
    const lines = ['WELES / DEMO', label ? 'SAMPLE SHIPPING LABEL' : customOnly ? 'SAMPLE CUSTOM DOCUMENT' : 'SAMPLE ORDER DOCUMENT',
      'NOT VALID FOR SHIPPING OR ACCOUNTING', ...orderLines, ...extra];
    const safe = value => value.normalize('NFKD').replace(/[^\x20-\x7E]/g, '?').replace(/[\\()]/g, '\\$&');
    const stream = `BT /F1 15 Tf 40 780 Td ${lines.map((line, i) => `${i ? '0 -30 Td ' : ''}(${safe(line)}) Tj`).join('\n')} ET`;
    const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
      '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`];
    let pdf = '%PDF-1.4\n';
    const offsets = [0];
    objects.forEach((object, i) => { offsets.push(pdf.length); pdf += `${i + 1} 0 obj\n${object}\nendobj\n`; });
    const xref = pdf.length;
    pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
    return new Response(pdf, { headers: { 'Content-Type': 'application/pdf', 'Cache-Control':'no-store' } });
  }
  const hasContent = template => template.blocks.some(block =>
    ['customer','items','line'].includes(block.type) || (block.type === 'logo' ? block.image : String(block.text || '').trim()));
  function validTemplate(template) {
    return template && /^[a-zA-Z0-9_-]{1,64}$/.test(template.id)
      && typeof template.name === 'string' && template.name.length > 0 && template.name.length <= 100
      && Array.isArray(template.blocks) && template.blocks.length <= 50 && template.blocks.every(block =>
        block && ['heading','text','placeholder','customer','items','logo','line'].includes(block.type)
        && typeof (block.text ?? '') === 'string' && (block.text || '').length <= 4000
        && !/\{\{|\}\}|\{%|%\}|\{#|#\}/.test((block.text || '').replace(/\{\{\s*[a-zA-Z_][a-zA-Z0-9_.]*\s*\}\}/g, '')));
  }
  async function request(path, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const route = path.split('?')[0];
    let body;
    try { body = typeof options.body === 'string' ? JSON.parse(options.body) : {}; }
    catch { return json({detail:'Nieprawidłowy JSON.'}, 422); }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return json({detail:'Nieprawidłowe dane.'}, 422);
    let response;
    if (route === '/orders/' && method === 'GET') return json(orders);
    if (route === '/orders/status') return json({ ok: true, quarantined: 0 });
    if (route === '/orders/auth/status') return json({ authorized: true });
    if (route === '/orders/archive') return json(archive);
    // Match file operations before the template-id routes (export/import are not IDs).
    if (route === '/print/document-templates/export' && method === 'GET') {
      const id = new URLSearchParams(path.split('?')[1] || '').get('template_id');
      const templates = id === null ? documents.templates : documents.templates.filter(entry => entry.id === id);
      if (!templates.length) return json({detail:'Template not found'}, 404);
      const filename = id === null ? 'packing-templates.json' : `packing-template-${id}.json`;
      return json({format:'packing.document-templates',version:1,exported_at:new Date().toISOString(),
        templates:templates.map(({id,name,blocks}) => ({id,name,blocks}))}, 200,
      {'Content-Disposition':`attachment; filename="${filename}"`,'Cache-Control':'no-store'});
    }
    if (route === '/print/document-templates/import' && method === 'POST') {
      const data = body.data;
      if (!['rename','overwrite'].includes(body.on_conflict)
        || Object.keys(body).some(key => !['data','on_conflict'].includes(key))
        || !data || typeof data !== 'object' || Array.isArray(data)
        || Object.keys(data).some(key => !['format','version','exported_at','templates'].includes(key))
        || data.format !== 'packing.document-templates' || data.version !== 1
        || typeof data.exported_at !== 'string' || !Number.isFinite(Date.parse(data.exported_at))
        || !Array.isArray(data.templates) || !data.templates.length || data.templates.length > 10
        || !data.templates.every(template => validTemplate(template) && template.name.trim())) {
        return json({detail:'Nieprawidłowy plik szablonów.'}, 422);
      }
      const incoming = data.templates.map(template => ({...template,name:template.name.trim()}));
      if (new Set(incoming.map(template => template.name)).size !== incoming.length) {
        return json({detail:'Duplicate template names'}, 422);
      }
      // Stage the entire import so a failed limit check cannot partially change state.
      const settings = JSON.parse(JSON.stringify(documents));
      const imported = [];
      let nextCounter = counter;
      for (const template of incoming) {
        const item = {...template};
        const index = settings.templates.findIndex(entry => entry.name.trim() === template.name);
        if (index !== -1 && body.on_conflict === 'overwrite') {
          item.id = settings.templates[index].id;
          settings.templates[index] = item;
        } else {
          const names = new Set(settings.templates.map(entry => entry.name.trim()));
          let number = 2;
          while (names.has(item.name)) {
            const suffix = ` (${number++})`;
            item.name = template.name.slice(0,100 - suffix.length) + suffix;
          }
          do { item.id = `template-${++nextCounter}`; }
          while (settings.templates.some(entry => entry.id === item.id) || incoming.some(entry => entry.id === item.id));
          settings.templates.push(item);
        }
        imported.push(item.id);
      }
      if (settings.templates.length > 10) return json({detail:'Maximum 10 templates'}, 422);
      documents = settings; counter = nextCounter;
      return json({settings:documents,imported});
    }
    const collection = route.match(/^\/print\/document-templates\/([^/]+)(?:\/(duplicate|select))?$/);
    if (collection) {
      const id = decodeURIComponent(collection[1]);
      const template = documents.templates.find(entry => entry.id === id);
      if (!template) return json({detail:'Template not found'}, 404);
      const profile = documents.profiles.default;
      if (method === 'POST' && collection[2] === 'duplicate') {
        if (documents.templates.length >= 10) return json({detail:'Maximum 10 templates'}, 422);
        if (body.name !== undefined && (typeof body.name !== 'string' || !body.name.length || body.name.length > 100)) return json({detail:'Nieprawidłowa nazwa.'}, 422);
        const copy = JSON.parse(JSON.stringify(template));
        copy.id = `template-${++counter}`;
        copy.name = body.name || `${template.name.slice(0,95)} copy`;
        documents.templates.push(copy); profile.active_template_id = copy.id;
      } else if (method === 'POST' && collection[2] === 'select') profile.active_template_id = id;
      else if (method === 'DELETE' && !collection[2]) {
        if (documents.templates.length === 1) return json({detail:'Cannot delete the last template'}, 422);
        documents.templates = documents.templates.filter(entry => entry.id !== id);
        if (profile.active_template_id === id) profile.active_template_id = documents.templates[0].id;
      } else return json({detail:'Nieobsługiwana operacja demo.'}, 405);
      return json(documents);
    }
    if (route === '/print/document-settings') {
      if (method === 'POST') {
        if (!['upload','template'].includes(body.source) || !validTemplate(body.template)
          || !documents.templates.some(entry => entry.id === body.template.id)
          || (body.source === 'template' && !hasContent(body.template))) {
          return json({detail:'Nieprawidłowy szablon demo.'}, 422);
        }
        documents.templates[documents.templates.findIndex(entry => entry.id === body.template.id)] = body.template;
        documents.profiles.default.source = body.source;
        documents.profiles.default.active_template_id = body.template.id;
      }
      return json(documents);
    }
    const activeTemplate = documents.templates.find(entry => entry.id === documents.profiles.default.active_template_id);
    const customAvailable = documents.profiles.default.source === 'template' && hasContent(activeTemplate);
    if (route === '/print/custom-doc/info') return json({available:Boolean(customAvailable),source:documents.profiles.default.source,upload_available:false,size:0});
    if (route === '/print/document-preview' && method === 'POST' || route === '/print/custom-doc' && method === 'GET') {
      const orderId = route === '/print/document-preview' ? body.order_id : new URLSearchParams(path.split('?')[1] || '').get('order_id');
      if (!orderId) return json({detail:'Wybierz zamówienie.'}, 422);
      const order = orders.find(entry => entry.id === orderId);
      if (!order) return json({detail:'Nie znaleziono zamówienia.'}, 404);
      if (route === '/print/custom-doc' && !customAvailable) return json({detail:'Wybierz i zapisz szablon dokumentu.'}, 404);
      const template = route === '/print/document-preview' ? body.template : activeTemplate;
      if (!validTemplate(template) || !hasContent(template)) return json({detail:'Nieprawidłowy lub pusty szablon.'}, 422);
      return samplePdf(order, false, templateLines(order, template), true);
    }
    if (route === '/print/custom-doc' && method === 'DELETE') return json({status:'deleted'});
    if (route === '/print/custom-doc' || route === '/print/custom-doc/upload') {
      return json({ detail: 'W demo pliki nie są przesyłane. Wypróbuj przykładowy dokument w widoku Pakowanie.' }, 400);
    }
    if (route === '/print/shipment-settings') {
      if (method === 'POST') shipment = body;
      return json(shipment);
    }
    if (route === '/print/invoice-settings') {
      if (method === 'POST') invoice = body;
      return json(invoice);
    }
    if (route === '/picking-lists' && method === 'GET') return json(lists);
    if (route === '/picking-lists' && method === 'POST') {
      const ids = [...new Set(body.order_ids || [])];
      if (!ids.length || ids.some(id => !orders.some(order => order.id === id && order.status === 'pending'))) {
        return json({ detail: 'Wybierz oczekujące zamówienia.' }, 400);
      }
      const list = { id: `list-${++counter}`, name: body.name || `Lista #${counter}`, order_ids: ids };
      lists.push(list);
      orders.filter(order => ids.includes(order.id)).forEach(order => {
        order.status = 'picking'; order.picking_list_id = list.id;
      });
      response = json(list);
    } else if (route.startsWith('/picking-lists/')) {
      const [, , id, action] = route.split('/');
      const list = lists.find(entry => entry.id === id);
      if (!list) return json({ detail: 'Nie znaleziono listy.' }, 404);
      if (method === 'PATCH') list.name = String(body.name || list.name).slice(0, 120);
      else if (method === 'POST' && ['start-packing', 'revert'].includes(action)) {
        orders.filter(order => list.order_ids.includes(order.id)).forEach(order => {
          order.status = action === 'revert' ? 'pending' : 'packing';
          if (action === 'revert') order.picking_list_id = null;
        });
        if (action === 'revert') lists = lists.filter(entry => entry.id !== id);
      } else return json({ detail: 'Nieobsługiwana operacja demo.' }, 400);
      response = json({ status: 'ok' });
    } else if (route === '/orders/sync' && method === 'POST') {
      const order = initialOrders()[syncCounter++ % 5];
      order.id = `sync-${syncCounter}`; order.allegro_id = `DEMO-SYNC-${syncCounter}`;
      orders.push(order); response = json({ added: 1 });
    } else if (route === '/orders/zakoncz-dzien' && method === 'POST') {
      const done = orders.filter(order => order.status === 'done');
      done.forEach(order => { archive.push({ ...order, archived_at: new Date().toISOString() }); detach(order.id); });
      orders = orders.filter(order => order.status !== 'done');
      response = json({ archived: done.length });
    } else if (/^\/orders\/[^/]+\/parcel-size$/.test(route) && method === 'PATCH') {
      const order = orders.find(entry => entry.id === route.split('/')[2]);
      if (!order) return json({detail:'Nie znaleziono zamówienia.'}, 404);
      if (order.shipment_id) return json({detail:'Przesyłka ma już etykietę.'}, 409);
      try { return json({parcel_size:setParcelSize(order.id, body.parcel_size)}); }
      catch (error) { return json({detail:error.message}, 422); }
    } else if (/^\/print\/orders\/[^/]+\/shipment$/.test(route)) {
      const order = orders.find(entry => entry.id === route.split('/')[3]);
      return order ? json({shipment_id:order.shipment_id,tracking_number:order.tracking_number || null}) : json({detail:'Nie znaleziono zamówienia.'},404);
    } else if (/^\/orders\/[^/]+\/(done|undo-done|revert-pending)$/.test(route) && method === 'POST') {
      const [, , id, action] = route.split('/');
      const order = orders.find(entry => entry.id === id);
      if (!order) return json({ detail: 'Nie znaleziono zamówienia.' }, 404);
      order.status = { done: 'done', 'undo-done': 'packing', 'revert-pending': 'pending' }[action];
      if (action === 'revert-pending') { order.picking_list_id = null; detach(id); }
      response = json({ status: order.status });
    } else if (/^\/print\/orders\/[^/]+\/(label|combined|invoice|document)$/.test(route) || /^\/print\/combined\/[^/]+$/.test(route)) {
      const parts = route.split('/');
      const [id,type] = parts[2] === 'combined' ? [parts[3],'combined'] : [parts[3],parts[4]];
      const order = orders.find(entry => entry.id === id);
      if (!order) return json({ detail: 'Nie znaleziono zamówienia.' }, 404);
      if (type === 'label') {
        if (method === 'GET') {
          return order.shipment_id ? samplePdf(order, true) : json({detail:'Shipment has not been created.'}, 409);
        }
        if (method !== 'POST') return json({detail:'Nieobsługiwana operacja demo.'}, 405);
        const params = new URLSearchParams(path.split('?')[1] || '');
        for (const key of ['length','width','height','weight']) {
          if (params.has(key) && (!(Number(params.get(key)) > 0) || Number(params.get(key)) > (key === 'weight' ? 100 : 500))) {
            return json({detail:'Nieprawidłowe wymiary lub waga.'}, 422);
          }
        }
        if (!order.shipment_id && order.delivery_type === 'inpost_locker' && !['A','B','C'].includes(order.parcel_size)) return json({detail:'Wybierz gabaryt A, B lub C.'}, 400);
        if (!order.shipment_id) {
          order.shipment_id = `sample-${id}`;
          order.tracking_number = `DEMO-TRACK-${id}`;
        }
        response = json({shipment_id:order.shipment_id,tracking_number:order.tracking_number});
      } else {
        if (method !== 'GET') return json({detail:'Nieobsługiwana operacja demo.'}, 405);
        response = samplePdf(order, false, type === 'combined' && customAvailable ? templateLines(order, activeTemplate) : []);
      }
    } else return json({ detail: 'Ta funkcja wymaga pełnej wersji Weles. Demo działa wyłącznie na przykładowych danych.' }, 400);
    updateGuide();
    return response;
  }
  const steps = [
    ['Wybierz produkty do zebrania', 'W kolejce Oczekujące zaznacz produkt, a następnie kliknij „Utwórz listę kompletowania”. Powiązane zamówienia trafią na jedną listę.', 'pending'],
    ['Przygotuj zamówienia razem', 'Lista zbiera produkty z wybranych zamówień. Możesz zmienić jej nazwę lub ją wydrukować. Kliknij „Pakuj →”, aby przejść dalej.', 'picking'],
    ['Spakuj pierwsze zamówienie', 'Sprawdź produkty. Dla Paczkomat InPost wybierz gabaryt A, B lub C; dla kuriera podaj wymiary i wagę. Otwórz przykładową etykietę lub dokument, a następnie kliknij „GOTOWE”. Wszystkie wydruki są oznaczone jako demo.', 'packing'],
    ['Zamknij dzień pracy', 'Zamówienie jest w kolejce Gotowe. Kliknij „Zakończ dzień”, aby przenieść gotowe zamówienia do archiwum.', 'done'],
    ['Gotowe — znasz cały proces', 'Od zamówienia do archiwum. Eksperymentuj dalej, pobierz kolejne przykładowe zamówienie lub uruchom demo od początku.', 'settings'],
  ];
  function updateGuide() {
    const panel = global.document?.getElementById('demo-guide');
    if (!panel || !tourActive) return;
    const step = archive.length ? 4 : orders.some(order => order.status === 'done') ? 3
      : orders.some(order => order.status === 'packing') ? 2 : lists.length ? 1 : 0;
    const [title, description, queue] = steps[step];
    panel.querySelector('#demo-step').textContent = `PRZEWODNIK · ${step + 1} / 5`;
    panel.querySelector('#demo-guide-title').textContent = title;
    panel.querySelector('#demo-guide-copy').textContent = description;
    panel.querySelector('#demo-progress').value = step + 1;
    const go = panel.querySelector('#demo-go');
    go.textContent = step === 4 ? 'Zobacz archiwum' : 'Pokaż ten etap';
    go.onclick = () => {
      if (step === 4) state.settingsTab = 'archive';
      renderQueue(queue);
    };
  }
  function rememberWelcome() {
    try { global.sessionStorage.setItem('weles-demo-welcome', 'seen'); } catch { /* Private browsing still works. */ }
  }
  function mount() {
    global.document.body.classList.add('demo-mode');
    const header = global.document.createElement('header');
    header.className = 'demo-bar';
    header.innerHTML = `<a class="demo-brand" href="./">Weles <span>Demo</span></a>
      <p>Fikcyjne zamówienia. Bez konta. Wypróbuj cały proces.</p>
      <div><button id="demo-tour" type="button">Przewodnik</button><button id="demo-reset" type="button">Zacznij od nowa</button>
      <a href="https://github.com/majorlupa/packing" target="_blank" rel="noopener noreferrer">GitHub</a></div>`;
    global.document.body.prepend(header);
    const guide = global.document.createElement('section');
    guide.id = 'demo-guide'; guide.className = 'demo-guide hidden';
    guide.setAttribute('aria-label', 'Przewodnik po demo');
    guide.innerHTML = `<div class="demo-guide-top"><span id="demo-step"></span><button id="demo-skip-guide" type="button">Pomiń przewodnik</button></div>
      <div aria-live="polite"><h2 id="demo-guide-title"></h2><p id="demo-guide-copy"></p></div>
      <div class="demo-guide-bottom"><progress id="demo-progress" max="5" value="1" aria-label="Postęp przewodnika"></progress>
      <button id="demo-go" class="btn btn-secondary" type="button">Pokaż ten etap</button></div>`;
    global.document.getElementById('content').before(guide);
    const dialog = global.document.createElement('dialog');
    dialog.className = 'demo-welcome';
    dialog.setAttribute('aria-labelledby', 'demo-welcome-title');
    dialog.innerHTML = `<p class="demo-eyebrow">Weles / interaktywne demo</p><h1 id="demo-welcome-title">Od zamówienia<br>do gotowej paczki.</h1>
      <p class="demo-lead">Zobacz, jak wygląda dzień pracy z Weles. Przejdź przez kompletowanie i pakowanie na pięciu przykładowych zamówieniach.</p>
      <ol class="demo-flow"><li><span>01</span>Wybierz zamówienia</li><li><span>02</span>Zbierz produkty</li><li><span>03</span>Spakuj i zakończ</li></ol>
      <div class="demo-welcome-actions"><button id="demo-start" class="btn btn-primary" autofocus type="button">Rozpocznij przewodnik</button>
      <button id="demo-skip" class="btn btn-secondary" type="button">Pomiń — odkryję samodzielnie</button></div>
      <p class="demo-footnote">Bez logowania i połączenia z Allegro. Zmiany znikną po odświeżeniu. Etykiety i dokumenty są przykładowe.</p>`;
    global.document.body.append(dialog);
    function setTour(active) {
      tourActive = active;
      guide.classList.toggle('hidden', !active);
      global.document.body.classList.toggle('demo-guided', active);
      updateGuide();
    }
    function dismiss(active) {
      rememberWelcome(); dialog.close(); setTour(active);
      global.document.getElementById(active ? 'demo-go' : 'demo-tour').focus();
    }
    dialog.querySelector('#demo-start').onclick = () => dismiss(true);
    dialog.querySelector('#demo-skip').onclick = () => dismiss(false);
    dialog.addEventListener('cancel', event => { event.preventDefault(); dismiss(false); });
    global.document.getElementById('demo-tour').onclick = () => { setTour(true); global.document.getElementById('demo-go').focus(); };
    global.document.getElementById('demo-skip-guide').onclick = () => { setTour(false); global.document.getElementById('demo-tour').focus(); };
    global.document.getElementById('demo-reset').onclick = async () => {
      if (!global.confirm('Przywrócić pięć przykładowych zamówień i rozpocząć od nowa?')) return;
      reset(); state.packingIndex = 0; state.currentCourier = null; state.currentQueue = 'pending';
      state.selectedOrderIds.clear(); await fetchAll(); setTour(true);
    };
    let seen = false;
    try { seen = global.sessionStorage.getItem('weles-demo-welcome') === 'seen'; } catch { /* Optional storage. */ }
    if (!seen) dialog.showModal();
  }
  global.WelesDemo = { request, reset, mount, setParcelSize };
})(globalThis);
