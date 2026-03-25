from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ENV_PATH = "/app/.env"
router = APIRouter(prefix="/config", tags=["config"])


class EnvContent(BaseModel):
    content: str


@router.get("/")
def get_env():
    try:
        with open(ENV_PATH) as f:
            return {"content": f.read()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=".env file not found.")


@router.post("/")
def save_env(body: EnvContent):
    with open(ENV_PATH, "w") as f:
        f.write(body.content)
    return {"status": "saved", "note": "Zrestartuj kontener żeby zmiany weszły w życie."}
