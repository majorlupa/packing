"""Product queries and virtual printing without CUPS."""
import asyncio
import stat
from pathlib import Path

import pytest
from helpers import PDF_BYTES, FakeAPI, make_order

from mcp_server.client import PackingError
from mcp_server.printing import print_pdf


@pytest.fixture
def virtual_printer(tmp_path, monkeypatch):
    directory = tmp_path / "virtual"
    monkeypatch.setenv("PACKING_PRINT_DIR", str(directory))

    def forbidden(*args, **kwargs):
        pytest.fail("Virtual printing must never invoke CUPS")

    monkeypatch.setattr("mcp_server.printing.shutil.which", forbidden)
    monkeypatch.setattr("mcp_server.printing.subprocess.run", forbidden)
    return directory


def test_virtual_print_is_private_unique_and_preserves_source(tmp_path, virtual_printer):
    source = tmp_path / "label.pdf"
    source.write_bytes(PDF_BYTES)
    first = print_pdf(source, copies=2, printer="ignored")
    second = print_pdf(source)
    assert first.printer == "file"
    assert first.job_id is None
    assert first.output_path != second.output_path
    saved = Path(first.output_path)
    assert saved.parent == virtual_printer
    assert saved.read_bytes() == source.read_bytes() == PDF_BYTES
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600


@pytest.mark.parametrize("copies", [0, 100, True])
def test_virtual_print_validates_copies(tmp_path, virtual_printer, copies):
    with pytest.raises(PackingError, match="copies must"):
        print_pdf(tmp_path / "missing.pdf", copies=copies)


def test_virtual_print_rejects_non_pdf(tmp_path, virtual_printer):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"not PDF")
    with pytest.raises(PackingError, match="not a PDF"):
        print_pdf(source)
    assert list(virtual_printer.iterdir()) == []


def test_unwritable_virtual_directory_fails_before_booking(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_text("not a directory")
    monkeypatch.setenv("PACKING_PRINT_DIR", str(target))
    api = FakeAPI()
    with pytest.raises(PackingError, match="Cannot write to PACKING_PRINT_DIR"):
        asyncio.run(api.tools().print_label("o1"))
    assert api.calls() == []


@pytest.mark.parametrize("tool", ["print_label", "print_document"])
def test_tools_return_virtual_output_path(tmp_path, virtual_printer, tool):
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[make_order(id="o1", shipment_id="ship1")])
    api.add("GET", "/api/print/orders/o1/shipment", json_body={"shipment_id": "ship1"})
    api.add("GET", "/api/print/orders/o1/label", content=PDF_BYTES)
    api.add("GET", "/api/print/orders/o1/document", content=PDF_BYTES)
    kwargs = {"document": "sales"} if tool == "print_document" else {}
    result = asyncio.run(getattr(api.tools(label_dir=str(tmp_path)), tool)("o1", **kwargs))
    assert result["print_dry_run"] is True
    assert Path(result["print_path"]).read_bytes() == PDF_BYTES
    assert result["printer"] == "file"
    assert not any(method == "POST" for method, _ in api.calls())
