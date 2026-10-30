"""Server-side product filtering and isolated inbound webhook authentication."""
import pytest
from conftest import sample_order


@pytest.mark.parametrize("product", ["lego", " LeGo ", "SKU-42", "offer-99"])
def test_product_filter(client, app_env, product):
    first = sample_order(items=[{
        "name": "LEGO Castle", "quantity": 1, "sku": "sku-42", "offer_id": "OFFER-99",
    }])
    second = sample_order("o-2", "a-2")
    app_env.write_state(app_env.default_state({"o-1": first, "o-2": second}))
    result = client.get("/api/orders/", params={"product": product})
    assert result.status_code == 200
    assert [order["id"] for order in result.json()] == ["o-1"]
    assert len(client.get("/api/orders/").json()) == 2
    assert len(client.get("/api/orders/", params={"product": "  "}).json()) == 2
    assert client.get("/api/orders/", params={"product": "missing"}).json() == []


def test_import_preserves_product_identifiers(app_env):
    from api.allegro import _order_from_form

    order = _order_from_form({"id": "a1", "lineItems": [{
        "offer": {"name": "LEGO", "id": "offer1", "external": {"id": "sku1"}}, "quantity": 1,
    }]})
    assert order.items[0].sku == "sku1"
    assert order.items[0].offer_id == "offer1"


def test_sync_backfills_item_metadata(client, app_env, monkeypatch):
    import api.allegro as allegro
    from models.order import Order

    old = sample_order()
    app_env.write_state(app_env.default_state({"o-1": old}))
    new = Order(**{**old, "items": [{**old["items"][0], "sku": "sku1", "offer_id": "offer1"}]})

    async def fetch():
        return [new]

    monkeypatch.setattr(allegro, "fetch_orders", fetch)
    assert client.post("/api/orders/sync").json()["updated"] == 1
    assert client.get("/api/orders/", params={"product": "sku1"}).json()[0]["id"] == "o-1"
    assert client.post("/api/orders/sync").json()["updated"] == 0


