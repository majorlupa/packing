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
