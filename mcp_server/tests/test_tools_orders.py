"""Queue, order and picking-list tools against a mocked API."""
import asyncio

import pytest
from helpers import FakeAPI, make_order

from mcp_server.client import PackingError


def test_list_orders_reports_queue_counts_and_filters_by_status():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[
        make_order(id="o1", status="pending"),
        make_order(id="o2", status="packing", allegro_id="ALLEGRO-2"),
        make_order(id="o3", status="done", allegro_id="ALLEGRO-3"),
    ])
    tools = api.tools()

    everything = asyncio.run(tools.list_orders())
    assert everything["count"] == 3
    assert everything["queue_counts"] == {"pending": 1, "picking": 0, "packing": 1, "done": 1}

    packing = asyncio.run(tools.list_orders(status="packing"))
    assert packing["count"] == 1
    assert packing["orders"][0]["id"] == "o2"


def test_list_orders_filters_by_courier_and_search():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[
        make_order(id="o1", buyer_name="Jan Kowalski", allegro_id="AAA-1"),
        make_order(id="o2", buyer_name="Anna Nowak", allegro_id="BBB-2",
                   courier="Allegro Kurier DPD", delivery_type="courier"),
    ])
    tools = api.tools()

    locker = asyncio.run(tools.list_orders(courier="inpost_locker"))
    assert [order["id"] for order in locker["orders"]] == ["o1"]

    dpd = asyncio.run(tools.list_orders(courier="dpd"))
    assert [order["id"] for order in dpd["orders"]] == ["o2"]

    by_buyer = asyncio.run(tools.list_orders(search="anna"))
    assert [order["id"] for order in by_buyer["orders"]] == ["o2"]

    by_id = asyncio.run(tools.list_orders(search="AAA-1"))
    assert [order["id"] for order in by_id["orders"]] == ["o1"]


def test_get_order_returns_the_record_or_explains_that_it_is_gone():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1")])
    tools = api.tools()

    assert asyncio.run(tools.get_order("o1"))["allegro_id"] == "ALLEGRO-1"
    with pytest.raises(PackingError, match="not in the queue"):
        asyncio.run(tools.get_order("ghost"))


@pytest.mark.parametrize(
    ("tool_name", "action"),
    [("mark_order_done", "done"), ("undo_order_done", "undo-done"),
     ("revert_order_to_pending", "revert-pending")],
)
def test_status_actions_call_their_routes(tool_name, action):
    api = FakeAPI()
    api.add("POST", f"/api/orders/o1/{action}", json_body={"status": action})
    tools = api.tools()
    assert asyncio.run(getattr(tools, tool_name)("o1")) == {"status": action}
    assert api.calls() == [("POST", f"/api/orders/o1/{action}")]


def test_set_parcel_size_sends_the_documented_body():
    api = FakeAPI()
    api.add("PATCH", "/api/orders/o1/parcel-size", json_body={"parcel_size": "B"})
    tools = api.tools()
    assert asyncio.run(tools.set_parcel_size("o1", "B")) == {"parcel_size": "B"}
    assert api.json_body(api.last()) == {"parcel_size": "B"}


def test_picking_list_tools_cover_the_sidebar_actions():
    api = FakeAPI()
    api.add("GET", "/api/picking-lists", json_body=[{"id": "pl1", "name": "Lista 1", "order_ids": ["o1"]}])
    api.add("POST", "/api/picking-lists", json_body={"id": "pl2", "name": "Lista 2", "order_ids": ["o1"]})
    api.add("PATCH", "/api/picking-lists/pl1", json_body={"id": "pl1", "name": "Rano", "order_ids": ["o1"]})
    api.add("POST", "/api/picking-lists/pl1/revert", json_body={"status": "ok"})
    api.add("POST", "/api/picking-lists/pl1/start-packing", json_body={"status": "ok", "order_ids": ["o1"]})
    tools = api.tools()

    listing = asyncio.run(tools.list_picking_lists())
    assert listing["count"] == 1

    created = asyncio.run(tools.create_picking_list(["o1", "o1"], ""))
    assert created["id"] == "pl2"
    assert api.json_body(api.last()) == {"name": "", "order_ids": ["o1", "o1"]}

    assert asyncio.run(tools.rename_picking_list("pl1", "  Rano "))["name"] == "Rano"
    assert api.json_body(api.last()) == {"name": "Rano"}

    assert asyncio.run(tools.revert_picking_list("pl1")) == {"status": "ok"}
    started = asyncio.run(tools.start_packing("pl1"))
    assert started["order_ids"] == ["o1"]


def test_create_and_rename_validate_input_before_calling_the_api():
    api = FakeAPI()
    tools = api.tools()
    with pytest.raises(PackingError, match="at least one order id"):
        asyncio.run(tools.create_picking_list([]))
    with pytest.raises(PackingError, match="must not be empty"):
        asyncio.run(tools.rename_picking_list("pl1", "   "))
    assert api.requests == []


def test_picking_list_contents_are_aggregated_like_the_printed_list():
    api = FakeAPI()
    api.add("GET", "/api/picking-lists", json_body=[{"id": "pl1", "name": "Lista 1", "order_ids": ["o1", "o2"]}])
    api.add("GET", "/api/orders/", json_body=[
        make_order(id="o1", items=[{"name": "Wkrętak", "quantity": 2, "unit_price": 10.0}]),
        make_order(id="o2", items=[
            {"name": "Wkrętak", "quantity": 1, "unit_price": 10.0},
            {"name": "Kabel", "quantity": 3, "unit_price": 5.0},
        ]),
        make_order(id="o3", items=[{"name": "Inny", "quantity": 9, "unit_price": 1.0}]),
    ])
    tools = api.tools()

    contents = asyncio.run(tools.get_picking_list("pl1"))
    assert contents["order_count"] == 2
    assert contents["items"] == [{"name": "Kabel", "quantity": 3}, {"name": "Wkrętak", "quantity": 3}]
    assert [order["id"] for order in contents["orders"]] == ["o1", "o2"]

    with pytest.raises(PackingError, match="does not exist"):
        asyncio.run(tools.get_picking_list("ghost"))


def test_sync_end_of_day_and_archive_tools():
    api = FakeAPI()
    api.add("POST", "/api/orders/sync", json_body={"added": 2, "updated": 1, "total": 7})
    api.add("POST", "/api/orders/seed-mock", json_body={"added": 3, "total": 10})
    api.add("POST", "/api/orders/zakoncz-dzien", json_body={"archived": 4})
    api.add("GET", "/api/orders/archive", json_body=[{"allegro_id": "A1", "archived_at": "2026-10-01T10:00:00+00:00"}])
    tools = api.tools()

    assert asyncio.run(tools.sync_orders()) == {"added": 2, "updated": 1, "total": 7}
    assert asyncio.run(tools.seed_mock_orders())["added"] == 3
    assert asyncio.run(tools.finish_day()) == {"archived": 4}
    archive = asyncio.run(tools.list_archive())
    assert archive["count"] == 1
    assert archive["archive"][0]["allegro_id"] == "A1"


def test_state_health_and_allegro_authorization_tools():
    api = FakeAPI()
    api.add("GET", "/health", json_body={"status": "ok", "state": {"ok": True}})
    api.add("GET", "/api/orders/status", json_body={"ok": True, "dry_run": False})
    api.add("GET", "/api/orders/auth/status", json_body={"authorized": True})
    api.add("GET", "/api/orders/auth/url", json_body={"url": "https://allegro.test/auth?state=x"})
    tools = api.tools()

    assert asyncio.run(tools.get_app_health())["status"] == "ok"
    assert asyncio.run(tools.get_state_status())["dry_run"] is False
    assert asyncio.run(tools.get_allegro_auth_status()) == {"authorized": True}
    assert asyncio.run(tools.get_allegro_auth_url())["url"].startswith("https://allegro.test/")
