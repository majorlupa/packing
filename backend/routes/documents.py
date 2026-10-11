"""Custom document settings and draft previews. No shipment or OAuth side effects."""
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

import store
from documents import DocumentSettings, DocumentTemplate, render_document_pdf
from localization import t

router = APIRouter(prefix="/print", tags=["documents"])
logger = logging.getLogger("packing.documents")


class DocumentSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["upload", "template"]
    template: DocumentTemplate


class DocumentPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(min_length=1, max_length=200)
    template: DocumentTemplate


def has_content(template: DocumentTemplate) -> bool:
    return any(block.type in ("customer", "items") or
               (block.type == "logo" and block.image) or
               (block.type in ("heading", "text") and block.text.strip()) for block in template.blocks)


def active_template(settings: dict) -> DocumentTemplate:
    selected = settings["profiles"]["default"]["active_template_id"]
    return DocumentTemplate.model_validate(next(item for item in settings["templates"] if item["id"] == selected))


def personalized_pdf(template: DocumentTemplate, order_id: str | None) -> bytes:
    if not order_id:
        raise HTTPException(status_code=422, detail=t("document.order_required"))
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=t("error.order_not_found"))
    if not has_content(template):
        raise HTTPException(status_code=422, detail=t("document.empty"))
    try:
        return render_document_pdf(template, order)
    except Exception as exc:
        logger.exception("Custom document rendering failed")
        raise HTTPException(status_code=500, detail=t("document.render_failed")) from exc


@router.get("/document-settings")
def document_settings():
    return store.get_document_settings()


@router.post("/document-settings")
def save_document_settings(body: DocumentSave):
    if body.source == "template" and not has_content(body.template):
        raise HTTPException(status_code=422, detail=t("document.empty"))

    def mutate(state):
        settings = state["document_settings"]
        profile = settings["profiles"]["default"]
        if body.template.id != profile["active_template_id"]:
            raise HTTPException(status_code=422, detail=t("document.template_id"))
        for index, item in enumerate(settings["templates"]):
            if item["id"] == body.template.id:
                settings["templates"][index] = body.template.model_dump()
                break
        profile["source"] = body.source
        saved = DocumentSettings.model_validate(settings).model_dump()
        state["document_settings"] = saved
        return saved

    return store.transact(mutate)


@router.post("/document-preview")
def preview_document(body: DocumentPreview):
    return Response(content=personalized_pdf(body.template, body.order_id), media_type="application/pdf",
                    headers={"Cache-Control": "no-store"})
