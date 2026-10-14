"""Structured custom documents; selection scopes are independent of OAuth accounts."""
import base64
import io
import re
import warnings
from datetime import date, datetime
from html import escape
from typing import Literal

from localization import current_language, date_format, t
from models.order import Order
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PLACEHOLDERS = {"buyer_name", "buyer_address", "order_number", "date", "courier", "pickup_point", "tracking_number"}
_TOKEN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")
CANVAS_PLACEHOLDERS = PLACEHOLDERS | {"buyer.name", "buyer.address", "order.id", "order.date", "items"}
MAX_LOGO_BYTES = 2 * 1024 * 1024


def validate_text(text: str) -> None:
    # Unknown identifiers are warnings, not errors, for both legacy and canvas blocks.
    # Expressions, directives and malformed delimiters remain invalid everywhere.
    remainder = _TOKEN.sub("", text)
    if any(marker in remainder for marker in ("{{", "}}", "{%", "%}", "{#", "#}")):
        raise ValueError(t("document.invalid_fields"))


def validate_logo(image: str) -> bytes:
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", image)
    if not match:
        raise ValueError(t("document.invalid_logo"))
    try:
        content = base64.b64decode(match.group(2), validate=True)
        if len(content) > MAX_LOGO_BYTES:
            raise ValueError("Logo too large")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as logo:
                if (
                    logo.format != {"png": "PNG", "jpeg": "JPEG"}[match.group(1)]
                    or logo.width * logo.height > 16_000_000
                ):
                    raise ValueError("Invalid image format or dimensions")
                logo.verify()
        return content
    except Exception as exc:
        raise ValueError(t("document.invalid_logo")) from exc


class DocumentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["heading", "text", "customer", "items", "logo", "placeholder", "line"]
    text: str = Field("", max_length=4000)
    align: Literal["left", "center", "right"] = "left"
    size: int = Field(12, ge=8, le=36, strict=True)
    show_prices: bool = False
    image: str = Field("", max_length=2_800_000)
    x: float | None = Field(None, allow_inf_nan=False)
    y: float | None = Field(None, allow_inf_nan=False)
    w: float | None = Field(None, allow_inf_nan=False)
    h: float | None = Field(None, allow_inf_nan=False)
    bold: bool = False

    @model_validator(mode="after")
    def safe_content(self):
        validate_text(self.text)
        if self.type == "logo":
            if self.image:
                validate_logo(self.image)
        elif self.image:
            raise ValueError(t("document.invalid_logo"))
        return self


class DocumentTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=100)
    blocks: list[DocumentBlock] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounded_images(self):
        # JSON state is parsed on each accessor: bound the aggregate, not just each logo.
        if sum(len(block.image) for block in self.blocks) > 2_800_000:
            raise ValueError(t("document.logo_total"))
        cursor = 18.0
        for block in self.blocks:
            default_height = {"heading": 18, "text": 24, "customer": 30, "items": 90,
                              "logo": 35, "placeholder": 24, "line": 1}[block.type]
            legacy = all(value is None for value in (block.x, block.y, block.w, block.h))
            block.x = max(0.0, min(209.0, block.x if block.x is not None else 18.0))
            block.y = max(0.0, min(296.0, block.y if block.y is not None else cursor))
            block.w = max(1.0, min(210.0 - block.x, block.w if block.w is not None else 174.0))
            block.h = max(1.0, min(297.0 - block.y, block.h if block.h is not None else default_height))
            if legacy and block.type == "heading" and "bold" not in block.model_fields_set:
                block.bold = True
            cursor = block.y + block.h + 6
        self.warnings = sorted({f"Unknown placeholder: {token}" for block in self.blocks
                                for token in _TOKEN.findall(block.text) if token not in CANVAS_PLACEHOLDERS})
        return self


class DocumentTemplateExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str
    version: int
    exported_at: datetime
    templates: list[DocumentTemplate] = Field(min_length=1, max_length=10)

    @field_validator("format", mode="before")
    @classmethod
    def valid_format(cls, value):
        if value != "packing.document-templates":
            raise ValueError(t("document.import_format"))
        return value

    @field_validator("version", mode="before")
    @classmethod
    def valid_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError(t("document.import_version"))
        return value

    @model_validator(mode="after")
    def unique_names(self):
        for template in self.templates:
            template.name = template.name.strip()
            if not template.name:
                raise ValueError(t("document.invalid_template"))
        names = [template.name for template in self.templates]
        if len(names) != len(set(names)):
            raise ValueError(t("document.import_duplicate_names"))
        return self


class DocumentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["upload", "template"] = "upload"
    active_template_id: str = Field("default", pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class DocumentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    templates: list[DocumentTemplate] = Field(min_length=1, max_length=10)
    profiles: dict[str, DocumentProfile] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_references(self):
        ids = [template.id for template in self.templates]
        if len(ids) != len(set(ids)) or "default" not in self.profiles:
            raise ValueError("Duplicate template IDs or missing default profile")
        if any(profile.active_template_id not in ids for profile in self.profiles.values()):
            raise ValueError("Selected template does not exist")
        return self


def default_document_settings() -> dict:
    return DocumentSettings(
        templates=[DocumentTemplate(id="default", name="Custom document")],
        profiles={"default": DocumentProfile()},
    ).model_dump()


def render_document_html(template: DocumentTemplate, order: Order) -> str:
    values = {
        "buyer_name": order.buyer_name, "buyer_address": order.buyer_address,
        "order_number": order.allegro_id, "date": date.today().strftime(date_format(current_language.get())),
        "courier": order.courier, "pickup_point": order.pickup_point, "tracking_number": order.tracking_number,
    }
    values.update({"buyer.name": order.buyer_name, "buyer.address": order.buyer_address,
                   "order.id": order.id, "order.date": values["date"],
                   "items": "\n".join(f"{item.name} × {item.quantity}" for item in order.items)})

    def text(value):
        # Substitute only original tokens: order data containing braces is never interpreted.
        return escape(_TOKEN.sub(lambda match: str(values.get(match.group(1)) or "—"), value))

    sections = []
    for block in template.blocks:
        style = (f'text-align:{block.align};font-size:{block.size}pt;'
                 f'font-weight:{"bold" if block.bold else "normal"}')
        sections.append(f'<div class="element" style="left:{block.x}mm;top:{block.y}mm;'
                        f'width:{block.w}mm;height:{block.h}mm;{style}">')
        if block.type in ("heading", "text", "placeholder"):
            tag = "h2" if block.type == "heading" else "p"
            sections.append(f'<{tag} class="text" style="{style}">{text(block.text)}</{tag}>')
        elif block.type == "logo" and block.image:
            sections.append(
                f'<div style="{style}"><img class="logo" src="{escape(block.image, quote=True)}" alt=""></div>'
            )
        elif block.type == "customer":
            sections.append(
                f'<section class="customer text" style="{style}">{escape(order.buyer_name)}\n'
                f'{escape(order.buyer_address)}</section>'
            )
        elif block.type == "items":
            headers = [t("doc.product"), t("doc.quantity")]
            if block.show_prices:
                headers.extend([t("doc.unit_price"), t("doc.value")])
            rows = []
            for item in order.items:
                cells = [escape(item.name), str(item.quantity)]
                if block.show_prices:
                    cells.extend([f'{item.unit_price:.2f} zł' if item.unit_price is not None else '—',
                                  f'{item.unit_price * item.quantity:.2f} zł' if item.unit_price is not None else '—'])
                rows.append('<tr>' + ''.join(f'<td>{cell}</td>' for cell in cells) + '</tr>')
            total = ''
            if block.show_prices and order.items and all(item.unit_price is not None for item in order.items):
                amount = sum(item.quantity * item.unit_price for item in order.items)
                total = (
                    f'<tbody class="total"><tr><td colspan="3">{escape(t("doc.total"))}</td>'
                    f'<td>{amount:.2f} zł</td></tr></tbody>'
                )
            sections.append(
                f'<table style="{style}"><thead><tr>' + ''.join(f'<th>{escape(header)}</th>' for header in headers)
                + '</tr></thead><tbody>' + ''.join(rows) + '</tbody>' + total + '</table>'
            )
        elif block.type == "line":
            sections.append('<div class="rule"></div>')
        sections.append('</div>')
    return ('<!doctype html><html lang="' + current_language.get() + '"><head><meta charset="utf-8"><title>'
            + escape(template.name) + '</title><style>'
            '@page{size:A4;margin:0}html,body{margin:0;padding:0}'
            'body{position:relative;width:210mm;height:297mm;font-family:DejaVu Sans,sans-serif;color:#222}'
            '.element{position:absolute;overflow:hidden;box-sizing:border-box}'
            'h2,p,section,table{margin:0;font-size:inherit;font-weight:inherit}'
            '.text{white-space:pre-wrap;overflow-wrap:anywhere}'
            '.logo{max-width:100%;max-height:100%;object-fit:contain}.rule{border-top:0.3mm solid #222}'
            'table{border-collapse:collapse;width:100%;table-layout:fixed}'
            'th,td{padding:3mm;border-bottom:1px solid #ddd;overflow-wrap:anywhere}'
            'th:first-child,td:first-child{width:48%}thead{display:table-header-group}tr{break-inside:avoid}.total{font-weight:bold}'
            '</style></head><body>' + ''.join(sections) + '</body></html>')


def render_document_pdf(template: DocumentTemplate, order: Order) -> bytes:
    from weasyprint import HTML
    from weasyprint.urls import URLFetcherResponse
    # Never fetch a URL supplied by an operator or embedded in order data.
    allowed_images = {block.image for block in template.blocks if block.type == "logo" and block.image}

    def fetch(url, *args, **kwargs):
        if url not in allowed_images:
            raise ValueError("Document resource access denied")
        return URLFetcherResponse(url, body=validate_logo(url),
                                  headers={"Content-Type": url.split(';', 1)[0][5:]})

    return HTML(string=render_document_html(template, order), url_fetcher=fetch).write_pdf()

