# Custom document editor

Approved scope: one editable template initially, with storage that leaves room for several templates and future per-Allegro-account selection. No account integration or credentials change in this feature. No commits unless requested.

## User experience

Keep sales-document settings and rendering unchanged. Settings → Documents gains an explicit choice of Uploaded PDF or Designed template. Keep both saved when switching; only the selected source is printed. Existing installations default to Uploaded PDF.

The block editor supports heading, text, customer-details, product-table and logo blocks, with add/remove/up/down controls. Text/heading blocks have alignment and size controls. Text supports insertion of allowlisted order placeholders via buttons. Product tables optionally include prices. Use one active template named by the user; do not expose a template library yet. Logos accept PNG/JPEG uploads, never arbitrary URLs or SVG. PDF preview uses an existing selected order and current unsaved draft. No fake order previews; disable preview with an explanation when there are no orders. Saving updates the active template and selected source atomically. Navigation and language changes must not silently overwrite a draft.

Packing custom-document printing sends the order ID. Combined printing includes the unchanged sales document followed by the selected custom document. Printing a designed template without an order is rejected. Missing optional values render as an em dash, unknown/malformed placeholders are rejected, tracking reads persisted order data only and never creates a shipment. UI controls and system-provided PDF labels support Polish/English; user-authored text is not automatically translated.

## Storage and interfaces

Add validated `document_settings` to state.json via store.py's existing atomic persistence, normalization and quarantine mechanisms. Schema: `{version: 1, templates: [{id, name, blocks}], profiles: {default: {source: 'upload'|'template', active_template_id}}}`. Profiles are document-selection scopes independent of OAuth; currently only default is used. Existing installations receive template id `default` with an empty block list, source upload. Limits: 10 templates, 50 blocks/template, name 100 characters, text 4000 characters/block; IDs bounded and safe. API saves only the default profile and its active template, preserving other collection entries for future compatibility.

Block schema: `{type: 'heading'|'text'|'customer'|'items'|'logo', text: '', align: 'left'|'center'|'right', size: 12, show_prices: false, image: ''}`. Size integer 8–36. Logo image is a bounded PNG/JPEG data URI (maximum decoded 2 MB) validated structurally; other blocks cannot supply an image. The sum of encoded image strings per template is capped at 2,800,000 characters (about 2 MB of decoded images) to bound repeated JSON state reads. Heading/text use plain text, not user-controlled Jinja or HTML.

GET `/api/print/document-settings` returns the schema. POST accepts `{source, template: {id, name, blocks}}` and returns the full saved schema. Template id must equal the current default active template id (no hidden creation/deletion via this UI).

POST `/api/print/document-preview` accepts `{order_id, template: {id, name, blocks}}` and returns a PDF without saving. GET `/api/print/custom-doc/info` continues to report `available` for the active source plus `source`, `upload_available`, and `size` (uploaded file size or null). GET `/api/print/custom-doc?order_id=...` prints the active source. Existing upload/delete endpoints remain file-only operations; they do not change selected source. GET `/api/print/orders/{order_id}/combined` appends whichever source is selected. A selected but unavailable custom source is omitted from combined output, matching existing no-custom-document behavior; standalone printing gives a localized 404.

Allowlisted placeholders: buyer_name, buyer_address, order_number (Allegro ID), date (render date in request language), courier, pickup_point, tracking_number. No attribute access, expressions, loops or arbitrary template code. Tables use existing order.items; unknown prices show an em dash and a total is shown only if all item prices are present.

## Rendering and security

Put schema, placeholder resolution and HTML construction in a focused backend document module; put new routes in a dedicated router under /print. WeasyPrint produces PDFs using the existing dependency. Escape every user/order string, preserve newlines as text, and use only validated alignment/size values. Reject external/local resource access in the PDF renderer: only the validated embedded logo data may be fetched. Use bounded JSON models, API authentication and no-store responses for PDF previews/customer documents. Validate uploaded PDF readability, not only its signature, before replacing the old file; leave existing valid upload intact on errors.

Malformed saved document settings are preserved in quarantine and safely replaced with defaults; normal queue processing remains available. Retain collection entries and inactive assets during source switches.

## Verification

Backend tests cover migration, multiple-entry preservation, persistence/reload, validation/quarantine, auth, escaped order/text inputs, placeholder rejection, missing optional fields, unsaved preview isolation, PNG/JPEG restrictions, genuine PDF content/pages, selected-source switching and combined output, and existing upload behavior. Frontend tests cover block operations, payloads, draft preservation, preview popup timing, order-specific printing and PL/EN catalog completeness. Run full backend and frontend suites, then an isolated browser flow against temporary state (never real orders, Allegro credentials or the live data directory). Verify multi-page product tables and Polish glyphs with rendered PDF extraction/visual inspection.
