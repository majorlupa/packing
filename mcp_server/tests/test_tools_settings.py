"""Settings tools: shipping, invoice, document templates and the custom PDF."""
import asyncio

import pytest
from helpers import PDF_BYTES, FakeAPI

from mcp_server.client import PackingError

SHIPMENT_SETTINGS = {
    "sender": {"name": "Weles", "company": "", "street": "", "postal_code": "", "city": "",
               "country_code": "PL", "email": "", "phone": ""},
    "package": {"type": "PACKAGE", "length": 30, "width": 20, "height": 15,
                "weight": 1.0, "label_format": "PDF", "page_size": "A6"},
}

INVOICE_SETTINGS = {
    "show_buyer_name": True, "show_buyer_address": True, "show_items": True,
    "show_price": True, "show_courier": True, "show_pickup_point": True,
    "show_allegro_id": True, "free_text": "",
}

DOCUMENT_SETTINGS = {
    "profiles": {"default": {"source": "template", "active_template_id": "t2"}},
    "templates": [
        {"id": "t1", "name": "Domyślny", "blocks": [{"type": "text", "text": "Hi"}]},
        {"id": "t2", "name": "Faktura", "blocks": []},
    ],
}


def test_shipment_settings_are_merged_and_saved():
    api = FakeAPI()
    api.add("GET", "/api/print/shipment-settings", json_body=SHIPMENT_SETTINGS)
    api.add("POST", "/api/print/shipment-settings", json_body={"status": "saved"})
    tools = api.tools()

    result = asyncio.run(tools.update_shipment_settings(length=64.0, height=41.0, page_size="A4"))
    assert result["status"] == "saved"
    package = result["shipment_settings"]["package"]
    assert package["length"] == 64.0
    assert package["height"] == 41.0
    assert package["width"] == 20
    assert package["page_size"] == "A4"
    assert package["label_format"] == "PDF"
    assert result["shipment_settings"]["sender"]["name"] == "Weles"
    assert api.json_body(api.last())["package"]["length"] == 64.0


def test_get_shipment_settings_reads_the_route():
    api = FakeAPI()
    api.add("GET", "/api/print/shipment-settings", json_body=SHIPMENT_SETTINGS)
    assert asyncio.run(api.tools().get_shipment_settings())["package"]["page_size"] == "A6"


def test_shipment_settings_need_something_to_change():
    api = FakeAPI()
    with pytest.raises(PackingError, match="Nothing to change"):
        asyncio.run(api.tools().update_shipment_settings())
    assert api.requests == []


def test_invoice_settings_are_read_before_they_are_changed():
    api = FakeAPI()
    api.add("GET", "/api/print/invoice-settings", json_body=INVOICE_SETTINGS)
    settings = asyncio.run(api.tools().get_invoice_settings())
    assert settings["show_courier"] is True
    assert settings["free_text"] == ""


def test_invoice_settings_are_merged_and_saved():
    api = FakeAPI()
    api.add("GET", "/api/print/invoice-settings", json_body=INVOICE_SETTINGS)
    api.add("POST", "/api/print/invoice-settings", json_body={"status": "saved"})
    tools = api.tools()

    result = asyncio.run(tools.update_invoice_settings(show_price=False, free_text="Dziękujemy!"))
    assert result["status"] == "saved"
    saved = result["invoice_settings"]
    assert saved["show_price"] is False
    assert saved["free_text"] == "Dziękujemy!"
    assert saved["show_items"] is True
    assert api.json_body(api.last())["show_price"] is False


def test_invoice_settings_need_something_to_change():
    api = FakeAPI()
    with pytest.raises(PackingError, match="Nothing to change"):
        asyncio.run(api.tools().update_invoice_settings())
    assert api.requests == []


def test_document_templates_are_listed_and_selected():
    api = FakeAPI()
    api.add("GET", "/api/print/document-settings", json_body=DOCUMENT_SETTINGS)
    api.add("POST", "/api/print/document-templates/t1/select", json_body=DOCUMENT_SETTINGS)
    tools = api.tools()

    listing = asyncio.run(tools.list_document_templates())
    assert listing["count"] == 2
    assert listing["active_template_id"] == "t2"
    assert [template["id"] for template in listing["templates"]] == ["t1", "t2"]
    assert listing["templates"][1]["active"] is True
    assert listing["templates"][0]["blocks"] == 1

    asyncio.run(tools.select_document_template("t1"))
    assert api.calls()[-1] == ("POST", "/api/print/document-templates/t1/select")


def test_full_document_settings_are_readable():
    api = FakeAPI()
    api.add("GET", "/api/print/document-settings", json_body=DOCUMENT_SETTINGS)
    settings = asyncio.run(api.tools().get_document_settings())
    assert settings["profiles"]["default"]["source"] == "template"


def test_custom_document_info_and_delete():
    api = FakeAPI()
    api.add("GET", "/api/print/custom-doc/info",
            json_body={"available": True, "source": "upload", "upload_available": True, "size": 1234})
    api.add("DELETE", "/api/print/custom-doc", json_body={"status": "deleted"})
    tools = api.tools()

    info = asyncio.run(tools.get_custom_doc_info())
    assert info["source"] == "upload"
    assert asyncio.run(tools.delete_custom_doc()) == {"status": "deleted"}


def test_upload_custom_doc_sends_the_file(tmp_path):
    api = FakeAPI()
    api.add("POST", "/api/print/custom-doc", json_body={"status": "uploaded"})
    source = tmp_path / "customer-terms.pdf"
    source.write_bytes(PDF_BYTES)

    result = asyncio.run(api.tools().upload_custom_doc(str(source)))
    assert result["status"] == "uploaded"
    assert result["file"] == str(source)
    assert b'filename="customer-terms.pdf"' in api.last().content


def test_upload_rejects_a_non_pdf_before_calling_the_api(tmp_path):
    api = FakeAPI()
    source = tmp_path / "notes.pdf"
    source.write_bytes(b"plain text")
    with pytest.raises(PackingError, match="not a PDF"):
        asyncio.run(api.tools().upload_custom_doc(str(source)))
    assert api.requests == []


def test_upload_rejects_a_missing_file(tmp_path):
    api = FakeAPI()
    with pytest.raises(PackingError, match="File not found"):
        asyncio.run(api.tools().upload_custom_doc(str(tmp_path / "nope.pdf")))
