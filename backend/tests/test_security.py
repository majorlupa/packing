"""Security boundaries: API access, removed secret routes, and OAuth callbacks."""
import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest


def request_without_fixture_auth(app_env, path, headers=None, method="GET"):
    async def send():
        transport = httpx.ASGITransport(app=app_env.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, headers=headers)

    return asyncio.run(send())


@pytest.mark.parametrize("authorization", [None, "Bearer incorrect", "Basic incorrect"])
def test_api_rejects_missing_or_invalid_access_token(app_env, authorization):
    headers = {"Authorization": authorization} if authorization else None
    response = request_without_fixture_auth(app_env, "/api/orders/", headers)
    assert response.status_code == 401
    assert response.headers["X-Packing-Auth-Required"] == "1"


@pytest.mark.parametrize("token", ["", "too-short"])
def test_api_fails_closed_when_access_token_is_not_configured(app_env, monkeypatch, token):
    monkeypatch.setenv("PACKING_ACCESS_TOKEN", token)
    assert request_without_fixture_auth(app_env, "/api/orders/").status_code == 503


@pytest.mark.parametrize("path", [
    "/api/config/",
    "/api/orders/auth/token",
    "/api/orders/debug/allegro-orders",
])
def test_removed_secret_endpoints_stay_absent(client, path):
    assert client.get(path).status_code == 404


def test_cors_preflight_and_auth_challenge_are_visible(app_env):
    origin = "http://localhost:3001"
    preflight = request_without_fixture_auth(app_env, "/api/orders/", {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    }, method="OPTIONS")
    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Origin"] == origin

    challenge = request_without_fixture_auth(app_env, "/api/orders/", {"Origin": origin})
    assert challenge.status_code == 401
    assert challenge.headers["Access-Control-Allow-Origin"] == origin
    assert "X-Packing-Auth-Required" in challenge.headers["Access-Control-Expose-Headers"]


def test_oauth_callback_requires_valid_unexpired_single_use_state(app_env, client, monkeypatch):
    import api.allegro as allegro
    import routes.orders as orders

    exchanged = []

    async def exchange(code):
        exchanged.append(code)

    monkeypatch.setattr(allegro, "exchange_code", exchange)
    callback = "/api/orders/auth/callback"
    assert request_without_fixture_auth(app_env, callback + "?code=code").status_code == 400

    url = client.get("/api/orders/auth/url").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert request_without_fixture_auth(app_env, callback + "?code=code&state=wrong").status_code == 400
    assert exchanged == []
    response = request_without_fixture_auth(app_env, callback + f"?code=code&state={state}")
    assert response.status_code == 307
    assert exchanged == ["code"]
    assert request_without_fixture_auth(app_env, callback + f"?code=code&state={state}").status_code == 400

    url = client.get("/api/orders/auth/url").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    monkeypatch.setattr(orders, "_oauth_state_deadline", 0.0)
    assert request_without_fixture_auth(app_env, callback + f"?code=code&state={state}").status_code == 400
    assert exchanged == ["code"]


def test_restart_invalidates_pending_oauth_callback(app_env, client, monkeypatch):
    import api.allegro as allegro
    import routes.orders as orders

    exchanged = []

    async def exchange(code):
        exchanged.append(code)

    monkeypatch.setattr(allegro, "exchange_code", exchange)
    url = client.get("/api/orders/auth/url").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    monkeypatch.setattr(orders, "_oauth_state", None)
    monkeypatch.setattr(orders, "_oauth_state_deadline", 0.0)
    callback = "/api/orders/auth/callback?code=code"
    for suffix in ("", f"&state={state}", "&state=wrong"):
        assert request_without_fixture_auth(app_env, callback + suffix).status_code == 400
    assert exchanged == []
