"""Exercise the real shipment client against Allegro's HTTP contract."""
import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from conftest import sample_order


@pytest.fixture
def shipment_api(app_env, monkeypatch):
    import api.allegro as allegro
    from models.order import Order

    allegro._token = 'test-token'
    original_client = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(allegro.httpx, 'AsyncClient', lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs))

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(allegro.asyncio, 'sleep', no_wait)
    return allegro, Order(**sample_order()), install


def proposal():
    return {'suggestedInput': {
        'sender': {'name': 'Seller', 'street': 'Sender 1', 'postalCode': '00-001',
                   'city': 'Warszawa', 'countryCode': 'PL', 'email': 'seller@example.com',
                   'phone': '500100200'},
        'receiver': {'name': 'Recipient', 'email': 'order+123@allegromail.pl',
                     'phone': '500200300', 'point': 'WAW01M'},
        'packages': [{'type': 'PACKAGE', 'weight': {'value': 99, 'unit': 'KILOGRAMS'}}],
        'labelFormat': 'ZPL',
        'credentialsId': 'carrier-contract',
        'insurance': {'amount': '49.99', 'currency': 'PLN'},
        'cashOnDelivery': {'amount': '55.00', 'currency': 'PLN', 'iban': 'test-iban'},
        'additionalServices': ['sendingAtPoint'],
        'additionalProperties': {'sendingCode': 'test'},
    }}


@pytest.mark.parametrize('legacy_sender', [{}, {'street': 'Obsolete local address'}])
def test_creation_uses_allegro_proposal_without_local_sender(shipment_api, legacy_sender):
    allegro, order, install = shipment_api
    order.delivery_method_id = None
    suggested = proposal()
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers['Authorization'] == 'Bearer test-token'
        if request.url.path.endswith('/delivery-proposals/a-1'):
            return httpx.Response(200, json=deepcopy(suggested))
        if request.method == 'POST':
            body = json.loads(request.content)['input']
            for field in ('sender', 'receiver', 'credentialsId', 'insurance',
                          'cashOnDelivery', 'additionalServices', 'additionalProperties'):
                assert body[field] == suggested['suggestedInput'][field]
            assert body['labelFormat'] == 'PDF'
            assert 'pageSize' not in body
            assert 'deliveryMethodId' not in body
            assert body['packages'][0]['length']['value'] == 40
            assert float(body['packages'][0]['weight']['value']) == 2.5
            return httpx.Response(201, json={'commandId': 'command-1'})
        return httpx.Response(200, json={'status': 'SUCCESS', 'shipmentId': 'shipment-1'})

    install(handler)
    assert asyncio.run(allegro.create_shipment(order, legacy_sender,
        {'length': 40, 'weight': 2.5, 'label_format': 'ZPL'})) == 'shipment-1'
    assert requests[0].url.path.endswith('/delivery-proposals/a-1')


@pytest.mark.parametrize('status', [401, 403, 404, 422, 500])
def test_proposal_error_never_creates_shipment(shipment_api, status):
    allegro, order, install = shipment_api
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={'errors': [{'code': 'NO_ADDRESS',
            'message': 'Missing sender', 'userMessage': 'Dodaj adres w Wysyłam z Allegro.'}]})

    install(handler)
    error = allegro.AllegroNotAuthorized if status == 401 else allegro.AllegroError
    with pytest.raises(error):
        asyncio.run(allegro.create_shipment(order, {}, {}))
    assert len(requests) == 1
    assert requests[0].method == 'GET'


@pytest.mark.parametrize('payload', [{}, {'suggestedInput': None},
    {'suggestedInput': {}}, {'suggestedInput': {'sender': {}, 'receiver': {}}}])
def test_incomplete_proposal_never_creates_shipment(shipment_api, payload):
    allegro, order, install = shipment_api
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    install(handler)
    with pytest.raises(allegro.AllegroError):
        asyncio.run(allegro.create_shipment(order, {}, {}))
    assert len(requests) == 1


def test_label_download_returns_pdf(shipment_api):
    allegro, _, install = shipment_api

    def handler(request):
        assert json.loads(request.content) == {'shipmentIds': ['shipment-1'], 'pageSize': 'A4'}
        return httpx.Response(200, content=b'%PDF-1.4\nlabel')

    install(handler)
    assert asyncio.run(allegro.download_label('shipment-1', 'A4')).startswith(b'%PDF-')


@pytest.mark.parametrize('content', [b'^XA^XZ', b'', b'{"error":"not a label"}'])
def test_label_download_rejects_non_pdf(shipment_api, content):
    allegro, _, install = shipment_api
    install(lambda request: httpx.Response(200, content=content))
    with pytest.raises(allegro.AllegroError, match='PDF'):
        asyncio.run(allegro.download_label('shipment-1'))


@pytest.mark.parametrize('create_body, status_body', [
    (None, None),                                        # 201 carrying an HTML proxy page
    ({'commandId': 'command-1'}, None),                  # poll answered with HTML
    ({'commandId': 'command-1'}, {'status': 'SUCCESS'}),  # SUCCESS without shipmentId
    ({'commandId': 'command-1'}, {'status': 'ERROR', 'errors': [{'code': None}]}),
    ({'commandId': 'command-1'}, {'status': 'ERROR', 'errors': [None]}),
    ({'commandId': 'command-1'}, {'status': 'ERROR', 'errors': None}),
])
def test_malformed_allegro_responses_raise_allegro_error(shipment_api, create_body, status_body):
    """An HTML error page or a changed payload shape must be a 502, never an unhandled 500."""
    allegro, order, install = shipment_api

    def handler(request):
        if request.url.path.endswith('/delivery-proposals/a-1'):
            return httpx.Response(200, json=proposal())
        if request.method == 'POST':
            if create_body is None:
                return httpx.Response(201, text='<html>bad gateway</html>')
            return httpx.Response(201, json=create_body)
        if status_body is None:
            return httpx.Response(200, text='<html>bad gateway</html>')
        return httpx.Response(200, json=status_body)

    install(handler)
    with pytest.raises(allegro.AllegroError):
        asyncio.run(allegro.create_shipment(order, {}, {}))


def test_label_route_runs_the_real_allegro_flow(app_env, client, monkeypatch):
    """Route + real client: proposal, create with operator dimensions, poll, label PDF."""
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({'o-1': sample_order('o-1', 'a-1')}))
    allegro._token = 'test-token'
    posted = {}

    def handler(request):
        if request.url.path.endswith('/delivery-proposals/a-1'):
            return httpx.Response(200, json=proposal())
        if request.method == 'POST' and request.url.path.endswith('/create-commands'):
            posted.update(json.loads(request.content)['input'])
            return httpx.Response(201, json={'commandId': 'command-1'})
        if request.url.path.endswith('/create-commands/command-1'):
            return httpx.Response(200, json={'status': 'SUCCESS', 'shipmentId': 'shipment-1'})
        if request.url.path.endswith('/shipment-management/label'):
            posted['label'] = json.loads(request.content)
            return httpx.Response(200, content=b'%PDF-1.7 label')
        raise AssertionError(f'unexpected {request.method} {request.url}')

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(allegro.asyncio, 'sleep', no_wait)
    original_client = httpx.AsyncClient

    def client_factory(**kwargs):
        # The test HTTP client passes its own ASGI transport; Allegro calls get the mock.
        kwargs.setdefault('transport', httpx.MockTransport(handler))
        return original_client(**kwargs)

    monkeypatch.setattr(allegro.httpx, 'AsyncClient', client_factory)

    response = client.get('/api/print/orders/o-1/label?length=40&width=30&height=20&weight=2.5')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF-')
    assert posted['labelFormat'] == 'PDF'
    assert posted['packages'][0]['length']['value'] == 40
    assert posted['label']['pageSize'] == 'A6'
    state = json.loads(app_env.state_file.read_text(encoding='utf-8'))
    assert state['orders']['o-1']['shipment_id'] == 'shipment-1'


def test_dry_run_label_flow_never_touches_allegro(app_env, monkeypatch):
    import api.allegro as allegro
    from models.order import Order

    def explode(**kwargs):
        raise AssertionError('dry run must not open an HTTP client')

    monkeypatch.setattr(allegro.httpx, 'AsyncClient', explode)
    monkeypatch.setenv('PACKING_SHIPMENT_DRY_RUN', '1')

    shipment_id = asyncio.run(allegro.create_shipment(Order(**sample_order()), {}, {}))
    assert shipment_id.startswith('dry-run-')
    assert asyncio.run(allegro.download_label(shipment_id, 'A4')).startswith(b'%PDF-')


def test_dry_run_label_route_works_without_allegro_authorization(app_env, client, monkeypatch):
    """No Allegro token at all: the beta instance can test the label flow end to end."""
    monkeypatch.setenv('PACKING_SHIPMENT_DRY_RUN', '1')
    app_env.write_state(app_env.default_state({'o-1': sample_order('o-1', 'a-1')}))

    response = client.get('/api/print/orders/o-1/label')
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF-')
    state = json.loads(app_env.state_file.read_text(encoding='utf-8'))
    assert state['orders']['o-1']['shipment_id'].startswith('dry-run-')

    # Printing again reuses the dry-run shipment instead of creating another one.
    assert client.get('/api/print/orders/o-1/label').status_code == 200
    state = json.loads(app_env.state_file.read_text(encoding='utf-8'))
    assert state['orders']['o-1']['shipment_id'].startswith('dry-run-')
