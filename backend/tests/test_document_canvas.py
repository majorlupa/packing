import io
from datetime import date
from html import escape

import pytest
from conftest import sample_order
from pypdf import PdfReader


def draft(*blocks):
    return {"id": "default", "name": "Canvas", "blocks": list(blocks)}


def test_legacy_migration_is_durable_and_idempotent(app_env):
    from documents import DocumentSettings, DocumentTemplate

    legacy = draft({"type": "heading", "text": "Hello {{buyer_name}}"},
                   {"type": "text", "text": "Second"}, {"type": "customer"},
                   {"type": "items"}, {"type": "logo"})
    migrated = DocumentTemplate.model_validate(legacy)
    assert legacy["blocks"][0] == {"type": "heading", "text": "Hello {{buyer_name}}"}
    assert migrated.blocks[0].bold is True
    assert [(b.x, b.y) for b in migrated.blocks] == [(18, 18), (18, 42), (18, 72), (18, 108), (18, 204)]
    assert all(b.w > 0 and b.h > 0 for b in migrated.blocks)
    assert DocumentTemplate.model_validate(migrated.model_dump()).model_dump() == migrated.model_dump()
    settings = app_env.store.get_document_settings()
    settings["templates"] = [legacy]
    state = app_env.default_state({"o-1": sample_order()})
    state["document_settings"] = settings
    app_env.write_state(state)
    restored = app_env.store.get_document_settings()
    assert restored["templates"][0] == migrated.model_dump()
    assert app_env.store.get_order("o-1") is not None
    assert app_env.store.state_status()["quarantined"] == 0
    app_env.store.save_document_settings(restored)
    assert app_env.store.get_document_settings() == DocumentSettings.model_validate(restored).model_dump()


def test_geometry_clamps_to_a4_and_partial_geometry_gets_defaults(app_env):
    from documents import DocumentTemplate

    model = DocumentTemplate.model_validate(draft(
        {"type": "text", "x": -8, "y": 999, "w": 999, "h": -3},
        {"type": "line", "x": 999, "y": -2, "w": 8, "h": 999},
        {"type": "placeholder", "text": "{{buyer.name}}", "x": 20},
    ))
    assert (model.blocks[0].x, model.blocks[0].y, model.blocks[0].w, model.blocks[0].h) == (0, 296, 210, 1)
    assert (model.blocks[1].x, model.blocks[1].y, model.blocks[1].w, model.blocks[1].h) == (209, 0, 1, 297)
    for block in model.blocks:
        assert 0 <= block.x < 210 and 0 <= block.y < 297
        assert 1 <= block.w <= 210 - block.x and 1 <= block.h <= 297 - block.y
    assert model.warnings == []


@pytest.mark.parametrize("field", ["x", "y", "w", "h"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_geometry_rejected(app_env, field, value):
    from documents import DocumentTemplate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DocumentTemplate.model_validate(draft({"type": "text", field: value}))


def test_element_limit(app_env):
    from documents import DocumentTemplate
    from pydantic import ValidationError

    assert len(DocumentTemplate.model_validate(draft(*[{"type": "line"}] * 50)).blocks) == 50
    with pytest.raises(ValidationError):
        DocumentTemplate.model_validate(draft(*[{"type": "line"}] * 51))


@pytest.mark.parametrize("type", ["heading", "text", "placeholder", "customer", "items", "logo", "line"])
@pytest.mark.parametrize("geometry", [{}, {"x": 10}, {"x": 10, "y": 20, "w": 100, "h": 30}])
def test_unknown_placeholders_warn_independently_of_geometry(app_env, type, geometry):
    from documents import DocumentTemplate, render_document_html
    from models.order import Order

    template = DocumentTemplate.model_validate(draft({
        "type": type, **geometry,
        "text": "{{buyer.name}} {{ unknown.field }} {{unknown.field}} {{Unknown_2}}",
    }))
    assert template.warnings == ["Unknown placeholder: Unknown_2", "Unknown placeholder: unknown.field"]
    assert DocumentTemplate.model_validate(template.model_dump()).warnings == template.warnings
    if type in ("heading", "text", "placeholder"):
        html = render_document_html(template, Order(**sample_order()))
        assert 'Jan Kowalski — — —' in html


def test_unknown_placeholder_warnings_saved_and_recomputed(app_env, client):
    template = draft({"type": "text", "text": "{{missing.field}} {{buyer.name}}"})
    template["warnings"] = ["Untrusted client warning"]
    response = client.post('/api/print/document-settings', json={"source": "template", "template": template})
    assert response.status_code == 200
    assert response.json()['templates'][0]['warnings'] == ['Unknown placeholder: missing.field']
    assert client.get('/api/print/document-settings').json() == response.json()
    template['blocks'][0]['text'] = '{{buyer.name}}'
    response = client.post('/api/print/document-settings', json={"source": "template", "template": template})
    assert response.status_code == 200
    assert response.json()['templates'][0]['warnings'] == []
    assert client.get('/api/print/document-settings').json() == response.json()


@pytest.mark.parametrize("language", ["pl", "en"])
def test_dotted_and_legacy_resolution_escaped_single_pass_and_warnings(app_env, language):
    from documents import DocumentTemplate, render_document_html
    from localization import current_language, date_format
    from models.order import Order

    order = Order(**sample_order(buyer_name='<script>{{order.id}}</script>',
                                buyer_address='A & "B"',
                                items=[{"name": "<img> {{buyer.name}}", "quantity": 3, "unit_price": None}]))
    template = DocumentTemplate.model_validate(draft({
        "type": "placeholder", "x": 10, "y": 10, "w": 180, "h": 80, "bold": True,
        "text": "{{buyer.name}} / {{buyer.address}} / {{order.id}} / {{order.date}} / {{items}}\n"
                "{{buyer_name}} / {{buyer_address}} / {{order_number}} / {{date}} / {{unknown.field}}",
    }))
    token = current_language.set(language)
    try:
        html = render_document_html(template, order)
        assert date.today().strftime(date_format(language)) in html
    finally:
        current_language.reset(token)
    assert '<script>' not in html and '<img>' not in html
    assert escape(order.buyer_name) in html and escape(order.buyer_address) in html
    assert '&lt;img&gt; {{buyer.name}} × 3' in html
    assert 'a-1' in html and 'o-1' in html and 'font-weight:bold' in html and '—' in html
    assert template.warnings == ['Unknown placeholder: unknown.field']
    assert DocumentTemplate.model_validate(template.model_dump()).warnings == template.warnings


@pytest.mark.parametrize("geometry", [{}, {"x": 10}])
@pytest.mark.parametrize("text", ["{{bad", "{{7*7}}", "{% for x in y %}", "{# comment #}", "{{buyer.name()}}"])
def test_malformed_syntax_still_rejected(app_env, text, geometry):
    from documents import DocumentTemplate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DocumentTemplate.model_validate(draft({"type": "text", **geometry, "text": text}))


@pytest.mark.parametrize("block", [
    {"type": "text", "size": 12.5}, {"type": "text", "size": True},
    {"type": "text", "size": "12"}, {"type": "text", "bold": "url(file:///etc/passwd)"},
    {"type": "text", "x": "0; background:url(https://example.com)"},
    {"type": "text", "style": "position:fixed"},
])
def test_canvas_style_injection_and_strict_font_size_rejected(client, block):
    before = client.get('/api/print/document-settings').json()
    response = client.post('/api/print/document-settings', json={"source": "template", "template": draft(block)})
    assert response.status_code == 422
    assert client.get('/api/print/document-settings').json() == before


def test_preview_absolute_a4_real_pdf(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    template = draft({"type": "text", "text": "Position {{order.id}}", "x": 100, "y": 120,
                      "w": 90, "h": 15, "bold": True},
                     {"type": "line", "x": 20, "y": 150, "w": 170, "h": 1})
    before = client.get('/api/print/document-settings').json()
    response = client.post('/api/print/document-preview', json={"order_id": "o-1", "template": template})
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF-')
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) == pytest.approx(210 * 72 / 25.4, abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(297 * 72 / 25.4, abs=0.01)
    assert 'Position o-1' in page.extract_text()
    positions = []

    def visitor(text, cm, tm, font, size):
        if 'Position' in text:
            positions.append((cm, tm))

    page.extract_text(visitor_text=visitor)
    assert positions
    # WeasyPrint's text matrix expresses positions in CSS px inside the PDF page transform.
    assert positions[0][1][4] == pytest.approx(100 * 96 / 25.4, abs=1)
    # Baseline is below the requested top by one line of 12pt text.
    assert 120 * 96 / 25.4 < positions[0][1][5] < 120 * 96 / 25.4 + 25
    assert client.get('/api/print/document-settings').json() == before


def test_template_collection_endpoints_and_reference_integrity(app_env, client):
    root = '/api/print/document-templates'
    initial = client.get('/api/print/document-settings').json()
    assert client.delete(root + '/default').status_code == 422
    response = client.post(root + '/default/duplicate', json={"name": "Packing note"})
    assert response.status_code == 200
    settings = response.json()
    duplicate_id = settings['profiles']['default']['active_template_id']
    assert duplicate_id != 'default'
    assert settings['templates'][1]['name'] == 'Packing note'
    assert client.get('/api/print/document-settings').json() == settings
    assert client.post(root + '/default/select').json()['profiles']['default']['active_template_id'] == 'default'
    changed = draft({"type": "text", "text": "{{buyer.name}}", "x": 10})
    changed['id'] = duplicate_id
    saved = client.post('/api/print/document-settings', json={"source": "template", "template": changed})
    assert saved.status_code == 200
    assert saved.json()['profiles']['default']['active_template_id'] == duplicate_id
    assert client.get('/api/print/document-settings').json() == saved.json()
    settings = saved.json()
    settings['profiles']['other'] = {"source": "template", "active_template_id": duplicate_id}
    app_env.store.save_document_settings(settings)
    deleted = client.delete(root + '/' + duplicate_id)
    assert deleted.status_code == 200
    assert all(profile['active_template_id'] == 'default' for profile in deleted.json()['profiles'].values())
    assert client.get('/api/print/document-settings').json() == deleted.json()
    assert len(deleted.json()['templates']) == len(initial['templates'])
    for suffix, method in [('/missing/select', client.post), ('/missing/duplicate', client.post),
                           ('/missing', client.delete)]:
        assert method(root + suffix).status_code == 404
        assert method(root + suffix, headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_template_collection_limit_and_optional_duplicate_name(client):
    root = '/api/print/document-templates'
    assert client.post(root + '/default/duplicate', json={"name": ""}).status_code == 422
    for _ in range(9):
        assert client.post(root + '/default/duplicate').status_code == 200
    settings = client.get('/api/print/document-settings').json()
    assert len(settings['templates']) == 10
    assert settings['templates'][1]['name'].endswith(' copy')
    assert client.post(root + '/default/duplicate', json={}).status_code == 422
    assert client.get('/api/print/document-settings').json() == settings


def test_duplicate_is_independent_and_failures_preserve_settings(client):
    root = '/api/print/document-templates'
    original = draft({"type": "text", "text": "Original {{unknown}}", "x": 30, "y": 40})
    original['name'] = 'N' * 100
    saved = client.post('/api/print/document-settings', json={"source": "template", "template": original})
    assert saved.status_code == 200
    duplicated = client.post(root + '/default/duplicate')
    assert duplicated.status_code == 200
    settings = duplicated.json()
    duplicate = settings['templates'][1]
    assert len(duplicate['name']) == 100 and duplicate['name'].endswith(' copy')
    assert duplicate['blocks'] == settings['templates'][0]['blocks']
    assert duplicate['warnings'] == ['Unknown placeholder: unknown']
    duplicate['blocks'][0]['text'] = 'Changed {{buyer.name}}'
    saved = client.post('/api/print/document-settings', json={"source": "template", "template": duplicate})
    assert saved.status_code == 200
    settings = client.get('/api/print/document-settings').json()
    assert settings == saved.json()
    assert settings['templates'][0]['blocks'][0]['text'] == 'Original {{unknown}}'
    assert settings['templates'][1]['warnings'] == []
    invalid = draft({"type": "line"})
    invalid['id'] = 'missing'
    assert client.post(
        '/api/print/document-settings', json={"source": "template", "template": invalid},
    ).status_code == 422
    assert client.post(root + '/default/duplicate', json={"name": 'N' * 101}).status_code == 422
    assert client.get('/api/print/document-settings').json() == settings
    deleted = client.delete(root + '/default')
    assert deleted.status_code == 200
    assert deleted.json()['profiles']['default']['active_template_id'] == duplicate['id']
    assert client.get('/api/print/document-settings').json() == deleted.json()


def test_settings_rejects_invalid_references_and_duplicates(app_env):
    from documents import DocumentSettings
    from pydantic import ValidationError

    settings = app_env.store.get_document_settings()
    settings['profiles']['default']['active_template_id'] = 'missing'
    with pytest.raises(ValidationError):
        DocumentSettings.model_validate(settings)
    settings['profiles']['default']['active_template_id'] = 'default'
    settings['templates'].append(settings['templates'][0])
    with pytest.raises(ValidationError):
        DocumentSettings.model_validate(settings)
