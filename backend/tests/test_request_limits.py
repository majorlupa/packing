import asyncio

import pytest


@pytest.mark.parametrize("path", [
    "/api/print/document-settings", "/api/print/document-preview",
    "/api/print/invoice-settings", "/api/print/shipment-settings", "/api/print/custom-doc", "/api/setup",
])
@pytest.mark.parametrize("declared_length", [None, "1", "100000000"])
def test_oversized_requests_rejected_before_parsing(app_env, client, monkeypatch, path, declared_length):
    import request_limits
    from routes.print_routes import CUSTOM_DOC_PATH

    monkeypatch.setattr(request_limits, "DEFAULT_BODY_LIMIT", 64)
    monkeypatch.setattr(request_limits, "BODY_LIMITS", {})
    before = app_env.store.get_document_settings()
    headers = {"Content-Type": "application/json"}
    if declared_length is not None:
        headers["Content-Length"] = declared_length

    async def chunks():
        yield b'{"image":"' + b"x" * 64
        yield b'"}'

    response = client.post(path, content=chunks(), headers=headers)
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    assert response.headers["cache-control"] == "no-store"
    assert app_env.store.get_document_settings() == before
    assert not CUSTOM_DOC_PATH.exists()


@pytest.mark.parametrize("size,expected", [(64, 204), (65, 413)])
def test_stream_limit_boundary_and_early_stop(app_env, monkeypatch, size, expected):
    from request_limits import RequestBodyLimitMiddleware

    monkeypatch.setattr("request_limits.DEFAULT_BODY_LIMIT", 64)
    messages = iter([
        {"type": "http.request", "body": b"x" * 32, "more_body": True},
        {"type": "http.request", "body": b"x" * (size - 32), "more_body": True},
        {"type": "http.request", "body": b"", "more_body": False},
    ])
    reads = []
    sent = []

    async def receive():
        reads.append(True)
        return next(messages)

    async def downstream(scope, receive, send):
        first = await receive()
        assert first["body"] == b"x" * size and not first["more_body"]
        await send({"type": "http.response.start", "status": 204, "headers": []})

    async def send(message):
        sent.append(message)

    asyncio.run(RequestBodyLimitMiddleware(downstream)(
        {"type": "http", "path": "/api/test", "method": "POST", "headers": []}, receive, send,
    ))
    assert sent[0]["status"] == expected
    assert len(reads) == (3 if expected == 204 else 2)


def test_limits_allow_document_logos_and_upload_overhead(app_env):
    from request_limits import BODY_LIMITS, DEFAULT_BODY_LIMIT
    from routes.print_routes import MAX_CUSTOM_DOC_BYTES

    assert DEFAULT_BODY_LIMIT == 64 * 1024
    assert BODY_LIMITS["/api/print/document-settings"] == 4 * 1024 * 1024
    assert BODY_LIMITS["/api/print/document-preview"] == 4 * 1024 * 1024
    assert BODY_LIMITS["/api/print/custom-doc"] == MAX_CUSTOM_DOC_BYTES + 1024 * 1024
