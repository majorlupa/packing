"""First-run setup saves only validated credentials and never exposes .env."""
import asyncio
import os
import subprocess
import sys

import httpx
import pytest
from dotenv import dotenv_values

ORIGIN = "http://localhost:3001"
CLIENT_ID = "onboarding-client-id"
CLIENT_SECRET = "onboarding-client-secret"
ACCESS_TOKEN = "test-access-token-for-packing-api-2026"


def request(app_env, method, path, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=app_env.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def first_run(app_env, monkeypatch, access_token=ACCESS_TOKEN):
    import api.allegro as allegro

    monkeypatch.setattr(allegro, "CLIENT_ID", "")
    monkeypatch.setattr(allegro, "CLIENT_SECRET", "")
    monkeypatch.setenv("ALLEGRO_CLIENT_ID", "")
    monkeypatch.setenv("ALLEGRO_CLIENT_SECRET", "")
    monkeypatch.setenv("PACKING_ACCESS_TOKEN", access_token)
    app_env.env_file.write_text(
        "# Keep my settings\nALLEGRO_CLIENT_ID=\nALLEGRO_CLIENT_SECRET=\n"
        "ALLEGRO_SANDBOX=true\nINPOST_SHIPX_TOKEN=preserve-me\n"
        f"PACKING_ACCESS_TOKEN={access_token}\n",
        encoding="utf-8",
    )


def submit(app_env, payload=None, access_token=ACCESS_TOKEN, origin=ORIGIN, setup_token=None):
    status = request(app_env, "GET", "/api/setup/status")
    headers = {
        "Origin": origin,
        "X-Packing-Setup-Token": setup_token if setup_token is not None else status.json().get("setup_token", ""),
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return request(
        app_env, "POST", "/api/setup", headers=headers,
        json=payload if payload is not None else {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
    )


def test_status_is_public_and_never_returns_credentials(app_env):
    response = request(app_env, "GET", "/api/setup/status")
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "client_id" not in response.json()
    assert "client_secret" not in response.json()
    assert "setup_token" not in response.json()
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("missing", ["CLIENT_ID", "CLIENT_SECRET"])
def test_either_missing_credential_needs_setup(app_env, monkeypatch, missing):
    import api.allegro as allegro

    monkeypatch.setattr(allegro, missing, "")
    response = request(app_env, "GET", "/api/setup/status")
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["requires_access_token"] is True
    assert response.json()["setup_token"]


def test_saves_credentials_preserves_other_settings_and_uses_them_immediately(app_env, monkeypatch):
    import api.allegro as allegro

    first_run(app_env, monkeypatch)
    response = submit(app_env)
    assert response.status_code == 200
    assert response.json() == {"configured": True}
    assert CLIENT_SECRET not in response.text
    saved = dotenv_values(app_env.env_file)
    assert saved["ALLEGRO_CLIENT_ID"] == CLIENT_ID
    assert saved["ALLEGRO_CLIENT_SECRET"] == CLIENT_SECRET
    assert saved["INPOST_SHIPX_TOKEN"] == "preserve-me"
    assert saved["ALLEGRO_SANDBOX"] == "true"
    assert saved["PACKING_ACCESS_TOKEN"] == ACCESS_TOKEN
    assert "# Keep my settings" in app_env.env_file.read_text()
    assert app_env.env_file.stat().st_mode & 0o777 == 0o600
    assert allegro.CLIENT_ID == CLIENT_ID
    assert allegro.CLIENT_SECRET == CLIENT_SECRET
    assert request(app_env, "GET", "/api/setup/status").json()["configured"] is True


def test_fresh_install_generates_access_token_and_locks_setup(app_env, monkeypatch):
    first_run(app_env, monkeypatch, access_token="")
    assert request(app_env, "GET", "/api/setup/status").json()["requires_access_token"] is False
    response = submit(app_env, access_token="")
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert len(token) >= 32
    assert dotenv_values(app_env.env_file)["PACKING_ACCESS_TOKEN"] == token
    assert request(app_env, "GET", "/api/orders/").status_code == 401
    assert request(app_env, "GET", "/api/orders/", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert submit(app_env, access_token="").status_code == 401


def test_setup_cannot_overwrite_configured_credentials(app_env):
    before = app_env.env_file.read_bytes()
    assert submit(app_env).status_code == 409
    assert app_env.env_file.read_bytes() == before


def test_setup_requires_existing_access_token(app_env, monkeypatch):
    first_run(app_env, monkeypatch)
    before = app_env.env_file.read_bytes()
    assert submit(app_env, access_token="wrong").status_code == 401
    assert submit(app_env, access_token="").status_code == 401
    assert app_env.env_file.read_bytes() == before


@pytest.mark.parametrize("origin,setup_token", [
    ("https://attacker.example", None),
    ("http://127.0.0.1:3001", None),
    (ORIGIN, "wrong"),
])
def test_first_run_rejects_cross_origin_and_invalid_setup_token(app_env, monkeypatch, origin, setup_token):
    first_run(app_env, monkeypatch, access_token="")
    before = app_env.env_file.read_bytes()
    assert submit(app_env, access_token="", origin=origin, setup_token=setup_token).status_code == 403
    assert app_env.env_file.read_bytes() == before


@pytest.mark.parametrize("payload", [
    {"client_id": "", "client_secret": CLIENT_SECRET},
    {"client_id": CLIENT_ID, "client_secret": "   "},
    {"client_id": CLIENT_ID, "client_secret": "sensitive\nINJECTED=1"},
    {"client_id": CLIENT_ID, "client_secret": "sensitive\x00value"},
    {"client_id": CLIENT_ID, "client_secret": "sensitive" * 1000},
    {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "PACKING_ACCESS_TOKEN": "injected"},
])
def test_invalid_setup_does_not_modify_file_or_echo_secrets(app_env, monkeypatch, payload):
    first_run(app_env, monkeypatch)
    before = app_env.env_file.read_bytes()
    response = submit(app_env, payload)
    assert response.status_code == 422
    assert "sensitive" not in response.text
    assert CLIENT_SECRET not in response.text
    assert app_env.env_file.read_bytes() == before


def test_save_preserves_file_inode_for_docker_bind_mount(app_env, monkeypatch):
    first_run(app_env, monkeypatch)
    inode = app_env.env_file.stat().st_ino
    assert submit(app_env).status_code == 200
    assert app_env.env_file.stat().st_ino == inode


def test_save_handles_duplicate_keys_and_multiline_settings(app_env, monkeypatch):
    first_run(app_env, monkeypatch)
    with app_env.env_file.open("a") as handle:
        handle.write("export ALLEGRO_CLIENT_ID=old\nALLEGRO_CLIENT_SECRET=old\nMESSAGE='line one\nline two'\n")
    assert submit(app_env).status_code == 200
    saved = dotenv_values(app_env.env_file)
    assert saved["ALLEGRO_CLIENT_ID"] == CLIENT_ID
    assert saved["ALLEGRO_CLIENT_SECRET"] == CLIENT_SECRET
    assert saved["MESSAGE"] == "line one\nline two"


def test_save_failure_is_safe_and_can_be_retried(app_env, monkeypatch):
    import api.allegro as allegro

    first_run(app_env, monkeypatch)
    env_file = app_env.env_file
    env_file.unlink()
    env_file.mkdir()
    response = submit(app_env)
    assert response.status_code == 503
    assert "client-secret" not in response.text
    assert allegro.CLIENT_ID == ""
    assert allegro.CLIENT_SECRET == ""
    assert request(app_env, "GET", "/api/setup/status").json()["configured"] is False
    env_file.rmdir()
    assert submit(app_env).status_code == 200


def test_saved_credentials_load_after_restart_even_with_stale_container_environment(app_env, monkeypatch):
    first_run(app_env, monkeypatch)
    assert submit(app_env).status_code == 200
    code = (
        "import main; import api.allegro as a; import os; "
        f"assert a.CLIENT_ID == {CLIENT_ID!r}; assert a.CLIENT_SECRET == {CLIENT_SECRET!r}; "
        f"assert os.environ['PACKING_ACCESS_TOKEN'] == {ACCESS_TOKEN!r}"
    )
    env = {**os.environ, "ALLEGRO_CLIENT_ID": "", "ALLEGRO_CLIENT_SECRET": "", "PACKING_ACCESS_TOKEN": ""}
    result = subprocess.run([sys.executable, "-c", code], cwd="backend", env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_startup_preserves_compose_resolved_unrelated_settings(app_env):
    with app_env.env_file.open("a") as handle:
        handle.write("PACKING_BASE_URL=http://localhost:3001\nALLEGRO_REDIRECT_URI=${PACKING_BASE_URL}/api/orders/auth/callback\n")
    env = {
        **os.environ,
        "ALLEGRO_REDIRECT_URI": "http://localhost:3001/api/orders/auth/callback",
        "PACKING_BASE_URL": "http://localhost:3001",
    }
    code = "import main; import api.allegro as a; assert a.REDIRECT_URI == 'http://localhost:3001/api/orders/auth/callback'"
    result = subprocess.run([sys.executable, "-c", code], cwd="backend", env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_write_failure_restores_previous_settings(app_env, monkeypatch):
    import configuration

    first_run(app_env, monkeypatch)
    before = app_env.env_file.read_bytes()
    real_fsync = os.fsync
    calls = 0

    def fail_first_sync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("Simulated disk error")
        real_fsync(descriptor)

    monkeypatch.setattr(configuration.os, "fsync", fail_first_sync)
    assert submit(app_env).status_code == 503
    assert app_env.env_file.read_bytes() == before
    assert request(app_env, "GET", "/api/setup/status").json()["configured"] is False
    assert submit(app_env).status_code == 200


def test_secret_with_quotes_backslashes_and_dollars_is_saved_literally(app_env, monkeypatch):
    import api.allegro as allegro

    first_run(app_env, monkeypatch)
    secret = "quote'backslash\\dollar${UNSET}#=+"
    response = submit(app_env, {"client_id": CLIENT_ID, "client_secret": secret})
    assert response.status_code == 200
    assert dotenv_values(app_env.env_file, interpolate=False)["ALLEGRO_CLIENT_SECRET"] == secret
    assert allegro.CLIENT_SECRET == secret
