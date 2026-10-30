"""Dedicated webhook authentication and order sync."""
import pytest
from conftest import sample_order

# Must satisfy the same minimum length as PACKING_ACCESS_TOKEN.
WEBHOOK_SECRET = "webhook-test-secret-0123456789abcdef"


@pytest.mark.parametrize("secret,authorization,status", [
    ("", f"Bearer {WEBHOOK_SECRET}", 503),
    ("short", "Bearer short", 503),
    ("        ", "Bearer         ", 503),
    (WEBHOOK_SECRET, "", 401),
    (WEBHOOK_SECRET, "Basic webhook-test-secret", 401),
    (WEBHOOK_SECRET, "Bearer wrong", 401),
    (WEBHOOK_SECRET, "Bearer test-access-token-for-packing-api-2026", 401),
    (WEBHOOK_SECRET, "Bearer 🔒", 401),
    (WEBHOOK_SECRET, f"Bearer {WEBHOOK_SECRET}", 200),
])
def test_webhook_auth(client, app_env, monkeypatch, secret, authorization, status):
    from routes import orders

    calls = []

    async def sync():
        calls.append(True)
        return {"added": 2, "updated": 0, "total": 2}

    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(orders, "sync_from_allegro", sync)
    # httpx accepts non-ASCII header values as UTF-8 bytes.
    result = client.post("/api/webhooks/sync", headers={"Authorization": authorization.encode("utf-8")})
    assert result.status_code == status
    assert len(calls) == (1 if status == 200 else 0)
    if status == 200:
        assert result.json() == {"added": 2, "updated": 0, "total": 2}


def test_webhook_secret_is_not_an_api_token(client, app_env, monkeypatch):
    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", WEBHOOK_SECRET)
    # The webhook secret must not open the rest of the API ...
    assert client.get(
        "/api/orders/", headers={"Authorization": f"Bearer {WEBHOOK_SECRET}"}
    ).status_code == 401
    assert client.get("/api/orders/").status_code == 200
    # ... and the UI/API token must not open the webhook.
    assert client.post(
        "/api/webhooks/sync",
        headers={"Authorization": "Bearer test-access-token-for-packing-api-2026"},
    ).status_code == 401


def test_webhook_works_without_an_api_token(client, app_env, monkeypatch):
    from routes import orders

    async def sync():
        return {"added": 0, "updated": 0, "total": 0}

    monkeypatch.setenv("PACKING_ACCESS_TOKEN", "")
    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(orders, "sync_from_allegro", sync)
    headers = {"Authorization": f"Bearer {WEBHOOK_SECRET}"}
    assert client.post("/api/webhooks/sync", headers=headers).status_code == 200
    # Without an access token the rest of the API stays closed.
    assert client.get("/api/orders/").status_code == 503


def test_webhook_syncs_and_deduplicates_orders(client, app_env, monkeypatch):
    import api.allegro as allegro
    from models.order import Order

    async def fetch():
        return [Order(**sample_order())]

    monkeypatch.setattr(allegro, "fetch_orders", fetch)
    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", WEBHOOK_SECRET)
    headers = {"Authorization": f"Bearer {WEBHOOK_SECRET}"}
    assert client.post("/api/webhooks/sync", headers=headers).json() == {"added": 1, "updated": 0, "total": 1}
    assert client.post("/api/webhooks/sync", headers=headers).json() == {"added": 0, "updated": 0, "total": 1}


def test_webhook_propagates_sync_failure(client, app_env, monkeypatch):
    from fastapi import HTTPException
    from routes import orders

    async def sync():
        raise HTTPException(status_code=502, detail="Upstream unavailable")

    monkeypatch.setenv("PACKING_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(orders, "sync_from_allegro", sync)
    result = client.post("/api/webhooks/sync", headers={"Authorization": f"Bearer {WEBHOOK_SECRET}"})
    assert result.status_code == 502
