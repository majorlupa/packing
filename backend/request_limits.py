"""Bound bodies before JSON decoding or multipart parsing/spooling."""
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

DEFAULT_BODY_LIMIT = 64 * 1024
BODY_LIMITS = {
    # Room for a 2.8 MB base64 logo plus text and JSON encoding overhead.
    "/api/print/document-settings": 4 * 1024 * 1024,
    "/api/print/document-preview": 4 * 1024 * 1024,
    # Batch imports (up to 10 templates) need room for logos and JSON overhead;
    # cap the entire file at 12 MiB before parsing, independently of per-template limits.
    "/api/print/document-templates/import": 4 * 1024 * 1024 * 3,
    # The existing 20 MiB PDF limit still applies; allow multipart overhead.
    "/api/print/custom-doc": 21 * 1024 * 1024,
}


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        limit = BODY_LIMITS.get(scope["path"].rstrip("/"), DEFAULT_BODY_LIMIT)
        response = JSONResponse(
            {"detail": "Request body too large"}, status_code=413, headers={"Cache-Control": "no-store"},
        )
        try:
            declared = int(Headers(scope=scope).get("content-length", "0"))
        except ValueError:
            declared = 0  # Actual bytes are authoritative, even with a bad header.
        if declared > limit:
            return await response(scope, receive, send)

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        # Buffer first: exceptions from a wrapped receive can become parser 400s.
        # Replay only after the complete body passes, so handlers cannot mutate state.
        pending = {"type": "http.request", "body": bytes(body), "more_body": False}
        del body

        async def replay():
            nonlocal pending
            if pending is not None:
                message, pending = pending, None
                return message
            return await receive()

        await self.app(scope, replay, send)
