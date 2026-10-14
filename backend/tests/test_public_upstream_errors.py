"""Upstream diagnostic text belongs in logs, never in public HTTP errors."""
import pytest
import httpx

from conftest import sample_order


@pytest.mark.parametrize("language", ["pl", "en"])
@pytest.mark.parametrize("operation", ["sync", "create", "download", "callback"])
@pytest.mark.parametrize("failure", ["allegro", "network", "authorization"])
def test_upstream_errors_are_logged_and_localized(
    app_env, client, monkeypatch, caplog, language, operation, failure,
):
    import api.allegro as allegro
    import localization

    raw = "RAW-UPSTREAM-DIAGNOSTIC-503"
    error_type, status, code = {
        "allegro": (allegro.AllegroError, 502, "allegro.request_failed"),
        "network": (httpx.ConnectError, 502, "common.allegro_unreachable"),
        "authorization": (allegro.AllegroNotAuthorized, 401, "allegro.not_authorized"),
    }[failure]

    async def failing(*args, **kwargs):
        raise error_type(raw)

    app_env.write_state(app_env.default_state({
        "o-1": sample_order(shipment_id="shipment-1" if operation == "download" else None),
    }))
    headers = {"Accept-Language": language}
    if operation == "sync":
        monkeypatch.setattr(allegro, "fetch_orders", failing)
        response = client.post("/api/orders/sync", headers=headers)
    elif operation == "create":
        monkeypatch.setattr(allegro, "create_shipment", failing)
        response = client.post("/api/print/orders/o-1/label", headers=headers)
    elif operation == "download":
        monkeypatch.setattr(allegro, "download_label", failing)
        response = client.get("/api/print/orders/o-1/label", headers=headers)
    else:
        from urllib.parse import parse_qs, urlparse

        monkeypatch.setattr(allegro, "exchange_code", failing)
        url = client.get("/api/orders/auth/url", headers=headers).json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        # The callback's browser language differs from the initiating request.
        response = client.get(
            "/api/orders/auth/callback", params={"state": state, "code": "test-code"},
            headers={"Accept-Language": "pl" if language == "en" else "en"},
        )
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": localization.t(code, lang=language)}}
    assert raw not in response.text
    assert any(
        record.name == "packing.allegro" and "Allegro request failed" in record.getMessage()
        and raw in record.getMessage()
        for record in caplog.records
    )
