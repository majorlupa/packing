"""Transport, authentication and error mapping of the API client."""
import asyncio

import httpx
import pytest
from helpers import PDF_BYTES, FakeAPI

from mcp_server.client import PackingError
from mcp_server.config import Settings


def test_requests_carry_bearer_token_and_language():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[])
    client = api.client(language="pl")
    asyncio.run(client.get_orders())

    request = api.last()
    assert request.headers["authorization"] == "Bearer test-token-not-a-secret"
    assert request.headers["accept-language"] == "pl"
    assert request.headers["accept"] == "application/json"
    assert str(request.url) == "http://packing.test/api/orders/"


def test_health_needs_no_token_and_hits_the_public_route():
    api = FakeAPI()
    api.add("GET", "/health", json_body={"status": "ok", "state": {"ok": True}})
    client = api.client(access_token="")
    assert asyncio.run(client.health())["status"] == "ok"
    assert "authorization" not in api.last().headers


def test_missing_token_fails_before_touching_the_network():
    api = FakeAPI()
    client = api.client(access_token="")
    with pytest.raises(PackingError, match="PACKING_ACCESS_TOKEN is not set"):
        asyncio.run(client.get_orders())
    assert api.requests == []


def test_structured_allegro_error_keeps_the_app_message_and_code():
    api = FakeAPI()
    api.add(
        "POST",
        "/api/orders/sync",
        status=502,
        json_body={"detail": {"code": "allegro.request_failed",
                              "message": "Allegro rejected the request."}},
    )
    with pytest.raises(PackingError) as error:
        asyncio.run(api.client().sync_orders())
    assert error.value.status_code == 502
    assert error.value.code == "allegro.request_failed"
    assert "Allegro rejected the request." in str(error.value)
    assert "[allegro.request_failed]" in str(error.value)


def test_unauthorized_error_tells_the_operator_what_to_fix():
    api = FakeAPI()
    api.add("GET", "/api/orders/", status=401, json_body={"detail": "Access token required."})
    with pytest.raises(PackingError) as error:
        asyncio.run(api.client().get_orders())
    message = str(error.value)
    assert "HTTP 401" in message
    assert "PACKING_ACCESS_TOKEN" in message
    assert "Access token required." in message
    assert "test-token-not-a-secret" not in message


def test_plain_detail_is_passed_through_for_conflicts():
    api = FakeAPI()
    api.add("GET", "/api/print/orders/order-1/label", status=409,
            json_body={"detail": "Shipment has not been created."})
    with pytest.raises(PackingError) as error:
        asyncio.run(api.client().label_pdf("order-1"))
    assert error.value.status_code == 409
    assert "conflicts with the current state" in str(error.value)
    assert "Shipment has not been created." in str(error.value)


def test_validation_errors_are_summarised_not_dumped():
    api = FakeAPI()
    api.add(
        "PATCH",
        "/api/orders/order-1/parcel-size",
        status=422,
        json_body={"detail": [{"loc": ["body", "parcel_size"], "msg": "Input should be 'A', 'B' or 'C'"}]},
    )
    with pytest.raises(PackingError) as error:
        asyncio.run(api.client().set_parcel_size("order-1", "D"))
    message = str(error.value)
    assert "HTTP 422" in message
    assert "parcel_size: Input should be 'A', 'B' or 'C'" in message


def test_connection_failure_names_the_configured_url_only():
    def refuse(_request):
        raise httpx.ConnectError("connection refused")

    api = FakeAPI()
    client = FakeAPI().client()
    client._transport = httpx.MockTransport(refuse)
    with pytest.raises(PackingError) as error:
        asyncio.run(client.get_orders())
    message = str(error.value)
    assert "http://packing.test" in message
    assert "PACKING_API_URL" in message
    assert "test-token-not-a-secret" not in message
    assert api.requests == []


def test_pdf_endpoints_return_bytes_and_reject_non_pdf():
    api = FakeAPI()
    api.add("GET", "/api/print/orders/order-1/label", content=PDF_BYTES,
            content_type="application/pdf")
    client = api.client()
    assert asyncio.run(client.label_pdf("order-1")).startswith(b"%PDF-")
    assert api.last().headers["accept"] == "application/pdf"

    broken = FakeAPI()
    broken.add("GET", "/api/print/orders/order-1/label", json_body={"ok": True})
    with pytest.raises(PackingError, match="not a PDF"):
        asyncio.run(broken.client().label_pdf("order-1"))


def test_custom_document_uses_the_order_id_query_parameter():
    api = FakeAPI()
    api.add("GET", "/api/print/custom-doc", content=PDF_BYTES, content_type="application/pdf")
    asyncio.run(api.client().document_pdf("order-1", "custom"))
    assert api.last().url.params["order_id"] == "order-1"


def test_upload_sends_multipart_pdf():
    api = FakeAPI()
    api.add("POST", "/api/print/custom-doc", json_body={"status": "uploaded"})
    asyncio.run(api.client().upload_custom_doc("custom.pdf", PDF_BYTES))
    request = api.last()
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'filename="custom.pdf"' in request.content
    assert PDF_BYTES in request.content


def test_invalid_payload_reports_a_readable_error():
    api = FakeAPI()
    api.add("GET", "/api/orders/", content=b"<html>gateway</html>", content_type="text/html")
    with pytest.raises(PackingError, match="not JSON"):
        asyncio.run(api.client().get_orders())


def test_settings_object_is_kept_but_token_hidden():
    settings = Settings(api_url="http://packing.test", access_token="secret")
    assert settings.access_token == "secret"
    assert "secret" not in repr(settings)
