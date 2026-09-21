import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ENV_PATH = Path(os.getenv("PACKING_ENV_FILE", "/app/.env"))

router = APIRouter(prefix="/config", tags=["config"])


class EnvContent(BaseModel):
    content: str


@router.get("/")
def get_env():
    try:
        return {"content": ENV_PATH.read_text(encoding="utf-8")}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=".env file not found.")


@router.post("/")
def save_env(body: EnvContent):
    # .env is bind-mounted as a single file in compose, so it has to be written in place:
    # os.replace() onto a mount point fails with EBUSY ("Device or resource busy").
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_PATH, "w", encoding="utf-8") as handle:
        handle.write(body.content)
        handle.flush()
        os.fsync(handle.fileno())
    return {"status": "saved", "note": "Zrestartuj kontener żeby zmiany weszły w życie."}
