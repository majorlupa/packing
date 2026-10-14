"""Upstream diagnostics belong in server logs, never in browser responses."""
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from conftest import sample_order


@pytest.mark.parametrize("language", ["pl", "en"])
@pytest.mark.parametrize("failure", ["api", "network", "authorization"])
@pytest.mark.parametrize("operation", ["sync", "create", "download", "oauth"])
def test_upstream_errors_are_logged_and_localized(
    app_env, client, monkeypatch, caplog, language, failure, operation,
):
    import api.allegro as allegro
    from localization import t

    raw = "RAW upstream diagnostic: gateway refused request /private/path"
    error, code, status = {
        "api": (allegro.AllegroError(raw), "allegro.request_failed", 502),
        "network": (httpx.ConnectError(raw), "common.allegro_unreachable", 502),
        "authorization": (allegro.AllegroNotAuthorized(raw), "allegro.not_authorized", 401),
    }[failure]

    async def fail(*args, **kwargs):
        raise error

    symbol = {
        "sync": "fetch_orders", "create": "create_shipment",
        "download": "download_label", "oauth": "exchange_code",
    }[operation]
    monkeypatch.setattr(allegro, symbol, fail)
    monkeypatch.delenv("PACKING_SHIPMENT_DRY_RUN", raising=False)
    app_env.write_state(app_env.default_state({
        "o-1": sample_order(shipment_id="existing" if operation == "download" else None),
    }))
    headers = {"Accept-Language": language}
    caplog.set_level(logging.WARNING, logger="packing.allegro")
    if operation == "oauth":
        url = client.get("/api/orders/auth/url", headers=headers).json()["url"]
        state = parse_qs(urlsplit(url).query)["state"][0]
        # Flow language must win over the callback browser's language.
        response = client.get("/api/orders/auth/callback", params={"state": state, "code": "c"},
                              headers={"Accept-Language": "en" if language == "pl" else "pl"})
    elif operation == "sync":
        response = client.post("/api/orders/sync", headers=headers)
    elif operation == "create":
        response = client.post("/api/print/orders/o-1/label", headers=headers)
    else:
        response = client.get("/api/print/orders/o-1/label", headers=headers)

    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": t(code, lang=language)}}
    assert raw not in response.text
    assert raw in caplog.text
    assert "Allegro request failed" in caplog.text
