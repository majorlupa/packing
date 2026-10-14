"""Blocking route work runs in workers; overlapping OAuth flows stay independent."""
import asyncio
import inspect
import threading
from urllib.parse import parse_qs, urlparse

import httpx
import pytest


@pytest.mark.parametrize("rejected", [False, True])
def test_two_concurrent_oauth_flows(app_env, monkeypatch, rejected):
    import api.allegro as allegro
    import routes.orders as orders

    exchanged = []

    async def exchange(code):
        await asyncio.sleep(0)
        exchanged.append(code)

    monkeypatch.setattr(allegro, "exchange_code", exchange)

    async def flows():
        transport = httpx.ASGITransport(app=app_env.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            starts = await asyncio.gather(*(
                client.get("/api/orders/auth/url", headers={
                    "Authorization": "Bearer test-access-token-for-packing-api-2026",
                    "Accept-Language": language,
                })
                for language in ("pl", "en")
            ))
            assert [response.status_code for response in starts] == [200, 200]
            states = [parse_qs(urlparse(response.json()["url"]).query)["state"][0] for response in starts]
            assert states[0] != states[1]
            params = [
                {"state": state, "error": "access_denied"} if rejected else {"state": state, "code": language}
                for state, language in zip(states, ("pl", "en"), strict=False)
            ]
            responses = await asyncio.gather(*(
                client.get("/api/orders/auth/callback", params=flow, headers={"Accept-Language": "en"})
                for flow in params
            ))
            if rejected:
                assert [response.status_code for response in responses] == [400, 400]
                for response, language in zip(responses, ("pl", "en"), strict=False):
                    assert f'<html lang="{language}">' in response.text
                assert exchanged == []
            else:
                assert [response.status_code for response in responses] == [307, 307]
                assert sorted(exchanged) == ["en", "pl"]
            assert orders._oauth_states == {}
            replays = await asyncio.gather(*(
                client.get("/api/orders/auth/callback", params={"state": state, "code": "replay"})
                for state in states
            ))
            assert [response.status_code for response in replays] == [400, 400]
            assert "replay" not in exchanged

    asyncio.run(flows())


def test_routes_without_await_are_sync(app_env):
    import ast

    from fastapi.routing import APIRoute

    for route in app_env.app.routes:
        if isinstance(route, APIRoute) and inspect.iscoroutinefunction(route.endpoint):
            tree = ast.parse(inspect.getsource(route.endpoint))
            assert any(
                isinstance(node, (ast.Await, ast.AsyncWith, ast.AsyncFor)) for node in ast.walk(tree)
            ), route.path


def test_upload_pdf_processing_runs_in_worker(app_env, monkeypatch):
    import routes.print_routes as printing

    async def upload():
        loop_thread = threading.get_ident()
        calls = []

        def save(payload):
            calls.append((payload, threading.get_ident()))
            return {"status": "uploaded"}

        monkeypatch.setattr(printing, "_save_custom_doc", save)
        transport = httpx.ASGITransport(app=app_env.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/print/custom-doc",
                headers={"Authorization": "Bearer test-access-token-for-packing-api-2026"},
                files={"file": ("doc.pdf", b"%PDF-test", "application/pdf")},
            )
        assert response.status_code == 200
        assert response.json() == {"status": "uploaded"}
        assert len(calls) == 1
        assert calls[0][0] == b"%PDF-test"
        assert calls[0][1] != loop_thread

    asyncio.run(upload())
