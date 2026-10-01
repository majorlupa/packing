"""Regression tests for the queue workflow, the state file and the Allegro edges.

These are the tests that would have caught the review findings: a damaged state file
taking the whole API down, a second label request creating a second shipment, an
unvalidated settings body bricking a settings tab, and a rename requiring order_ids.
"""
import asyncio
import json
import threading

import httpx
import pytest

from conftest import sample_order

# ---------------------------------------------------------------- wiring


def test_ui_and_health_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/orders/").json() == []
    assert client.get("/api/orders/status").json()["ok"] is True


def test_unknown_order_is_404(client):
    assert client.post("/api/orders/nope/done").status_code == 404


# ---------------------------------------------------------------- queue workflow


def test_queue_workflow_end_to_end(app_env, client):
    app_env.write_state(app_env.default_state({
        "o-1": sample_order("o-1", "a-1"),
        "o-2": sample_order("o-2", "a-2"),
    }))

    created = client.post("/api/picking-lists", json={"name": "", "order_ids": ["o-1", "o-2"]})
    assert created.status_code == 200
    pl = created.json()
    assert pl["name"] == "Lista #1"

    statuses = {o["id"]: o["status"] for o in client.get("/api/orders/").json()}
    assert statuses == {"o-1": "picking", "o-2": "picking"}

    assert client.post(f"/api/picking-lists/{pl['id']}/start-packing").status_code == 200
    assert client.post("/api/orders/o-1/done").json() == {"status": "done"}
    assert client.post("/api/orders/o-2/done").status_code == 200

    archived = client.post("/api/orders/zakoncz-dzien").json()
    assert archived == {"archived": 2}
    assert client.get("/api/orders/").json() == []
    # the list referenced the archived orders — it must be gone, not left dangling
    assert client.get("/api/picking-lists").json() == []

    archive = client.get("/api/orders/archive").json()
    assert sorted(e["allegro_id"] for e in archive) == ["a-1", "a-2"]
    assert all(e["archived_at"] for e in archive)


def test_archive_tombstone_is_not_resynced(app_env, client, monkeypatch):
    """An archived order must not come back on the next sync."""
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({"o-1": sample_order("o-1", "a-1", status="done")}))
    client.post("/api/orders/zakoncz-dzien")

    from models.order import Order

    async def fake_fetch(limit=100):
        return [Order(**sample_order("o-new", "a-1"))]

    monkeypatch.setattr(allegro, "fetch_orders", fake_fetch)
    assert client.post("/api/orders/sync").json()["added"] == 0


def test_sync_adds_once_and_backfills(app_env, client, monkeypatch):
    import api.allegro as allegro
    from models.order import Order

    stale = sample_order("o-1", "a-1")
    stale["buyer_email"] = None  # older record missing a field added later
    app_env.write_state(app_env.default_state({"o-1": stale}))

    async def fake_fetch(limit=100):
        fresh = sample_order("o-1", "a-1")
        fresh["buyer_email"] = "nowy@example.com"
        return [Order(**fresh), Order(**sample_order("o-9", "a-9"))]

    monkeypatch.setattr(allegro, "fetch_orders", fake_fetch)

    first = client.post("/api/orders/sync").json()
    assert (first["added"], first["updated"]) == (1, 1)
    second = client.post("/api/orders/sync").json()
    assert (second["added"], second["updated"]) == (0, 0)
    assert client.get("/api/orders/").json()[0]["buyer_email"] in (None, "nowy@example.com")


def test_sync_without_authorization_is_401(app_env, client):
    import api.allegro as allegro

    response = client.post("/api/orders/sync")
    assert response.status_code == 401
    assert "Autoryzuj" in response.json()["detail"]


# ---------------------------------------------------------------- request contracts


def test_rename_needs_only_the_name(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    pl = client.post("/api/picking-lists", json={"name": "", "order_ids": ["o-1"]}).json()

    renamed = client.patch(f"/api/picking-lists/{pl['id']}", json={"name": "Priorytet"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Priorytet"
    assert renamed.json()["order_ids"] == ["o-1"]  # name change must not touch the orders


def test_rename_rejects_empty_name(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    pl = client.post("/api/picking-lists", json={"name": "", "order_ids": ["o-1"]}).json()
    assert client.patch(f"/api/picking-lists/{pl['id']}", json={"name": ""}).status_code == 422


def test_picking_list_needs_at_least_one_order(client):
    assert client.post("/api/picking-lists", json={"name": "x", "order_ids": []}).status_code == 422


def test_unknown_order_in_picking_list_is_404(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    response = client.post("/api/picking-lists", json={"name": "", "order_ids": ["o-1", "ghost"]})
    assert response.status_code == 404
    # nothing half-written: the counter must not have moved
    assert client.get("/api/picking-lists").json() == []


def test_reverted_order_is_removed_from_its_picking_list(app_env, client):
    """Reverting one order must not leave a stale reference that start-packing revives."""
    app_env.write_state(app_env.default_state({
        "o-1": sample_order("o-1", "a-1"),
        "o-2": sample_order("o-2", "a-2"),
    }))
    pl = client.post("/api/picking-lists", json={"name": "", "order_ids": ["o-1", "o-2"]}).json()

    assert client.post("/api/orders/o-2/revert-pending").status_code == 200
    lists = client.get("/api/picking-lists").json()
    assert lists[0]["order_ids"] == ["o-1"]

    assert client.post(f"/api/picking-lists/{pl['id']}/start-packing").status_code == 200
    statuses = {o["id"]: o["status"] for o in client.get("/api/orders/").json()}
    assert statuses == {"o-1": "packing", "o-2": "pending"}


def test_order_moved_to_a_new_picking_list_leaves_the_old_one(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    first = client.post("/api/picking-lists", json={"name": "A", "order_ids": ["o-1"]}).json()
    second = client.post("/api/picking-lists", json={"name": "B", "order_ids": ["o-1"]}).json()

    # The empty first list is dropped and the order points at the second one only.
    assert [pl["id"] for pl in client.get("/api/picking-lists").json()] == [second["id"]]
    assert client.get("/api/orders/").json()[0]["picking_list_id"] == second["id"]
    assert first["id"] != second["id"]

    # Reverting the whole second list still returns the order to pending.
    assert client.post(f"/api/picking-lists/{second['id']}/revert").status_code == 200
    assert client.get("/api/orders/").json()[0]["status"] == "pending"


# ---------------------------------------------------------------- settings


def test_duplicate_requested_orders_are_only_attached_once(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    response = client.post("/api/picking-lists", json={"order_ids": ["o-1", "o-1"]})
    assert response.status_code == 200
    assert response.json()["order_ids"] == ["o-1"]


def test_revert_removes_every_legacy_duplicate_reference(app_env, client):
    orders = {"o-1": sample_order(), "o-2": sample_order("o-2", "a-2")}
    state = app_env.default_state(orders)
    state["picking_lists"] = {
        "pl-1": {"id": "pl-1", "name": "Legacy", "order_ids": ["o-1", "o-1", "o-2"]},
        "pl-2": {"id": "pl-2", "name": "Empty after detach", "order_ids": ["o-1", "o-1"]},
    }
    app_env.write_state(state)
    assert client.post("/api/orders/o-1/revert-pending").status_code == 200
    lists = client.get("/api/picking-lists").json()
    assert [pl["id"] for pl in lists] == ["pl-1"]
    assert lists[0]["order_ids"] == ["o-2"]
    assert client.post("/api/picking-lists/pl-1/start-packing").status_code == 200
    statuses = {order["id"]: order["status"] for order in client.get("/api/orders/").json()}
    assert statuses == {"o-1": "pending", "o-2": "packing"}


def test_shipment_settings_reject_garbage_and_stay_readable(client):
    bad = client.post("/api/print/shipment-settings", json={"sender": "oops", "package": []})
    assert bad.status_code == 422

    good = client.get("/api/print/shipment-settings")
    assert good.status_code == 200
    assert good.json()["package"]["height"] == 15


def test_shipment_settings_roundtrip(client):
    payload = {
        "sender": {"name": "Weles", "street": "ul. Testowa 1", "postal_code": "00-001",
                   "city": "Warszawa", "country_code": "PL", "email": "a@b.pl", "phone": "500100200"},
        "package": {"type": "PACKAGE", "length": 25, "width": 18, "height": 12,
                    "weight": 2.5, "label_format": "PDF", "page_size": "A4"},
    }
    assert client.post("/api/print/shipment-settings", json=payload).status_code == 200
    saved = client.get("/api/print/shipment-settings").json()
    assert saved["package"]["page_size"] == "A4"
    assert saved["package"]["weight"] == 2.5
    assert saved["sender"]["city"] == "Warszawa"


def test_shipment_settings_reject_nonsense_dimensions(client):
    payload = {"package": {"length": -5, "weight": 0}}
    assert client.post("/api/print/shipment-settings", json=payload).status_code == 422


def test_invoice_settings_limits_free_text(client):
    payload = {
        "show_buyer_name": True, "show_buyer_address": True, "show_items": True, "show_price": True,
        "show_courier": True, "show_pickup_point": True, "show_allegro_id": True,
        "free_text": "x" * 161,
    }
    assert client.post("/api/print/invoice-settings", json=payload).status_code == 422


def test_settings_survive_a_hand_edited_file(app_env, client):
    """A hand-edited state.json with wrong shapes must not break the settings tab."""
    state = app_env.default_state()
    state["shipment_settings"] = {"sender": "oops", "package": []}
    state["invoice_settings"] = {"show_price": "yes", "unknown_key": 1}
    app_env.write_state(state)

    shipped = client.get("/api/print/shipment-settings")
    assert shipped.status_code == 200
    assert shipped.json()["sender"]["country_code"] == "PL"
    invoiced = client.get("/api/print/invoice-settings")
    assert invoiced.status_code == 200
    assert "unknown_key" not in invoiced.json()


# ---------------------------------------------------------------- state file health


def test_truncated_state_is_503_and_the_file_is_preserved(app_env, client):
    broken = '{"orders": {"o-1": {"id": "o-1"'
    app_env.state_file.write_text(broken, encoding="utf-8")

    response = client.get("/api/orders/")
    assert response.status_code == 503
    assert response.json()["state_ok"] is False
    assert app_env.state_file.read_text(encoding="utf-8") == broken  # never clobbered
    assert client.get("/health").json()["status"] == "degraded"


def test_corrupt_state_recovers_from_backup(app_env, client):
    good = app_env.default_state({"o-1": sample_order()})
    app_env.backup_file.write_text(json.dumps(good), encoding="utf-8")
    app_env.state_file.write_text("{not json", encoding="utf-8")

    orders = client.get("/api/orders/")
    assert orders.status_code == 200
    assert len(orders.json()) == 1

    status = client.get("/api/orders/status").json()
    assert status["ok"] is False
    assert "kopii zapasowej" in status["message"]
    # the unreadable file is kept aside, not deleted
    assert list(app_env.data_dir.glob("state.json.corrupt-*"))


def test_missing_state_file_starts_empty(client):
    assert client.get("/api/orders/").json() == []


def test_one_bad_record_is_quarantined_instead_of_500(app_env, client):
    broken = sample_order("o-2", "a-2")
    del broken["buyer_name"]
    app_env.write_state(app_env.default_state({"o-1": sample_order("o-1", "a-1"), "o-2": broken}))

    orders = client.get("/api/orders/")
    assert orders.status_code == 200
    assert [o["id"] for o in orders.json()] == ["o-1"]

    status = client.get("/api/orders/status").json()
    assert status["ok"] is False
    assert status["quarantined"] == 1
    # the bad record is not silently thrown away — it waits in quarantine…
    assert client.get("/api/picking-lists").status_code == 200
    persisted = json.loads(app_env.state_file.read_text(encoding="utf-8"))
    assert "quarantine" not in persisted  # a read must not rewrite the file
    # …and it is carried into the file by the next write
    assert client.post("/api/orders/o-1/done").status_code == 200
    persisted = json.loads(app_env.state_file.read_text(encoding="utf-8"))
    assert persisted["quarantine"][0]["id"] == "o-2"


def test_dangling_picking_list_reference_is_repaired(app_env, client):
    state = app_env.default_state({"o-1": sample_order("o-1", "a-1")})
    state["picking_lists"] = {
        "pl-1": {"id": "pl-1", "name": "Lista", "order_ids": ["o-1", "ghost"]},
        "pl-2": {"id": "pl-2", "name": "Pusta", "order_ids": ["ghost"]},
    }
    app_env.write_state(state)

    lists = client.get("/api/picking-lists").json()
    assert [pl["id"] for pl in lists] == ["pl-1"]
    assert lists[0]["order_ids"] == ["o-1"]


def test_writes_are_atomic_and_keep_a_backup(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))

    assert client.post("/api/orders/o-1/done").status_code == 200

    assert not list(app_env.data_dir.glob("*.tmp"))
    assert app_env.backup_file.exists()
    assert json.loads(app_env.backup_file.read_text(encoding="utf-8"))["orders"]["o-1"]["status"] == "pending"
    assert json.loads(app_env.state_file.read_text(encoding="utf-8"))["orders"]["o-1"]["status"] == "done"


def test_concurrent_writes_lose_nothing(app_env):
    """Many threads writing different orders: every write must survive (lock + one load/save)."""
    store = app_env.store
    app_env.write_state(app_env.default_state({}))
    from models.order import Order

    orders = [Order(**sample_order(f"o-{i}", f"a-{i}")) for i in range(20)]
    barrier = threading.Barrier(4)

    def worker(chunk):
        barrier.wait()
        for order in chunk:
            store.save_order(order)

    threads = [threading.Thread(target=worker, args=(orders[i::4],)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    saved = json.loads(app_env.state_file.read_text(encoding="utf-8"))["orders"]
    assert sorted(saved) == sorted(o.id for o in orders)


def test_picking_list_numbers_do_not_repeat_under_concurrency(app_env):
    store = app_env.store
    app_env.write_state(app_env.default_state({}))
    numbers = []
    lock = threading.Lock()

    def grab():
        number = store.next_picking_list_number()
        with lock:
            numbers.append(number)

    threads = [threading.Thread(target=grab) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(numbers) == list(range(1, 13))


# ---------------------------------------------------------------- labels / shipments


def _fake_allegro(monkeypatch, order):
    """Patch the Allegro client so label tests never touch the network."""
    import api.allegro as allegro

    calls = {"create": 0, "download": 0}

    async def fake_create(order_arg, sender, package):
        calls["create"] += 1
        await asyncio.sleep(0.05)  # widen the window a double click would exploit
        calls["last_package"] = package
        return "shipment-uuid"

    async def fake_download(shipment_id, page_size="A6"):
        calls["download"] += 1
        calls["page_size"] = page_size
        return b"%PDF-1.4 fake"

    monkeypatch.setattr(allegro, "create_shipment", fake_create)
    monkeypatch.setattr(allegro, "download_label", fake_download)
    return calls


def test_label_without_authorization_is_401_not_404(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    assert client.get("/api/print/orders/o-1/label").status_code == 401


def test_label_upstream_failure_is_502(app_env, client, monkeypatch):
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    allegro._token = "test-token"

    async def boom(order, sender, package):
        raise allegro.AllegroError("Allegro create shipment 500: nope")

    monkeypatch.setattr(allegro, "create_shipment", boom)
    response = client.get("/api/print/orders/o-1/label")
    assert response.status_code == 502
    assert "nope" in response.json()["detail"]


def test_two_parallel_label_requests_create_one_shipment(app_env, monkeypatch):
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    allegro._token = "test-token"
    calls = _fake_allegro(monkeypatch, None)

    async def go():
        transport = httpx.ASGITransport(app=app_env.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            return await asyncio.gather(
                c.get(
                    "/api/print/orders/o-1/label",
                    headers={"Authorization": "Bearer test-access-token-for-packing-api-2026"},
                ),
                c.get(
                    "/api/print/orders/o-1/label",
                    headers={"Authorization": "Bearer test-access-token-for-packing-api-2026"},
                ),
            )

    responses = asyncio.run(go())
    assert [r.status_code for r in responses] == [200, 200]
    assert calls["create"] == 1
    assert calls["download"] == 2

    order = json.loads(app_env.state_file.read_text(encoding="utf-8"))["orders"]["o-1"]
    assert order["shipment_id"] == "shipment-uuid"


def test_label_uses_saved_package_settings_when_no_override(app_env, client, monkeypatch):
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    allegro._token = "test-token"
    calls = _fake_allegro(monkeypatch, None)
    client.post("/api/print/shipment-settings", json={"package": {
        "length": 33, "width": 22, "height": 11, "weight": 3.0, "page_size": "A4"}})

    assert client.get("/api/print/orders/o-1/label").status_code == 200
    assert calls["last_package"]["length"] == 33
    assert calls["last_package"]["height"] == 11
    assert calls["page_size"] == "A4"


def test_label_query_params_override_settings(app_env, client, monkeypatch):
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    allegro._token = "test-token"
    calls = _fake_allegro(monkeypatch, None)

    assert client.get("/api/print/orders/o-1/label?length=40&width=30&height=20&weight=5").status_code == 200
    assert calls["last_package"]["length"] == 40
    assert calls["last_package"]["weight"] == 5


def test_label_rejects_bad_dimensions(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    assert client.get("/api/print/orders/o-1/label?length=0").status_code == 422


def test_repeated_label_request_reuses_the_shipment(app_env, client, monkeypatch):
    import api.allegro as allegro

    app_env.write_state(app_env.default_state({"o-1": sample_order(shipment_id="already-there")}))
    allegro._token = "test-token"
    calls = _fake_allegro(monkeypatch, None)

    assert client.get("/api/print/orders/o-1/label").status_code == 200
    assert calls["create"] == 0
    assert calls["download"] == 1


# ---------------------------------------------------------------- documents


def test_invoice_html_renders(client, app_env):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    response = client.get("/api/print/orders/o-1/invoice")
    assert response.status_code == 200
    assert "Jan Kowalski" in response.text


def test_custom_doc_upload_rejects_non_pdf(client):
    files = {"file": ("notes.txt", b"hello", "text/plain")}
    assert client.post("/api/print/custom-doc", files=files).status_code == 400
    files = {"file": ("fake.pdf", b"not really a pdf", "application/pdf")}
    assert client.post("/api/print/custom-doc", files=files).status_code == 400


def test_custom_doc_upload_and_delete(app_env, client):
    files = {"file": ("doc.pdf", b"%PDF-1.4 minimal", "application/pdf")}
    assert client.post("/api/print/custom-doc", files=files).status_code == 200
    assert client.get("/api/print/custom-doc/info").json()["available"] is True
    assert client.get("/api/print/custom-doc").content.startswith(b"%PDF-")
    assert client.delete("/api/print/custom-doc").status_code == 200
    assert client.get("/api/print/custom-doc/info").json()["available"] is False


def test_missing_order_invoice_is_404(client):
    assert client.get("/api/print/orders/ghost/invoice").status_code == 404
