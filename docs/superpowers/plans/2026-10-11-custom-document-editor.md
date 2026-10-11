# Custom Document Editor Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Let operators choose an uploaded PDF or design one personalized order document, preview it, and print it during packing.

Architecture: A validated document collection and independent selection profile live in the existing JSON store. A focused safe renderer produces PDF from structured blocks, while the vanilla frontend editor manages drafts and calls authenticated endpoints.

Tech Stack: Existing FastAPI/Pydantic, Jinja2/WeasyPrint/pypdf, vanilla JavaScript/CSS, pytest and node:test. No new runtime dependencies.

Spec: docs/superpowers/specs/2026-10-11-custom-document-editor-design.md

## Global Constraints

- Existing installations default to Uploaded PDF; sales documents remain unchanged.
- One template exposed now; keep a template collection and document profile independent of OAuth.
- No account integration or credentials change in this feature. No commits unless requested.
- Limits: 10 templates, 50 blocks/template, name 100 characters, text 4000 characters/block; IDs bounded and safe.
- Logos accept PNG/JPEG uploads, maximum decoded 2 MB; no URLs or SVG.
- Controls and system PDF labels support Polish/English. No arbitrary HTML/Jinja execution or resource fetching.
- Use temporary state and no real Allegro calls for tests/browser verification.

## File responsibilities

Create backend/documents.py for validated models, safe rendering and default schema; backend/routes/documents.py for settings and preview endpoints; backend/tests/test_documents.py for contract and PDF tests. Modify backend/store.py for durable document settings, backend/main.py for router inclusion, backend/routes/print_routes.py for active-source printing, backend/localization.py for new errors. Create frontend/static/document-editor.js for editor behavior, modify frontend/index.html for script inclusion, frontend/static/app.js for integration/translations and frontend/static/style.css for editor layout. Create frontend/tests/document-editor.test.cjs. Update README.md and CLAUDE.md for usage.

### Task 1: Durable schema and safe rendering

Interfaces: DocumentTemplate(id, name, blocks), DocumentSettings(version, templates, profiles), DocumentSave(source, template), DocumentPreview(order_id, template). default_document_settings() -> dict. render_document_pdf(template, order) -> bytes. store.get_document_settings() -> dict; store.save_document_settings(settings: dict) -> None.

- [x] Write backend tests before implementation: default state includes version 1, source upload and template id default; save/reload preserves inactive templates/profiles; unsupported placeholders and external logos fail validation.

```python
def test_default_document_settings(client):
    response = client.get('/api/print/document-settings')
    assert response.status_code == 200
    assert response.json()['profiles']['default'] == {'source': 'upload', 'active_template_id': 'default'}
```

- [x] Run `.venv/bin/python -m pytest backend/tests/test_documents.py -q` and verify missing endpoints/schema fail.
- [x] Implement bounded Pydantic models, allowlisted token replacement with escaped HTML, customer/items blocks and restricted WeasyPrint data-image fetcher. Extend store defaults/normalization with validation and quarantine, and add accessors using transact.
- [x] Add tests for escaped script-like buyer names, unknown and malformed placeholders, missing tracking, invalid sizes/types and real PDF bytes/text. Run the new tests.

### Task 2: API and existing print integration

Consumes Task 1 models and renderer. Produces GET/POST /print/document-settings, POST /print/document-preview, GET /print/custom-doc/info and GET /print/custom-doc?order_id=… with the exact spec contracts.

- [x] Add failing API tests for draft preview (state unchanged), template printing with required order, auth rejection and switching upload/template while preserving assets.

```python
def test_preview_requires_order(client):
    payload = {'order_id': 'missing', 'template': {'id': 'default', 'name': 'Insert', 'blocks': [{'type': 'text', 'text': 'Hello {{buyer_name}}'}]}}
    assert client.post('/api/print/document-preview', json=payload).status_code == 404
```

- [x] Verify failures with the targeted pytest command.
- [x] Register the new router; implement default-profile save by updating just its active entry. Validate a selected template is nonempty before activation. Preview drafts without saving; no-store PDF responses. Extend custom-doc info and route to resolve selected source; combined appends selected PDF with real order data. Validate uploaded PDFs before replacement and surface localized errors.
- [x] Test real uploaded PDF pages versus template PDF content, missing-source combined behavior, invalid upload preserving previous file, order 404, missing optional values, render errors and authentication. Run all backend tests.

### Task 3: Block editor and print UI

Consumes the Task 2 HTTP contracts. Editor exposed as DocumentEditor.mount(container, {settings, orders, onSaved}); owns draft, rendering and listeners. Integration invokes it below unchanged invoice controls. Save posts {source, template}; preview posts {order_id, template}; packing custom route includes order_id.

- [x] Write Node tests for block add/move/delete, save payload, unsaved-preview payload and popup open-before-fetch; run `node --test frontend/tests/document-editor.test.cjs` and verify failures.
- [x] Implement editor controls for source selection, template name, heading/text/customer/items/logo blocks, up/down/remove, align/size, price option, local image file conversion and dynamic-token insertion at the cursor. Keep draft across redraws/navigation and language changes; display save/unsaved/error statuses. Reject SVG and oversize logos before encoding. Disable preview with no orders and clear explanation.
- [x] Add Polish/English catalog entries to app.js, script include after app.js, editor CSS, and call mount from existing document settings without changing invoice controls. Adapt existing upload status handlers so selected-source availability remains correct. Pass order ID from packing print actions.
- [x] Run Node tests and existing localization/print/parcel suites. Verify catalog keys exist in both languages and every dynamic label follows current language without rewriting user text.

### Task 4: End-to-end verification and docs

- [x] Run `.venv/bin/python -m pytest backend/tests -q` and `node --test frontend/tests/*.test.cjs`; fix root causes.
- [x] Start isolated app with temporary state and dummy local credentials/access token, no live .env; exercise editor save, unsaved preview, order-specific PDF and upload/template switching in browser. Read back saved settings and PDFs. Include a long product list for multi-page pagination and Polish text.
- [x] Inspect rendered PDF page image(s) and extracted text for user fields, logo and table layout. Do not generate shipments or call Allegro.
- [x] Update usage docs, inspect git diff and report verified results plus any deployment left. Do not commit or start the real Docker service without user request.
