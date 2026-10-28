"""Label/document download and CUPS printing, with `lp` mocked."""
import asyncio
import stat
import subprocess
import threading

import pytest
from helpers import PDF_BYTES, FakeAPI, make_order

from mcp_server.client import PackingError
from mcp_server.printing import print_pdf
from mcp_server.tools import _write_pdf


class FakeLP:
    """Stands in for shutil.which + subprocess.run around the CUPS client."""

    def __init__(self, returncode: int = 0, stdout: str = "request id is Office-42 (1 file(s))",
                 stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def which(self, name: str) -> str | None:
        return "/usr/bin/lp" if name == "lp" else None

    def run(self, command, **_kwargs):
        self.commands.append(list(command))
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def fake_lp(monkeypatch):
    fake = FakeLP()
    monkeypatch.setattr("mcp_server.printing.shutil.which", fake.which)
    monkeypatch.setattr("mcp_server.printing.subprocess.run", fake.run)
    return fake


def _label_api(tmp_path) -> FakeAPI:
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1", shipment_id=None)])
    api.add("GET", "/api/print/orders/o1/shipment", json_body={"shipment_id": None, "tracking_number": None})
    api.add("POST", "/api/print/orders/o1/label",
            json_body={"shipment_id": "ship-1", "tracking_number": "PL123"})
    api.add("GET", "/api/print/orders/o1/label", content=PDF_BYTES, content_type="application/pdf")
    return api


def test_get_shipment_info_reads_the_existing_shipment():
    api = FakeAPI()
    api.add("GET", "/api/print/orders/o1/shipment",
            json_body={"shipment_id": "ship-1", "tracking_number": "PL123"})
    assert asyncio.run(api.tools().get_shipment_info("o1")) == {
        "shipment_id": "ship-1", "tracking_number": "PL123",
    }


def test_create_label_sends_only_the_given_dimensions(tmp_path):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path))

    result = asyncio.run(tools.create_label("o1", length=40.0, weight=2.5))
    assert result["shipment_id"] == "ship-1"
    assert result["tracking_number"] == "PL123"
    params = dict(api.last().url.params)
    assert params == {"length": "40.0", "weight": "2.5"}


def test_download_label_writes_the_pdf_without_printing(tmp_path, fake_lp):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path))
    target = tmp_path / "labels" / "order-1.pdf"

    result = asyncio.run(tools.download_label("o1", output_path=str(target)))
    assert target.read_bytes() == PDF_BYTES
    assert result["bytes"] == len(PDF_BYTES)
    assert result["path"] == str(target)
    assert fake_lp.commands == []


def test_download_label_uses_the_configured_directory_by_default(tmp_path, fake_lp):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path))
    result = asyncio.run(tools.download_label("o1"))
    assert result["path"].startswith(str(tmp_path))
    assert "label-ALLEGRO-1" in result["path"]


def test_download_label_surfaces_the_missing_shipment_conflict(tmp_path):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1")])
    api.add("GET", "/api/print/orders/o1/label", status=409,
            json_body={"detail": "Shipment has not been created."})
    tools = api.tools(label_dir=str(tmp_path))
    with pytest.raises(PackingError, match="Shipment has not been created"):
        asyncio.run(tools.download_label("o1"))


def test_print_label_creates_the_shipment_then_prints(tmp_path, fake_lp):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path), printer="Office")

    result = asyncio.run(tools.print_label("o1"))

    assert ("POST", "/api/print/orders/o1/label") in api.calls()
    assert result["shipment_created_now"] is True
    assert result["shipment_id"] == "ship-1"
    assert result["tracking_number"] == "PL123"
    assert result["job_id"] == "Office-42"
    assert result["printer"] == "Office"
    assert result["path"].endswith(".pdf")
    assert fake_lp.commands == [["/usr/bin/lp", "-d", "Office", "-t", "Label ALLEGRO-1", result["path"]]]


def test_print_label_reuses_an_existing_shipment(tmp_path, fake_lp):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1", shipment_id="ship-9",
                                                        tracking_number="PL999")])
    api.add("GET", "/api/print/orders/o1/shipment",
            json_body={"shipment_id": "ship-9", "tracking_number": "PL999"})
    api.add("GET", "/api/print/orders/o1/label", content=PDF_BYTES, content_type="application/pdf")
    tools = api.tools(label_dir=str(tmp_path), printer="Office")

    result = asyncio.run(tools.print_label("o1"))
    assert ("POST", "/api/print/orders/o1/label") not in api.calls()
    assert result["shipment_created_now"] is False
    assert result["tracking_number"] == "PL999"
    assert "existing shipment reused" in result["message"]


def test_print_label_can_refuse_to_create_a_shipment(tmp_path, fake_lp):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path))
    with pytest.raises(PackingError, match="no shipment yet"):
        asyncio.run(tools.print_label("o1", create_if_missing=False))
    assert ("POST", "/api/print/orders/o1/label") not in api.calls()


def test_print_label_falls_back_to_the_cups_default_queue(tmp_path, fake_lp):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path), printer="")
    asyncio.run(tools.print_label("o1"))
    assert fake_lp.commands[0][0] == "/usr/bin/lp"
    assert "-d" not in fake_lp.commands[0]
    assert "-n" not in fake_lp.commands[0]


def test_print_label_reports_an_lp_failure(tmp_path, monkeypatch):
    api = _label_api(tmp_path)
    failing = FakeLP(returncode=1, stdout="", stderr="lp: The printer or class does not exist.")
    monkeypatch.setattr("mcp_server.printing.shutil.which", failing.which)
    monkeypatch.setattr("mcp_server.printing.subprocess.run", failing.run)
    tools = api.tools(label_dir=str(tmp_path), printer="Ghost")

    with pytest.raises(PackingError) as error:
        asyncio.run(tools.print_label("o1"))
    assert "The printer or class does not exist" in str(error.value)
    assert "lpstat -p" in str(error.value)


def test_missing_cups_client_is_explained(tmp_path, monkeypatch):
    api = _label_api(tmp_path)
    monkeypatch.setattr("mcp_server.printing.shutil.which", lambda _name: None)
    tools = api.tools(label_dir=str(tmp_path))
    with pytest.raises(PackingError, match="cups-client"):
        asyncio.run(tools.print_label("o1"))


@pytest.mark.parametrize("copies", [0, -1, 100])
def test_print_label_validates_copies(tmp_path, fake_lp, copies):
    api = _label_api(tmp_path)
    tools = api.tools(label_dir=str(tmp_path))
    with pytest.raises(PackingError, match="copies must be a whole number"):
        asyncio.run(tools.print_label("o1", copies=copies))
    assert fake_lp.commands == []


def test_print_pdf_refuses_a_non_pdf_file(tmp_path, fake_lp):
    path = tmp_path / "not-a-pdf.txt"
    path.write_text("hello")
    with pytest.raises(PackingError, match="not a PDF"):
        print_pdf(path)


def test_invalid_copies_do_not_create_a_shipment(tmp_path, fake_lp):
    api = _label_api(tmp_path)
    with pytest.raises(PackingError, match="copies must be a whole number"):
        asyncio.run(api.tools(label_dir=str(tmp_path)).print_label("o1", copies=0))
    assert api.calls() == []


def test_missing_lp_does_not_create_a_shipment(tmp_path, monkeypatch):
    api = _label_api(tmp_path)
    monkeypatch.setattr("mcp_server.printing.shutil.which", lambda _name: None)
    with pytest.raises(PackingError, match="cups-client"):
        asyncio.run(api.tools(label_dir=str(tmp_path)).print_label("o1"))
    assert api.calls() == []


def test_print_pdf_reports_a_missing_file(tmp_path, fake_lp):
    with pytest.raises(PackingError, match="does not exist"):
        print_pdf(tmp_path / "missing.pdf")


def test_print_document_auto_prefers_the_custom_document(tmp_path, fake_lp):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1")])
    api.add("GET", "/api/print/custom-doc/info", json_body={"available": True, "source": "template"})
    api.add("GET", "/api/print/custom-doc", content=PDF_BYTES, content_type="application/pdf")
    tools = api.tools(label_dir=str(tmp_path), printer="Office")

    result = asyncio.run(tools.print_document("o1"))
    assert result["document"] == "custom"
    assert result["job_id"] == "Office-42"
    assert api.last("GET").url.path == "/api/print/custom-doc"
    assert api.last("GET").url.params["order_id"] == "o1"


def test_print_document_auto_falls_back_to_the_sales_document(tmp_path, fake_lp):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1")])
    api.add("GET", "/api/print/custom-doc/info", json_body={"available": False, "source": "template"})
    api.add("GET", "/api/print/orders/o1/document", content=PDF_BYTES, content_type="application/pdf")
    tools = api.tools(label_dir=str(tmp_path), printer="Office")

    result = asyncio.run(tools.print_document("o1"))
    assert result["document"] == "sales"
    assert api.last("GET").url.path == "/api/print/orders/o1/document"


def test_download_document_combined_writes_the_merged_pdf(tmp_path):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1")])
    api.add("GET", "/api/print/orders/o1/combined", content=PDF_BYTES, content_type="application/pdf")
    tools = api.tools(label_dir=str(tmp_path))
    target = tmp_path / "combined.pdf"

    result = asyncio.run(tools.download_document("o1", "combined", output_path=str(target)))
    assert result["document"] == "combined"
    assert target.read_bytes() == PDF_BYTES


def test_unknown_document_kind_is_rejected(tmp_path):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1")])
    tools = api.tools(label_dir=str(tmp_path))
    with pytest.raises(PackingError, match="document must be"):
        asyncio.run(tools.download_document("o1", "invoice"))


def test_generated_pdf_paths_are_unique_and_private(tmp_path):
    first = _write_pdf(PDF_BYTES, str(tmp_path), "label-order")
    second = _write_pdf(PDF_BYTES + b"second", str(tmp_path), "label-order")
    assert first != second
    assert first.read_bytes() == PDF_BYTES
    assert stat.S_IMODE(first.stat().st_mode) == 0o600


def test_default_pdf_directory_is_private():
    path = _write_pdf(PDF_BYTES, "", "label-order")
    try:
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        path.unlink()
        path.parent.rmdir()


@pytest.mark.parametrize("tool_name", ["print_label", "print_document"])
def test_slow_printer_does_not_block_health(tmp_path, fake_lp, monkeypatch, tool_name):
    api = _label_api(tmp_path)
    api.add("GET", "/health", json_body={"status": "ok"})
    api.add("GET", "/api/print/orders/o1/document", content=PDF_BYTES)
    started, release = threading.Event(), threading.Event()
    original_run = fake_lp.run

    def slow_run(command, **kwargs):
        started.set()
        release.wait(2)
        return original_run(command, **kwargs)

    monkeypatch.setattr("mcp_server.printing.subprocess.run", slow_run)
    tools = api.tools(label_dir=str(tmp_path))

    async def exercise():
        kwargs = {"document": "sales"} if tool_name == "print_document" else {}
        task = asyncio.create_task(getattr(tools, tool_name)("o1", **kwargs))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            assert not task.done(), "Printing blocked the event loop until the subprocess exited"
            assert await asyncio.wait_for(tools.get_app_health(), 0.5) == {"status": "ok"}
        finally:
            release.set()
            await task

    asyncio.run(exercise())
