const API = '/api';

let state = {
  orders: [],         // all orders from backend
  pickingLists: [],   // all picking lists
  currentQueue: 'pending',
  currentCourier: null, // courier filter for pending view
  selectedOrderIds: new Set(),  // for pending → picking list creation
  packingQueue: [],      // orders currently in packing carousel
  packingIndex: 0,       // which card is shown
  packingDirection: null, // 'next' | 'prev' | null
  settingsTab: 'config',
  customDocAvailable: false,
};

// ---- Fetch ----

async function fetchAll() {
  const [ordersRes, plRes] = await Promise.all([
    fetch(`${API}/orders/`),
    fetch(`${API}/picking-lists`),
  ]);
  state.orders = await ordersRes.json();
  state.pickingLists = await plRes.json();
  updateBadges();
  renderQueue(state.currentQueue);
}

// ---- Badges ----

function updateBadges() {
  const counts = { pending: 0, picking: 0, packing: 0, done: 0 };
  state.orders.forEach(o => counts[o.status]++);
  Object.entries(counts).forEach(([k, v]) => {
    document.getElementById(`count-${k}`).textContent = v;
  });

  // Inject courier sub-items under Oczekujące
  const pendingOrders = state.orders.filter(o => o.status === 'pending');
  const courierCounts = {};
  pendingOrders.forEach(o => {
    const c = o.courier || 'Inny';
    courierCounts[c] = (courierCounts[c] || 0) + 1;
  });

  const existing = document.getElementById('courier-subnav');
  if (existing) existing.remove();

  const couriers = Object.keys(courierCounts);
  if (couriers.length <= 1) return; // no point showing sub-nav for single courier

  const ul = document.createElement('ul');
  ul.id = 'courier-subnav';
  couriers.forEach(courier => {
    const li = document.createElement('li');
    li.className = 'courier-nav-item' + (state.currentCourier === courier ? ' active' : '');
    li.innerHTML = `${courier} <span class="badge badge-dim">${courierCounts[courier]}</span>`;
    li.addEventListener('click', (e) => {
      e.stopPropagation();
      state.currentCourier = state.currentCourier === courier ? null : courier;
      updateBadges();
      renderQueue('pending');
    });
    ul.appendChild(li);
  });

  const pendingItem = document.querySelector('[data-queue="pending"]');
  pendingItem.after(ul);
}

// ---- Routing ----

function renderQueue(queue) {
  state.currentQueue = queue;
  if (queue !== 'pending') state.currentCourier = null;
  document.querySelectorAll('.queue-item').forEach(el => {
    el.classList.toggle('active', el.dataset.queue === queue);
  });
  const btnSettings = document.getElementById('btn-settings');
  if (btnSettings) btnSettings.classList.toggle('active', queue === 'settings');
  const content = document.getElementById('content');

  if (queue === 'pending') renderPending(content);
  else if (queue === 'picking') renderPicking(content);
  else if (queue === 'packing') renderPacking(content);
  else if (queue === 'done') renderDone(content);
  else if (queue === 'settings') renderSettings(content);
}

// ---- Pending view ----

function renderPending(el) {
  const orders = state.orders.filter(o =>
    o.status === 'pending' &&
    (!state.currentCourier || (o.courier || 'Inny') === state.currentCourier)
  );
  state.selectedOrderIds.clear();

  el.innerHTML = `
    <h2>Oczekujące zamówienia</h2>
    <div id="pending-toolbar">
      <button class="btn btn-primary" id="btn-create-pl" disabled>
        Utwórz listę kompletowania
      </button>
      <span id="selected-count" style="font-size:13px;color:#888">Zaznacz produkty</span>
    </div>
    <div class="order-list" id="order-list"></div>
  `;

  const list = el.querySelector('#order-list');

  if (!orders.length) {
    list.innerHTML = '<p class="empty">Brak oczekujących zamówień. Kliknij "Pobierz zamówienia".</p>';
    return;
  }

  // Group orders by courier
  const byCourier = {};
  orders.forEach(order => {
    const courier = order.courier || 'Inny';
    if (!byCourier[courier]) byCourier[courier] = [];
    byCourier[courier].push(order);
  });

  // Track which products are selected (globally across couriers)
  const selectedProducts = new Set();
  const productMap = {};

  Object.entries(byCourier).forEach(([courier, courierOrders]) => {
    // Section header — only show when viewing all couriers
    if (!state.currentCourier) {
      const header = document.createElement('div');
      header.className = 'courier-header';
      header.textContent = courier;
      list.appendChild(header);
    }

    // Aggregate by product name within this courier
    const courierProductMap = {};
    courierOrders.forEach(order => {
      order.items.forEach(item => {
        if (!courierProductMap[item.name]) courierProductMap[item.name] = { qty: 0, orderIds: new Set() };
        courierProductMap[item.name].qty += item.quantity;
        courierProductMap[item.name].orderIds.add(order.id);
        // Also track globally for order ID collection
        if (!productMap[item.name]) productMap[item.name] = { qty: 0, orderIds: new Set() };
        productMap[item.name].qty += item.quantity;
        productMap[item.name].orderIds.add(order.id);
      });
    });

    Object.entries(courierProductMap).forEach(([name, data]) => {
      const txCount = data.orderIds.size;
      const card = document.createElement('div');
      card.className = 'order-card';
      card.innerHTML = `
        <input type="checkbox" />
        <div class="order-info">
          <div class="buyer">${data.qty}x ${name}</div>
          <div class="address" style="margin-top:4px">${txCount} ${txCount === 1 ? 'transakcja' : txCount < 5 ? 'transakcje' : 'transakcji'}</div>
        </div>
      `;
      const cb = card.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) {
          selectedProducts.add(name);
          card.classList.add('selected');
        } else {
          selectedProducts.delete(name);
          card.classList.remove('selected');
        }

        state.selectedOrderIds.clear();
        selectedProducts.forEach(pName => {
          productMap[pName].orderIds.forEach(id => state.selectedOrderIds.add(id));
        });

        const n = selectedProducts.size;
        document.getElementById('btn-create-pl').disabled = n === 0;
        document.getElementById('selected-count').textContent =
          n ? `${n} ${n === 1 ? 'produkt' : 'produkty'} — ${state.selectedOrderIds.size} zamówień` : 'Zaznacz produkty';
      });
      list.appendChild(card);
    });
  });

  el.querySelector('#btn-create-pl').addEventListener('click', async () => {
    await fetch(`${API}/picking-lists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: '', order_ids: [...state.selectedOrderIds] }),
    });
    await fetchAll();
    renderQueue('picking');
  });
}

// ---- Picking view ----

function renderPicking(el) {
  const pickingOrders = state.orders.filter(o => o.status === 'picking');

  el.innerHTML = `<h2>Kompletowanie</h2><div class="order-list" id="pl-list"></div>`;
  const list = el.querySelector('#pl-list');

  if (!state.pickingLists.length) {
    list.innerHTML = '<p class="empty">Brak aktywnych list kompletowania.</p>';
    return;
  }

  state.pickingLists.forEach(pl => {
    const orderCount = pl.order_ids.length;
    const card = document.createElement('div');
    card.className = 'picking-card';
    card.innerHTML = `
      <div class="pl-info">
        <div class="pl-name-wrap">
          <span class="pl-name" data-id="${pl.id}">${pl.name}</span>
          <span class="pl-count">${orderCount} zamówień</span>
        </div>
        <div class="pl-rename hidden" data-id="${pl.id}">
          <input class="pl-rename-input" type="text" value="${pl.name}" />
          <button class="btn btn-primary btn-rename-confirm" data-id="${pl.id}">Zapisz</button>
          <button class="btn btn-secondary btn-rename-cancel">Anuluj</button>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn-icon-red btn-revert" data-id="${pl.id}" title="Cofnij do oczekujących">↩</button>
        <button class="btn btn-secondary btn-rename-toggle" data-id="${pl.id}">✏ Zmień nazwę</button>
        <button class="btn btn-secondary btn-print-pl" data-id="${pl.id}">🖨 Drukuj listę</button>
        <button class="btn btn-primary btn-start-pack" data-id="${pl.id}">Pakuj →</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll('.btn-revert').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch(`${API}/picking-lists/${btn.dataset.id}/revert`, { method: 'POST' });
      await fetchAll();
      renderQueue('picking');
    });
  });

  list.querySelectorAll('.btn-rename-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.picking-card');
      card.querySelector('.pl-name-wrap').classList.toggle('hidden');
      const renameDiv = card.querySelector('.pl-rename');
      renameDiv.classList.toggle('hidden');
      if (!renameDiv.classList.contains('hidden')) {
        const input = renameDiv.querySelector('.pl-rename-input');
        input.addEventListener('keydown', e => e.stopPropagation());
        input.focus();
        input.select();
      }
    });
  });

  list.querySelectorAll('.btn-rename-cancel').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.picking-card');
      card.querySelector('.pl-name-wrap').classList.remove('hidden');
      card.querySelector('.pl-rename').classList.add('hidden');
    });
  });

  list.querySelectorAll('.btn-rename-confirm').forEach(btn => {
    btn.addEventListener('click', async () => {
      const card = btn.closest('.picking-card');
      const newName = card.querySelector('.pl-rename-input').value.trim();
      if (!newName) return;
      await fetch(`${API}/picking-lists/${btn.dataset.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, order_ids: [] }),
      });
      await fetchAll();
      renderQueue('picking');
    });
  });

  list.querySelectorAll('.btn-start-pack').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch(`${API}/picking-lists/${btn.dataset.id}/start-packing`, { method: 'POST' });
      await fetchAll();
      renderQueue('packing');
    });
  });

  list.querySelectorAll('.btn-print-pl').forEach(btn => {
    btn.addEventListener('click', () => printPickingList(btn.dataset.id));
  });
}

function printPickingList(plId) {
  const pl = state.pickingLists.find(p => p.id === plId);
  if (!pl) return;

  const orders = state.orders.filter(o => pl.order_ids.includes(o.id));

  // Consolidate items across orders
  const consolidated = {};
  orders.forEach(o => {
    o.items.forEach(item => {
      consolidated[item.name] = (consolidated[item.name] || 0) + item.quantity;
    });
  });

  const rows = Object.entries(consolidated).map(([name, qty]) =>
    `<tr><td>${name}</td><td>${qty}</td></tr>`
  ).join('');

  const win = window.open('', '_blank');
  win.document.write(`<!DOCTYPE html><html><head><title>${pl.name}</title>
    <style>body{font-family:Arial;margin:40px}table{width:100%;border-collapse:collapse}
    td,th{border:1px solid #ccc;padding:8px}th{background:#eee}</style></head>
    <body><h2>Lista: ${pl.name}</h2>
    <table><thead><tr><th>Produkt</th><th>Ilość</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <script>window.onload=()=>window.print()<\/script></body></html>`);
  win.document.close();
}

// ---- Packing view ----

function renderPacking(el) {
  state.packingQueue = state.orders.filter(o => o.status === 'packing');
  state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
  renderPackingCard(el);
}

function renderPackingCard(el) {
  const orders = state.packingQueue;

  el.innerHTML = `<h2>Pakowanie</h2><div id="packing-view"></div>`;
  const view = el.querySelector('#packing-view');

  if (!orders.length) {
    view.innerHTML = '<p class="empty">Brak zamówień do pakowania. Przesuń listę kompletowania do pakowania.</p>';
    return;
  }

  const idx = state.packingIndex;
  const order = orders[idx];

  const animClass = state.packingDirection === 'next' ? 'animate-next'
                  : state.packingDirection === 'prev' ? 'animate-prev' : '';
  state.packingDirection = null;

  view.innerHTML = `
    <div class="pack-nav">
      <button class="btn btn-secondary" id="btn-prev" ${idx === 0 ? 'disabled' : ''}>← Poprzednie</button>
      <span>${idx + 1} / ${orders.length}</span>
      <button class="btn btn-secondary" id="btn-next" ${idx === orders.length - 1 ? 'disabled' : ''}>Następne →</button>
    </div>
    <div class="pack-card ${animClass}">
      <button class="btn-icon-red btn-revert-pending" id="btn-revert-pending" title="Cofnij do oczekujących">↩</button>
      <div class="buyer">${order.buyer_name}</div>
      <div class="address">${order.buyer_address}</div>
      <div class="allegro-id">
        <span class="allegro-id-label">ID:</span>
        <span class="allegro-id-value">${order.allegro_id}</span>
        <button class="btn-copy" title="Kopiuj ID" onclick="navigator.clipboard.writeText('${order.allegro_id}').then(()=>{this.textContent='✓';setTimeout(()=>this.textContent='⧉',1200)})">⧉</button>
      </div>
      <div class="items">${order.items.map(i => `${i.quantity}x ${i.name}`).join('<br/>')}</div>
      <div class="pack-buttons">
        <button class="btn btn-label" id="btn-label">🖨 Etykieta kurierska</button>
        <button class="btn btn-invoice" id="btn-invoice">🖨 Dokument</button>
        <button class="btn btn-done" id="btn-done">✓ GOTOWE</button>
      </div>
    </div>
  `;

  view.querySelector('#btn-revert-pending').addEventListener('click', async () => {
    await fetch(`${API}/orders/${order.id}/revert-pending`, { method: 'POST' });
    await fetchAll();
    state.packingQueue = state.orders.filter(o => o.status === 'packing');
    state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
    renderPackingCard(document.getElementById('content'));
  });

  let labelClicked = false;

  view.querySelector('#btn-prev').addEventListener('click', () => {
    state.packingDirection = 'prev';
    state.packingIndex--;
    renderPackingCard(document.getElementById('content'));
  });
  view.querySelector('#btn-next').addEventListener('click', () => {
    state.packingDirection = 'next';
    state.packingIndex++;
    renderPackingCard(document.getElementById('content'));
  });
  view.querySelector('#btn-label').addEventListener('click', () => {
    labelClicked = true;
    view.querySelector('#btn-label').classList.add('printed');
    view.querySelector('#btn-label').textContent = '✓ Etykieta kurierska';
    window.open(`${API}/print/orders/${order.id}/label`, '_blank');
  });
  view.querySelector('#btn-invoice').addEventListener('click', () => {
    window.open(`${API}/print/orders/${order.id}/combined`, '_blank');
  });
  view.querySelector('#btn-done').addEventListener('click', async () => {
    if (!labelClicked) {
      const ok = confirm('Etykieta nie wydrukowana — czy na pewno chcesz oznaczyć jako gotowe?');
      if (!ok) return;
    }
    const card = view.querySelector('.pack-card');
    card.classList.add('animate-done');
    await new Promise(r => setTimeout(r, 430));
    await fetch(`${API}/orders/${order.id}/done`, { method: 'POST' });
    await fetchAll();
    state.packingQueue = state.orders.filter(o => o.status === 'packing');
    state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
    state.packingDirection = null;
    renderPackingCard(document.getElementById('content'));
  });
}

// ---- Done view ----

function renderDone(el) {
  const orders = state.orders.filter(o => o.status === 'done');
  el.innerHTML = `<h2>Gotowe (${orders.length})</h2><div class="order-list" id="done-list"></div>`;
  const list = el.querySelector('#done-list');

  if (!orders.length) {
    list.innerHTML = '<p class="empty">Brak ukończonych zamówień.</p>';
    return;
  }

  orders.forEach(order => {
    const card = document.createElement('div');
    card.className = 'order-card';
    const trackingHtml = order.tracking_number
      ? `<div class="tracking-number">📦 ${order.tracking_number}</div>`
      : `<div class="tracking-number missing">— brak numeru śledzenia —</div>`;
    card.innerHTML = `
      <div class="order-info">
        <div class="buyer">${order.buyer_name}</div>
        <div class="address">${order.buyer_address}</div>
        <div class="allegro-id">
          <span class="allegro-id-label">ID:</span>
          <span class="allegro-id-value">${order.allegro_id}</span>
          <button class="btn-copy" title="Kopiuj ID" onclick="navigator.clipboard.writeText('${order.allegro_id}').then(()=>{this.textContent='✓';setTimeout(()=>this.textContent='⧉',1200)})">⧉</button>
        </div>
        ${trackingHtml}
      </div>
      <button class="btn btn-secondary btn-undo" data-id="${order.id}">↩ Cofnij</button>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll('.btn-undo').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch(`${API}/orders/${btn.dataset.id}/undo-done`, { method: 'POST' });
      await fetchAll();
    });
  });
}

// ---- Settings view ----

function renderSettings(el) {
  const activeTab = state.settingsTab;

  el.innerHTML = `
    <h2>Ustawienia</h2>
    <div class="settings-tabs">
      <button class="settings-tab ${activeTab === 'config'    ? 'active' : ''}" data-tab="config">Konfiguracja</button>
      <button class="settings-tab ${activeTab === 'documents' ? 'active' : ''}" data-tab="documents">Dokumenty</button>
      <button class="settings-tab ${activeTab === 'archive'   ? 'active' : ''}" data-tab="archive">Archiwum</button>
    </div>
    <div id="settings-panel"></div>
  `;

  el.querySelectorAll('.settings-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      state.settingsTab = btn.dataset.tab;
      renderSettings(el);
    });
  });

  const panel = el.querySelector('#settings-panel');
  if (activeTab === 'config')    renderSettingsConfig(panel);
  if (activeTab === 'documents') renderSettingsDocuments(panel);
  if (activeTab === 'archive')   renderSettingsArchive(panel);
}

async function renderSettingsConfig(panel) {
  const res  = await fetch(`${API}/config/`);
  const data = await res.json();

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc">Plik konfiguracyjny API (.env)</p>
      <textarea id="config-content" spellcheck="false">${data.content}</textarea>
      <p id="config-note" class="settings-note hidden"></p>
      <div class="settings-actions">
        <button class="btn btn-primary" id="config-save">Zapisz</button>
      </div>
    </div>
  `;

  panel.querySelector('#config-save').addEventListener('click', async () => {
    const content = panel.querySelector('#config-content').value;
    const res  = await fetch(`${API}/config/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    const result = await res.json();
    const note = panel.querySelector('#config-note');
    note.textContent = '✓ ' + result.note;
    note.classList.remove('hidden');
  });
}

async function renderSettingsDocuments(panel) {
  const [invRes, docRes] = await Promise.all([
    fetch(`${API}/print/invoice-settings`),
    fetch(`${API}/print/custom-doc/info`),
  ]);
  const data = await invRes.json();
  const docInfo = await docRes.json();

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc">Zaznacz pola które mają pojawiać się na wydruku.</p>
      <div class="settings-checks">
        <label><input type="checkbox" id="inv-buyer-name"    ${(data.show_buyer_name    ?? true) ? 'checked' : ''}> Nazwa kupującego</label>
        <label><input type="checkbox" id="inv-buyer-address" ${(data.show_buyer_address ?? true) ? 'checked' : ''}> Adres kupującego</label>
        <label><input type="checkbox" id="inv-items"         ${(data.show_items         ?? true) ? 'checked' : ''}> Lista produktów</label>
        <label><input type="checkbox" id="inv-price"         ${(data.show_price         ?? true) ? 'checked' : ''}> Cena za sztukę</label>
        <label><input type="checkbox" id="inv-courier"       ${(data.show_courier       ?? true) ? 'checked' : ''}> Kurier</label>
        <label><input type="checkbox" id="inv-pickup-point"  ${(data.show_pickup_point  ?? true) ? 'checked' : ''}> Punkt odbioru (paczkomat)</label>
        <label><input type="checkbox" id="inv-allegro-id"    ${(data.show_allegro_id    ?? true) ? 'checked' : ''}> Numer zamówienia Allegro</label>
      </div>
      <div class="settings-field">
        <label>Tekst własny (maks. 160 znaków)</label>
        <textarea id="inv-free-text" rows="2" maxlength="160" placeholder="np. Dziękujemy za zakup!">${data.free_text || ''}</textarea>
        <span id="inv-free-text-count" class="settings-char-count">${(data.free_text || '').length} / 160</span>
      </div>
      <p id="invoice-settings-note" class="settings-note hidden"></p>
      <div class="settings-actions">
        <button class="btn btn-primary" id="invoice-settings-save">Zapisz</button>
      </div>
    </div>

    <div class="settings-section">
      <p class="settings-desc">Własny dokument PDF — drukowany przyciskiem "Własny dokument" podczas pakowania.</p>
      <div class="custom-doc-status ${docInfo.available ? 'available' : 'empty'}" id="custom-doc-status">
        ${docInfo.available
          ? `<span>✓ Dokument wgrany</span><button class="btn btn-secondary btn-sm" id="btn-doc-delete">Usuń</button>`
          : `<span class="dim">Brak dokumentu</span>`
        }
      </div>
      <div class="settings-field" style="margin-top:12px">
        <input type="file" id="custom-doc-file" accept=".pdf" style="display:none">
        <button class="btn btn-secondary" id="btn-doc-pick">${docInfo.available ? 'Zastąp plik' : 'Wybierz plik PDF'}</button>
        <span id="custom-doc-filename" class="dim" style="margin-left:10px;font-size:13px"></span>
      </div>
      <p id="custom-doc-note" class="settings-note hidden"></p>
    </div>
  `;

  panel.querySelector('#inv-free-text').addEventListener('input', function() {
    panel.querySelector('#inv-free-text-count').textContent = `${this.value.length} / 160`;
  });

  panel.querySelector('#invoice-settings-save').addEventListener('click', async () => {
    const body = {
      show_buyer_name:    panel.querySelector('#inv-buyer-name').checked,
      show_buyer_address: panel.querySelector('#inv-buyer-address').checked,
      show_items:         panel.querySelector('#inv-items').checked,
      show_price:         panel.querySelector('#inv-price').checked,
      show_courier:       panel.querySelector('#inv-courier').checked,
      show_pickup_point:  panel.querySelector('#inv-pickup-point').checked,
      show_allegro_id:    panel.querySelector('#inv-allegro-id').checked,
      free_text:          panel.querySelector('#inv-free-text').value,
    };
    await fetch(`${API}/print/invoice-settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const note = panel.querySelector('#invoice-settings-note');
    note.textContent = '✓ Zapisano';
    note.classList.remove('hidden');
  });

  // Custom doc — file picker
  const fileInput = panel.querySelector('#custom-doc-file');
  panel.querySelector('#btn-doc-pick').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    panel.querySelector('#custom-doc-filename').textContent = file.name;
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API}/print/custom-doc`, { method: 'POST', body: form });
    const note = panel.querySelector('#custom-doc-note');
    if (res.ok) {
      state.customDocAvailable = true;
      note.textContent = '✓ Wgrano pomyślnie';
      note.classList.remove('hidden');
      panel.querySelector('#custom-doc-status').outerHTML =
        `<div class="custom-doc-status available" id="custom-doc-status"><span>✓ Dokument wgrany</span><button class="btn btn-secondary btn-sm" id="btn-doc-delete">Usuń</button></div>`;
      panel.querySelector('#btn-doc-pick').textContent = 'Zastąp plik';
      attachDeleteHandler(panel);
    } else {
      const err = await res.json();
      note.textContent = '✗ ' + (err.detail || 'Błąd');
      note.classList.remove('hidden');
    }
  });

  function attachDeleteHandler(p) {
    const btn = p.querySelector('#btn-doc-delete');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      await fetch(`${API}/print/custom-doc`, { method: 'DELETE' });
      state.customDocAvailable = false;
      p.querySelector('#custom-doc-status').outerHTML =
        `<div class="custom-doc-status empty" id="custom-doc-status"><span class="dim">Brak dokumentu</span></div>`;
      p.querySelector('#btn-doc-pick').textContent = 'Wybierz plik PDF';
      p.querySelector('#custom-doc-filename').textContent = '';
      attachDeleteHandler(p);
    });
  }
  attachDeleteHandler(panel);
}

async function renderSettingsArchive(panel) {
  const res = await fetch(`${API}/orders/archive`);
  const ids = await res.json();

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc">${ids.length ? `${ids.length} zarchiwizowanych zamówień.` : 'Archiwum jest puste.'}</p>
      ${ids.length ? `<div class="archive-list">${ids.map(id => `<div class="archive-item">${id}</div>`).join('')}</div>` : ''}
    </div>
  `;
}

// ---- Sidebar events ----

document.querySelectorAll('.queue-item').forEach(el => {
  el.addEventListener('click', () => renderQueue(el.dataset.queue));
});

document.getElementById('btn-settings').addEventListener('click', () => renderQueue('settings'));

document.getElementById('btn-zakoncz').addEventListener('click', async () => {
  const doneOrders = state.orders.filter(o => o.status === 'done');
  if (!doneOrders.length) {
    alert('Brak zamówień w Gotowe.');
    return;
  }
  const missing = doneOrders.filter(o => !o.tracking_number);
  if (missing.length) {
    const ok = confirm(`${missing.length} ${missing.length === 1 ? 'zamówienie nie ma' : 'zamówień nie ma'} numeru śledzenia. Czy na pewno chcesz zakończyć dzień?`);
    if (!ok) return;
  }
  await fetch(`${API}/orders/zakoncz-dzien`, { method: 'POST' });
  await fetchAll();
  if (state.currentQueue === 'settings') renderQueue('settings');
});

document.getElementById('btn-sync').addEventListener('click', async () => {
  const res = await fetch(`${API}/orders/sync`, { method: 'POST' });
  const data = await res.json();
  if (data.detail) alert('Błąd: ' + data.detail);
  else await fetchAll();
});

document.getElementById('btn-auth').addEventListener('click', async () => {
  try {
    const res = await fetch(`${API}/orders/auth/url`);
    const data = await res.json();
    window.location.href = data.url;
  } catch (e) {
    alert('Błąd: ' + e.message);
  }
});


document.getElementById('btn-seed').addEventListener('click', async () => {
  await fetch(`${API}/orders/dev/seed`, { method: 'POST' });
  await fetchAll();
});

// ---- Auto-refresh pending every 60s ----
setInterval(() => {
  if (state.currentQueue === 'pending') fetchAll();
}, 60000);

// ---- Auth status ----

async function checkAuthStatus() {
  try {
    const res = await fetch(`${API}/orders/auth/status`);
    const data = await res.json();
    document.getElementById('btn-auth').style.display = data.authorized ? 'none' : 'block';
  } catch {}
}

// ---- Custom doc availability ----

async function checkCustomDoc() {
  try {
    const res = await fetch(`${API}/print/custom-doc/info`);
    const data = await res.json();
    state.customDocAvailable = data.available;
  } catch {}
}

// ---- Boot ----
fetchAll();
checkAuthStatus();
checkCustomDoc();

// Check every 30s in case user just came back from Allegro auth page
setInterval(checkAuthStatus, 30000);
