"""Dedicated webhook authentication and order sync."""
import pytest
from conftest import sample_order


@pytest.mark.parametrize("secret,authorization,status", [
    ("", "Bearer webhook-test-secret", 503),
    ("webhook-test-secret", "", 401),
    ("webhook-test-secret", "Basic webhook-test-secret", 401),
    ("webhook-test-secret", "Bearer wrong", 401),
    ("webhook-test-secret", "Bearer test-access-token-for-packing-api-2026", 401),
    ("webhook-test-secret", "Bearer 🔒", 401),
    ("webhook-test-secret", "Bearer webhook-test-secret", 200),
])
def test_webhook_auth(client, app_env, monkeypatch, secret, authorization, status):
    from routes import orders

    calls = []

    async def sync():
        calls.append(True)
        return {"added": 2, "updated": 0, "total": 2}

    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("PACKING_ACCESS_TOKEN", "")
    monkeypatch.setattr(orders, "sync_from_allegro", sync)
    # httpx accepts non-ASCII header values as UTF-8 bytes.
    result = client.post("/api/webhooks/sync", headers={"Authorization": authorization.encode("utf-8")})
    assert result.status_code == status
    assert len(calls) == (1 if status == 200 else 0)
    if status == 200:
        assert result.json() == {"added": 2, "updated": 0, "total": 2}
    assert client.get("/api/orders/", headers={"Authorization": "Bearer webhook-test-secret"}).status_code == 503


def test_webhook_syncs_and_deduplicates_orders(client, app_env, monkeypatch):
    import api.allegro as allegro
    from models.order import Order

    async def fetch():
        return [Order(**sample_order())]

    monkeypatch.setattr(allegro, "fetch_orders", fetch)
    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", "webhook-test-secret")
    headers = {"Authorization": "Bearer webhook-test-secret"}
    assert client.post("/api/webhooks/sync", headers=headers).json() == {"added": 1, "updated": 0, "total": 1}
    assert client.post("/api/webhooks/sync", headers=headers).json() == {"added": 0, "updated": 0, "total": 1}


def test_webhook_propagates_sync_failure(client, app_env, monkeypatch):
    from fastapi import HTTPException
    from routes import orders

    async def sync():
        raise HTTPException(status_code=502, detail="Upstream unavailable")

    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", "webhook-test-secret")
    monkeypatch.setattr(orders, "sync_from_allegro", sync)
    result = client.post("/api/webhooks/sync", headers={"Authorization": "Bearer webhook-test-secret"})
    assert result.status_code == 502
