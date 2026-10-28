"""Environment-driven configuration for the Packing MCP server.

Every setting has a PACKING_* name so one .env can describe the app and the MCP
server. The access token is kept out of ``repr`` and is never logged or echoed in
an error message.
"""
import os
from dataclasses import dataclass, field

DEFAULT_API_URL = "http://127.0.0.1:3001"
DEFAULT_LANGUAGE = "en"
DEFAULT_TIMEOUT = 60.0
SUPPORTED_LANGUAGES = ("pl", "en")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class Settings:
    """Connection and printing settings resolved from the environment."""

    api_url: str = DEFAULT_API_URL
    access_token: str = field(default="", repr=False)
    language: str = DEFAULT_LANGUAGE
    printer: str = ""
    label_dir: str = ""
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "Settings":
        language = os.getenv("PACKING_LANGUAGE", DEFAULT_LANGUAGE).strip().lower() or DEFAULT_LANGUAGE
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"PACKING_LANGUAGE must be one of {', '.join(SUPPORTED_LANGUAGES)}, got {language!r}"
            )
        api_url = (os.getenv("PACKING_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ValueError("PACKING_API_URL must start with http:// or https://")
        return cls(
            api_url=api_url,
            access_token=os.getenv("PACKING_ACCESS_TOKEN", "").strip(),
            language=language,
            printer=os.getenv("PACKING_PRINTER", "").strip(),
            label_dir=os.getenv("PACKING_LABEL_DIR", "").strip(),
            timeout=_env_float("PACKING_API_TIMEOUT", DEFAULT_TIMEOUT),
        )
