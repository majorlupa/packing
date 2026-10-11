// Custom document block editor. Weles has no template library: the settings UI
// edits the single active template and chooses which source (uploaded PDF or the
// designed template) is printed. The editor owns a module-local draft so an
// unsaved template survives re-renders, navigation away, language switches and
// an in-flight save. It builds its DOM programmatically (no HTML string), which
// keeps user-authored text out of any markup path.
//
// Loaded after app.js; uses the shared t(), setText(), bindDynamicText(), api()
// and openPdf() helpers from the page.
var DocumentEditor = (function () {
  'use strict';

  var BLOCK_TYPES = ['heading', 'text', 'customer', 'items', 'logo'];
  var TYPE_LABEL = {
    heading: 'doc.blockHeading', text: 'doc.blockText', customer: 'doc.blockCustomer',
    items: 'doc.blockItems', logo: 'doc.blockLogo',
  };
  var TOKENS = ['buyer_name', 'buyer_address', 'order_number', 'date', 'courier', 'pickup_point', 'tracking_number'];
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
    return { type: type, text: '', align: 'left', size: 12, show_prices: false, image: '' };
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
    return (blocks || []).map(function (block) {
      return {
        type: block.type, text: block.text || '', align: normalizeAlign(block.align),
        size: normalizeSize(block.size), show_prices: Boolean(block.show_prices), image: block.image || '',
      };
    });
  }

  // Mirrors the backend's notion of a non-empty template: only content the PDF
  // would actually show counts.
  function hasContent() {
    return Boolean(draft) && draft.blocks.some(function (block) {
      return block.type === 'customer' || block.type === 'items'
        || (block.type === 'logo' && block.image)
        || ((block.type === 'heading' || block.type === 'text') && (block.text || '').trim());
    });
  }

  function buildBlocks() {
    return draft.blocks.map(function (block) {
      return {
        type: block.type, text: block.text || '', align: normalizeAlign(block.align),
        size: normalizeSize(block.size), show_prices: Boolean(block.show_prices),
        image: block.type === 'logo' ? (block.image || '') : '',
      };
    });
  }

  function buildTemplate() {
    return { id: draft.templateId, name: (draft.name || '').slice(0, MAX_NAME), blocks: buildBlocks() };
  }

  function syncDraft(settings) {
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
      status: 'idle', error: '', saving: false, revision: 0, previewOrderId: '',
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
    if (ui.saveBtn) ui.saveBtn.disabled = draft.saving || Boolean(blocked);
    if (ui.previewBtn) ui.previewBtn.disabled = !ctx.orders.length || !hasContent() || Boolean(blocked);
    if (ui.noteNode) ui.noteNode.textContent = previewNoteText(ctx);
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

    if (block.type === 'heading' || block.type === 'text') {
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
      if (block.image) preview.setAttribute('src', block.image);
      row.appendChild(preview);
      var logoNote = el('span', 'editor-logo-name');
      setText(logoNote, block.image ? 'doc.logoChosen' : 'doc.logoNone');
      row.appendChild(logoNote);
    }
    return row;
  }

  function render(ctx) {
    teardown();
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
    templateWrap.appendChild(blocksWrap);

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
    ctx.orders.forEach(function (order) {
      var option = document.createElement('option');
      option.value = order.id;
      option.setAttribute('value', order.id);
      option.textContent = (order.buyer_name || order.id) + (order.allegro_id ? ' — ' + order.allegro_id : '');
      previewOrder.appendChild(option);
    });
    previewOrder.value = draft.previewOrderId;
    previewOrder.disabled = !ctx.orders.length;
    previewOrder.addEventListener('change', function () { draft.previewOrderId = previewOrder.value; });
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
    ctx.ui = { statusNode: statusNode, noteNode: noteNode, saveBtn: saveBtn, previewBtn: previewBtn };
    refreshUI(ctx);
  }

  function adoptSaved(saved) {
    if (!saved || !saved.templates) return;
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
    if (!draft || draft.saving) return lastSavePromise || Promise.resolve();
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
    if (!ctx.orders.length || !hasContent() || blocked) return Promise.resolve();
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
    if (!ctx.orders.some(function (order) { return order.id === draft.previewOrderId; })) {
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
