"""Load the server's .env and update the three first-run settings only."""
import fcntl
import io
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from dotenv.parser import parse_stream

ENV_FILE = Path(os.getenv("PACKING_ENV_FILE", Path(__file__).resolve().parent.parent / ".env"))


def load_environment() -> None:
    # Keep Compose's resolved values for unrelated settings and support normal
    # dotenv interpolation in local development.
    load_dotenv(ENV_FILE, override=False)
    # Setup keys alone are authoritative after `docker restart`, when Compose's
    # original process environment still contains old values. Read them literally
    # so dollar signs in a saved secret never expand into environment references.
    saved = dotenv_values(ENV_FILE, interpolate=False)
    for key in ("ALLEGRO_CLIENT_ID", "ALLEGRO_CLIENT_SECRET", "PACKING_ACCESS_TOKEN"):
        if saved.get(key) is not None:
            os.environ[key] = saved[key]


def save_setup(values: dict[str, str]) -> None:
    """Preserve unrelated settings and the inode of Docker's file bind mount."""
    descriptor = os.open(ENV_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8", newline="") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        original = handle.read()
        remaining = dict(values)
        lines = []
        for binding in parse_stream(io.StringIO(original)):
            if binding.error:
                raise ValueError("Existing .env cannot be parsed.")
            if binding.key in values:
                if binding.key in remaining:
                    value = remaining.pop(binding.key)
                    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
                    lines.append(f"{binding.key}='{escaped}'\n")
                # Drop duplicate definitions so they cannot override the save.
            else:
                lines.append(binding.original.string)
        updated = "".join(lines)
        if updated and not updated.endswith("\n"):
            updated += "\n"
        for key, value in remaining.items():
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            updated += f"{key}='{escaped}'\n"
        os.fchmod(handle.fileno(), 0o600)
        try:
            handle.seek(0)
            handle.write(updated)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
        except OSError:
            # Recover the previous contents on a failed write where possible.
            try:
                handle.seek(0)
                handle.write(original)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
            except OSError:
                pass
            raise
