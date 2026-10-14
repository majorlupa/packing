import copy
from datetime import datetime
from uuid import UUID

import pytest

BASE = "/api/print/document-templates"


def export_data(*templates):
    return {"format": "packing.document-templates", "version": 1,
            "exported_at": "2026-10-14T12:00:00+00:00", "templates": list(templates)}


def template(name="Imported", **changes):
    return {"id": "untrusted", "name": name, "blocks": [{"type": "text", "text": "Hello {{buyer.name}}"}],
            **changes}


def post(client, data, mode="rename", **kwargs):
    return client.post(BASE + "/import", json={"data": data, "on_conflict": mode}, **kwargs)


def test_export_single_all_and_missing(app_env, client):
    settings = app_env.store.get_document_settings()
    settings["templates"].append(template("Other", id="other"))
    app_env.store.save_document_settings(settings)
    before = app_env.state_file.read_bytes()
    for query, filename, count in [("", "packing-templates.json", 2),
                                   ("?template_id=other", "packing-template-other.json", 1)]:
        response = client.get(BASE + "/export" + query)
        assert response.status_code == 200
        assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        assert set(data) == {"format", "version", "exported_at", "templates"}
        assert data["format"] == "packing.document-templates" and data["version"] == 1
        assert datetime.fromisoformat(data["exported_at"]).tzinfo is not None
        assert len(data["templates"]) == count
        assert all(set(item) == {"id", "name", "blocks"} for item in data["templates"])
    assert client.get(BASE + "/export?template_id=missing").status_code == 404
    assert app_env.state_file.read_bytes() == before


def test_round_trip_rename_preserves_active_and_uses_fresh_ids(app_env, client):
    original = app_env.store.get_document_settings()
    data = client.get(BASE + "/export").json()
    response = post(client, data)
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"settings", "imported"}
    saved = result["settings"]
    assert saved == app_env.store.get_document_settings()
    assert saved["profiles"] == original["profiles"]
    imported = saved["templates"][-1]
    assert imported["name"] == "Custom document (2)"
    assert imported["blocks"] == original["templates"][0]["blocks"]
    assert UUID(imported["id"]).version == 4
    assert result["imported"] == [imported["id"]] and imported["id"] != "default"
    result = post(client, data).json()
    assert result["settings"]["templates"][-1]["name"] == "Custom document (3)"


def test_overwrite_keeps_id_and_all_profile_references(app_env, client):
    settings = app_env.store.get_document_settings()
    settings["profiles"]["default"]["source"] = "template"
    settings["profiles"]["other"] = settings["profiles"]["default"].copy()
    app_env.store.save_document_settings(settings)
    response = post(client, export_data(template(" Custom document ")), "overwrite")
    assert response.status_code == 200
    saved = response.json()["settings"]
    assert response.json()["imported"] == ["default"]
    assert saved["profiles"] == settings["profiles"]
    assert len(saved["templates"]) == 1
    assert saved["templates"][0]["name"] == "Custom document"
    assert saved["templates"][0]["blocks"][0]["text"] == "Hello {{buyer.name}}"
    result = post(client, export_data(template("New")), "overwrite").json()
    assert result["imported"][0] != "untrusted"
    assert UUID(result["imported"][0]).version == 4


@pytest.mark.parametrize("changes", [
    {"format": "wrong"}, {"version": 2}, {"version": True}, {"version": "1"},
    {"unknown": 1}, {"templates": []},
    {"templates": [template(str(i)) for i in range(11)]},
    {"templates": [template("Same"), template(" Same ")]},
    {"templates": [template(name="x" * 101)]},
    {"templates": [template(name=" ")]},
    {"templates": [template(blocks=[{"type": "text", "text": "{{ a+b }}"}])]},
    {"templates": [template(blocks=[{"type": "text", "text": "{% x %}"}])]},
    {"templates": [template(blocks=[{"type": "text", "text": "x" * 4001}])]},
    {"templates": [template(blocks=[{"type": "text"}] * 51)]},
    {"templates": [template(blocks=[{"type": "logo", "image": "data:image/png;base64,aGVsbG8="}])]},
    {"templates": [template(extra="bad")]},
    {"templates": [template(blocks=[{"type": "text", "extra": "bad"}])]},
])
def test_invalid_import_is_atomic(app_env, client, changes):
    settings = app_env.store.get_document_settings()
    app_env.store.save_document_settings(settings)
    before = app_env.state_file.read_bytes()
    data = export_data(template())
    data.update(copy.deepcopy(changes))
    response = post(client, data)
    assert response.status_code == 422, response.text
    assert app_env.store.get_document_settings() == settings
    assert app_env.state_file.read_bytes() == before


@pytest.mark.parametrize("lang", ["pl", "en"])
@pytest.mark.parametrize("field,value,key", [
    ("format", "wrong", "document.import_format"), ("version", 2, "document.import_version"),
    ("templates", [template("X"), template("X")], "document.import_duplicate_names"),
])
def test_import_errors_localized(client, lang, field, value, key):
    from localization import t
    data = export_data(template())
    data[field] = value
    response = post(client, data, headers={"Accept-Language": lang})
    assert response.status_code == 422
    assert response.json()["detail"] == t(key, lang=lang)


def test_limit_is_atomic_and_overwrite_allowed_at_capacity(app_env, client):
    settings = app_env.store.get_document_settings()
    settings["templates"] = [template(str(i), id=f"t{i}") for i in range(10)]
    settings["profiles"]["default"]["active_template_id"] = "t0"
    app_env.store.save_document_settings(settings)
    before = app_env.state_file.read_bytes()
    for mode in ["rename", "overwrite"]:
        response = post(client, export_data(template("0"), template("New")), mode)
        assert response.status_code == 422
        assert app_env.state_file.read_bytes() == before
    response = post(client, export_data(template("0")), "overwrite")
    assert response.status_code == 200
    assert response.json()["imported"] == ["t0"]
    assert len(response.json()["settings"]["templates"]) == 10


def test_rename_truncates_and_names_are_case_sensitive(app_env, client):
    name = "x" * 100
    response = post(client, export_data(template(name), template(name.upper())))
    assert response.status_code == 200
    response = post(client, export_data(template(name)))
    assert response.status_code == 200
    assert response.json()["settings"]["templates"][-1]["name"] == name[:96] + " (2)"


@pytest.mark.parametrize("extra", [{"unknown": 1}, {"on_conflict": "skip"}])
def test_import_request_fields_rejected(client, extra):
    body = {"data": export_data(template()), "on_conflict": "rename", **extra}
    assert client.post(BASE + "/import", json=body).status_code == 422


def test_aggregate_images_and_invalid_later_template_preserve_state(app_env, client):
    import base64
    import io
    import random

    from PIL import Image

    image = io.BytesIO()
    Image.frombytes("RGB", (600, 600), random.Random(1).randbytes(600 * 600 * 3)).save(image, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
    settings = app_env.store.get_document_settings()
    app_env.store.save_document_settings(settings)
    before = app_env.state_file.read_bytes()
    data = export_data(template("Valid first"), template("Too many logos", blocks=[
        {"type": "logo", "image": uri}, {"type": "logo", "image": uri},
    ]))
    response = post(client, data, headers={"Accept-Language": "en"})
    assert response.status_code == 422
    assert response.json()["detail"] == "The combined logo size in this template is too large (about 2 MB)."
    assert uri not in response.text
    assert app_env.state_file.read_bytes() == before


def test_body_limit_and_auth(app_env, client):
    from request_limits import BODY_LIMITS
    settings = app_env.store.get_document_settings()
    app_env.store.save_document_settings(settings)
    before = app_env.state_file.read_bytes()
    assert BODY_LIMITS[BASE + "/import"] == 4 * 1024 * 1024 * 3
    response = client.post(BASE + "/import", content=b"x" * (BODY_LIMITS[BASE + "/import"] + 1))
    assert response.status_code == 413
    assert app_env.state_file.read_bytes() == before
    assert client.get(BASE + "/export", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert post(client, export_data(template()), headers={"Authorization": "Bearer wrong"}).status_code == 401
