"""One-time, same-origin Allegro setup. No endpoint reads back credentials."""
import hmac
import logging
import os
import secrets
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

import api.allegro as allegro
import configuration
from localization import t

router = APIRouter(prefix="/setup", tags=["setup"])
logger = logging.getLogger("packing.setup")
_setup_token = secrets.token_urlsafe(32)
_setup_lock = threading.Lock()


class SetupCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    client_secret: SecretStr

    @field_validator("client_id", "client_secret")
    @classmethod
    def validate_credential(cls, value):
        text = value.get_secret_value() if isinstance(value, SecretStr) else value
        text = text.strip()
        if not text or len(text) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in text):
            raise ValueError(t("setup.invalid_credentials"))
        return SecretStr(text) if isinstance(value, SecretStr) else text


def is_configured() -> bool:
    return bool(allegro.CLIENT_ID.strip() and allegro.CLIENT_SECRET.strip())


def requires_access_token() -> bool:
    return len(os.getenv("PACKING_ACCESS_TOKEN", "")) >= 32


@router.get("/status")
def setup_status():
    configured = is_configured()
    status = {"configured": configured, "requires_access_token": requires_access_token()}
    if not configured:
        status.update({
            "setup_token": _setup_token,
            "sandbox": allegro.SANDBOX,
            "redirect_uri": allegro.REDIRECT_URI,
        })
    return JSONResponse(status, headers={"Cache-Control": "no-store"})


@router.post("")
def complete_setup(credentials: SetupCredentials, request: Request):
    with _setup_lock:
        if is_configured():
            raise HTTPException(status_code=409, detail=t("setup.already_configured"))
        # Require the browser's exact origin and a token from the setup status
        # response. This prevents a different website from claiming first-run setup.
        origin = request.headers.get("origin", "")
        token = request.headers.get("x-packing-setup-token", "")
        if origin != str(request.base_url).rstrip("/") or not hmac.compare_digest(
            token.encode("utf-8"), _setup_token.encode("utf-8")
        ):
            raise HTTPException(status_code=403, detail=t("setup.wrong_origin"))

        generated_token = None
        if not requires_access_token():
            if request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise HTTPException(status_code=403, detail=t("setup.localhost_only"))
            generated_token = secrets.token_urlsafe(32)

        values = {
            "ALLEGRO_CLIENT_ID": credentials.client_id,
            "ALLEGRO_CLIENT_SECRET": credentials.client_secret.get_secret_value(),
        }
        if generated_token:
            values["PACKING_ACCESS_TOKEN"] = generated_token
        try:
            configuration.save_setup(values)
        except (OSError, UnicodeError, ValueError) as exc:
            logger.error("Could not save first-run configuration (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail=t("setup.save_failed"),
            ) from None

        os.environ.update(values)
        allegro.CLIENT_ID = values["ALLEGRO_CLIENT_ID"]
        allegro.CLIENT_SECRET = values["ALLEGRO_CLIENT_SECRET"]
        result = {"configured": True}
        if generated_token:
            # Return the newly generated operator token once, so it can be saved
            # for subsequent visits. Never return either Allegro credential.
            result["access_token"] = generated_token
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
