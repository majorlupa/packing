"""Recovery must handle invalid state shapes, not only invalid JSON syntax."""
import json

import pytest
from conftest import sample_order


@pytest.mark.parametrize("broken", ["[]", "null", '"oops"', "42", "true"])
def test_non_object_state_recovers_from_backup(app_env, client, broken):
    backup = json.dumps(app_env.default_state({"o-1": sample_order()}))
    app_env.backup_file.write_text(backup, encoding="utf-8")
    app_env.state_file.write_text(broken, encoding="utf-8")

    response = client.get("/api/orders/")
    assert response.status_code == 200
    assert [order["id"] for order in response.json()] == ["o-1"]
    preserved = list(app_env.data_dir.glob("state.json.corrupt-*"))
    assert len(preserved) == 1
    assert preserved[0].read_text(encoding="utf-8") == broken
    assert app_env.backup_file.read_text(encoding="utf-8") == backup
    assert client.get("/api/orders/status").json()["ok"] is False

    # A subsequent transaction must use the recovered orders, not start empty.
    assert client.post("/api/orders/o-1/done").status_code == 200
    persisted = json.loads(app_env.state_file.read_text(encoding="utf-8"))
    assert persisted["orders"]["o-1"]["status"] == "done"
    assert preserved[0].read_text(encoding="utf-8") == broken
    assert app_env.backup_file.read_text(encoding="utf-8") == backup


def test_non_object_state_without_backup_is_preserved(app_env, client):
    app_env.state_file.write_text("[]", encoding="utf-8")

    response = client.get("/api/orders/")
    assert response.status_code == 503
    assert response.json()["state_ok"] is False
    assert app_env.state_file.read_text(encoding="utf-8") == "[]"
    assert not list(app_env.data_dir.glob("state.json.corrupt-*"))
    assert client.get("/health").json()["status"] == "degraded"


@pytest.mark.parametrize("backup", ["[]", "{not json"])
def test_non_object_state_with_invalid_backup_is_503(app_env, client, backup):
    app_env.state_file.write_text("null", encoding="utf-8")
    app_env.backup_file.write_text(backup, encoding="utf-8")

    response = client.get("/api/orders/", headers={"Accept-Language": "en"})
    assert response.status_code == 503
    assert response.json()["state_ok"] is False
    assert "backup" in response.json()["detail"]
    preserved = list(app_env.data_dir.glob("state.json.corrupt-*"))
    assert len(preserved) == 1
    assert preserved[0].read_text(encoding="utf-8") == "null"
    assert app_env.backup_file.read_text(encoding="utf-8") == backup
    assert client.get("/health").json()["status"] == "degraded"
