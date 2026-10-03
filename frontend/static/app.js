const API = '/api';
let accessToken = '';
let accessTokenPrompt = null;
let appReady = false;

async function promptForAccessToken() {
  if (accessToken) return accessToken;
  if (!accessTokenPrompt) {
    accessTokenPrompt = Promise.resolve().then(() => {
      const entered = window.prompt('Podaj PACKING_ACCESS_TOKEN z pliku .env:');
      if (!entered || !entered.trim()) throw new Error('Token dostępu jest wymagany.');
      accessToken = entered.trim();
      return accessToken;
    }).finally(() => { accessTokenPrompt = null; });
  }
  return accessTokenPrompt;
}

async function apiFetch(path, options = {}) {
  const send = token => {
    const headers = new Headers(options.headers || {});
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return fetch(`${API}${path}`, { ...options, headers });
  };

  let res = await send(accessToken);
  if (res.status !== 401 || res.headers.get('X-Packing-Auth-Required') !== '1') return res;

  const token = await promptForAccessToken();
  res = await send(token);
  if (res.status === 401 && res.headers.get('X-Packing-Auth-Required') === '1') accessToken = '';
  return res;
}

// Escape every value that came from the API (Allegro data and settings) before it
// reaches innerHTML. Allegro product names and buyer fields are untrusted input.
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// All API calls go through here: a failed request raises instead of silently
// re-rendering the same stale queue.
async function api(path, options = {}) {
  const res = await apiFetch(path, options);
  const type = res.headers.get('content-type') || '';
  let payload = null;
  if (type.includes('application/json')) {
    try { payload = await res.json(); } catch { payload = null; }
  }
  if (!res.ok) {
    const detail = payload && (payload.detail || payload.message);
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || `${res.status} ${res.statusText}`));
  }
  return payload;
}

function reportError(prefix, err) {
  alert(`${prefix}\n\n${err && err.message ? err.message : err}`);
}

// PDFs are fetched first so a failure (401/502/404) shows up as a message instead of
// a browser tab full of JSON.
async function openPdf(path) {
  // Reserve the tab during the click; browsers block popups after a slow API call.
  const printTab = window.open('about:blank', '_blank');
  if (!printTab) throw new Error('Przeglądarka blokuje okno wydruku. Zezwól na wyskakujące okna i spróbuj ponownie.');
  printTab.opener = null;
  try {
    const res = await apiFetch(path);
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const payload = await res.json();
        if (payload && payload.detail) detail = payload.detail;
      } catch { /* not JSON — keep the status line */ }
      throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    printTab.location.replace(url);
  } catch (err) {
    printTab.close();
    throw err;
  }
}

let state = {
  orders: [],         // all orders from backend
  pickingLists: [],   // all picking lists
  currentQueue: 'pending',
  currentCourier: null, // courier filter for pending view
  selectedOrderIds: new Set(),  // for pending → picking list creation
  packingQueue: [],      // orders currently in packing carousel
  packingIndex: 0,       // which card is shown
  packingDirection: null, // 'next' | 'prev' | null
  settingsTab: 'documents',
  customDocAvailable: false,
  shipmentSettings: null, // sender + package defaults for the packing view
  parcelSizeSaves: new Map(),
  parcelSizeErrors: new Map(),
  dryRun: false,        // PACKING_SHIPMENT_DRY_RUN — enables test-only actions
};

// ---- Fetch ----

function renderStateBanner(status) {
  const el = document.getElementById('state-banner');
  if (!el) return;
  let message = '';
  if (status && status.ok === false) {
    message = status.message || 'Problem ze stanem aplikacji.';
  } else if (status && status.quarantined) {
    message = `${status.quarantined} rekord(ów) pominięto — dane nie przechodzą walidacji.`;
  }
  if (!message) {
    el.classList.add('hidden');
    el.textContent = '';
    return;
  }
  el.textContent = '⚠ ' + message;
  el.classList.remove('hidden');
}

async function fetchAll() {
  try {
    const [orders, lists, settings, status] = await Promise.all([
      api('/orders/'),
      api('/picking-lists'),
      api('/print/shipment-settings'),
      api('/orders/status'),
    ]);
    state.orders = orders;
    state.pickingLists = lists;
    state.shipmentSettings = settings;
    state.dryRun = Boolean(status && status.dry_run);
    renderStateBanner(status);
  } catch (err) {
    renderStateBanner({ ok: false, message: err.message });
    return;
  }
  updateBadges();
  renderQueue(state.currentQueue);
}


function deliveryCategory(order) {
  return order.delivery_type === 'inpost_locker' ? 'Paczkomat InPost' : (order.courier || 'Inny');
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
    const c = deliveryCategory(o);
    courierCounts[c] = (courierCounts[c] || 0) + 1;
  });

  const existing = document.getElementById('courier-subnav');
  if (existing) existing.remove();

  const couriers = Object.keys(courierCounts);
  if (couriers.length <= 1 && !courierCounts['Paczkomat InPost']) return;

  const ul = document.createElement('ul');
  ul.id = 'courier-subnav';
  couriers.forEach(courier => {
    const li = document.createElement('li');
    li.className = 'courier-nav-item' + (state.currentCourier === courier ? ' active' : '');
    li.innerHTML = `${esc(courier)} <span class="badge badge-dim">${courierCounts[courier]}</span>`;
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
    (!state.currentCourier || (deliveryCategory(o)) === state.currentCourier)
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
    // Seeding sample orders is a dry-run affordance. On a real instance the
    // backend rejects it, so the button must not be offered at all.
    const seedAction = state.dryRun
      ? ' lub <button class="btn btn-secondary" id="btn-seed-sample" style="display:inline-block;margin-left:8px;padding:4px 8px;font-size:12px">Wczytaj zamówienia testowe</button>'
      : '';
    list.innerHTML = `<p class="empty">Brak oczekujących zamówień. Kliknij "Pobierz zamówienia"${seedAction}.</p>`;
    const seedBtn = list.querySelector('#btn-seed-sample');
    if (seedBtn) {
      seedBtn.addEventListener('click', async () => {
        seedBtn.disabled = true;
        try {
          await api('/orders/seed-mock', { method: 'POST' });
          await fetchAll();
          renderQueue('pending');
        } catch (err) {
          reportError('Nie udało się wczytać zamówień testowych', err);
        }
      });
    }
    return;
  }

  // Group orders by courier
  const byCourier = {};
  orders.forEach(order => {
    const courier = deliveryCategory(order);
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
        // Keep products from different delivery categories separate.
        const key = JSON.stringify([courier, item.name]);
        if (!productMap[key]) productMap[key] = { qty: 0, orderIds: new Set() };
        productMap[key].qty += item.quantity;
        productMap[key].orderIds.add(order.id);
      });
    });

    Object.entries(courierProductMap).forEach(([name, data]) => {
      const productKey = JSON.stringify([courier, name]);
      const txCount = data.orderIds.size;
      const card = document.createElement('div');
      card.className = 'order-card';
      card.innerHTML = `
        <input type="checkbox" />
        <div class="order-info">
          <div class="buyer">${data.qty}x ${esc(name)}</div>
          <div class="address" style="margin-top:4px">${txCount} ${txCount === 1 ? 'transakcja' : txCount < 5 ? 'transakcje' : 'transakcji'}</div>
        </div>
      `;
      const cb = card.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) {
          selectedProducts.add(productKey);
          card.classList.add('selected');
        } else {
          selectedProducts.delete(productKey);
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
    if (!state.selectedOrderIds.size) return;
    try {
      await api('/picking-lists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: '', order_ids: [...state.selectedOrderIds] }),
      });
    } catch (err) {
      reportError('Nie udało się utworzyć listy', err);
      return;
    }
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
          <span class="pl-name" data-id="${pl.id}">${esc(pl.name)}</span>
          <span class="pl-count">${orderCount} zamówień</span>
        </div>
        <div class="pl-rename hidden" data-id="${pl.id}">
          <input class="pl-rename-input" type="text" value="${esc(pl.name)}" />
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
      try {
        await api(`/picking-lists/${btn.dataset.id}/revert`, { method: 'POST' });
      } catch (err) {
        reportError('Nie udało się cofnąć listy', err);
        return;
      }
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
      try {
        await api(`/picking-lists/${btn.dataset.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName }),
        });
      } catch (err) {
        reportError('Nie udało się zmienić nazwy', err);
        return;
      }
      await fetchAll();
      renderQueue('picking');
    });
  });

  list.querySelectorAll('.btn-start-pack').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/picking-lists/${btn.dataset.id}/start-packing`, { method: 'POST' });
      } catch (err) {
        reportError('Nie udało się przenieść do pakowania', err);
        return;
      }
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
    `<tr><td>${esc(name)}</td><td>${qty}</td></tr>`
  ).join('');

  const win = window.open('', '_blank');
  win.document.write(`<!DOCTYPE html><html><head><title>${esc(pl.name)}</title>
    <style>body{font-family:Arial;margin:40px}table{width:100%;border-collapse:collapse}
    td,th{border:1px solid #ccc;padding:8px}th{background:#eee}</style></head>
    <body><h2>Lista: ${esc(pl.name)}</h2>
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

  const pkg = (state.shipmentSettings && state.shipmentSettings.package) || {};
  const isLocker = order.delivery_type === 'inpost_locker';
  const pendingSize = state.parcelSizeSaves.get(order.id);
  const selectedSize = pendingSize ? pendingSize.value : order.parcel_size;
  const lockerNeedsSize = isLocker && !order.shipment_id && !selectedSize;

  view.innerHTML = `
    <div class="pack-nav">
      <button class="btn btn-secondary" id="btn-prev" ${idx === 0 ? 'disabled' : ''}>← Poprzednie</button>
      <span>${idx + 1} / ${orders.length}</span>
      <button class="btn btn-secondary" id="btn-next" ${idx === orders.length - 1 ? 'disabled' : ''}>Następne →</button>
    </div>
    <div class="pack-card ${animClass}">
      <button class="btn-icon-red btn-revert-pending" id="btn-revert-pending" title="Cofnij do oczekujących">↩</button>
      <div class="buyer">${esc(order.buyer_name)}</div>
      <div class="address">${esc(order.buyer_address)}</div>
      <div class="allegro-id">
        <span class="allegro-id-label">ID:</span>
        <span class="allegro-id-value">${esc(order.allegro_id)}</span>
        <button class="btn-copy" data-copy="${esc(order.allegro_id)}" title="Kopiuj ID">⧉</button>
      </div>
      <div class="items">${order.items.map(i => `${i.quantity}x ${esc(i.name)}`).join('<br/>')}</div>
      ${order.tracking_number ? `<div class="tracking-info" style="color:#65dfb5;margin:8px 0;font-size:13px">📦 Nr przesyłki: <strong>${esc(order.tracking_number)}</strong></div>` : ''}
      ${isLocker ? `
      <fieldset class="parcel-sizes" ${pendingSize || order.shipment_id || order.tracking_number ? 'disabled' : ''}>
        <legend>Paczkomat InPost — gabaryt paczki</legend>
        <div class="parcel-size-options">
          ${[['A', 'Mała (8×38×64 cm)'], ['B', 'Średnia (19×38×64 cm)'], ['C', 'Duża (41×38×64 cm)']].map(([size, title]) => `
            <label class="parcel-size-option">
              <input type="radio" name="parcel-size" value="${size}" ${selectedSize === size ? 'checked' : ''}>
              <span><strong>${size}</strong>${title}</span>
            </label>`).join('')}
        </div>
      </fieldset>` : `<div class="pack-dims">
        <label>Wymiary (cm)</label>
        <input type="number" class="dim-input" id="dim-l" value="${esc(pkg.length ?? 30)}" min="1"> ×
        <input type="number" class="dim-input" id="dim-w" value="${esc(pkg.width ?? 20)}" min="1"> ×
        <input type="number" class="dim-input" id="dim-h" value="${esc(pkg.height ?? 15)}" min="1">
        <label style="margin-left:12px">Waga (kg)</label>
        <input type="number" class="dim-input" id="dim-wt" value="${esc(pkg.weight ?? 1.0)}" min="0.1" step="0.1">
      </div>`}
      ${lockerNeedsSize ? '<p class="parcel-size-note">Wybierz gabaryt paczki (A, B lub C), aby utworzyć etykietę Paczkomat InPost.</p>' : ''}
      <p id="parcel-size-status" class="parcel-size-note" role="status" aria-live="polite">${pendingSize ? 'Zapisywanie gabarytu…' : esc(state.parcelSizeErrors.get(order.id) || '')}</p>
      <div class="pack-buttons">
        <button class="btn btn-label" id="btn-label" ${lockerNeedsSize || pendingSize ? 'disabled' : ''}>${isLocker ? '🖨 Etykieta Paczkomat' : '🖨 Etykieta kurierska'}</button>
        <button class="btn btn-invoice" id="btn-invoice">🖨 Dokument</button>
        <button class="btn btn-done" id="btn-done">✓ GOTOWE</button>
      </div>
    </div>
  `;

  view.querySelector('#btn-revert-pending').addEventListener('click', async () => {
    try {
      await api(`/orders/${order.id}/revert-pending`, { method: 'POST' });
    } catch (err) {
      reportError('Nie udało się cofnąć zamówienia', err);
      return;
    }
    await fetchAll();
    state.packingQueue = state.orders.filter(o => o.status === 'packing');
    state.packingIndex = Math.min(state.packingIndex, Math.max(0, state.packingQueue.length - 1));
    renderPackingCard(document.getElementById('content'));
  });

  const copyBtn = view.querySelector('.btn-copy');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(copyBtn.dataset.copy);
        copyBtn.textContent = '✓';
        setTimeout(() => { copyBtn.textContent = '⧉'; }, 1200);
      } catch (err) {
        reportError('Nie udało się skopiować ID', err);
      }
    });
  }

  // The label may already exist from an earlier session — do not warn in that case.
  let labelReady = Boolean(order.shipment_id);
  view.querySelectorAll('input[name="parcel-size"]').forEach(input => {
    input.addEventListener('change', async () => {
      if (state.parcelSizeSaves.has(order.id)) return;
      const fieldset = view.querySelector('.parcel-sizes');
      const note = view.querySelector('#parcel-size-status');
      state.parcelSizeSaves.set(order.id, { value: input.value });
      state.parcelSizeErrors.delete(order.id);
      fieldset.disabled = true;
      note.textContent = 'Zapisywanie gabarytu…';
      try {
        const result = await api(`/orders/${order.id}/parcel-size`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parcel_size: input.value }),
        });
        for (const saved of [order, ...state.orders, ...state.packingQueue]) {
          if (saved.id === order.id) saved.parcel_size = result.parcel_size;
        }
      } catch (err) {
        state.parcelSizeErrors.set(order.id, `Nie udało się zapisać gabarytu: ${err.message}`);
      } finally {
        state.parcelSizeSaves.delete(order.id);
        if (state.currentQueue === 'packing' && state.packingQueue[state.packingIndex]?.id === order.id) {
          renderPackingCard(document.getElementById('content'));
        }
      }
    });
  });

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
  view.querySelector('#btn-label').addEventListener('click', async () => {
    const btn = view.querySelector('#btn-label');
    const params = isLocker
      ? new URLSearchParams()
      : new URLSearchParams({
        length: view.querySelector('#dim-l').value, width: view.querySelector('#dim-w').value,
        height: view.querySelector('#dim-h').value, weight: view.querySelector('#dim-wt').value,
      });
    btn.disabled = true;
    const previousLabel = btn.textContent;
    btn.textContent = 'Generowanie etykiety…';
    try {
      await openPdf(`/print/orders/${order.id}/label?${params}`);
      // Only claim the label is printed once the PDF actually came back.
      labelReady = true;
      btn.classList.add('printed');
      btn.textContent = isLocker ? '✓ Etykieta Paczkomat' : '✓ Etykieta kurierska';
      try {
        const info = await api(`/print/orders/${order.id}/shipment`);
        if (info && info.shipment_id) {
          order.shipment_id = info.shipment_id;
          if (info.tracking_number) {
            order.tracking_number = info.tracking_number;
            for (const o of [...state.orders, ...state.packingQueue]) {
              if (o.id === order.id) o.tracking_number = info.tracking_number;
            }
          }
        }
      } catch { /* best effort */ }
    } catch (err) {
      btn.textContent = previousLabel;
      reportError('Nie udało się pobrać etykiety', err);
    } finally {
      btn.disabled = false;
    }
  });
  view.querySelector('#btn-invoice').addEventListener('click', async () => {
    try {
      await openPdf(`/print/orders/${order.id}/combined`);
    } catch (err) {
      reportError('Nie udało się wygenerować dokumentu', err);
    }
  });
  view.querySelector('#btn-done').addEventListener('click', async () => {
    if (!labelReady) {
      const ok = confirm('Etykieta nie wydrukowana — czy na pewno chcesz oznaczyć jako gotowe?');
      if (!ok) return;
    }
    const card = view.querySelector('.pack-card');
    card.classList.add('animate-done');
    await new Promise(r => setTimeout(r, 430));
    try {
      await api(`/orders/${order.id}/done`, { method: 'POST' });
    } catch (err) {
      reportError('Nie udało się oznaczyć jako gotowe', err);
      renderPackingCard(document.getElementById('content'));
      return;
    }
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
    const labelHtml = order.tracking_number
      ? `<div class="tracking-number">📦 ${esc(order.tracking_number)}</div>`
      : order.shipment_id
        ? `<div class="tracking-number">🏷 Etykieta utworzona</div>`
        : `<div class="tracking-number missing">— brak etykiety —</div>`;
    card.innerHTML = `
      <div class="order-info">
        <div class="buyer">${esc(order.buyer_name)}</div>
        <div class="address">${esc(order.buyer_address)}</div>
        <div class="allegro-id">
          <span class="allegro-id-label">ID:</span>
          <span class="allegro-id-value">${esc(order.allegro_id)}</span>
          <button class="btn-copy" data-copy="${esc(order.allegro_id)}" title="Kopiuj ID">⧉</button>
        </div>
        ${labelHtml}
      </div>
      <button class="btn btn-secondary btn-undo" data-id="${order.id}">↩ Cofnij</button>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll('.btn-copy').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = '⧉'; }, 1200);
      } catch (err) {
        reportError('Nie udało się skopiować ID', err);
      }
    });
  });

  list.querySelectorAll('.btn-undo').forEach(btn => {
    btn.addEventListener('click', async () => {
      try {
        await api(`/orders/${btn.dataset.id}/undo-done`, { method: 'POST' });
      } catch (err) {
        reportError('Nie udało się cofnąć zamówienia', err);
        return;
      }
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
      <button class="settings-tab ${activeTab === 'documents' ? 'active' : ''}" data-tab="documents">Dokumenty</button>
      <button class="settings-tab ${activeTab === 'shipping'  ? 'active' : ''}" data-tab="shipping">Wysyłka</button>
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
  if (activeTab === 'documents') renderSettingsDocuments(panel);
  if (activeTab === 'shipping')  renderSettingsShipping(panel);
  if (activeTab === 'archive')   renderSettingsArchive(panel);
}

async function renderSettingsShipping(panel) {
  const s = await api('/print/shipment-settings');
  const sender = s.sender || {};
  const pkg = s.package || {};

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc">Dane nadawcy, odbiorcy i punktu odbioru pobieramy automatycznie z Allegro.
      Adres nadawcy ustaw w książce adresowej Wysyłam z Allegro.</p>
    </div>
    <div class="settings-section">
      <p class="settings-desc"><strong>Domyślna paczka</strong> — wartości startowe w widoku pakowania.</p>
      <div class="settings-field"><label>Długość (cm)</label><input type="number" id="sh-pkg-length" min="1" value="${esc(pkg.length ?? 30)}"></div>
      <div class="settings-field"><label>Szerokość (cm)</label><input type="number" id="sh-pkg-width" min="1" value="${esc(pkg.width ?? 20)}"></div>
      <div class="settings-field"><label>Wysokość (cm)</label><input type="number" id="sh-pkg-height" min="1" value="${esc(pkg.height ?? 15)}"></div>
      <div class="settings-field"><label>Waga (kg)</label><input type="number" id="sh-pkg-weight" min="0.1" step="0.1" value="${esc(pkg.weight ?? 1.0)}"></div>
      <div class="settings-field"><label>Rozmiar etykiety</label>
        <select id="sh-pkg-page">
          <option value="A6" ${pkg.page_size === 'A6' ? 'selected' : ''}>A6</option>
          <option value="A4" ${pkg.page_size === 'A4' ? 'selected' : ''}>A4</option>
        </select>
      </div>
      <p class="settings-desc">Etykiety są generowane w formacie PDF do wydruku w przeglądarce.</p>
    </div>
    <p id="shipping-note" class="settings-note hidden"></p>
    <div class="settings-actions">
      <button class="btn btn-primary" id="shipping-save">Zapisz</button>
    </div>
  `;

  panel.querySelector('#shipping-save').addEventListener('click', async () => {
    const note = panel.querySelector('#shipping-note');
    const num = (id, fallback) => {
      const value = parseFloat(panel.querySelector(id).value);
      return Number.isFinite(value) ? value : fallback;
    };
    const body = {
      sender, // Preserve legacy settings; shipment addresses now come from Allegro.
      package: {
        type: 'PACKAGE',
        length: num('#sh-pkg-length', 30),
        width: num('#sh-pkg-width', 20),
        height: num('#sh-pkg-height', 15),
        weight: num('#sh-pkg-weight', 1.0),
        label_format: 'PDF',
        page_size: panel.querySelector('#sh-pkg-page').value,
      },
    };
    try {
      await api('/print/shipment-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (err) {
      note.textContent = '✗ ' + err.message;
      note.classList.remove('hidden');
      return;
    }
    state.shipmentSettings = { sender: body.sender, package: body.package };
    note.textContent = '✓ Zapisano';
    note.classList.remove('hidden');
    setTimeout(() => note.classList.add('hidden'), 3000);
  });
}

async function renderSettingsDocuments(panel) {
  const [data, docInfo] = await Promise.all([
    api('/print/invoice-settings'),
    api('/print/custom-doc/info'),
  ]);

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
        <textarea id="inv-free-text" rows="2" maxlength="160" placeholder="np. Dziękujemy za zakup!">${esc(data.free_text || '')}</textarea>
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
    const note = panel.querySelector('#invoice-settings-note');
    try {
      await api('/print/invoice-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      note.textContent = '✓ Zapisano';
    } catch (err) {
      note.textContent = '✗ ' + err.message;
    }
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
    const note = panel.querySelector('#custom-doc-note');
    let res;
    try {
      res = await apiFetch('/print/custom-doc', { method: 'POST', body: form });
    } catch (err) {
      note.textContent = '✗ ' + err.message;
      note.classList.remove('hidden');
      return;
    }
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
      try {
        await api('/print/custom-doc', { method: 'DELETE' });
      } catch (err) {
        reportError('Nie udało się usunąć dokumentu', err);
        return;
      }
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
  const entries = await api('/orders/archive');

  panel.innerHTML = `
    <div class="settings-section">
      <p class="settings-desc">${entries.length ? `${entries.length} zarchiwizowanych zamówień.` : 'Archiwum jest puste.'}</p>
      ${entries.length ? `<div class="archive-list">${entries.map(e => `<div class="archive-item">
        <span>${esc(e.allegro_id)}</span>
        <span class="dim">${e.archived_at ? esc(new Date(e.archived_at).toLocaleString('pl-PL')) : 'brak daty'}</span>
      </div>`).join('')}</div>` : ''}
    </div>
  `;
}

// ---- Sidebar events ----

document.querySelectorAll('.queue-item').forEach(el => {
  el.addEventListener('click', () => renderQueue(el.dataset.queue));
});

document.getElementById('btn-settings').addEventListener('click', () => renderQueue('settings'));

document.getElementById('btn-zakoncz').addEventListener('click', async () => {
  if (!confirm('Zakończyć dzień i zarchiwizować wszystkie zamówienia z Gotowe?')) return;
  const doneOrders = state.orders.filter(o => o.status === 'done');
  if (!doneOrders.length) {
    alert('Brak zamówień w Gotowe.');
    return;
  }
  const missing = doneOrders.filter(o => !o.shipment_id && !o.tracking_number);
  if (missing.length) {
    const ok = confirm(`${missing.length} ${missing.length === 1 ? 'zamówienie nie ma' : 'zamówień nie ma'} utworzonej etykiety. Czy na pewno chcesz zakończyć dzień?`);
    if (!ok) return;
  }
  try {
    await api('/orders/zakoncz-dzien', { method: 'POST' });
  } catch (err) {
    reportError('Nie udało się zakończyć dnia', err);
    return;
  }
  await fetchAll();
  if (state.currentQueue === 'settings') renderQueue('settings');
});

document.getElementById('btn-sync').addEventListener('click', async () => {
  const btn = document.getElementById('btn-sync');
  btn.disabled = true;
  try {
    await api('/orders/sync', { method: 'POST' });
  } catch (err) {
    reportError('Synchronizacja nie powiodła się', err);
    return;
  } finally {
    btn.disabled = false;
  }
  await fetchAll();
});

document.getElementById('btn-auth').addEventListener('click', async () => {
  try {
    const data = await api('/orders/auth/url');
    window.location.href = data.url;
  } catch (e) {
    alert('Błąd: ' + e.message);
  }
});


// ---- Auto-refresh pending every 60s ----
setInterval(() => {
  if (appReady && state.currentQueue === 'pending') fetchAll();
}, 60000);

// ---- Auth status ----

async function checkAuthStatus() {
  try {
    const data = await api('/orders/auth/status');
    document.getElementById('btn-auth').style.display = data.authorized ? 'none' : 'block';
  } catch {}
}

// ---- Custom doc availability ----

async function checkCustomDoc() {
  try {
    const data = await api('/print/custom-doc/info');
    state.customDocAvailable = data.available;
  } catch {}
}

// ---- Boot ----

async function startApp() {
  document.getElementById('setup').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  appReady = true;
  await Promise.all([fetchAll(), checkAuthStatus(), checkCustomDoc()]);
}

function setupMessage(message, isError = false) {
  const el = document.getElementById('setup-message');
  el.textContent = message;
  el.classList.toggle('error', isError);
}

async function boot() {
  const retry = document.getElementById('setup-retry');
  retry.classList.add('hidden');
  setupMessage('Sprawdzanie konfiguracji…');
  try {
    const status = await api('/setup/status');
    if (status.configured) {
      await startApp();
      return;
    }
    const form = document.getElementById('setup-form');
    document.getElementById('setup-environment').textContent = status.sandbox
      ? 'Środowisko: Allegro Sandbox. Użyj danych aplikacji testowej.'
      : 'Środowisko: Allegro. Użyj danych aplikacji produkcyjnej.';
    document.getElementById('setup-redirect-uri').textContent = status.redirect_uri;
    form.classList.remove('hidden');
    setupMessage('');
    form.onsubmit = async event => {
      event.preventDefault();
      const submit = document.getElementById('setup-submit');
      const clientId = document.getElementById('setup-client-id');
      const clientSecret = document.getElementById('setup-client-secret');
      submit.disabled = true;
      submit.textContent = 'Zapisywanie…';
      setupMessage('');
      try {
        // Existing installations keep their current operator authentication.
        if (status.requires_access_token) await promptForAccessToken();
        const result = await api('/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Packing-Setup-Token': status.setup_token },
          body: JSON.stringify({ client_id: clientId.value.trim(), client_secret: clientSecret.value.trim() }),
        });
        clientId.value = '';
        clientSecret.value = '';
        form.classList.add('hidden');
        retry.classList.add('hidden');
        if (result.access_token) {
          accessToken = result.access_token;
          document.getElementById('setup-access-token').value = result.access_token;
          document.getElementById('setup-success').classList.remove('hidden');
          setupMessage('Dane Allegro zapisane. Zachowaj token dostępu przed przejściem do aplikacji.');
          document.getElementById('setup-access-token').focus();
        } else {
          await startApp();
        }
      } catch (err) {
        setupMessage(err.message || 'Nie udało się zapisać konfiguracji.', true);
        retry.classList.remove('hidden');
      } finally {
        submit.disabled = false;
        submit.textContent = 'Zapisz i kontynuuj';
      }
    };
    document.getElementById('setup-client-id').focus();
  } catch (err) {
    setupMessage(err.message || 'Nie udało się sprawdzić konfiguracji.', true);
    retry.classList.remove('hidden');
  }
}

document.getElementById('setup-retry').addEventListener('click', boot);
document.getElementById('setup-continue').addEventListener('click', async () => {
  document.getElementById('setup-access-token').value = '';
  await startApp();
});
document.getElementById('setup-copy-token').addEventListener('click', async () => {
  const field = document.getElementById('setup-access-token');
  try {
    await navigator.clipboard.writeText(field.value);
    setupMessage('Token skopiowany. Zachowaj go w bezpiecznym miejscu.');
  } catch {
    field.focus();
    field.select();
    setupMessage('Skopiuj zaznaczony token i zachowaj go w bezpiecznym miejscu.');
  }
});

boot();

// Check every 30s in case user just came back from Allegro auth page
setInterval(() => { if (appReady) checkAuthStatus(); }, 30000);
