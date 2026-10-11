"""Beta locker selection persists locally without invoking a carrier API."""
import importlib

import pytest

from conftest import sample_order


@pytest.mark.parametrize('courier,kind', [
    ('Paczkomat InPost', 'inpost_locker'),
    ('Allegro Paczkomaty InPost', 'inpost_locker'),
    ('ALLEGRO PACZKOMATY INPOST', 'inpost_locker'),
    ('Allegro Kurier InPost', 'courier'),
    ('Allegro One Box', 'courier'),
    (None, 'courier'),
])
def test_locker_classification(app_env, client, courier, kind):
    app_env.write_state(app_env.default_state({'o-1': sample_order(courier=courier)}))
    assert client.get('/api/orders/').json()[0]['delivery_type'] == kind


def test_size_persists_across_reload_and_queue_changes(app_env, client):
    app_env.write_state(app_env.default_state({'o-1': sample_order(courier='Allegro Paczkomaty InPost')}))
    for size in ['A', 'B', 'C']:
        result = client.patch('/api/orders/o-1/parcel-size', json={'parcel_size': size})
        assert result.status_code == 200
        assert result.json() == {'parcel_size': size}
    importlib.reload(app_env.store)
    assert client.get('/api/orders/').json()[0]['parcel_size'] == 'C'
    listing = client.post('/api/picking-lists', json={'order_ids': ['o-1']}).json()
    client.post(f"/api/picking-lists/{listing['id']}/start-packing")
    assert client.get('/api/orders/').json()[0]['parcel_size'] == 'C'
    assert client.patch('/api/orders/o-1/parcel-size', json={'parcel_size': 'D'}).status_code == 422
    assert client.get('/api/orders/').json()[0]['parcel_size'] == 'C'


@pytest.mark.parametrize('overrides,status', [
    ({'courier': 'Allegro Kurier InPost'}, 400),
    ({'shipment_id': 'existing-shipment'}, 409),
    ({'tracking_number': 'existing-tracking'}, 409),
])
def test_size_rejects_couriers_and_existing_shipments(app_env, client, overrides, status):
    data = sample_order(courier='Paczkomat InPost', parcel_size='A')
    data.update(overrides)
    app_env.write_state(app_env.default_state({'o-1': data}))
    assert client.patch('/api/orders/o-1/parcel-size', json={'parcel_size': 'B'}).status_code == status
    assert client.get('/api/orders/').json()[0]['parcel_size'] == 'A'
    assert client.patch('/api/orders/missing/parcel-size', json={'parcel_size': 'B'}).status_code == 404


def test_new_locker_labels_require_parcel_size(app_env, client, monkeypatch):
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(courier='Paczkomat InPost')}))
    async def unexpected(*args):
        pytest.fail('Locker order without size must not call carrier API')
    monkeypatch.setattr(allegro, 'create_shipment', unexpected)
    monkeypatch.setattr(allegro, 'download_label', unexpected)
    response = client.get('/api/print/orders/o-1/label')
    assert response.status_code == 400
    assert 'gabaryt' in response.json()['detail'].lower()
    assert app_env.store.get_order('o-1').shipment_id is None


def test_new_locker_labels_create_shipment_with_locker_dimensions(app_env, client, monkeypatch):
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(
        courier='Paczkomat InPost', parcel_size='A')}))
    called_package = {}

    async def mock_create(order, sender, package):
        called_package.update(package)
        return 'inpost-shipment-123'

    async def mock_tracking(shipment_id):
        return 'INP-TRACK-999'

    async def mock_download(shipment_id, page_size):
        return b'%PDF-locker-label'

    monkeypatch.setattr(allegro, 'create_shipment', mock_create)
    monkeypatch.setattr(allegro, 'get_shipment_tracking', mock_tracking)
    monkeypatch.setattr(allegro, 'download_label', mock_download)

    response = client.get('/api/print/orders/o-1/label')
    assert response.status_code == 200
    assert response.content == b'%PDF-locker-label'
    assert called_package['length'] == 64.0
    assert called_package['width'] == 38.0
    assert called_package['height'] == 8.0
    order = app_env.store.get_order('o-1')
    assert order.shipment_id == 'inpost-shipment-123'
    assert order.tracking_number == 'INP-TRACK-999'


def test_existing_locker_label_remains_downloadable(app_env, client, monkeypatch):
    import api.allegro as allegro
    app_env.write_state(app_env.default_state({'o-1': sample_order(
        courier='Paczkomat InPost', shipment_id='existing-shipment')}))
    async def download(shipment_id, page_size):
        assert shipment_id == 'existing-shipment'
        return b'%PDF-saved'
    async def unexpected(*args):
        pytest.fail('Existing shipment must not be recreated')
    monkeypatch.setattr(allegro, 'create_shipment', unexpected)
    monkeypatch.setattr(allegro, 'download_label', download)
    response = client.get('/api/print/orders/o-1/label')
    assert response.status_code == 200
    assert response.content == b'%PDF-saved'
