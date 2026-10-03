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
    assert state['orders']['o-1']['tracking_number'].startswith('DRY-PL-')


def test_dry_run_sync_returns_mock_orders_without_allegro_auth(app_env, client, monkeypatch):
    """When Allegro sandbox is down or unauthorized, dry run sync seeds mock orders."""
    monkeypatch.setenv('PACKING_SHIPMENT_DRY_RUN', '1')
    response = client.post('/api/orders/sync')
    assert response.status_code == 200
    data = response.json()
    assert data['added'] == 3
    assert data['total'] == 3

    # Calling seed-mock explicitly also works
    response2 = client.post('/api/orders/seed-mock')
    assert response2.status_code == 200
    assert response2.json()['added'] == 0


def test_seed_mock_is_refused_without_dry_run(app_env, client, monkeypatch):
    """Sample orders must never enter a real queue, whatever the credentials.

    They carry fabricated Allegro ids: the operator cannot ship them, and a
    later label attempt would send live requests for orders that do not exist.
    """
    monkeypatch.delenv('PACKING_SHIPMENT_DRY_RUN', raising=False)
    response = client.post('/api/orders/seed-mock')
    assert response.status_code == 409
    assert 'DRY_RUN' in response.json()['detail']
    assert client.get('/api/orders/').json() == []


def test_seed_mock_is_refused_even_with_a_valid_allegro_session(app_env, client, monkeypatch):
    """A working Allegro session must not unlock test data."""
    import api.allegro as allegro
    monkeypatch.delenv('PACKING_SHIPMENT_DRY_RUN', raising=False)
    allegro._token, allegro._refresh_token, allegro._expires_at = 'tok', 'ref', 0.0
    assert client.post('/api/orders/seed-mock').status_code == 409
    assert client.get('/api/orders/').json() == []


def test_sync_does_not_hide_upstream_failure_behind_mock_orders(app_env, client, monkeypatch):
    """A transient Allegro error in dry run must surface, not become "added: 3"."""
    import api.allegro as allegro
    monkeypatch.setenv('PACKING_SHIPMENT_DRY_RUN', '1')
    allegro._token, allegro._refresh_token, allegro._expires_at = 'tok', 'ref', 0.0

    async def failing(_limit=100):
        raise allegro.AllegroError('Allegro checkout-forms 503: serwer chwilowo niedostępny')

    monkeypatch.setattr(allegro, 'fetch_orders', failing)
    response = client.post('/api/orders/sync')
    assert response.status_code == 502
    assert '503' in response.json()['detail']
    assert client.get('/api/orders/').json() == []


def test_sync_reports_network_failure_in_dry_run(app_env, client, monkeypatch):
    """A dropped connection is not an authorization gap; it stays a 502."""
    import httpx

    import api.allegro as allegro
    monkeypatch.setenv('PACKING_SHIPMENT_DRY_RUN', '1')
    allegro._token, allegro._refresh_token, allegro._expires_at = 'tok', 'ref', 0.0

    async def failing(_limit=100):
        raise httpx.ConnectError('connection refused')

    monkeypatch.setattr(allegro, 'fetch_orders', failing)
    assert client.post('/api/orders/sync').status_code == 502
    assert client.get('/api/orders/').json() == []


def test_status_reports_dry_run_so_the_ui_can_hide_test_actions(app_env, client, monkeypatch):
    monkeypatch.delenv('PACKING_SHIPMENT_DRY_RUN', raising=False)
    assert client.get('/api/orders/status').json()['dry_run'] is False
    monkeypatch.setenv('PACKING_SHIPMENT_DRY_RUN', '1')
    assert client.get('/api/orders/status').json()['dry_run'] is True

# ---- Tracking number ----


@pytest.mark.parametrize('payload, expected', [
    # The carrier number is the one on the label and in carrier tracking.
    ({'packages': [{'waybill': 'ALLEGRO-1',
                    'transportingInfo': [{'carrierId': 'INPOST', 'carrierWaybill': 'WWWW123PL'}]}]},
     'WWWW123PL'),
    # Allegro documents an empty carrierWaybill on the first read after creation.
    ({'packages': [{'waybill': 'ALLEGRO-1',
                    'transportingInfo': [{'carrierId': 'INPOST', 'carrierWaybill': ''}]}]},
     'ALLEGRO-1'),
    ({'packages': [{'waybill': 'ALLEGRO-1'}]}, 'ALLEGRO-1'),
    ({'packages': [{'transportingInfo': [{'carrierWaybill': 'WWWW123PL'}]}]}, 'WWWW123PL'),
    # Multi-package shipments must not be limited to the first package.
    ({'packages': [{'waybill': 'A'},
                   {'waybill': 'B', 'transportingInfo': [{'carrierWaybill': 'SECOND99PL'}]}]},
     'SECOND99PL'),
    # Nothing usable yet.
    ({'packages': []}, None),
    ({'packages': [{'waybill': '   '}]}, None),
    ({'packages': 'nonsense'}, None),
    ({}, None),
])
def test_tracking_prefers_the_carrier_waybill(shipment_api, payload, expected):
    allegro, _, install = shipment_api
    install(lambda request: httpx.Response(200, json=payload))
    assert asyncio.run(allegro.get_shipment_tracking('shipment-1')) == expected


def test_new_shipment_id_is_saved_even_when_tracking_is_unavailable(app_env, client, monkeypatch):
    """A paid shipment must never be orphaned: losing the id risks buying a second one."""
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order('o-1', 'a-1')}))
    created = []

    async def create(_order, _sender, _package):
        created.append('created')
        return 'shipment-1'

    async def no_tracking(_shipment_id):
        return None

    async def label(_shipment_id, _page_size):
        return b'%PDF-1.4 label'

    monkeypatch.setattr(allegro, 'create_shipment', create)
    monkeypatch.setattr(allegro, 'get_shipment_tracking', no_tracking)
    monkeypatch.setattr(allegro, 'download_label', label)

    assert client.get('/api/print/orders/o-1/label').status_code == 200
    state = json.loads(app_env.state_file.read_text(encoding='utf-8'))
    assert state['orders']['o-1']['shipment_id'] == 'shipment-1'
    assert state['orders']['o-1']['tracking_number'] is None

    # A second print must reuse the stored id rather than buying another shipment.
    assert client.get('/api/print/orders/o-1/label').status_code == 200
    assert created == ['created']


def test_reprint_stores_a_waybill_that_was_missing_at_creation(app_env, client, monkeypatch):
    """An order shipped before the number existed recovers it on the next print."""
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(
        'o-1', 'a-1', shipment_id='shipment-existing', tracking_number=None)}))

    async def tracking(_shipment_id):
        return 'WWWW123PL'

    async def label(_shipment_id, _page_size):
        return b'%PDF-1.4 label'

    monkeypatch.setattr(allegro, 'get_shipment_tracking', tracking)
    monkeypatch.setattr(allegro, 'download_label', label)

    assert client.get('/api/print/orders/o-1/label').status_code == 200
    state = json.loads(app_env.state_file.read_text(encoding='utf-8'))
    assert state['orders']['o-1']['tracking_number'] == 'WWWW123PL'
    # The existing shipment id must survive untouched.
    assert state['orders']['o-1']['shipment_id'] == 'shipment-existing'
    assert client.get('/api/print/orders/o-1/shipment').json()['tracking_number'] == 'WWWW123PL'


def test_shipment_info_recovers_a_missing_tracking_number(app_env, client, monkeypatch):
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(
        'o-1', 'a-1', shipment_id='shipment-existing', tracking_number=None)}))

    async def tracking(_shipment_id):
        return 'LATE456PL'

    monkeypatch.setattr(allegro, 'get_shipment_tracking', tracking)
    assert client.get('/api/print/orders/o-1/shipment').json()['tracking_number'] == 'LATE456PL'
    state = json.loads(app_env.state_file.read_text(encoding='utf-8'))
    assert state['orders']['o-1']['tracking_number'] == 'LATE456PL'


def test_shipment_info_does_not_refetch_a_stored_tracking_number(app_env, client, monkeypatch):
    """Once stored, the number is served from state without touching Allegro."""
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(
        'o-1', 'a-1', shipment_id='shipment-existing', tracking_number='KNOWN7PL')}))

    async def forbidden(_shipment_id):
        raise AssertionError('stored tracking number must not trigger an Allegro call')

    monkeypatch.setattr(allegro, 'get_shipment_tracking', forbidden)
    assert client.get('/api/print/orders/o-1/shipment').json()['tracking_number'] == 'KNOWN7PL'


def test_shipment_info_survives_a_missing_tracking_number(app_env, client, monkeypatch):
    """A failed lookup must not break the packing view."""
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(
        'o-1', 'a-1', shipment_id='shipment-existing', tracking_number=None)}))

    async def failing(_shipment_id):
        return None

    monkeypatch.setattr(allegro, 'get_shipment_tracking', failing)
    assert client.get('/api/print/orders/o-1/shipment').json() == {
        'shipment_id': 'shipment-existing', 'tracking_number': None}
