"""API ของ Gem: ครูสร้างและแก้ได้ Admin ดูได้อย่างเดียว"""

import asyncio
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db, seed
from ..gems import builder, manage
from ..tutor import rag, service
from .deps import require

router = APIRouter(prefix="/api/gems", tags=["gems"])
teacher = require("teacher")
viewer = require("teacher", "admin")


class GemBody(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    icon: str | None = None
    color: str | None = None
    tools: dict[str, bool] | None = None
    starter_prompts: list[str] | None = None


class RefineBody(BaseModel):
    name: str = ""
    description: str = ""
    instructions: str = ""


class FlagBody(BaseModel):
    keep: bool


def _fields(body: GemBody) -> dict:
    return body.model_dump(exclude_none=True)


def _load(gem_id: str) -> dict:
    try:
        return manage.get(gem_id)
    except manage.GemError as error:
        raise HTTPException(404, str(error)) from error


@router.get("")
def list_gems(auth: dict = Depends(viewer)):
    return [manage.summary(manage.get(g["id"])) for g in db.list_gems()]


@router.get("/{gem_id}")
def get_gem(gem_id: str, auth: dict = Depends(viewer)):
    return manage.detail(_load(gem_id))


@router.post("")
def create_gem(body: GemBody, auth: dict = Depends(teacher)):
    try:
        return manage.detail(manage.create(_fields(body), auth["role"]))
    except manage.GemError as error:
        raise HTTPException(400, str(error)) from error


@router.put("/{gem_id}")
def update_gem(gem_id: str, body: GemBody, auth: dict = Depends(teacher)):
    _load(gem_id)
    try:
        return manage.detail(manage.update(gem_id, _fields(body)))
    except manage.GemError as error:
        raise HTTPException(400, str(error)) from error


@router.delete("/{gem_id}")
def delete_gem(gem_id: str, auth: dict = Depends(teacher)):
    _load(gem_id)
    manage.delete(gem_id)
    return {"ok": True}


@router.post("/{gem_id}/build")
async def build_gem(gem_id: str, auth: dict = Depends(teacher)):
    """เริ่มสร้าง Item Bank รุ่นใหม่เป็นงานเบื้องหลัง หน้าเว็บดึงสถานะจาก GET /api/gems/{id}"""
    _load(gem_id)
    if builder.is_running(gem_id):
        raise HTTPException(409, "กำลังสร้างคลังโจทย์อยู่")
    reason = manage.can_build()
    if reason:
        raise HTTPException(400, reason)
    asyncio.create_task(builder.build(gem_id))
    await asyncio.sleep(0)
    return manage.detail(manage.get(gem_id))


@router.post("/refine")
async def refine_instructions(body: RefineBody, auth: dict = Depends(teacher)):
    """ปุ่มไม้กายสิทธิ์: ให้ AI เกลาคำสั่งของครูให้ชัดขึ้น ครูกดย้อนกลับได้ที่หน้าเว็บ"""
    reason = manage.can_build()
    if reason:
        raise HTTPException(400, reason)
    system = (
        "คุณช่วยครูเขียนคำสั่งของ Gem ซึ่งเป็นติวเตอร์ AI ภาษาไทย ให้ชัดเจนและนำไปใช้ได้ทันที "
        "ระบุบทบาท กลุ่มผู้เรียนและระดับชั้น เนื้อหาที่สอน และน้ำเสียงในการสอน คงเจตนาเดิมของครูทุกข้อ "
        "ห้ามเพิ่มคำสั่งให้เฉลยคำตอบ เพราะระบบห้ามเฉลยอยู่แล้ว ตอบเฉพาะคำสั่งที่เกลาแล้ว ไม่ต้องมีคำนำ "
        "เขียนเป็นย่อหน้าข้อความธรรมดาที่ขึ้นต้นด้วย \"คุณคือ\" ไม่ใช้สัญลักษณ์ markdown เช่น ** # หรือ ---"
    )
    user = f"ชื่อ Gem: {body.name}\nคำอธิบาย: {body.description}\nคำสั่งเดิมของครู:\n{body.instructions or '(ยังไม่มี เขียนร่างจากชื่อและคำอธิบาย)'}"
    result, errors = await service._call(system, user, max_tokens=1500, timeout=60.0, backup_models=builder.GEMINI_BACKUPS)
    service._log(None, "gem_refine", {"role": system, "task": user}, None, result, result.text if result else "", None, errors)
    if result is None:
        raise HTTPException(502, "; ".join(errors) or "เรียก AI ไม่สำเร็จ")
    return {"instructions": _plain(result.text)}


def _plain(text: str) -> str:
    """เอาสัญลักษณ์ markdown ที่หลุดมาออก ช่องคำสั่งเป็นข้อความธรรมดา"""
    lines = [re.sub(r"^#+\s*|\*\*|__", "", line).rstrip() for line in text.strip().splitlines()]
    lines = [line for line in lines if not re.fullmatch(r"\s*[-*_]{3,}\s*", line)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


@router.get("/{gem_id}/files")
def gem_files(gem_id: str, auth: dict = Depends(viewer)):
    _load(gem_id)
    return manage.files(gem_id)


@router.post("/{gem_id}/files")
async def upload_file(gem_id: str, file: UploadFile = File(...), auth: dict = Depends(teacher)):
    _load(gem_id)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 15 MB")
    text, warning = rag.extract_text(file.filename or "file.txt", data)
    if not text:
        raise HTTPException(400, warning or "อ่านข้อความจากไฟล์นี้ไม่ได้")
    doc_id = seed.add_document(gem_id, file.filename or "เอกสาร", text, warning)
    return {"id": doc_id, "warning": warning, "chars": len(text)}


@router.delete("/{gem_id}/files/{doc_id}")
def delete_file(gem_id: str, doc_id: int, auth: dict = Depends(teacher)):
    _load(gem_id)
    db.execute("DELETE FROM documents WHERE id = ? AND subject_id = ?", (doc_id, gem_id))
    seed.rebuild_index(gem_id)
    return {"ok": True}


@router.post("/{gem_id}/items/{item_id}/flag")
def resolve_flag(gem_id: str, item_id: str, body: FlagBody, auth: dict = Depends(teacher)):
    """ครูยืนยันเฉลยของ Flagged Item (keep = true) หรือลบข้อนั้นออกจากคลัง (keep = false)"""
    _load(gem_id)
    try:
        return manage.resolve_flag(gem_id, item_id, body.keep)
    except manage.GemError as error:
        raise HTTPException(404, str(error)) from error
