import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import configuration
from fastapi import APIRouter, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

configuration.load_environment()

import store
from localization import current_language, negotiate_language, t
from request_limits import RequestBodyLimitMiddleware
from routes.documents import router as documents_router
from routes.orders import router as orders_router
from routes.print_routes import router as print_router
from routes.queue import router as queue_router
from routes.setup import is_configured, requires_access_token
from routes.setup import router as setup_router

logger = logging.getLogger("packing")

# The UI is served from this same origin, so CORS is only needed for other origins —
# list them explicitly with PACKING_CORS_ORIGINS instead of allowing every site.
DEFAULT_CORS_ORIGINS = ["http://localhost:3001", "http://127.0.0.1:3001"]
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("PACKING_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
    if origin.strip()
]

# Mirrors the access-token policy in routes/setup.py: a short shared secret is not a
# secret. Anything shorter is treated as "webhook not configured" and answers 503.
WEBHOOK_SECRET_MIN_LENGTH = 32

@asynccontextmanager
async def lifespan(_app: FastAPI):
    status = store.state_status()
    if status.get("ok"):
        logger.info("state file OK (%s)", store.DATA_FILE)
    else:
        logger.warning("state file problem: %s", status.get("message"))
    yield


app = FastAPI(title="Packing App", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/api/setup":
        # Pydantic's normal error payload includes the submitted input. Do not
        # echo a client secret, even when that input fails validation.
        return JSONResponse(
            status_code=422,
            content={"detail": t("setup.invalid_credentials_bounded")},
            headers={"Cache-Control": "no-store"},
        )
    if request.url.path in (
        "/api/print/document-settings", "/api/print/document-preview", "/api/print/document-templates/import",
    ):
        # Do not echo a logo's base64 payload or operator-authored document text.
        messages = []
        for error in exc.errors():
            cause = error.get("ctx", {}).get("error")
            if isinstance(cause, ValueError):
                messages.append(str(cause))
        detail = "; ".join(dict.fromkeys(messages)) if messages else t("document.invalid_template")
        return JSONResponse(status_code=422, content={"detail": detail}, headers={"Cache-Control": "no-store"})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(store.StateError)
async def state_error_handler(request: Request, exc: store.StateError):
    """A broken state file is an operator problem, not a crash: say so plainly."""
    logger.error("state file unusable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": str(exc), "state_ok": False})


# Keep the public API under /api, matching the URLs used by the frontend and the previous
# nginx reverse-proxy setup. A router prefix (not a mounted sub-app) so that error handlers
# and exceptions behave exactly as they do for any other route.
api = APIRouter(prefix="/api")
api.include_router(orders_router)
api.include_router(queue_router)
api.include_router(print_router)
api.include_router(documents_router)
api.include_router(setup_router)
app.include_router(api)


@app.post("/api/webhooks/sync", tags=["webhooks"])
async def webhook_sync():
    """Trigger the same order sync as the UI, authenticated by the webhook secret."""
    from routes.orders import sync_from_allegro

    return await sync_from_allegro()


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Protect the API; allow public status and a limited first-run bootstrap."""
    if (
        request.method == "OPTIONS"
        or not request.url.path.startswith("/api/")
        or request.url.path == "/api/orders/auth/callback"
        or (request.method == "GET" and request.url.path == "/api/setup/status")
        or (
            request.method == "POST"
            and request.url.path == "/api/setup"
            and not is_configured()
            and not requires_access_token()
        )
    ):
        return await call_next(request)

    if request.url.path == "/api/webhooks/sync":
        expected = os.getenv("PACKING_WEBHOOK_SECRET", "").strip()
        if len(expected) < WEBHOOK_SECRET_MIN_LENGTH:
            return JSONResponse(status_code=503, content={"detail": "Webhook is disabled."})
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        ):
            return JSONResponse(
                status_code=401, content={"detail": "Webhook authentication required."},
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
            )
        return await call_next(request)

    expected = os.getenv("PACKING_ACCESS_TOKEN", "")
    if len(expected) < 32:
        return JSONResponse(
            status_code=503,
            content={"detail": t("auth.token_not_configured")},
        )

    authorization = request.headers.get("authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
    ):
        return Response(
            status_code=401,
            content=json.dumps({"detail": t("auth.required")}),
            media_type="application/json",
            headers={
                "WWW-Authenticate": "Bearer",
                "Cache-Control": "no-store",
                "X-Packing-Auth-Required": "1",
            },
        )

    return await call_next(request)


# CORS must wrap the auth middleware so preflights and auth errors receive CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Packing-Auth-Required"],
)


@app.middleware("http")
async def use_request_language(request: Request, call_next):
    """Negotiate pl/en once per request and keep it request-scoped.

    Registered last, so this wraps the CORS and auth middleware, the exception
    handlers and every route. The ContextVar is copied into the downstream task,
    so concurrent requests with different headers never share a language.
    """
    token = current_language.set(negotiate_language(request.headers.get("accept-language")))
    try:
        return await call_next(request)
    finally:
        current_language.reset(token)


# In the single-container image the backend serves the built-in static UI.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if not (FRONTEND_DIR / "static").is_dir():
    raise RuntimeError(
        f"Brak katalogu {FRONTEND_DIR / 'static'} — obraz zbudowany bez frontendu (COPY frontend)."
    )
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    status = store.state_status()
    return {"status": "ok" if status.get("ok") else "degraded", "state": status}
