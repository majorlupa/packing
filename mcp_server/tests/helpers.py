"""Shared helpers: a fake Packing API behind httpx.MockTransport.

No network is used and no real printer is touched.

This module is deliberately not called ``conftest.py``: the repository has a
second test suite under ``backend/tests`` with its own conftest, and running both
suites in one pytest invocation would otherwise share a single top-level
``conftest`` module name.
"""
import json
from collections.abc import Callable

import httpx

from mcp_server.client import PackingClient
from mcp_server.config import Settings
from mcp_server.tools import PackingTools

PDF_BYTES = b"%PDF-1.4\n% fake label\n%%EOF\n"


def make_order(**overrides) -> dict:
    order = {
        "id": "order-1",
        "allegro_id": "ALLEGRO-1",
        "buyer_name": "Jan Kowalski",
        "buyer_address": "ul. Marszałkowska 10, 00-001 Warszawa",
        "items": [
            {"name": "Zestaw wkrętaków", "quantity": 2, "unit_price": 69.9},
            {"name": "Kabel USB-C", "quantity": 1, "unit_price": 24.5},
        ],
        "status": "pending",
        "picking_list_id": None,
        "courier": "Allegro Paczkomaty InPost",
        "delivery_type": "inpost_locker",
        "pickup_point": "WAW01M",
        "tracking_number": None,
        "shipment_id": None,
        "parcel_size": None,
    }
    order.update(overrides)
    return order


class FakeAPI:
    """Records every request and answers the routes a test registered."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[httpx.Request] = []

    def add(
        self,
        method: str,
        path: str,
        *,
        json_body: object = None,
        status: int = 200,
        content: bytes | None = None,
        content_type: str = "application/json",
    ) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            if content is not None:
                return httpx.Response(status, content=content, headers={"content-type": content_type})
            if json_body is None:
                return httpx.Response(status, json=None)
            return httpx.Response(status, json=json_body, headers={"content-type": content_type})

        self.routes[(method, path)] = handler

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get((request.method, request.url.path))
        if route is None:
            return httpx.Response(404, json={"detail": f"No fake route for {request.method} {request.url.path}"})
        return route(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def client(self, **settings_overrides) -> PackingClient:
        values = {
            "api_url": "http://packing.test",
            "access_token": "test-token-not-a-secret",
            "language": "en",
        }
        values.update(settings_overrides)
        return PackingClient(Settings(**values), transport=self.transport)

    def tools(self, **settings_overrides) -> PackingTools:
        client = self.client(**settings_overrides)
        return PackingTools(client, client.settings)

    def last(self, method: str | None = None) -> httpx.Request:
        if method is None:
            return self.requests[-1]
        for request in reversed(self.requests):
            if request.method == method:
                return request
        raise AssertionError(f"No {method} request recorded")

    def calls(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]

    def json_body(self, request: httpx.Request) -> dict:
        return json.loads(request.content.decode("utf-8"))
