"""Custom document settings and draft previews. No shipment or OAuth side effects."""
import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import store
from documents import DocumentSettings, DocumentTemplate, DocumentTemplateExport, render_document_pdf
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from localization import t
from pydantic import BaseModel, ConfigDict, Field

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


class DocumentDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=100)


class DocumentImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: DocumentTemplateExport
    on_conflict: Literal["rename", "overwrite"]


def has_content(template: DocumentTemplate) -> bool:
    return any(block.type in ("customer", "items", "line") or
               (block.type == "logo" and block.image) or
               (block.type in ("heading", "text", "placeholder") and block.text.strip()) for block in template.blocks)


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
        if not any(item["id"] == body.template.id for item in settings["templates"]):
            raise HTTPException(status_code=422, detail=t("document.template_id"))
        for index, item in enumerate(settings["templates"]):
            if item["id"] == body.template.id:
                settings["templates"][index] = body.template.model_dump()
                break
        profile["source"] = body.source
        profile["active_template_id"] = body.template.id
        saved = DocumentSettings.model_validate(settings).model_dump()
        state["document_settings"] = saved
        return saved

    return store.transact(mutate)


@router.post("/document-preview")
def preview_document(body: DocumentPreview):
    return Response(content=personalized_pdf(body.template, body.order_id), media_type="application/pdf",
                    headers={"Cache-Control": "no-store"})


def find_template(settings: dict, template_id: str) -> dict:
    for template in settings["templates"]:
        if template["id"] == template_id:
            return template
    raise HTTPException(status_code=404, detail="Template not found")


@router.get("/document-templates/export")
def export_document_templates(template_id: str | None = None):
    settings = store.get_document_settings()
    templates = [find_template(settings, template_id)] if template_id is not None else settings["templates"]
    filename = f"packing-template-{template_id}.json" if template_id is not None else "packing-templates.json"
    return JSONResponse(content={
        "format": "packing.document-templates", "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "templates": [{key: template[key] for key in ("id", "name", "blocks")} for template in templates],
    }, headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.post("/document-templates/import")
def import_document_templates(body: DocumentImport):
    def mutate(state):
        settings = state["document_settings"]
        templates = settings["templates"]
        imported = []
        for template in body.data.templates:
            item = template.model_dump()
            original = next((entry for entry in templates if entry["name"].strip() == template.name), None)
            if original is not None and body.on_conflict == "overwrite":
                item["id"] = original["id"]
                templates[templates.index(original)] = item
            else:
                names = {entry["name"].strip() for entry in templates}
                number = 2
                while item["name"] in names:
                    suffix = f" ({number})"
                    item["name"] = template.name[:100 - len(suffix)] + suffix
                    number += 1
                item["id"] = uuid4().hex
                templates.append(item)
            imported.append(item["id"])
        if len(templates) > 10:
            raise HTTPException(status_code=422, detail=t("document.import_limit"))
        saved = DocumentSettings.model_validate(settings).model_dump()
        state["document_settings"] = saved
        return {"settings": saved, "imported": imported}
    return store.transact(mutate)


@router.post("/document-templates/{template_id}/duplicate")
def duplicate_document_template(template_id: str, body: DocumentDuplicate | None = None):
    def mutate(state):
        settings = state["document_settings"]
        original = find_template(settings, template_id)
        if len(settings["templates"]) >= 10:
            raise HTTPException(status_code=422, detail="Maximum 10 templates")
        duplicate = DocumentTemplate.model_validate(original).model_dump()
        duplicate["id"] = uuid4().hex
        duplicate["name"] = body.name if body and body.name else (original["name"][:95] + " copy")
        settings["templates"].append(duplicate)
        settings["profiles"]["default"]["active_template_id"] = duplicate["id"]
        saved = DocumentSettings.model_validate(settings).model_dump()
        state["document_settings"] = saved
        return saved
    return store.transact(mutate)


@router.delete("/document-templates/{template_id}")
def delete_document_template(template_id: str):
    def mutate(state):
        settings = state["document_settings"]
        find_template(settings, template_id)
        if len(settings["templates"]) == 1:
            raise HTTPException(status_code=422, detail="Cannot delete the last template")
        settings["templates"] = [item for item in settings["templates"] if item["id"] != template_id]
        fallback = settings["templates"][0]["id"]
        for profile in settings["profiles"].values():
            if profile["active_template_id"] == template_id:
                profile["active_template_id"] = fallback
        saved = DocumentSettings.model_validate(settings).model_dump()
        state["document_settings"] = saved
        return saved
    return store.transact(mutate)


@router.post("/document-templates/{template_id}/select")
def select_document_template(template_id: str):
    def mutate(state):
        settings = state["document_settings"]
        find_template(settings, template_id)
        settings["profiles"]["default"]["active_template_id"] = template_id
        saved = DocumentSettings.model_validate(settings).model_dump()
        state["document_settings"] = saved
        return saved
    return store.transact(mutate)
