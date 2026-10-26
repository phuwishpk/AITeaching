"""ให้ Gemini อ่าน Knowledge File เอง: PDF (รวมภาพสแกน) และรูปภาพ ถอดเป็นข้อความครบทุกหน้า

ตัวอ่านในเครื่อง (rag.extract_text) อ่าน PDF ภาษาไทยได้ไม่ครบเสมอ (สระลอย ตาราง สมการ) และอ่านภาพสแกนไม่ได้
จึงส่งไฟล์ให้ Gemini อ่านทีละ PAGES_PER_PART หน้าพร้อมกัน ส่วนไหนอ่านไม่สำเร็จใช้ตัวอ่านในเครื่องแทนเฉพาะส่วนนั้น
ไม่มี Gemini key หรือเปิด Offline Mode ก็ใช้ตัวอ่านในเครื่องทั้งไฟล์ ไฟล์ของครูถูกส่งไป Google เพื่ออ่านเท่านั้น
"""

import asyncio
import io
import logging

from .. import settings_store
from . import providers, rag

log = logging.getLogger(__name__)

PAGES_PER_PART = 6
PARALLEL = 4
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

SYSTEM = (
    "คุณถอดความเอกสารการสอนเป็นข้อความธรรมดาอย่างครบถ้วนและตรงตัว ไม่สรุป ไม่ตัด ไม่แต่งเพิ่ม "
    "รักษาหัวข้อ ลำดับ และย่อหน้าเดิม คั่นย่อหน้าด้วยบรรทัดว่าง ตารางเขียนเป็นแถวละบรรทัดคั่นช่องด้วย | "
    "สมการและนิพจน์เขียนแบบข้อความธรรมดาที่พิมพ์ได้ เช่น 2x + 3 = 11, 3/4, 2² (ไม่ใช้ LaTeX) "
    "รูปหรือแผนภาพที่มีความหมายต่อการสอนให้อธิบายสั้น ๆ ในวงเล็บเหลี่ยม เช่น [รูป: ตาชั่งสองข้างเท่ากัน] "
    "ข้ามเลขหน้า หัวกระดาษ และท้ายกระดาษที่ซ้ำทุกหน้า ตอบเฉพาะข้อความที่ถอดได้"
)


def _gemini() -> tuple[str, str] | None:
    ai = settings_store.ai_settings()
    key, _ = settings_store.api_key("gemini")
    if ai["active"] == "offline" or not key:
        return None
    return key, ai["gemini_design_model"]  # อ่านเอกสารเป็นงานสร้างบทเรียน


async def _transcribe(gemini: tuple[str, str], mime: str, data: bytes, label: str) -> str:
    key, model = gemini
    result = await providers.call_gemini(
        key, model, SYSTEM, f"ถอดความ{label}ให้ครบทุกบรรทัด", max_tokens=32000, timeout=240.0,
        backup_models=providers.GEMINI_BACKUPS, attachments=[{"mime": mime, "data": data}],
    )
    return result.text.strip()


def _pdf_parts(data: bytes) -> list[tuple[bytes, str, int, int]]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        reader.decrypt("")
    total = len(reader.pages)
    parts = []
    for start in range(0, total, PAGES_PER_PART):
        writer = PdfWriter()
        for page in reader.pages[start:start + PAGES_PER_PART]:
            writer.add_page(page)
        buffer = io.BytesIO()
        writer.write(buffer)
        end = min(total, start + PAGES_PER_PART)
        parts.append((buffer.getvalue(), local_pages(reader, start, end), start + 1, end))
    return parts


def local_pages(reader, start: int, end: int) -> str:
    texts = [reader.pages[i].extract_text() or "" for i in range(start, end)]
    return "\n\n".join(rag.clean_pdf_text(t) for t in texts if t.strip())


async def read_file(filename: str, data: bytes) -> tuple[str, str | None, str]:
    """คืน (ข้อความ, คำเตือน, ผู้อ่าน) ผู้อ่านคือ "gemini", "gemini+local" (บางส่วนใช้ตัวอ่านในเครื่อง) หรือ "local" """
    name = filename.lower()
    suffix = name[name.rfind("."):] if "." in name else ""
    gemini = _gemini()
    if suffix in IMAGES:
        if gemini is None:
            return "", "อ่านรูปภาพได้เมื่อใส่ Gemini API key ในหน้าตั้งค่าของ Admin", "local"
        try:
            return await _transcribe(gemini, IMAGES[suffix], data, "รูปนี้"), None, "gemini"
        except providers.ProviderError as error:
            return "", f"Gemini อ่านรูปนี้ไม่สำเร็จ: {error}", "local"
    if suffix != ".pdf" or gemini is None:
        text, warning = rag.extract_text(filename, data)
        return text, warning, "local"
    try:
        parts = _pdf_parts(data)
    except Exception:  # noqa: BLE001 ไฟล์เสียหรือตั้งรหัส ให้ตัวอ่านในเครื่องรายงานข้อผิดพลาดเดิม
        text, warning = rag.extract_text(filename, data)
        return text, warning, "local"
    gate = asyncio.Semaphore(PARALLEL)
    failed: list[str] = []

    async def one(part: bytes, fallback: str, first: int, last: int) -> str:
        async with gate:
            try:
                return await _transcribe(gemini, "application/pdf", part, f"หน้า {first}–{last} ของเอกสารนี้")
            except providers.ProviderError as error:
                log.warning("Gemini อ่าน %s หน้า %s–%s ไม่สำเร็จ: %s", filename, first, last, error)
                failed.append(f"{first}–{last}")
                return fallback

    texts = await asyncio.gather(*(one(*part) for part in parts))
    text = "\n\n".join(t for t in texts if t.strip())
    if len(text.strip()) < 20:
        return "", "อ่านตัวอักษรจาก PDF นี้ไม่ได้ทั้งจาก Gemini และตัวอ่านในเครื่อง", "local"
    if failed:
        return text, f"Gemini อ่านหน้า {', '.join(failed)} ไม่สำเร็จ ใช้ตัวอ่านในเครื่องแทนเฉพาะหน้าเหล่านั้น", "gemini+local"
    return text, None, "gemini"
