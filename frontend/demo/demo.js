/* Browser-only sample data. Every demo request terminates here; no network fallback. */
(function (global) {
  'use strict';
  const initialOrders = () => [
    ['101', 'Anna Demo', 'Warszawa', 'InPost', [['Kubek ceramiczny — szałwia', 2, 39], ['Notes w kropki A5', 1, 24]]],
    ['102', 'Marek Demo', 'Kraków', 'InPost', [['Kubek ceramiczny — szałwia', 1, 39]]],
    ['103', 'Julia Demo', 'Gdańsk', 'DPD', [['Torba bawełniana', 2, 29], ['Notes w kropki A5', 1, 24]]],
    ['104', 'Piotr Demo', 'Poznań', 'DPD', [['Świeca sojowa — las', 1, 49]]],
    ['105', 'Ewa Demo', 'Wrocław', 'InPost', [['Notes w kropki A5', 3, 24]]],
  ].map(([id, buyer, city, courier, items]) => ({
    id: `demo-${id}`, allegro_id: `DEMO-${id}`, buyer_name: buyer,
    buyer_address: `ul. Przykładowa 1, ${city} (dane fikcyjne)`,
    courier, pickup_point: courier === 'InPost' ? 'DEMO01M' : null,
    status: 'pending', picking_list_id: null, shipment_id: null,
    items: items.map(([name, quantity, unit_price]) => ({ name, quantity, unit_price })),
  }));
  let orders, lists, archive, shipment, invoice, counter, syncCounter;
  let tourActive = false;
  const json = (body, status = 200) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });
  function reset() {
    orders = initialOrders(); lists = []; archive = []; counter = 0; syncCounter = 0;
    shipment = { sender: {}, package: { length: 30, width: 20, height: 15, weight: 1, page_size: 'A6' } };
    invoice = { free_text: 'Dziękujemy za zakup! — Weles DEMO' };
  }
  reset();
  function detach(id) {
    lists.forEach(list => { list.order_ids = list.order_ids.filter(oid => oid !== id); });
    lists = lists.filter(list => list.order_ids.length);
  }
  // A real, minimal PDF with an unmistakable sample watermark; no usable shipping barcode.
  function samplePdf(order, label) {
    const lines = ['WELES / DEMO', label ? 'SAMPLE SHIPPING LABEL' : 'SAMPLE ORDER DOCUMENT',
      'NOT VALID FOR SHIPPING OR ACCOUNTING', order.allegro_id,
      ...order.items.map(item => `${item.quantity} x ${item.name}`)];
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
    return new Response(pdf, { headers: { 'Content-Type': 'application/pdf' } });
  }
  async function request(path, options = {}) {
    const method = options.method || 'GET';
    const route = path.split('?')[0];
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : {};
    let response;
    if (route === '/orders/' && method === 'GET') return json(orders);
    if (route === '/orders/status') return json({ ok: true, quarantined: 0 });
    if (route === '/orders/auth/status') return json({ authorized: true });
    if (route === '/orders/archive') return json(archive);
    if (route === '/print/custom-doc/info') return json({ available: false });
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
    } else if (/^\/orders\/[^/]+\/(done|undo-done|revert-pending)$/.test(route) && method === 'POST') {
      const [, , id, action] = route.split('/');
      const order = orders.find(entry => entry.id === id);
      if (!order) return json({ detail: 'Nie znaleziono zamówienia.' }, 404);
      order.status = { done: 'done', 'undo-done': 'packing', 'revert-pending': 'pending' }[action];
      if (action === 'revert-pending') { order.picking_list_id = null; detach(id); }
      response = json({ status: order.status });
    } else if (/^\/print\/orders\/[^/]+\/(label|combined|invoice)$/.test(route)) {
      const [, , , id, type] = route.split('/');
      const order = orders.find(entry => entry.id === id);
      if (!order) return json({ detail: 'Nie znaleziono zamówienia.' }, 404);
      if (type === 'label') order.shipment_id = `sample-${id}`;
      response = samplePdf(order, type === 'label');
    } else return json({ detail: 'Ta funkcja wymaga pełnej wersji Weles. Demo działa wyłącznie na przykładowych danych.' }, 400);
    updateGuide();
    return response;
  }
  const steps = [
    ['Wybierz produkty do zebrania', 'W kolejce Oczekujące zaznacz produkt, a następnie kliknij „Utwórz listę kompletowania”. Powiązane zamówienia trafią na jedną listę.', 'pending'],
    ['Przygotuj zamówienia razem', 'Lista zbiera produkty z wybranych zamówień. Możesz zmienić jej nazwę lub ją wydrukować. Kliknij „Pakuj →”, aby przejść dalej.', 'picking'],
    ['Spakuj pierwsze zamówienie', 'Sprawdź produkty i wymiary paczki. Otwórz przykładową etykietę lub dokument, a następnie kliknij „GOTOWE”. Wszystkie wydruki są oznaczone jako demo.', 'packing'],
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
    header.innerHTML = `<a class="demo-brand" href="./">Weles <span>DEMO</span></a>
      <p>Fikcyjne zamówienia. Bez konta. Wypróbuj cały proces.</p>
      <div><button id="demo-tour" type="button">Przewodnik</button><button id="demo-reset" type="button">Zacznij od nowa</button>
      <a href="https://github.com/majorlupa/packing" target="_blank" rel="noopener noreferrer">GitHub ↗</a></div>`;
    global.document.body.prepend(header);
    const guide = global.document.createElement('section');
    guide.id = 'demo-guide'; guide.className = 'demo-guide hidden';
    guide.setAttribute('aria-label', 'Przewodnik po demo');
    guide.innerHTML = `<div class="demo-guide-top"><span id="demo-step"></span><button id="demo-skip-guide" type="button">Pomiń przewodnik ×</button></div>
      <div aria-live="polite"><h2 id="demo-guide-title"></h2><p id="demo-guide-copy"></p></div>
      <div class="demo-guide-bottom"><progress id="demo-progress" max="5" value="1" aria-label="Postęp przewodnika"></progress>
      <button id="demo-go" class="btn btn-secondary" type="button">Pokaż ten etap</button></div>`;
    global.document.getElementById('content').before(guide);
    const dialog = global.document.createElement('dialog');
    dialog.className = 'demo-welcome';
    dialog.setAttribute('aria-labelledby', 'demo-welcome-title');
    dialog.innerHTML = `<p class="demo-eyebrow">WELES / INTERAKTYWNE DEMO</p><h1 id="demo-welcome-title">Od zamówienia<br>do gotowej paczki.</h1>
      <p class="demo-lead">Zobacz, jak wygląda dzień pracy z Weles. Przejdź przez kompletowanie i pakowanie na pięciu przykładowych zamówieniach.</p>
      <ol class="demo-flow"><li><span>01</span>Wybierz zamówienia</li><li><span>02</span>Zbierz produkty</li><li><span>03</span>Spakuj i zakończ</li></ol>
      <div class="demo-welcome-actions"><button id="demo-start" class="btn btn-primary" autofocus type="button">Pokaż mi, jak to działa →</button>
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
  global.WelesDemo = { request, reset, mount };
})(globalThis);
