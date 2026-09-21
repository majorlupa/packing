import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import store
from routes.orders import router as orders_router
from routes.queue import router as queue_router
from routes.print_routes import router as print_router
from routes.config import router as config_router

logger = logging.getLogger("packing")

# The UI is served from this same origin, so CORS is only needed for other origins —
# list them explicitly with PACKING_CORS_ORIGINS instead of allowing every site.
DEFAULT_CORS_ORIGINS = ["http://localhost:3001", "http://127.0.0.1:3001"]
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("PACKING_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
    if origin.strip()
]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    status = store.state_status()
    if status.get("ok"):
        logger.info("state file OK (%s)", store.DATA_FILE)
    else:
        logger.warning("state file problem: %s", status.get("message"))
    yield


app = FastAPI(title="Packing App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
api.include_router(config_router)
app.include_router(api)

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
