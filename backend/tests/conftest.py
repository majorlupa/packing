"""Shared fixtures: boot the app with its data dir and .env redirected into a tmp dir."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

PACKAGE_MODULES = ("store", "main", "api", "api.allegro", "routes")


def sample_order(order_id="o-1", allegro_id="a-1", **overrides):
    data = {
        "id": order_id,
        "allegro_id": allegro_id,
        "buyer_name": "Jan Kowalski",
        "buyer_address": "ul. Testowa 1 00-001 Warszawa",
        "items": [{"name": "Wiertarka", "quantity": 2, "unit_price": 49.99}],
        "status": "pending",
        "picking_list_id": None,
        "courier": "Kurier",
        "pickup_point": None,
        "tracking_number": None,
        "buyer_email": "jan@example.com",
        "buyer_phone": "500100200",
        "buyer_street": "ul. Testowa 1",
        "buyer_postal_code": "00-001",
        "buyer_city": "Warszawa",
        "buyer_country": "PL",
        "delivery_method_id": "dm-1",
        "shipment_id": None,
    }
    data.update(overrides)
    return data


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """Fresh app instance per test, with data/ and .env pointed at tmp_path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("ALLEGRO_CLIENT_ID=test\nALLEGRO_CLIENT_SECRET=test\n", encoding="utf-8")

    monkeypatch.setenv("PACKING_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PACKING_ENV_FILE", str(env_file))

    for name in list(sys.modules):
        if name in PACKAGE_MODULES or name.startswith(("api.", "routes.")):
            del sys.modules[name]

    import store  # noqa: E402
    import main  # noqa: E402

    def write_state(state):
        (data_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

    def default_state(orders=None):
        return {
            "orders": orders or {},
            "picking_lists": {},
            "picking_list_counter": 0,
            "invoice_settings": {},
            "shipment_settings": {},
            "archive": [],
        }

    return SimpleNamespace(
        app=main.app,
        store=store,
        data_dir=data_dir,
        env_file=env_file,
        state_file=data_dir / "state.json",
        backup_file=data_dir / "state.json.bak",
        write_state=write_state,
        default_state=default_state,
    )


@pytest.fixture()
def client(app_env):
    """Sync wrapper around an ASGI client so tests stay readable."""
    import asyncio

    import httpx

    class Client:
        def request(self, method, url, **kwargs):
            async def go():
                transport = httpx.ASGITransport(app=app_env.app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                    return await c.request(method, url, **kwargs)

            return asyncio.run(go())

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

    return Client()
