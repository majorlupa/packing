import io
import json

import pytest
from conftest import sample_order
from pypdf import PdfReader, PdfWriter


def template(*blocks, name="Customer insert"):
    return {"id": "default", "name": name, "blocks": list(blocks)}


def test_document_defaults_and_durable_collection(app_env):
    settings = app_env.store.get_document_settings()
    assert settings["version"] == 1
    assert settings["profiles"]["default"] == {"source": "upload", "active_template_id": "default"}
    settings["templates"].append({"id": "other", "name": "Other seller", "blocks": []})
    settings["profiles"]["future-account"] = {"source": "template", "active_template_id": "other"}
    app_env.store.save_document_settings(settings)
    restored = app_env.store.get_document_settings()
    assert restored == settings
    assert json.loads(app_env.state_file.read_text())["document_settings"] == settings


@pytest.mark.parametrize(
    "text", ["{{unknown}}", "{{ buyer.name }}", "{{7*7}}", "{{buyer_name", "buyer_name}}", "{% for x in y %}"]
)
def test_rejects_unsupported_template_syntax(app_env, text):
    from documents import DocumentTemplate
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DocumentTemplate.model_validate(template({"type": "text", "text": text}))


def test_safe_rendering_and_real_pdf(app_env):
    from documents import DocumentTemplate, render_document_html, render_document_pdf
    from models.order import Order
    order = Order(**sample_order(buyer_name='<script>alert("x")</script>', tracking_number=None))
    draft = DocumentTemplate.model_validate(template(
        {"type": "heading", "text": "Dziękujemy {{buyer_name}}", "align": "center", "size": 24},
        {"type": "text", "text": "Order {{order_number}}\nTracking {{tracking_number}}"},
        {"type": "customer"}, {"type": "items", "show_prices": True},
    ))
    html = render_document_html(draft, order)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'Tracking —' in html
    pdf = render_document_pdf(draft, order)
    assert pdf.startswith(b'%PDF-')
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert 'Dziękujemy' in text and 'a-1' in text and 'Wiertarka' in text


@pytest.mark.parametrize("image", [
    "https://example.com/logo.png", "file:///etc/passwd",
    "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,aGVsbG8=",
])
def test_rejects_unsafe_or_broken_logo(app_env, image):
    from documents import DocumentTemplate
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DocumentTemplate.model_validate(template({"type": "logo", "image": image}))


def pdf_text(response):
    assert response.status_code == 200, response.text[:300] if not response.is_success else ''
    return '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


def test_settings_save_preview_and_personalized_print(app_env, client):
    app_env.write_state(app_env.default_state({'o-1': sample_order()}))
    settings = client.get('/api/print/document-settings').json()
    draft = template({'type': 'text', 'text': 'Hello {{buyer_name}} / {{order_number}}'})
    preview = client.post('/api/print/document-preview', json={'order_id': 'o-1', 'template': draft})
    assert 'Hello Jan Kowalski / a-1' in pdf_text(preview)
    assert preview.headers['cache-control'] == 'no-store'
    assert client.get('/api/print/document-settings').json() == settings
    saved = client.post('/api/print/document-settings', json={'source': 'template', 'template': draft})
    assert saved.status_code == 200
    assert saved.json()['profiles']['default']['source'] == 'template'
    assert client.get('/api/print/custom-doc/info').json()['available'] is True
    assert client.get('/api/print/custom-doc').status_code == 422
    assert 'Hello Jan Kowalski / a-1' in pdf_text(client.get('/api/print/custom-doc?order_id=o-1'))
    assert 'Hello Jan Kowalski / a-1' in pdf_text(client.get('/api/print/orders/o-1/combined'))
    assert client.get('/api/print/custom-doc?order_id=missing').status_code == 404


def test_standalone_sales_pdf_never_appends_selected_custom_document(app_env, client):
    app_env.write_state(app_env.default_state({'o-1': sample_order()}))
    draft = template({'type': 'text', 'text': 'CUSTOM INSERT ONLY'})
    assert client.post(
        '/api/print/document-settings', json={'source': 'template', 'template': draft}
    ).status_code == 200
    response = client.get('/api/print/orders/o-1/document')
    text = pdf_text(response)
    assert 'CUSTOM INSERT ONLY' not in text
    assert 'Wiertarka' in text
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/print/orders/missing/document').status_code == 404


def test_mode_switch_preserves_upload_and_other_templates(app_env, client):
    app_env.write_state(app_env.default_state({'o-1': sample_order()}))
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    output = io.BytesIO()
    writer.write(output)
    uploaded = output.getvalue()
    assert client.post(
        '/api/print/custom-doc', files={'file': ('insert.pdf', uploaded, 'application/pdf')}
    ).status_code == 200
    settings = app_env.store.get_document_settings()
    settings['templates'].append({'id': 'future', 'name': 'Future', 'blocks': []})
    app_env.store.save_document_settings(settings)
    draft = template({'type': 'text', 'text': 'Personalized {{buyer_name}}'})
    assert client.post(
        '/api/print/document-settings', json={'source': 'template', 'template': draft}
    ).status_code == 200
    assert client.get('/api/print/custom-doc/info').json()['upload_available'] is True
    assert client.post('/api/print/document-settings', json={'source': 'upload', 'template': draft}).status_code == 200
    assert client.get('/api/print/custom-doc').content == uploaded
    assert len(app_env.store.get_document_settings()['templates']) == 2
    assert app_env.store.get_document_settings()['templates'][0]['blocks'][0]['text'].startswith('Personalized')


def test_document_api_validation_and_auth(client):
    empty = template()
    assert client.post(
        '/api/print/document-settings', json={'source': 'template', 'template': empty}
    ).status_code == 422
    assert client.post(
        '/api/print/document-preview',
        json={'order_id': 'missing', 'template': template({'type':'text', 'text':'Hi'})},
    ).status_code == 404
    wrong = template({'type':'text', 'text':'Hi'})
    wrong['id'] = 'new'
    assert client.post('/api/print/document-settings', json={'source':'template', 'template':wrong}).status_code == 422
    for url in ['/api/print/document-settings', '/api/print/custom-doc/info']:
        assert client.get(url, headers={'Authorization':'Bearer wrong'}).status_code == 401


def test_broken_pdf_upload_preserves_previous_file(client):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    output = io.BytesIO()
    writer.write(output)
    valid = output.getvalue()
    assert client.post('/api/print/custom-doc', files={'file':('valid.pdf',valid,'application/pdf')}).status_code == 200
    bad = client.post('/api/print/custom-doc', files={'file':('broken.pdf',b'%PDF-1.4 broken','application/pdf')})
    assert bad.status_code == 400
    assert client.get('/api/print/custom-doc').content == valid


@pytest.mark.parametrize('format,mime', [('PNG','png'),('JPEG','jpeg')])
def test_valid_logo_formats(app_env, format, mime):
    import base64

    from documents import DocumentTemplate, render_document_pdf
    from models.order import Order
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (80,40), 'green').save(image, format=format)
    draft = DocumentTemplate.model_validate(template({
        'type':'logo','image':f'data:image/{mime};base64,'+base64.b64encode(image.getvalue()).decode(),
    }))
    reader = PdfReader(io.BytesIO(render_document_pdf(draft, Order(**sample_order()))))
    assert '/XObject' in reader.pages[0]['/Resources']


def test_rejects_encrypted_upload(client):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.encrypt('test-only-password')
    output = io.BytesIO()
    writer.write(output)
    response = client.post('/api/print/custom-doc',files={'file':('encrypted.pdf',output.getvalue(),'application/pdf')})
    assert response.status_code == 400
    info = client.get('/api/print/custom-doc/info').json()
    assert info == {'available':False, 'source':'upload', 'upload_available':False, 'size':None}


def test_caps_aggregate_logo_payload(app_env):
    import base64
    import random

    from documents import DocumentTemplate
    from PIL import Image
    from pydantic import ValidationError
    image = io.BytesIO()
    pixels = random.Random(1).randbytes(600 * 600 * 3)
    Image.frombytes('RGB', (600, 600), pixels).save(image, format='PNG')
    uri = 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()
    with pytest.raises(ValidationError):
        DocumentTemplate.model_validate(template({'type':'logo','image':uri}, {'type':'logo','image':uri}))


def test_logo_and_multi_page_table_pdf(app_env):
    import base64

    from documents import DocumentTemplate, render_document_pdf
    from models.order import Order
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (120, 60), 'blue').save(image, format='PNG')
    uri = 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()
    draft = DocumentTemplate.model_validate(template({'type':'logo','image':uri}, {'type':'items','show_prices':True}))
    order = Order(**sample_order(items=[
        {'name':f'Śruba numer {i}', 'quantity':1, 'unit_price':2.5} for i in range(100)
    ]))
    reader = PdfReader(io.BytesIO(render_document_pdf(draft, order)))
    assert len(reader.pages) > 1
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert 'Śruba numer 0' in text and 'Śruba numer 99' in text and '250.00' in text
    assert any('/XObject' in page['/Resources'] for page in reader.pages)


def test_invalid_saved_settings_quarantined_without_losing_orders(app_env):
    state = app_env.default_state({'o-1':sample_order()})
    state['document_settings'] = {'version':42, 'secret-design':'keep me'}
    app_env.write_state(state)
    assert app_env.store.get_order('o-1').buyer_name == 'Jan Kowalski'
    assert app_env.store.get_document_settings()['version'] == 1
    app_env.store.save_invoice_settings({'free_text':'Unrelated save'})
    saved = json.loads(app_env.state_file.read_text())
    assert any(entry['record'] == state['document_settings'] for entry in saved['quarantine'])


@pytest.mark.parametrize('language,label', [('pl','Produkt'),('en','Product')])
def test_preview_language_and_missing_prices(app_env, client, language, label):
    app_env.write_state(app_env.default_state({
        'o-1':sample_order(items=[{'name':'No price', 'quantity':1, 'unit_price':None}]),
    }))
    draft = template({'type':'text','text':'{{tracking_number}}'}, {'type':'items','show_prices':True})
    response = client.post(
        '/api/print/document-preview', json={'order_id':'o-1','template':draft},
        headers={'Accept-Language':language},
    )
    text = pdf_text(response)
    assert label in text and '—' in text and 'No price' in text
    assert 'Total' not in text and 'Razem' not in text


def test_validation_errors_are_localized_and_do_not_echo_template_input(client):
    response = client.post(
        '/api/print/document-settings',
        json={'source':'template','template':template({'type':'text','text':'PRIVATE_TEXT {{unknown}}'})},
        headers={'Accept-Language':'en'},
    )
    assert response.status_code == 422
    assert response.json()['detail'] == 'Unknown or malformed dynamic field.'
    assert 'PRIVATE_TEXT' not in response.text
    invalid_size = client.post(
        '/api/print/document-preview',
        json={'order_id':'o-1','template':template({'type':'text','text':'Hi','size':100})},
        headers={'Accept-Language':'en'},
    )
    assert isinstance(invalid_size.json()['detail'], str)


@pytest.mark.parametrize('block', [
    {'type':'text','text':'x'*4001}, {'type':'text','size':7},
    {'type':'text','size':37}, {'type':'text','align':'justify'},
    {'type':'html','text':'<h1>Hi</h1>'}, {'type':'text','image':'file:///etc/passwd'},
])
def test_block_limits_rejected(client, block):
    response = client.post('/api/print/document-settings', json={'source':'template','template':template(block)})
    assert response.status_code == 422


def test_combined_with_missing_selected_upload_is_sales_only(app_env, client):
    app_env.write_state(app_env.default_state({'o-1':sample_order()}))
    response = client.get('/api/print/orders/o-1/combined')
    assert 'Jan Kowalski' in pdf_text(response)
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 1


def test_render_failure_returns_safe_localized_error(app_env, client, monkeypatch):
    import routes.documents as routes
    def fail(*args):
        raise RuntimeError('Internal sensitive path')
    monkeypatch.setattr(routes, 'render_document_pdf', fail)
    app_env.write_state(app_env.default_state({'o-1':sample_order()}))
    response = client.post(
        '/api/print/document-preview',
        json={'order_id':'o-1','template':template({'type':'text','text':'Hi'})},
        headers={'Accept-Language':'en'},
    )
    assert response.status_code == 500
    assert response.json()['detail'] == 'Could not generate the PDF document.'
    assert 'sensitive' not in response.text




