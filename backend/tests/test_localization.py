"""Polish/English localization: negotiation, request scope and translated messages.

The frontend sends ``Accept-Language: pl`` or ``en`` on every application API
call (including PDFs, setup and the OAuth initiation). Anything absent,
unsupported or malformed must fall back to Polish, and the chosen language must
stay request-scoped so two concurrent requests never see each other's language.
"""
import threading

import pytest

from conftest import sample_order


# ---------------------------------------------------------------- negotiation


@pytest.mark.parametrize("header, expected", [
    (None, "pl"),
    ("", "pl"),
    ("   ", "pl"),
    ("pl", "pl"),
    ("PL", "pl"),
    ("pl-PL", "pl"),
    ("en", "en"),
    ("EN", "en"),
    ("en-US", "en"),
    ("en-US,en;q=0.9", "en"),
    ("en-US,en;q=0.9,pl;q=0.8", "en"),
    ("pl-PL,pl;q=0.9,en;q=0.8", "pl"),
    ("en;q=0.1,pl;q=0.9", "pl"),
    ("de-DE,de;q=0.9", "pl"),
    ("de,en;q=0.8", "en"),
    ("en;q=0,pl", "pl"),
    ("fr,*;q=0.5", "pl"),
    ("*", "pl"),
    ("pl;q=0.5,en;q=0.5", "pl"),
    ("en ; q=0.7", "en"),
    ("ru-RU,ru;q=0.9,uk;q=0.8", "pl"),
    ("en;q=invalid", "pl"),
    ("en;q=NaN", "pl"),
    ("en;q=inf", "pl"),
    ("en;q=1.1", "pl"),
    ("en;q=-0.1", "pl"),
    ("en;q=abc,pl;q=0.2", "pl"),
    ("en;q=0.9;foo=bar", "en"),
])
def test_negotiate_language(header, expected):
    import localization

    assert localization.negotiate_language(header) == expected


def test_negotiate_handles_an_absurdly_long_header():
    import localization

    header = ",".join(f"de-DE;q=0.{i % 10}" for i in range(500)) + ",en;q=0.9"
    assert localization.negotiate_language(header) == "en"


def test_negotiate_language_accepts_a_different_default():
    import localization

    assert localization.negotiate_language(None, default="en") == "en"
    assert localization.negotiate_language("de", default="en") == "en"


# ---------------------------------------------------------------- lookups


def test_translation_defaults_to_polish_and_supports_english():
    import localization

    assert localization.t("error.order_not_found") == "Nie znaleziono zamówienia."
    assert localization.t("error.order_not_found", lang="en") == "Order not found."


def test_translation_formats_parameters_and_keeps_upstream_text():
    import localization

    detail = localization.t("allegro.session_expired", lang="en")
    # The frontend's English button is "Connect Allegro" (nav.authorizeAllegro).
    assert "Connect Allegro" in detail
    assert "Authorize Allegro" not in detail
    assert localization.t("common.allegro_unreachable", error="boom").endswith("boom")
    assert localization.t("common.allegro_unreachable", lang="en", error="boom") == "Cannot reach Allegro: boom"


def test_unknown_key_is_visible_instead_of_silently_empty():
    import localization

    assert localization.t("nope.missing") == "nope.missing"


def test_english_falls_back_to_polish_for_a_missing_translation():
    import localization

    # A key that exists only in Polish must still answer in English mode.
    localization.MESSAGES["test.polish_only"] = {"pl": "tylko po polsku"}
    try:
        assert localization.t("test.polish_only", lang="en") == "tylko po polsku"
    finally:
        del localization.MESSAGES["test.polish_only"]


def test_request_scope_uses_the_current_language():
    import localization

    assert localization.t("error.order_not_found") == "Nie znaleziono zamówienia."
    with localization.language_scope("en"):
        assert localization.t("error.order_not_found") == "Order not found."
        with localization.language_scope("pl"):
            assert localization.t("error.order_not_found") == "Nie znaleziono zamówienia."
    assert localization.t("error.order_not_found") == "Nie znaleziono zamówienia."


def test_language_scope_is_isolated_between_threads():
    import localization

    results = {}
    barrier = threading.Barrier(2)

    def worker(language):
        barrier.wait()
        with localization.language_scope(language):
            results[language] = localization.t("error.order_not_found")

    threads = [threading.Thread(target=worker, args=(lang,)) for lang in ("pl", "en")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == {
        "pl": "Nie znaleziono zamówienia.",
        "en": "Order not found.",
    }


# ---------------------------------------------------------------- API surface

TOKEN = "test-access-token-for-packing-api-2026"


def _anonymous(app_env, method, path, base_url="http://test", **kwargs):
    """Send a request without the fixture's Authorization header."""
    import asyncio

    import httpx

    async def send():
        transport = httpx.ASGITransport(app=app_env.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as c:
            return await c.request(method, path, **kwargs)

    return asyncio.run(send())


def test_api_error_defaults_to_polish(client):
    response = client.post("/api/orders/nope/done")
    assert response.status_code == 404
    assert response.json()["detail"] == "Nie znaleziono zamówienia."


def test_api_error_uses_english_when_requested(client):
    response = client.post("/api/orders/nope/done", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found."


def test_api_error_falls_back_to_polish_for_an_unsupported_language(client):
    response = client.post("/api/orders/nope/done", headers={"Accept-Language": "de-DE,de;q=0.9"})
    assert response.json()["detail"] == "Nie znaleziono zamówienia."


def test_authentication_challenge_is_localized(app_env):
    polish = _anonymous(app_env, "GET", "/api/orders/")
    assert polish.status_code == 401
    assert polish.headers["X-Packing-Auth-Required"] == "1"
    assert polish.json()["detail"] == "Wymagane uwierzytelnienie."

    english = _anonymous(app_env, "GET", "/api/orders/", headers={"Accept-Language": "en"})
    assert english.status_code == 401
    assert english.json()["detail"] == "Authentication required."


def test_missing_access_token_message_is_localized(app_env, monkeypatch):
    monkeypatch.setenv("PACKING_ACCESS_TOKEN", "too-short")
    assert "co najmniej 32 znaki" in _anonymous(app_env, "GET", "/api/orders/").json()["detail"]
    english = _anonymous(app_env, "GET", "/api/orders/", headers={"Accept-Language": "en"})
    assert english.json()["detail"] == "PACKING_ACCESS_TOKEN must be configured with at least 32 characters."


def test_request_language_is_isolated_between_concurrent_requests(app_env):
    """Two callers with different headers must never share one language."""
    import asyncio

    import httpx

    async def go():
        transport = httpx.ASGITransport(app=app_env.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            polish = [
                c.post("/api/orders/nope/done", headers={"Authorization": f"Bearer {TOKEN}", "Accept-Language": "pl"})
                for _ in range(5)
            ]
            english = [
                c.post("/api/orders/nope/done", headers={"Authorization": f"Bearer {TOKEN}", "Accept-Language": "en"})
                for _ in range(5)
            ]
            return await asyncio.gather(*polish, *english)

    details = [r.json()["detail"] for r in asyncio.run(go())]
    assert details == ["Nie znaleziono zamówienia."] * 5 + ["Order not found."] * 5


def test_picking_list_default_name_is_localized(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    polish = client.post("/api/picking-lists", json={"order_ids": ["o-1"]}).json()
    assert polish["name"] == "Lista #1"

    english = client.post(
        "/api/picking-lists", json={"order_ids": ["o-1"]}, headers={"Accept-Language": "en"}
    ).json()
    assert english["name"] == "List #2"


def test_state_file_error_detail_is_localized(app_env, client):
    app_env.state_file.write_text("{not json", encoding="utf-8")
    app_env.backup_file.write_text("{also not json", encoding="utf-8")

    polish = client.get("/api/orders/")
    assert polish.status_code == 503
    assert "kopii zapasowej" in polish.json()["detail"]

    english = client.get("/api/orders/", headers={"Accept-Language": "en"})
    assert english.status_code == 503
    assert "backup" in english.json()["detail"]


# ---------------------------------------------------------------- setup


def _fresh_install(app_env, monkeypatch):
    """No credentials and no access token: the bootstrap POST is public."""
    import api.allegro as allegro

    monkeypatch.setattr(allegro, "CLIENT_ID", "")
    monkeypatch.setattr(allegro, "CLIENT_SECRET", "")
    monkeypatch.setenv("ALLEGRO_CLIENT_ID", "")
    monkeypatch.setenv("ALLEGRO_CLIENT_SECRET", "")
    monkeypatch.delenv("PACKING_ACCESS_TOKEN", raising=False)
    app_env.env_file.write_text(
        "ALLEGRO_CLIENT_ID=\nALLEGRO_CLIENT_SECRET=\n", encoding="utf-8"
    )


def _setup_headers(app_env, language=None):
    """Origin and setup token for the localhost first-run bootstrap."""
    token = _anonymous(
        app_env, "GET", "/api/setup/status", base_url="http://localhost:3001"
    ).json()["setup_token"]
    headers = {"Origin": "http://localhost:3001", "X-Packing-Setup-Token": token}
    if language:
        headers["Accept-Language"] = language
    return headers


def test_setup_already_configured_message_is_localized(app_env, client):
    body = {"client_id": "a", "client_secret": "b"}
    polish = client.post("/api/setup", json=body)
    assert polish.status_code == 409
    assert polish.json()["detail"] == "Allegro jest już skonfigurowane."

    english = client.post("/api/setup", json=body, headers={"Accept-Language": "en"})
    assert english.json()["detail"] == "Allegro is already configured."


def test_setup_validation_message_is_localized(client):
    body = {"client_id": "", "client_secret": "x"}
    assert client.post("/api/setup", json=body).json()["detail"].startswith("Podaj poprawny")
    english = client.post("/api/setup", json=body, headers={"Accept-Language": "en"})
    assert english.status_code == 422
    assert english.json()["detail"] == (
        "Enter a valid Client ID and Client Secret (no spaces or newlines, at most 4096 characters)."
    )


def test_setup_wrong_origin_message_is_localized(app_env, monkeypatch):
    _fresh_install(app_env, monkeypatch)
    headers = _setup_headers(app_env, "en")
    headers["Origin"] = "https://attacker.example"
    response = _anonymous(
        app_env, "POST", "/api/setup", base_url="http://localhost:3001", headers=headers,
        json={"client_id": "a", "client_secret": "b"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Open the configuration inside the Weles app and try again."


def test_setup_save_failure_message_is_localized(app_env, monkeypatch):
    _fresh_install(app_env, monkeypatch)
    app_env.env_file.unlink()
    app_env.env_file.mkdir()
    response = _anonymous(
        app_env, "POST", "/api/setup", base_url="http://localhost:3001",
        headers=_setup_headers(app_env, "en"),
        json={"client_id": "a", "client_secret": "b"},
    )
    assert response.status_code == 503
    assert response.json()["detail"].startswith("Could not save .env.")


# ---------------------------------------------------------------- orders / printing


def test_seed_mock_refusal_is_localized(client, monkeypatch):
    monkeypatch.delenv("PACKING_SHIPMENT_DRY_RUN", raising=False)
    polish = client.post("/api/orders/seed-mock")
    assert polish.status_code == 409
    assert "Zamówienia testowe" in polish.json()["detail"]

    english = client.post("/api/orders/seed-mock", headers={"Accept-Language": "en"})
    assert english.json()["detail"] == (
        "Sample orders are available only with PACKING_SHIPMENT_DRY_RUN=1. "
        "Never enable this mode in production."
    )


def test_sync_connectivity_failure_is_localized(app_env, client, monkeypatch):
    import httpx

    import api.allegro as allegro

    async def failing(_limit=100):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(allegro, "fetch_orders", failing)

    polish = client.post("/api/orders/sync")
    assert polish.status_code == 502
    assert polish.json()["detail"].startswith("Brak łączności z Allegro:")

    english = client.post("/api/orders/sync", headers={"Accept-Language": "en"})
    assert english.status_code == 502
    assert english.json()["detail"] == "Cannot reach Allegro: connection refused"


def test_label_size_requirement_is_localized(app_env, client):
    app_env.write_state(app_env.default_state({
        "o-1": sample_order(courier="Paczkomat InPost"),
    }))
    # A locker order with no size chosen yet must be refused before any carrier call.
    english = client.get("/api/print/orders/o-1/label", headers={"Accept-Language": "en"})
    assert english.status_code == 400
    assert english.json()["detail"] == "Choose a parcel size (A, B or C) for the InPost parcel locker."


def test_custom_doc_errors_are_localized(client):
    not_pdf = {"file": ("notes.txt", b"hello", "text/plain")}
    assert client.post("/api/print/custom-doc", files=not_pdf).json()["detail"] == "Wymagany plik PDF."
    english = client.post(
        "/api/print/custom-doc", files=not_pdf, headers={"Accept-Language": "en"}
    )
    assert english.json()["detail"] == "A PDF file is required."

    fake_pdf = {"file": ("fake.pdf", b"not really a pdf", "application/pdf")}
    assert client.post(
        "/api/print/custom-doc", files=fake_pdf, headers={"Accept-Language": "en"}
    ).json()["detail"] == "This is not a PDF file."

    missing = client.get("/api/print/custom-doc", headers={"Accept-Language": "en"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "No document has been uploaded."


# ---------------------------------------------------------------- sales document


def test_sales_document_scaffolding_defaults_to_polish(app_env, client):
    app_env.write_state(app_env.default_state({
        "o-1": sample_order(pickup_point="WAW01M"),
    }))
    html = client.get("/api/print/orders/o-1/invoice").text
    assert '<html lang="pl">' in html
    assert "Dokument sprzedażowy" in html
    assert "Zamówione produkty" in html
    assert "Kupujący" in html
    assert "Adres" in html
    assert "Kurier" in html
    assert "Punkt odbioru" in html
    assert "Nr zamówienia" in html
    assert ">Ilość<" in html
    assert "Cena jedn." in html
    assert "Razem" in html


def test_sales_document_scaffolding_is_english_when_requested(app_env, client):
    app_env.write_state(app_env.default_state({
        "o-1": sample_order(pickup_point="WAW01M"),
    }))
    html = client.get(
        "/api/print/orders/o-1/invoice", headers={"Accept-Language": "en"}
    ).text
    assert '<html lang="en">' in html
    assert "Sales document" in html
    assert "Ordered products" in html
    assert "Buyer" in html
    assert "Address" in html
    assert "Courier" in html
    assert "Pickup point" in html
    assert "Order number" in html
    assert "Quantity" in html
    assert "Unit price" in html
    assert "Total" in html
    # The order's own data is untouched, and no Polish scaffolding leaks through.
    assert "Jan Kowalski" in html
    assert "Dokument sprzedażowy" not in html
    assert "Zamówione produkty" not in html
    assert "Razem" not in html


def test_sales_document_date_format_follows_the_language():
    import localization

    # Polish uses d.m.yyyy; English follows the frontend locale (en-GB): dd/mm/yyyy.
    assert localization.date_format("pl") == "%-d.%-m.%Y"
    assert localization.date_format("en") == "%d/%m/%Y"
    assert localization.date_format(None) == "%-d.%-m.%Y"


# ---------------------------------------------------------------- OAuth


def _start_oauth(client, language=None):
    """Ask the API for an authorization URL; returns (state, url)."""
    from urllib.parse import parse_qs, urlparse

    headers = {"Accept-Language": language} if language else {}
    url = client.get("/api/orders/auth/url", headers=headers).json()["url"]
    return parse_qs(urlparse(url).query)["state"][0], url


def test_oauth_callback_html_keeps_the_language_chosen_at_initiation(app_env, client):
    """The callback is a browser navigation: it must remember the start language."""
    state, _ = _start_oauth(client, "en")
    # The browser returns with a different header; the carried language still wins.
    response = _anonymous(
        app_env, "GET", "/api/orders/auth/callback",
        params={"state": state, "error": "access_denied"},
        headers={"Accept-Language": "pl"},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="en">' in response.text
    assert "Allegro rejected the authorization: access_denied" in response.text


def test_oauth_callback_is_polish_when_started_without_a_language(app_env, client):
    state, _ = _start_oauth(client)
    response = _anonymous(
        app_env, "GET", "/api/orders/auth/callback",
        params={"state": state, "code": "c", "error": "access_denied"},
        headers={"Accept-Language": "en"},
    )
    assert response.status_code == 400
    assert '<html lang="pl">' in response.text
    assert "Allegro odrzuciło autoryzację: access_denied" in response.text


def test_oauth_callback_state_error_uses_the_request_language(app_env):
    english = _anonymous(
        app_env, "GET", "/api/orders/auth/callback",
        params={"code": "c", "state": "wrong"},
        headers={"Accept-Language": "en"},
    )
    assert english.status_code == 400
    assert "Invalid or expired authorization state." in english.text

    polish = _anonymous(app_env, "GET", "/api/orders/auth/callback", params={"code": "c"})
    assert polish.status_code == 400
    assert "Nieprawidłowy lub wygasły stan autoryzacji." in polish.text


def test_oauth_callback_escapes_upstream_error_text(app_env, client):
    """The error comes from the query string: it must never become markup."""
    state, _ = _start_oauth(client, "en")
    response = _anonymous(
        app_env, "GET", "/api/orders/auth/callback",
        params={"state": state, "error": "<script>alert(1)</script>"},
    )
    assert response.status_code == 400
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_oauth_state_still_single_use_with_the_language_carry(app_env, client, monkeypatch):
    """Carrying the language must not weaken the one-shot state check."""
    import api.allegro as allegro

    exchanged = []

    async def fake_exchange(code):
        exchanged.append(code)

    monkeypatch.setattr(allegro, "exchange_code", fake_exchange)

    state, _ = _start_oauth(client, "en")
    first = _anonymous(
        app_env, "GET", "/api/orders/auth/callback", params={"state": state, "code": "c"}
    )
    assert first.status_code == 307
    replay = _anonymous(
        app_env, "GET", "/api/orders/auth/callback", params={"state": state, "code": "c"}
    )
    assert replay.status_code == 400
    assert exchanged == ["c"]


# ---------------------------------------------------------------- Allegro client


def test_allegro_not_authorized_message_is_localized(app_env, client):
    polish = client.post("/api/orders/sync")
    assert polish.status_code == 401
    assert polish.json()["detail"] == "Allegro nie jest autoryzowane. Kliknij 'Autoryzuj Allegro'."

    english = client.post("/api/orders/sync", headers={"Accept-Language": "en"})
    assert english.status_code == 401
    assert english.json()["detail"] == "Allegro is not authorized. Click 'Connect Allegro'."


def test_allegro_invalid_data_message_is_localized(app_env, client, monkeypatch):
    """A gateway HTML page from Allegro must read as a translated 502."""
    import httpx

    import api.allegro as allegro

    class FakeResponse:
        is_success = True
        text = "<html>gateway</html>"

        def json(self):
            raise ValueError("Expecting value")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            return FakeResponse()

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        allegro.httpx, "AsyncClient",
        lambda **kwargs: real_client(**kwargs) if "transport" in kwargs else FakeClient(),
    )
    allegro._token = "test-token"

    english = client.post("/api/orders/sync", headers={"Accept-Language": "en"})
    assert english.status_code == 502
    assert english.json()["detail"].endswith("Allegro returned invalid data (order list).")


def test_allegro_incomplete_sync_message_is_localized(app_env, client, monkeypatch):
    import httpx

    import api.allegro as allegro

    class FakeResponse:
        is_success = True
        text = ""

        def __init__(self, forms):
            self._forms = forms

        def json(self):
            return {"checkoutForms": self._forms}

    def form(allegro_id):
        return {
            "id": allegro_id,
            "buyer": {}, "delivery": {"address": {}, "method": {}, "pickupPoint": None},
            "lineItems": [{"offer": {"name": "x"}, "quantity": 1}],
        }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            offset = params["offset"]
            if offset == 0:
                return FakeResponse([form(f"a-{i}") for i in range(100)])
            return FakeResponse([form("overflow")])

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        allegro.httpx, "AsyncClient",
        lambda **kwargs: real_client(**kwargs) if "transport" in kwargs else FakeClient(),
    )
    monkeypatch.setattr(allegro, "MAX_SYNC_PAGES", 1)
    allegro._token = "test-token"

    english = client.post("/api/orders/sync", headers={"Accept-Language": "en"})
    assert english.status_code == 502
    assert english.json()["detail"] == (
        "Allegro: Incomplete sync: the limit of 100 orders was exceeded. "
        "No results from this sync were saved."
    )


def test_allegro_shipment_error_hint_is_localized(app_env):
    import api.allegro as allegro
    import localization

    class FakeResponse:
        def json(self):
            return {"errors": []}

    assert "Wysyłam z Allegro" in allegro._shipment_error(FakeResponse())
    with localization.language_scope("en"):
        hint = allegro._shipment_error(FakeResponse())
    assert hint == "Check the 'Ship with Allegro' settings and the app's shipment permissions."


# ------------------------------------------------- sales document date, rendered


def test_sales_document_english_date_is_dd_mm_yyyy(app_env, client, monkeypatch):
    """The English sales document must follow the frontend locale (en-GB): dd/mm/yyyy.

    Day and month differ on the fixed date, so a mm/dd/yyyy rendering is observably wrong.
    """
    import datetime

    import routes.print_routes as print_routes

    class FixedDate:
        @staticmethod
        def today():
            return datetime.date(2026, 3, 5)

    monkeypatch.setattr(print_routes, "date", FixedDate)
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))

    english = client.get(
        "/api/print/orders/o-1/invoice", headers={"Accept-Language": "en"}
    ).text
    assert "05/03/2026" in english
    assert "03/05/2026" not in english

    # Polish is unchanged: d.m.yyyy.
    polish = client.get("/api/print/orders/o-1/invoice").text
    assert "5.3.2026" in polish


# ------------------------------------------------- catalog placeholder parity


def test_every_message_has_the_same_placeholders_in_both_languages():
    """A translation must not silently drop or invent a ``{placeholder}``.

    This catches a catalog entry whose English text lost its placeholder (e.g. a
    literal ``***`` instead of ``{error}``): the value would stop being shown even
    though the Polish companion still interpolates it.
    """
    import re

    import localization

    placeholder = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    mismatches = {}
    for key, entry in localization.MESSAGES.items():
        pl = set(placeholder.findall(entry.get("pl", "")))
        en = set(placeholder.findall(entry.get("en", "")))
        if pl != en:
            mismatches[key] = {"pl": sorted(pl), "en": sorted(en)}
    assert mismatches == {}


def test_oauth_rejected_interpolates_the_error_in_both_languages():
    """Both catalogs carry ``{error}``, so the callback shows the real reason."""
    import localization

    assert "{error}" in localization.MESSAGES["oauth.rejected"]["pl"]
    assert "{error}" in localization.MESSAGES["oauth.rejected"]["en"]
    assert localization.t("oauth.rejected", lang="en", error="access_denied") == (
        "Allegro rejected the authorization: access_denied"
    )


# ------------------------------------------------- Allegro error-wrapper translation


def _install_allegro_transport(monkeypatch, handler):
    """Route api.allegro's HTTP calls to ``handler``; leave the ASGI test client intact."""
    import httpx

    import api.allegro as allegro

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        allegro.httpx, "AsyncClient",
        lambda **kwargs: real_client(**kwargs) if "transport" in kwargs
        else real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return allegro


def _allegro_error_message(coro, language):
    """Run ``coro`` and return the ``AllegroError`` message raised, in ``language``."""
    import asyncio

    import api.allegro as allegro
    import localization

    with localization.language_scope(language):
        with pytest.raises(allegro.AllegroError) as excinfo:
            asyncio.run(coro)
    return str(excinfo.value)


def test_allegro_token_refresh_wrapper_is_localized(app_env, monkeypatch):
    import httpx

    allegro = _install_allegro_transport(
        monkeypatch, lambda request: httpx.Response(503, text="upstream down")
    )
    allegro._token = None
    allegro._refresh_token = "r1"
    allegro._expires_at = 0.0

    message = _allegro_error_message(allegro._access_token(), "pl")
    assert message.startswith("Błąd Allegro")
    assert "odświeżenie tokenu" in message
    assert "503" in message
    assert "upstream down" in message  # raw upstream text stays verbatim


def test_allegro_token_exchange_wrapper_is_localized(app_env, monkeypatch):
    import httpx

    allegro = _install_allegro_transport(
        monkeypatch, lambda request: httpx.Response(500, text="bad code")
    )
    message = _allegro_error_message(allegro.exchange_code("code"), "pl")
    assert message.startswith("Błąd Allegro")
    assert "wymiana tokenu" in message
    assert "500" in message
    assert "bad code" in message


def test_allegro_label_api_wrapper_is_localized(app_env, monkeypatch):
    import httpx

    allegro = _install_allegro_transport(
        monkeypatch, lambda request: httpx.Response(500, text="label broker down")
    )
    allegro._token = "test-token"

    polish = _allegro_error_message(allegro.download_label("shipment-1"), "pl")
    assert polish.startswith("Błąd Allegro")
    assert "pobranie etykiety" in polish
    assert "500" in polish
    assert "label broker down" in polish

    # English keeps the exact wording it had before localization.
    english = _allegro_error_message(allegro.download_label("shipment-1"), "en")
    assert english == "Allegro label API 500: label broker down"


def test_allegro_checkout_forms_wrapper_is_localized(app_env, monkeypatch):
    """The endpoint identifier stays verbatim; only the surrounding prose is Polish."""
    import httpx

    allegro = _install_allegro_transport(
        monkeypatch, lambda request: httpx.Response(502, text="gateway")
    )
    allegro._token = "test-token"

    message = _allegro_error_message(allegro.fetch_orders(), "pl")
    assert message.startswith("Błąd Allegro")
    assert "checkout-forms" in message  # technical identifier, never translated
    assert "502" in message
    assert "gateway" in message


def _proposal_response():
    import httpx

    return httpx.Response(200, json={"suggestedInput": {
        "sender": {"name": "Seller", "email": "seller@example.com"},
        "receiver": {"email": "recipient@example.com"},
    }})


def test_allegro_create_shipment_wrapper_is_localized(app_env, monkeypatch):
    import httpx

    from models.order import Order

    def handler(request):
        if request.url.path.endswith("/delivery-proposals/a-1"):
            return _proposal_response()
        if request.method == "POST":
            return httpx.Response(500, json={"errors": [{"message": "create failed"}]})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    allegro = _install_allegro_transport(monkeypatch, handler)
    allegro._token = "test-token"

    message = _allegro_error_message(
        allegro.create_shipment(Order(**sample_order()), {}, {}), "pl"
    )
    assert message.startswith("Błąd Allegro")
    assert "utworzenie przesyłki" in message
    assert "500" in message
    assert "create failed" in message


def test_allegro_shipment_status_wrapper_is_localized(app_env, monkeypatch):
    import httpx

    from models.order import Order

    def handler(request):
        if request.url.path.endswith("/delivery-proposals/a-1"):
            return _proposal_response()
        if request.method == "POST":
            return httpx.Response(201, json={"commandId": "command-1"})
        return httpx.Response(500, text="poll broken")

    allegro = _install_allegro_transport(monkeypatch, handler)
    allegro._token = "test-token"

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(allegro.asyncio, "sleep", no_wait)

    message = _allegro_error_message(
        allegro.create_shipment(Order(**sample_order()), {}, {}), "pl"
    )
    assert message.startswith("Błąd Allegro")
    assert "status przesyłki" in message
    assert "500" in message
    assert "poll broken" in message
