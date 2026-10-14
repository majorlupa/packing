"""Picking-list names have the same bounds on creation and rename."""

import pytest
from conftest import sample_order


@pytest.mark.parametrize("operation", ["create", "rename"])
def test_oversized_name_rejected_without_changing_queue(app_env, client, operation):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    created = client.post("/api/picking-lists", json={"name": "Existing", "order_ids": ["o-1"]})
    assert created.status_code == 200
    before = app_env.state_file.read_bytes()
    payload = {"name": "ą" * 121}

    if operation == "create":
        response = client.post("/api/picking-lists", json={**payload, "order_ids": ["o-1"]})
    else:
        response = client.patch(f"/api/picking-lists/{created.json()['id']}", json=payload)

    assert response.status_code == 422
    assert app_env.state_file.read_bytes() == before
    assert client.get("/api/picking-lists").json() == [created.json()]
    order = client.get("/api/orders/").json()[0]
    assert order["status"] == "picking"
    assert order["picking_list_id"] == created.json()["id"]


@pytest.mark.parametrize("name_fields", [{}, {"name": ""}, {"name": "ą" * 120}])
def test_create_accepts_default_and_boundary_names(app_env, client, name_fields):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    response = client.post("/api/picking-lists", json={**name_fields, "order_ids": ["o-1"]})
    assert response.status_code == 200
    expected = name_fields.get("name") or "Lista #1"
    assert response.json()["name"] == expected
    assert client.get("/api/picking-lists").json()[0]["name"] == expected


def test_rename_accepts_boundary_name(app_env, client):
    app_env.write_state(app_env.default_state({"o-1": sample_order()}))
    created = client.post("/api/picking-lists", json={"order_ids": ["o-1"]}).json()
    response = client.patch(f"/api/picking-lists/{created['id']}", json={"name": "ą" * 120})
    assert response.status_code == 200
    assert response.json()["name"] == "ą" * 120
    assert response.json()["order_ids"] == ["o-1"]
    assert client.get("/api/picking-lists").json()[0]["name"] == "ą" * 120
