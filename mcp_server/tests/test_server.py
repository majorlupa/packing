"""Server wiring, MCP round trip, interval sync and the CLI."""
import asyncio
import json
import logging

import httpx
import pytest
from helpers import FakeAPI, make_order
from mcp.server.mcpserver.exceptions import ToolError

import mcp_server.__main__ as cli
from mcp_server.client import PackingError
from mcp_server.config import Settings
from mcp_server.server import TOOL_NAMES, create_server
from mcp_server.sync_loop import run_loop


def _settings(**overrides) -> Settings:
    values = {"api_url": "http://packing.test", "access_token": "test-token-not-a-secret"}
    values.update(overrides)
    return Settings(**values)


def test_every_tool_is_registered_with_an_actionable_description():
    server = create_server(_settings())
    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == list(TOOL_NAMES)
    for tool in tools:
        description = tool.description or ""
        assert len(description) > 60, tool.name
        assert "/api/" in description or "/health" in description, tool.name


def test_tool_names_are_stable_and_unique():
    assert len(TOOL_NAMES) == len(set(TOOL_NAMES))
    for name in TOOL_NAMES:
        assert name.islower() and " " not in name


def test_mcp_round_trip_returns_json_content():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1", buyer_name="Jan Kowalski")])
    server = create_server(_settings(), client=api.client())

    result = asyncio.run(server.call_tool("list_orders", {"status": "pending"}))
    # mcp 2.x returns a CallToolResult instead of a bare sequence of content blocks.
    assert len(result.content) == 1
    payload = json.loads(result.content[0].text)
    assert payload["count"] == 1
    assert payload["orders"][0]["id"] == "o1"


def test_mcp_tool_errors_reach_the_client_with_the_app_message():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[])
    server = create_server(_settings(), client=api.client())

    with pytest.raises(ToolError, match="not in the queue"):
        asyncio.run(server.call_tool("get_order", {"order_id": "ghost"}))


def test_tool_errors_carry_the_app_message_over_the_wire():
    # mcp 2.x only forwards ToolError messages to the model; anything else becomes
    # "Error executing tool <name>", so the app's own text has to survive a real call.
    from mcp.client import Client

    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[])
    server = create_server(_settings(), client=api.client())

    async def call():
        async with Client(server) as client:
            return await client.call_tool("get_order", {"order_id": "ghost"})

    result = asyncio.run(call())
    assert result.is_error is True
    assert "is not in the queue" in result.content[0].text


def test_sync_loop_runs_the_requested_number_of_syncs():
    api = FakeAPI()
    api.add("POST", "/api/orders/sync", json_body={"added": 1, "updated": 0, "total": 1})
    code = asyncio.run(run_loop(api.client(), interval=0.01, max_iterations=2))
    assert code == 0
    assert api.calls().count(("POST", "/api/orders/sync")) == 2


def test_sync_loop_keeps_running_after_a_failed_tick():
    api = FakeAPI()
    responses = [
        httpx.Response(502, json={"detail": {"code": "allegro.request_failed",
                                             "message": "Allegro is down."}}),
        httpx.Response(200, json={"added": 0, "updated": 0, "total": 0}),
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    api.routes[("POST", "/api/orders/sync")] = handler
    code = asyncio.run(run_loop(api.client(), interval=0.01, max_iterations=2))
    assert code == 0
    assert responses == []


def test_sync_loop_rejects_a_non_positive_interval():
    api = FakeAPI()
    with pytest.raises(ValueError, match="greater than zero"):
        asyncio.run(run_loop(api.client(), interval=0))


def test_sync_loop_run_is_logged(caplog):
    api = FakeAPI()
    api.add("POST", "/api/orders/sync", json_body={"added": 2, "updated": 1, "total": 9})
    with caplog.at_level(logging.INFO, logger="packing_mcp.sync"):
        asyncio.run(run_loop(api.client(), interval=0.01, max_iterations=1))
    assert "added=2" in caplog.text
    assert "test-token-not-a-secret" not in caplog.text


def test_cli_defaults_to_serve_on_stdio():
    args = cli.build_parser().parse_args([])
    assert args.command is None
    assert args.log_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_cli_without_subcommand_starts_stdio(monkeypatch):
    transports = []
    monkeypatch.setattr("mcp.server.mcpserver.MCPServer.run",
                        lambda self, *, transport: transports.append(transport))
    assert cli.main([]) == 0
    assert transports == ["stdio"]


def test_cli_streamable_http_passes_host_and_port_to_run(monkeypatch):
    monkeypatch.delenv("PACKING_MCP_HOST", raising=False)
    monkeypatch.delenv("PACKING_MCP_PORT", raising=False)
    calls = []
    monkeypatch.setattr("mcp.server.mcpserver.MCPServer.run",
                        lambda self, **kwargs: calls.append(kwargs))
    assert cli.main(["serve", "--transport", "streamable-http", "--port", "9000"]) == 0
    assert calls == [{"transport": "streamable-http", "host": "127.0.0.1", "port": 9000}]


def test_cli_parses_streamable_http_and_sync_loop():
    parser = cli.build_parser()
    http_args = parser.parse_args(["serve", "--transport", "streamable-http", "--port", "9000"])
    assert http_args.transport == "streamable-http"
    assert http_args.port == 9000

    loop_args = parser.parse_args(["sync-loop", "--interval", "30", "--iterations", "2"])
    assert loop_args.command == "sync-loop"
    assert loop_args.interval == 30
    assert loop_args.iterations == 2


def test_cli_rejects_invalid_configuration(monkeypatch):
    monkeypatch.setenv("PACKING_LANGUAGE", "de")
    assert cli.main(["sync-once"]) == 2


def test_cli_sync_once_returns_zero_on_success(monkeypatch):
    calls = []

    async def fake_sync(client):
        calls.append(client)
        return {"added": 1}

    monkeypatch.setattr(cli, "PackingClient", lambda settings: object())
    monkeypatch.setattr(cli, "sync_once", fake_sync)
    assert cli.main(["sync-once"]) == 0
    assert len(calls) == 1


def test_cli_sync_once_reports_a_failure(monkeypatch):
    async def failing_sync(client):
        raise PackingError("Allegro sync failed.")

    monkeypatch.setattr(cli, "PackingClient", lambda settings: object())
    monkeypatch.setattr(cli, "sync_once", failing_sync)
    assert cli.main(["sync-once"]) == 1


def test_cli_sync_loop_rejects_bad_interval(monkeypatch):
    monkeypatch.setattr(cli, "PackingClient", lambda settings: object())
    assert cli.main(["sync-loop", "--interval", "0"]) == 2
    assert cli.main(["sync-loop", "--iterations", "0"]) == 2
