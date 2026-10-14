// Lightweight A4 document editor. The editor owns a module-local draft so an
// unsaved template survives re-renders, navigation away, language switches and
// an in-flight save. It builds its DOM programmatically (no HTML string), which
// keeps user-authored text out of any markup path.
//
// Loaded after app.js; uses the shared t(), setText(), bindDynamicText(), api()
// and openPdf() helpers from the page.
var DocumentEditor = (function () {
  'use strict';

  var BLOCK_TYPES = ['text', 'placeholder', 'items', 'logo', 'line', 'heading', 'customer'];
  var TYPE_LABEL = {
    heading: 'doc.blockHeading', text: 'doc.blockText', customer: 'doc.blockCustomer',
    items: 'doc.blockItems', logo: 'doc.blockLogo', placeholder: 'doc.blockPlaceholder', line: 'doc.blockLine',
  };
  var TOKENS = ['buyer.name', 'buyer.address', 'order.id', 'order.date', 'items', 'buyer_name', 'buyer_address', 'order_number', 'date', 'courier', 'pickup_point', 'tracking_number'];

  var MAX_NAME = 100;
  var MAX_TEXT = 4000;
  var MAX_BLOCKS = 50;
  var MAX_LOGO_BYTES = 2 * 1024 * 1024;
  // The backend caps the combined logo payload across the whole template.
  var MAX_LOGO_CHARS = 2_800_000;

  var draft = null;
  var lastSavePromise = null;
  var activeInstance = null;
  var onSaved = null;
  var boundNodes = [];
  var settingsCache = null;
  var collectionBusy = false;

  function el(tag, className) {
    var node = document.createElement(tag);
    if (className) addClass(node, className);
    return node;
  }

  function addClass(node, className) {
    String(className).split(/\s+/).filter(Boolean).forEach(function (name) { node.classList.add(name); });
    return node;
  }

  function emptyBlock(type) {
    return cloneBlocks([{ type: type, text: type === 'placeholder' ? '{{buyer.name}}' : '' }])[0];
  }

  function clampGeometry(block) {
    function number(value, fallback) { return value !== null && value !== undefined && Number.isFinite(Number(value)) ? Math.round(Number(value)) : fallback; }
    block.x = Math.max(0, Math.min(209, number(block.x, 18)));
    block.y = Math.max(0, Math.min(296, number(block.y, 18)));
    block.w = Math.max(1, Math.min(210 - block.x, number(block.w, 174)));
    block.h = Math.max(1, Math.min(297 - block.y, number(block.h, 24)));
    return block;
  }

  function resolveText(text, order) {
    order = order || {};
    var values = {
      'buyer.name': order.buyer_name, 'buyer.address': order.buyer_address,
      'order.id': order.id, 'order.date': new Date().toLocaleDateString('sv-SE'),
      items: (order.items || []).map(function (item) { return item.name + ' × ' + item.quantity; }).join('\n'),
      buyer_name: order.buyer_name, buyer_address: order.buyer_address, order_number: order.allegro_id,
      courier: order.courier, pickup_point: order.pickup_point, tracking_number: order.tracking_number,
    };
    values.date = values['order.date'];
    // One pass: never resolve braces introduced by untrusted customer data.
    return String(text || '').replace(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}/g, function (_, token) { return !TOKENS.includes(token) || values[token] === undefined || values[token] === null || values[token] === '' ? '—' : String(values[token]); });
  }

  function unknownTokens(blocks) {
    var result = new Set();
    blocks.forEach(function (block) {
      String(block.text || '').replace(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}/g, function (_, token) { if (!TOKENS.includes(token)) result.add(token); return ''; });
    });
    return Array.from(result).sort();
  }

  function normalizeSize(value) {
    var size = Math.round(Number(value));
    if (!Number.isFinite(size)) return 12;
    return Math.min(36, Math.max(8, size));
  }

  function normalizeAlign(value) {
    return value === 'center' || value === 'right' ? value : 'left';
  }

  function cloneBlocks(blocks) {
    var cursor = 18;
    return (blocks || []).map(function (block) {
      var legacy = ['x', 'y', 'w', 'h'].every(function (key) { return block[key] === null || block[key] === undefined; });
      var copy = {
        type: block.type, text: block.text || '', align: normalizeAlign(block.align),
        size: normalizeSize(block.size), show_prices: Boolean(block.show_prices), image: block.image || '',
        bold: block.bold === undefined ? legacy && block.type === 'heading' : Boolean(block.bold),
        x: block.x == null ? 18 : block.x, y: block.y == null ? cursor : block.y,
        w: block.w == null ? 174 : block.w,
        h: block.h == null ? ({heading: 18, text: 24, customer: 30, items: 90, logo: 35, placeholder: 24, line: 1}[block.type] || 24) : block.h,
      };
      clampGeometry(copy);
      cursor = copy.y + copy.h + 6;
      return copy;
    });
  }

  // Mirrors the backend's notion of a non-empty template: only content the PDF
  // would actually show counts.
  function hasContent() {
    return Boolean(draft) && draft.blocks.some(function (block) {
      return block.type === 'customer' || block.type === 'items' || block.type === 'line'
        || (block.type === 'logo' && block.image)
        || ((block.type === 'heading' || block.type === 'text' || block.type === 'placeholder') && (block.text || '').trim());
    });
  }

  function buildBlocks() {
    return draft.blocks.map(function (block) {
      return {
        type: block.type, text: block.text || '', align: normalizeAlign(block.align),
        size: normalizeSize(block.size), show_prices: Boolean(block.show_prices),
        image: block.type === 'logo' ? (block.image || '') : '',
        x: block.x, y: block.y, w: block.w, h: block.h, bold: Boolean(block.bold),
      };
    });
  }

  function buildTemplate() {
    return { id: draft.templateId, name: (draft.name || '').slice(0, MAX_NAME), blocks: buildBlocks() };
  }

  function syncDraft(settings) {
    settingsCache = settings || settingsCache;
    var profile = (settings && settings.profiles && settings.profiles.default) || {};
    var id = profile.active_template_id || 'default';
    // Keep an existing draft for the same template: edits and status must not be
    // overwritten by a redraw or a navigation return.
    if (draft && draft.templateId === id) return;
    var template = ((settings && settings.templates) || []).filter(function (item) { return item.id === id; })[0]
      || { id: id, name: '', blocks: [] };
    draft = {
      templateId: id,
      source: profile.source === 'template' ? 'template' : 'upload',
      name: template.name || '',
      blocks: cloneBlocks(template.blocks),
      status: 'idle', error: '', saving: false, revision: 0, previewOrderId: '', selectedIndex: 0,
    };
  }

  function validateLogoFile(file) {
    var type = (file && file.type) || '';
    if (/svg/i.test(type)) return { ok: false, error: 'doc.logoSvg' };
    if (type !== 'image/png' && type !== 'image/jpeg') return { ok: false, error: 'doc.logoFormat' };
    if (file.size && file.size > MAX_LOGO_BYTES) return { ok: false, error: 'doc.logoTooLarge' };
    return { ok: true };
  }

  function logoTotal() {
    return draft.blocks.reduce(function (sum, block) {
      return sum + (block.type === 'logo' ? String(block.image || '').length : 0);
    }, 0);
  }

  // A blocking reason the backend would also reject; used to disable save and
  // preview before a round trip.
  function templateBlockedReason() {
    if (draft.blocks.some(function (block) { return /\{\{|\}\}|\{%|%\}|\{#|#\}/.test(String(block.text || '').replace(/\{\{\s*[a-zA-Z_][a-zA-Z0-9_.]*\s*\}\}/g, '')); })) return 'doc.malformed';
    if (draft.source === 'template' && !hasContent()) return 'doc.empty';
    if (logoTotal() > MAX_LOGO_CHARS) return 'doc.logoTotalTooLarge';
    return null;
  }

  function markDirty() {
    if (!draft) return;
    draft.revision++;
    if (!draft.saving) draft.status = 'dirty';
  }

  function statusText() {
    if (!draft) return '';
    if (draft.status === 'saving') return t('doc.statusSaving');
    if (draft.status === 'error') return t('doc.statusError', { detail: draft.errorKey ? t(draft.errorKey) : (draft.error || '') });
    if (draft.status === 'saved') return t('doc.statusSaved');
    if (draft.status === 'dirty') return t('doc.statusDirty');
    return '';
  }

  function previewNoteText(ctx) {
    if (!ctx.orders.length) return t('doc.previewNoOrders');
    var blocked = templateBlockedReason() || (!hasContent() ? 'doc.empty' : null);
    return blocked ? t(blocked) : '';
  }

  function setError(message, key = null) {
    if (draft) { draft.status = 'error'; draft.error = message; draft.errorKey = key; }
    refreshActive();
  }

  function refreshActive() {
    if (activeInstance && activeInstance.refresh) activeInstance.refresh();
  }

  function refreshUI(ctx) {
    var ui = ctx.ui;
    if (!ui) return;
    var blocked = templateBlockedReason();
    if (ui.statusNode) ui.statusNode.textContent = statusText();
    if (ui.saveBtn) ui.saveBtn.disabled = draft.saving || collectionBusy || Boolean(blocked);
    if (ui.previewBtn) ui.previewBtn.disabled = !ctx.orders.length || !draft.previewOrderId || !hasContent() || Boolean(blocked);
    if (ui.noteNode) ui.noteNode.textContent = previewNoteText(ctx);
    if (ui.collectionControls) ui.collectionControls.forEach(function (node) {
      node.disabled = draft.saving || collectionBusy || (node.classList.contains('editor-template-delete') && settingsCache.templates.length < 2) || (node.classList.contains('editor-template-duplicate') && settingsCache.templates.length >= 10);
    });
    ctx.root.querySelectorAll('.editor-block input, .editor-block textarea, .editor-block select, .editor-block button, .editor-source input, .editor-template-name, .editor-add-block, .editor-block-type').forEach(function (node) {
      if (node.classList.contains('editor-block-up') || node.classList.contains('editor-block-down')) {
        var index = Number(node.parentNode.parentNode.getAttribute('data-index'));
        node.disabled = collectionBusy || (node.classList.contains('editor-block-up') ? index === 0 : index === draft.blocks.length - 1); return;
      }
      node.disabled = collectionBusy;
    });
    refreshCanvas(ctx);
  }

  function bindNode(node, render) {
    bindDynamicText(node, render);
    boundNodes.push(node);
  }

  function teardown() {
    boundNodes.forEach(function (node) { dynamicText.delete(node); });
    boundNodes = [];
  }

  function labelControl(node, key) {
    node.setAttribute('data-i18n-aria', key);
    node.setAttribute('aria-label', t(key));
  }

  function iconButton(className, glyph, key) {
    var button = document.createElement('button');
    button.setAttribute('type', 'button');
    addClass(button, className);
    button.textContent = glyph;
    button.setAttribute('data-i18n-title', key);
    button.setAttribute('title', t(key));
    labelControl(button, key);
    return button;
  }

  function moveBlock(ctx, index, delta) {
    if (collectionBusy) return;
    var target = index + delta;
    if (target < 0 || target >= draft.blocks.length) return;
    var swap = draft.blocks[target];
    draft.blocks[target] = draft.blocks[index];
    draft.blocks[index] = swap;
    markDirty();
    render(ctx);
  }

  function buildBlock(ctx, block, index) {
    var row = el('div', 'editor-block');
    row.setAttribute('data-type', block.type);
    row.setAttribute('data-index', String(index));

    var head = el('div', 'editor-block-head');
    var title = el('span', 'editor-block-title');
    setText(title, TYPE_LABEL[block.type]);
    head.appendChild(title);
    head.addEventListener('click', function (event) { if (event.target.tagName === 'BUTTON') return; draft.selectedIndex = index; syncGeometryInputs(ctx); refreshCanvas(ctx); });

    var up = iconButton('editor-block-up', '↑', 'doc.moveUp');
    var down = iconButton('editor-block-down', '↓', 'doc.moveDown');
    var remove = iconButton('editor-block-remove', '✕', 'doc.removeBlock');
    up.disabled = index === 0;
    down.disabled = index === draft.blocks.length - 1;
    up.addEventListener('click', function () { moveBlock(ctx, index, -1); });
    down.addEventListener('click', function () { moveBlock(ctx, index, 1); });
    remove.addEventListener('click', function () {
      draft.blocks.splice(index, 1);
      markDirty();
      render(ctx);
    });
    head.appendChild(up);
    head.appendChild(down);
    head.appendChild(remove);
    row.appendChild(head);

    if (block.type === 'heading' || block.type === 'text' || block.type === 'placeholder') {
      var textarea = document.createElement('textarea');
      addClass(textarea, 'editor-block-text');
      labelControl(textarea, TYPE_LABEL[block.type]);
      textarea.setAttribute('maxlength', String(MAX_TEXT));
      textarea.value = block.text || '';
      textarea.addEventListener('input', function () {
        block.text = String(textarea.value || '').slice(0, MAX_TEXT);
        markDirty();
        refreshUI(ctx);
      });
      row.appendChild(textarea);

      var controls = el('div', 'editor-block-row');
      var alignLabel = el('span', 'editor-label');
      setText(alignLabel, 'doc.align');
      var align = document.createElement('select');
      addClass(align, 'editor-block-align');
      labelControl(align, 'doc.align');
      [['left', 'doc.alignLeft'], ['center', 'doc.alignCenter'], ['right', 'doc.alignRight']].forEach(function (pair) {
        var option = document.createElement('option');
        option.setAttribute('value', pair[0]);
        option.value = pair[0];
        setText(option, pair[1]);
        align.appendChild(option);
      });
      align.value = normalizeAlign(block.align);
      align.addEventListener('change', function () { block.align = normalizeAlign(align.value); markDirty(); refreshUI(ctx); });
      var sizeLabel = el('span', 'editor-label');
      setText(sizeLabel, 'doc.size');
      var size = document.createElement('input');
      size.setAttribute('type', 'number');
      addClass(size, 'editor-block-size');
      labelControl(size, 'doc.size');
      size.setAttribute('min', '8');
      size.setAttribute('max', '36');
      size.value = String(normalizeSize(block.size));
      size.addEventListener('input', function () { block.size = normalizeSize(size.value); markDirty(); refreshUI(ctx); });
      controls.appendChild(alignLabel);
      controls.appendChild(align);
      controls.appendChild(sizeLabel);
      controls.appendChild(size);
      row.appendChild(controls);

      var tokens = el('div', 'editor-tokens');
      var tokensLabel = el('span', 'editor-label');
      setText(tokensLabel, 'doc.insertField');
      tokens.appendChild(tokensLabel);
      TOKENS.forEach(function (token) {
        var button = document.createElement('button');
        button.setAttribute('type', 'button');
        addClass(button, 'editor-token');
        button.setAttribute('data-token', token);
        button.textContent = '{{' + token + '}}';
        button.addEventListener('click', function () {
          var start = textarea.selectionStart || 0;
          var end = textarea.selectionEnd === undefined || textarea.selectionEnd === null ? start : textarea.selectionEnd;
          var value = String(textarea.value || '');
          var marker = '{{' + token + '}}';
          var updated = value.slice(0, start) + marker + value.slice(end);
          if (updated.length > MAX_TEXT) { setError('', 'doc.textLimit'); return; }
          textarea.value = updated;
          textarea.selectionStart = textarea.selectionEnd = start + marker.length;
          block.text = String(textarea.value).slice(0, MAX_TEXT);
          markDirty();
          refreshUI(ctx);
        });
        tokens.appendChild(button);
      });
      row.appendChild(tokens);
    } else if (block.type === 'items') {
      var pricesLabel = el('label', 'editor-block-prices-label');
      var prices = document.createElement('input');
      prices.setAttribute('type', 'checkbox');
      addClass(prices, 'editor-block-prices');
      prices.checked = Boolean(block.show_prices);
      prices.addEventListener('change', function () { block.show_prices = Boolean(prices.checked); markDirty(); refreshUI(ctx); });
      var pricesText = el('span');
      setText(pricesText, 'doc.showPrices');
      pricesLabel.appendChild(prices);
      pricesLabel.appendChild(pricesText);
      row.appendChild(pricesLabel);
    } else if (block.type === 'logo') {
      var file = document.createElement('input');
      file.setAttribute('type', 'file');
      addClass(file, 'editor-logo-file');
      labelControl(file, 'doc.blockLogo');
      file.setAttribute('accept', 'image/png,image/jpeg');
      file.addEventListener('change', function () {
        var chosen = file.files && file.files[0];
        if (!chosen) return;
        var check = validateLogoFile(chosen);
        if (!check.ok) { setError('', check.error); return; }
        if (typeof FileReader === 'undefined') { setError('', 'doc.logoFormat'); return; }
        var reader = new FileReader();
        reader.onload = function () {
          if (!draft.blocks.includes(block)) return;
          block.image = String(reader.result || '');
          markDirty();
          if (activeInstance) render(activeInstance.ctx);
        };
        reader.onerror = function () { setError('', 'doc.logoFormat'); };
        reader.readAsDataURL(chosen);
      });
      row.appendChild(file);
      var preview = document.createElement('img');
      addClass(preview, 'editor-logo-preview');
      preview.setAttribute('alt', '');
      if (/^data:image\/(png|jpeg);base64,/i.test(block.image)) preview.setAttribute('src', block.image);
      row.appendChild(preview);
      var logoNote = el('span', 'editor-logo-name');
      setText(logoNote, block.image ? 'doc.logoChosen' : 'doc.logoNone');
      row.appendChild(logoNote);
    }
    var properties = el('div', 'editor-block-row');
    ['x', 'y', 'w', 'h'].forEach(function (key) {
      var label = el('label', 'editor-geometry-label');
      label.textContent = key.toUpperCase() + ' (mm)';
      var input = el('input', 'editor-geometry-' + key);
      input.setAttribute('type', 'number');
      input.setAttribute('step', '1');
      input.setAttribute('min', key === 'x' || key === 'y' ? '0' : '1');
      input.setAttribute('max', key === 'x' ? '209' : key === 'y' ? '296' : key === 'w' ? '210' : '297');
      input.value = String(block[key]);
      input.addEventListener('input', function () { block[key] = input.value; clampGeometry(block); markDirty(); refreshUI(ctx); syncGeometryInputs(ctx); });
      label.appendChild(input); properties.appendChild(label);
    });
    if (!row.querySelector('.editor-block-size')) {
      var font = el('input', 'editor-block-size');
      font.setAttribute('type', 'number'); font.setAttribute('min', '8'); font.setAttribute('max', '36');
      labelControl(font, 'doc.size'); font.value = String(block.size);
      font.addEventListener('input', function () { block.size = normalizeSize(font.value); markDirty(); refreshUI(ctx); });
      properties.appendChild(font);
      var alignment = el('select', 'editor-block-align'); labelControl(alignment, 'doc.align');
      ['left', 'center', 'right'].forEach(function (value) { var option = el('option'); option.value = value; setText(option, 'doc.align' + value[0].toUpperCase() + value.slice(1)); alignment.appendChild(option); });
      alignment.value = block.align;
      alignment.addEventListener('change', function () { block.align = normalizeAlign(alignment.value); markDirty(); refreshUI(ctx); });
      properties.appendChild(alignment);
    }
    var boldLabel = el('label'); var bold = el('input', 'editor-block-bold');
    bold.setAttribute('type', 'checkbox'); bold.checked = block.bold; labelControl(bold, 'doc.bold');
    bold.addEventListener('change', function () { block.bold = bold.checked; markDirty(); refreshUI(ctx); });
    boldLabel.appendChild(bold); var boldText = el('span'); setText(boldText, 'doc.bold'); boldLabel.appendChild(boldText); properties.appendChild(boldLabel);
    row.appendChild(properties);
    row.classList.toggle('selected', index === draft.selectedIndex);
    return row;
  }

  function syncGeometryInputs(ctx) {
    ctx.root.querySelectorAll('.editor-block').forEach(function (row, index) {
      row.classList.toggle('selected', index === draft.selectedIndex);
      ['x', 'y', 'w', 'h'].forEach(function (key) { row.querySelector('.editor-geometry-' + key).value = String(draft.blocks[index][key]); });
    });
  }

  function previewOrder(ctx) {
    return ctx.orders.find(function (order) { return order.id === draft.previewOrderId; }) || {
      id: 'SAMPLE-1', allegro_id: '123456', buyer_name: 'Anna Kowalska', buyer_address: 'ul. Przykładowa 12\n00-001 Warszawa',
      courier: 'InPost', pickup_point: 'WAW01A', tracking_number: '123456789', items: [{ name: 'Sample item', quantity: 2, unit_price: 19.99 }],
    };
  }

  function refreshCanvas(ctx) {
    if (!ctx.ui || !ctx.ui.canvasNodes) return;
    var order = previewOrder(ctx);
    ctx.ui.canvasNodes.forEach(function (node, index) {
      var block = draft.blocks[index];
      node.style.left = block.x / 210 * 100 + '%'; node.style.top = block.y / 297 * 100 + '%';
      node.style.width = block.w / 210 * 100 + '%'; node.style.height = block.h / 297 * 100 + '%';
      // A4 width is 210 mm; font point size scales with the responsive page.
      node.style.fontSize = block.size * 100 / 595.28 + 'cqw';
      node.style.fontWeight = block.bold ? '700' : '400'; node.style.textAlign = block.align;
      node.classList.toggle('selected', index === draft.selectedIndex);
      var content = node.querySelector('.editor-canvas-content');
      if (block.type === 'logo') {
        var image = content.querySelector('img');
        if (block.image && /^data:image\/(png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(block.image)) image.setAttribute('src', block.image);
        else image.removeAttribute('src');
      } else if (block.type === 'items') {
        content.textContent = '';
        var table = el('table'); var header = el('tr');
        var headers = currentLanguage === 'pl' ? ['Produkt', 'Ilość'] : ['Product', 'Quantity'];
        if (block.show_prices) headers.push(currentLanguage === 'pl' ? 'Cena' : 'Price', currentLanguage === 'pl' ? 'Wartość' : 'Value');
        headers.forEach(function (value) { var cell = el('th'); cell.textContent = value; header.appendChild(cell); }); table.appendChild(header);
        var total = 0; var complete = (order.items || []).length > 0;
        (order.items || []).forEach(function (item) {
          var row = el('tr'); var cells = [item.name, item.quantity];
          if (item.unit_price == null) complete = false; else total += Number(item.unit_price) * Number(item.quantity);
          if (block.show_prices) cells.push(item.unit_price == null ? '—' : Number(item.unit_price).toFixed(2) + ' zł', item.unit_price == null ? '—' : (Number(item.unit_price) * Number(item.quantity)).toFixed(2) + ' zł');
          cells.forEach(function (value) { var cell = el('td'); cell.textContent = String(value == null ? '—' : value); row.appendChild(cell); }); table.appendChild(row);
        });
        if (block.show_prices && complete) {
          var totalRow = el('tr'); var totalLabel = el('td'); totalLabel.setAttribute('colspan', '3'); totalLabel.textContent = currentLanguage === 'pl' ? 'Razem' : 'Total';
          var amount = el('td'); amount.textContent = total.toFixed(2) + ' zł'; totalRow.appendChild(totalLabel); totalRow.appendChild(amount); table.appendChild(totalRow);
        }
        content.appendChild(table);
      } else if (block.type !== 'line') {
        var text = block.text;
        if (block.type === 'customer') text = '{{buyer.name}}\n{{buyer.address}}';
        content.textContent = resolveText(text, order);
      }
    });
    var unknown = unknownTokens(draft.blocks);
    ctx.ui.warnings.textContent = unknown.length ? t('doc.unknown') + ': ' + unknown.join(', ') : '';
  }

  function buildCanvas(ctx) {
    var canvas = el('div', 'editor-canvas'); labelControl(canvas, 'doc.canvas');
    var nodes = [];
    draft.blocks.forEach(function (block, index) {
      var node = el('div', 'editor-canvas-block'); node.setAttribute('tabindex', '0'); node.setAttribute('data-type', block.type);
      labelControl(node, TYPE_LABEL[block.type]);
      var content = el('div', 'editor-canvas-content');
      if (block.type === 'logo') { var img = el('img'); img.setAttribute('alt', ''); content.appendChild(img); }
      node.appendChild(content);
      var resize = iconButton('editor-resize', '↘', 'doc.resize'); node.appendChild(resize);
      function select() { draft.selectedIndex = index; syncGeometryInputs(ctx); refreshCanvas(ctx); }
      node.addEventListener('click', select);
      node.addEventListener('keydown', function (event) {
        if (collectionBusy) return;
        if (event.target !== node) return;
        var steps = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); draft.blocks.splice(index, 1); markDirty(); render(ctx); return; }
        if (!steps[event.key]) return;
        event.preventDefault(); select(); var step = event.shiftKey ? 10 : 1;
        // Moving preserves dimensions at the page edge.
        block.x = Math.max(0, Math.min(210 - block.w, block.x + steps[event.key][0] * step));
        block.y = Math.max(0, Math.min(297 - block.h, block.y + steps[event.key][1] * step));
        markDirty(); syncGeometryInputs(ctx); refreshUI(ctx);
      });
      var gesture = null;
      node.addEventListener('pointerdown', function (event) {
        if (collectionBusy) return;
        if (event.button !== undefined && event.button !== 0) return;
        event.preventDefault(); select(); node.focus();
        var rect = canvas.getBoundingClientRect();
        gesture = { id: event.pointerId, x: event.clientX, y: event.clientY, block: { x: block.x, y: block.y, w: block.w, h: block.h }, resize: event.target === resize, width: rect.width, height: rect.height };
        if (node.setPointerCapture) node.setPointerCapture(event.pointerId);
      });
      node.addEventListener('pointermove', function (event) {
        if (collectionBusy) return;
        if (!gesture || event.pointerId !== gesture.id || !gesture.width || !gesture.height) return;
        var dx = Math.round((event.clientX - gesture.x) * 210 / gesture.width), dy = Math.round((event.clientY - gesture.y) * 297 / gesture.height);
        if (gesture.resize) { block.w = gesture.block.w + dx; block.h = gesture.block.h + dy; }
        else { block.x = Math.max(0, Math.min(210 - block.w, gesture.block.x + dx)); block.y = Math.max(0, Math.min(297 - block.h, gesture.block.y + dy)); }
        clampGeometry(block); markDirty(); syncGeometryInputs(ctx); refreshUI(ctx);
      });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(function (type) { node.addEventListener(type, function () { gesture = null; }); });
      nodes.push(node); canvas.appendChild(node);
    });
    return { canvas: canvas, nodes: nodes };
  }

  function collectionAction(ctx, action, id) {
    if (draft.saving || collectionBusy) return Promise.resolve();
    if (action === 'delete' && settingsCache.templates.length < 2 || action === 'duplicate' && settingsCache.templates.length >= 10) return Promise.resolve();
    if (action === 'delete' && !window.confirm(t('doc.confirmDelete'))) return Promise.resolve();
    // Duplicate/save must snapshot the latest draft, rather than silently cloning stale server content.
    var dirty = draft.revision > 0 && draft.status !== 'saved' && draft.status !== 'idle';
    if (action === 'select' || action === 'delete') {
      if (dirty && !window.confirm(t('doc.discard'))) { render(ctx); return Promise.resolve(); }
    }
    var prepare = action === 'duplicate' && dirty ? doSave(ctx) : Promise.resolve();
    collectionBusy = true; refreshUI(ctx);
    return prepare.then(function () {
      if (action === 'duplicate' && (draft.status === 'error' || templateBlockedReason() || draft.status === 'dirty')) throw new Error(draft.error || t(draft.errorKey || templateBlockedReason() || 'doc.statusDirty'));
      return api('/print/document-templates/' + encodeURIComponent(id) + (action === 'delete' ? '' : '/' + action), {
        method: action === 'delete' ? 'DELETE' : 'POST', headers: { 'Content-Type': 'application/json' },
        ...(action === 'duplicate' ? { body: JSON.stringify({ name: draft.name.slice(0, 90) + ' (copy)' }) } : {}),
      });
    }).then(function (saved) {
      draft = null; syncDraft(saved); if (onSaved) onSaved(saved);
      if (activeInstance) { var active = activeInstance.ctx; draft.previewOrderId = active.orders.length ? active.orders[0].id : ''; render(active); }
    }).catch(function (err) { setError(err.message || String(err)); }).finally(function () { collectionBusy = false; refreshActive(); });
  }

  function render(ctx) {
    teardown();
    draft.selectedIndex = Math.max(0, Math.min(draft.blocks.length - 1, draft.selectedIndex));
    var root = el('div', 'document-editor');

    // Source selection: which document the print buttons actually serve.
    var sourceWrap = el('div', 'editor-source');
    var sourceLabel = el('span', 'editor-label');
    setText(sourceLabel, 'doc.source');
    sourceWrap.appendChild(sourceLabel);
    [['upload', 'doc.sourceUpload'], ['template', 'doc.sourceTemplate']].forEach(function (pair) {
      var label = el('label', 'editor-source-option');
      var input = document.createElement('input');
      input.setAttribute('type', 'radio');
      input.setAttribute('name', 'doc-source');
      input.setAttribute('value', pair[0]);
      input.value = pair[0];
      input.checked = draft.source === pair[0];
      input.addEventListener('change', function () {
        draft.source = pair[0];
        markDirty();
        refreshUI(ctx);
      });
      var span = el('span');
      setText(span, pair[1]);
      label.appendChild(input);
      label.appendChild(span);
      sourceWrap.appendChild(label);
    });
    root.appendChild(sourceWrap);

    var templateWrap = el('div', 'editor-template');
    var collection = el('div', 'editor-collection');
    var templateSelect = el('select', 'editor-template-select'); labelControl(templateSelect, 'doc.templates');
    (settingsCache.templates || []).forEach(function (template) { var option = el('option'); option.value = template.id; option.textContent = template.name; templateSelect.appendChild(option); });
    templateSelect.value = draft.templateId;
    templateSelect.addEventListener('change', function () { return collectionAction(ctx, 'select', templateSelect.value); });
    var duplicate = el('button', 'editor-template-duplicate'); duplicate.setAttribute('type', 'button'); setText(duplicate, 'doc.duplicate');
    duplicate.addEventListener('click', function () { return collectionAction(ctx, 'duplicate', draft.templateId); });
    var deleteTemplate = el('button', 'editor-template-delete'); deleteTemplate.setAttribute('type', 'button'); setText(deleteTemplate, 'doc.deleteTemplate');
    deleteTemplate.addEventListener('click', function () { return collectionAction(ctx, 'delete', draft.templateId); });
    [templateSelect, duplicate, deleteTemplate].forEach(function (node) { collection.appendChild(node); }); templateWrap.appendChild(collection);
    var nameLabel = el('label', 'editor-label');
    setText(nameLabel, 'doc.templateName');
    nameLabel.setAttribute('for', 'document-template-name');
    var nameInput = document.createElement('input');
    nameInput.setAttribute('type', 'text');
    addClass(nameInput, 'editor-template-name');
    nameInput.setAttribute('id', 'document-template-name');
    nameInput.setAttribute('maxlength', String(MAX_NAME));
    nameInput.value = draft.name;
    nameInput.addEventListener('input', function () {
      draft.name = String(nameInput.value || '').slice(0, MAX_NAME);
      markDirty();
      refreshUI(ctx);
    });
    templateWrap.appendChild(nameLabel);
    templateWrap.appendChild(nameInput);

    var blocksWrap = el('div', 'editor-blocks');
    draft.blocks.forEach(function (block, index) { blocksWrap.appendChild(buildBlock(ctx, block, index)); });
    var workspace = el('div', 'editor-workspace'); var canvasUI = buildCanvas(ctx);
    var canvasWrap = el('div', 'editor-canvas-wrap'); var instructions = el('p', 'editor-canvas-instructions'); setText(instructions, 'doc.canvas'); canvasWrap.appendChild(instructions); canvasWrap.appendChild(canvasUI.canvas);
    var warnings = el('p', 'editor-warnings'); warnings.setAttribute('role', 'status'); canvasWrap.appendChild(warnings);
    bindNode(warnings, function () { var tokens = unknownTokens(draft.blocks); return tokens.length ? t('doc.unknown') + ': ' + tokens.join(', ') : ''; });
    workspace.appendChild(canvasWrap); workspace.appendChild(blocksWrap); templateWrap.appendChild(workspace);

    var addRow = el('div', 'editor-add');
    var typeSelect = document.createElement('select');
    addClass(typeSelect, 'editor-block-type');
    labelControl(typeSelect, 'doc.blockType');
    BLOCK_TYPES.forEach(function (type) {
      var option = document.createElement('option');
      option.setAttribute('value', type);
      option.value = type;
      setText(option, TYPE_LABEL[type]);
      typeSelect.appendChild(option);
    });
    typeSelect.value = BLOCK_TYPES[0];
    var addBtn = document.createElement('button');
    addBtn.setAttribute('type', 'button');
    addClass(addBtn, 'editor-add-block');
    setText(addBtn, 'doc.addBlock');
    addBtn.addEventListener('click', function () {
      if (draft.blocks.length >= MAX_BLOCKS) return;
      draft.blocks.push(emptyBlock(typeSelect.value || BLOCK_TYPES[0]));
      draft.selectedIndex = draft.blocks.length - 1;
      markDirty();
      render(ctx);
    });
    addRow.appendChild(typeSelect);
    addRow.appendChild(addBtn);
    templateWrap.appendChild(addRow);

    var previewOrderLabel = el('label', 'editor-label');
    setText(previewOrderLabel, 'doc.previewOrder');
    previewOrderLabel.setAttribute('for', 'document-preview-order');
    var previewOrder = el('select', 'editor-preview-order');
    previewOrder.setAttribute('id', 'document-preview-order');
    var sampleOption = el('option'); sampleOption.value = ''; setText(sampleOption, 'doc.sample'); previewOrder.appendChild(sampleOption);
    ctx.orders.forEach(function (order) {
      var option = document.createElement('option');
      option.value = order.id;
      option.setAttribute('value', order.id);
      option.textContent = (order.buyer_name || order.id) + (order.allegro_id ? ' — ' + order.allegro_id : '');
      previewOrder.appendChild(option);
    });
    previewOrder.value = draft.previewOrderId;
    previewOrder.addEventListener('change', function () { draft.previewOrderId = previewOrder.value; refreshUI(ctx); });
    templateWrap.appendChild(previewOrderLabel);
    templateWrap.appendChild(previewOrder);

    var actions = el('div', 'editor-actions');
    var saveBtn = document.createElement('button');
    saveBtn.setAttribute('type', 'button');
    addClass(saveBtn, 'editor-save');
    setText(saveBtn, 'common.save');
    saveBtn.addEventListener('click', function () { return doSave(ctx); });
    var previewBtn = document.createElement('button');
    previewBtn.setAttribute('type', 'button');
    addClass(previewBtn, 'editor-preview');
    setText(previewBtn, 'doc.preview');
    previewBtn.addEventListener('click', function () { return doPreview(ctx); });
    var statusNode = el('span', 'editor-status');
    statusNode.setAttribute('role', 'status');
    var noteNode = el('span', 'editor-preview-note');
    bindNode(statusNode, statusText);
    bindNode(noteNode, function () { return previewNoteText(ctx); });
    actions.appendChild(saveBtn);
    actions.appendChild(previewBtn);
    actions.appendChild(statusNode);
    actions.appendChild(noteNode);
    templateWrap.appendChild(actions);
    root.appendChild(templateWrap);

    if (ctx.root && ctx.root.parentNode) ctx.root.remove();
    ctx.container.appendChild(root);
    ctx.root = root;
    ctx.ui = { statusNode: statusNode, noteNode: noteNode, saveBtn: saveBtn, previewBtn: previewBtn, canvasNodes: canvasUI.nodes, warnings: warnings, collectionControls: [templateSelect, duplicate, deleteTemplate] };
    refreshUI(ctx);
  }

  function adoptSaved(saved) {
    if (!saved || !saved.templates) return;
    settingsCache = saved;
    var template = saved.templates.filter(function (item) { return item.id === draft.templateId; })[0];
    if (template) {
      draft.name = template.name;
      draft.blocks = cloneBlocks(template.blocks);
    }
    if (saved.profiles && saved.profiles.default) {
      draft.source = saved.profiles.default.source === 'template' ? 'template' : 'upload';
    }
  }

  function doSave(ctx) {
    if (!draft || draft.saving || collectionBusy) return lastSavePromise || Promise.resolve();
    var blocked = templateBlockedReason();
    if (blocked) { setError('', blocked); return Promise.resolve(); }
    var submittedRevision = draft.revision;
    draft.saving = true;
    draft.status = 'saving';
    refreshActive();
    var request;
    try {
      request = api('/print/document-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: draft.source, template: buildTemplate() }),
      });
    } catch (err) {
      draft.saving = false;
      setError(err && err.message ? err.message : String(err));
      return Promise.resolve();
    }
    lastSavePromise = Promise.resolve(request).then(function (saved) {
      if (draft.revision === submittedRevision) {
        adoptSaved(saved);
        draft.status = 'saved';
        // New normalized blocks need new listeners, not stale captured objects.
        if (activeInstance) render(activeInstance.ctx);
      } else {
        draft.status = 'dirty';
      }
      draft.error = '';
      draft.errorKey = null;
      if (onSaved) onSaved(saved);
    }).catch(function (err) {
      draft.status = 'error';
      draft.errorKey = null;
      draft.error = err && err.message ? err.message : String(err);
    }).then(function () {
      draft.saving = false;
      refreshActive();
    });
    return lastSavePromise;
  }

  function doPreview(ctx) {
    var blocked = templateBlockedReason();
    if (!ctx.orders.length || !draft.previewOrderId || !hasContent() || blocked) return Promise.resolve();
    var body = JSON.stringify({ order_id: draft.previewOrderId, template: buildTemplate() });
    var promise;
    try {
      // openPdf reserves the print window before the request and reports API
      // failures as a message rather than a JSON tab.
      promise = openPdf('/print/document-preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body,
      });
    } catch (err) {
      setError(err && err.message ? err.message : String(err));
      return Promise.resolve();
    }
    return Promise.resolve(promise).catch(function (err) {
      setError(err && err.message ? err.message : String(err));
    });
  }

  function mount(container, options) {
    options = options || {};
    syncDraft(options.settings);
    onSaved = options.onSaved || null;
    var ctx = { container: container, orders: options.orders || [], root: null, ui: null };
    if (!draft.previewOrderId && draft.revision === 0 || draft.previewOrderId && !ctx.orders.some(function (order) { return order.id === draft.previewOrderId; })) {
      draft.previewOrderId = ctx.orders.length ? ctx.orders[0].id : '';
    }
    var instance = { ctx: ctx, refresh: function () { refreshUI(ctx); } };
    activeInstance = instance;
    render(ctx);
    return instance;
  }

  return {
    mount: mount,
    validateLogoFile: validateLogoFile,
    get draft() { return draft; },
    get lastSavePromise() { return lastSavePromise; },
  };
}());
