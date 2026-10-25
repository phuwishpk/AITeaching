"""สร้าง Item Bank ของ Gem ด้วย LLM (ADR-0003)

ขั้นตอน: วางแผน (Knowledge Map, Bug Library, Walkthrough) → สร้างโจทย์หลักพร้อมข้อคู่ขนาน
→ สร้างโจทย์ทบทวนพื้นฐานและโจทย์ท้าทาย → Answer Key Check → บันทึกเป็น Subject + Question Set
ผลลัพธ์อยู่ในรูปเดียวกับวิชาที่ครูเขียนเอง engine จึงใช้ 3 ด่าน บันไดคำใบ้ และ Remedial Loop ได้เหมือนเดิม
LLM เขียนเฉลยแบบมีโครงสร้าง แต่ engine เป็นคนตรวจคำตอบด้วยกฎ LLM ไม่ได้ตัดสินถูกผิด

คลังโจทย์แต่ละรุ่นเป็น Subject แยก (id = {gem}-b{รุ่น}) รุ่นเก่ายังอยู่ให้ Session ที่ค้างอยู่ทำต่อจนจบ
ไฟล์ความรู้ผูกกับตัว Gem (subject_id ในตาราง documents = id ของ Gem) ใช้ร่วมกันทุกรุ่น
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import Counter
from fractions import Fraction

from .. import db, settings_store
from ..content.readiness import check_set
from ..engine.answers import parse_number, same_number
from ..tutor import providers, service
from . import flowspec, verify, versions

log = logging.getLogger(__name__)

STEPS = [
    ("read", "อ่านไฟล์ความรู้"),
    ("plan", "วางแผนผังความรู้และ Bug Library"),
    ("items", "สร้างโจทย์หลักและข้อคู่ขนาน"),
    ("extras", "สร้างโจทย์ทบทวนพื้นฐานและโจทย์ท้าทาย"),
    ("flow", "ออกแบบ Flow การสอนจากคำสั่ง"),
    ("verify", "ตรวจเฉลย (sympy และให้ AI แก้ซ้ำ)"),
    ("save", "บันทึกและตรวจความพร้อม"),
]

BANK_DEFAULTS = {"main": 8, "prerequisites": 3, "remedial_per_concept": 3, "challenge": 2, "live_cap": 10}

# Slip ทั่วไปที่ engine จับได้เองจากตัวเลข (answers.match_bug) ทุก Gem จึงต้องมีสองแท็กนี้
GENERIC_SLIPS = [
    {"id": "S-ARITH", "type": "slip", "name": "คำนวณคลาดเคลื่อน", "prerequisite": None,
     "description": "ขั้นตอนถูกต้องแต่คำนวณตัวเลขคลาดไปเล็กน้อย",
     "response": "สะกิดให้ตรวจการคำนวณอีกรอบ ไม่ต้องอธิบายหลักการใหม่",
     "socratic": "ลองตรวจการคำนวณทีละขั้นอีกรอบ มีขั้นไหนที่คิดเร็วไปไหม"},
    {"id": "S-SIGNFLIP", "type": "slip", "name": "เผลอใส่เครื่องหมายผิด", "prerequisite": None,
     "description": "ได้ตัวเลขถูกแต่เครื่องหมายบวกลบกลับกัน",
     "response": "ชวนให้ตรวจเครื่องหมายของคำตอบ",
     "socratic": "ลองดูเครื่องหมายของคำตอบอีกครั้ง ควรเป็นบวกหรือลบ"},
]

FALLBACK_HINTS = [
    "ลองอ่านโจทย์อีกครั้ง มีจุดไหนที่ควรตรวจทานไหม",
    "ลองนึกถึงกฎหรือหลักการที่ใช้กับโจทย์แบบนี้ แล้วทำทีละขั้น",
    "ลองเริ่มจากขั้นแรกของวิธีทำ แล้วค่อยทำต่อเอง",
]

LETTERS = "abcd"

SYSTEM = (
    "คุณเป็นนักออกแบบบทเรียนให้ระบบติวเตอร์อัจฉริยะภาษาไทย ระบบตรวจคำตอบของนักเรียนด้วยกฎจากเฉลยที่คุณเขียน "
    "เฉลยจึงต้องถูกต้องแน่นอน และต้องตรวจได้ด้วยกฎ (ตัวเลข ตัวเลือก หรือคำตอบสั้น)\n"
    "ตอบเป็น JSON ตามโครงสร้างที่กำหนดเท่านั้น ห้ามมีข้อความอื่นนอก JSON\n"
    "ใช้ภาษาไทยที่นักเรียนระดับนั้นอ่านเข้าใจ คำใบ้ทุกระดับต้องเป็นคำถามนำแบบโสเครตีสและห้ามบอกคำตอบสุดท้าย "
    "คำใบ้ระดับ 3 แสดงได้แค่ขั้นแรกของวิธีทำ\n"
    "ทำตามคำสั่งของครูผู้สร้าง Gem เมื่อมี <knowledge> (เอกสารที่ครูแนบ) ทุกอย่างต้องมาจากเอกสารนั้น: มโนทัศน์ "
    "ความรู้พื้นฐาน ข้อผิดพลาด โจทย์ และคำใบ้ ใช้คำศัพท์ วิธีคิด และลำดับขั้นแบบที่เอกสารใช้ ห้ามใช้ความรู้นอกเอกสารที่ขัดกับเอกสาร "
    "ใช้ <memory> (สิ่งที่จดจากเอกสารก่อนสร้าง) เป็นรายการตรวจว่าใช้ครบ"
)

ITEM_SHAPE = """{
  "prompt": "คำสั่งของโจทย์ เช่น จงหาค่าของ x จากสมการ",
  "math": "สมการหรือนิพจน์แบบข้อความธรรมดา ห้ามใช้ LaTeX ใช้ / แทนเศษส่วน เช่น 2x + 3 = 11 หรือ 1/2 + 1/4 (ไม่มีให้ใส่ \\"\\")",
  "format": "numeric | mcq | short",
  "solution": ["คิดวิธีทำทีละขั้นให้ครบก่อนเขียน answer เช่น ขั้นที่ 1 2² = 4"],
  "answer": "numeric: ตัวเลข เช่น 4 หรือ 2.5 · mcq: ลำดับตัวเลือกที่ถูก 0–3 · short: รายการคำตอบที่ยอมรับ เช่น [\\"สมบัติการเท่ากัน\\"]",
  "options": ["ตัวเลือก 4 ข้อ ใส่เฉพาะ mcq"],
  "difficulty": 0.5,
  "expected_time": 45,
  "hints": ["ระดับ 1 สะกิดจุดสังเกต", "ระดับ 2 อธิบายกฎสั้น ๆ", "ระดับ 3 แสดงเฉพาะขั้นแรก"],
  "socratic": ["คำถามนำสั้น ๆ 2 ข้อ"],
  "source": "ส่วนของเอกสารที่ใช้สร้างข้อนี้ เช่น [ชื่อไฟล์] หัวข้อหรือข้อความสั้น ๆ (ไม่มีเอกสารให้เป็น \"\")",
  "wrong_answers": [{"answer": "คำตอบผิดที่พบบ่อย (mcq ใช้ลำดับตัวเลือก)", "bug": "รหัส Bug Library เช่น M-1", "hints": ["คำใบ้ระดับ 1–3 เฉพาะคำตอบผิดนี้ ใส่เมื่อครูกำหนดไว้ ไม่มีให้เป็น []"]}]
}"""


class BuildError(Exception):
    pass


def bank_sizes() -> dict:
    return {**BANK_DEFAULTS, **(db.get_setting("gem_bank", {}) or {})}


def bank_ids(gem_id: str, version: int) -> tuple[str, str]:
    subject_id = f"{gem_id}-b{version}"
    return subject_id, f"{subject_id}-set"


# ไฟล์ความรู้ที่ AI อ่านตอนสร้างคลัง: ส่งเต็มทั้งไฟล์ได้ถึง READ_LIMIT ตัวอักษร (Gemini รับบริบทได้ราว 1 ล้านโทเคน)
# ยาวกว่านั้นให้ AI สรุปทีละส่วน (DIGEST_SEGMENT ตัวอักษร สูงสุด DIGEST_MAX ส่วน) แล้วใช้บันทึกสรุปทั้งหมดแทน
# จึงอ่านครบทุกหน้า ไม่ใช่แค่ต้นไฟล์
READ_LIMIT = 600_000
CLAUDE_READ_LIMIT = 300_000
DIGEST_SEGMENT = 100_000
DIGEST_MAX = 20


def read_limit() -> int:
    """Gemini รับบริบทได้ราว 1 ล้านโทเคน (ภาษาไทยราว 0.8 โทเคนต่อตัวอักษร) Claude รับได้น้อยกว่า"""
    return READ_LIMIT if settings_store.ai_settings()["active"] == "gemini" else min(READ_LIMIT, CLAUDE_READ_LIMIT)


def documents_text(gem_id: str) -> list[tuple[str, str]]:
    rows = db.query("SELECT filename, chunks FROM documents WHERE subject_id = ? ORDER BY uploaded_at", (gem_id,))
    return [(row["filename"], "\n\n".join(db.loads(row["chunks"], []))) for row in rows]


def knowledge_text(gem_id: str, limit: int | None = None) -> str:
    """ไฟล์ความรู้ทั้งไฟล์ (ตัดที่ limit) แยกหัวข้อตามชื่อไฟล์"""
    limit = read_limit() if limit is None else limit
    parts, used = [], 0
    for filename, text in documents_text(gem_id):
        take = text[: max(0, limit - used)]
        if not take:
            break
        parts.append(f"### ไฟล์: {filename}\n{take}")
        used += len(take)
    return "\n\n".join(parts)


def digest_prompt(filename: str, segment: str, index: int, total: int) -> str:
    return (
        f"นี่คือส่วนที่ {index} จาก {total} ของไฟล์ความรู้ที่ครูแนบให้ Gem ({filename}) ระบบจะใช้บันทึกของคุณแทนต้นฉบับตอนสร้างบทเรียน "
        "จดทุกประเด็นที่ใช้สอนให้ครบ: มโนทัศน์ นิยาม กฎ ลำดับขั้นวิธีทำ ตัวอย่าง ความรู้พื้นฐานที่ต้องรู้ก่อน "
        "ข้อผิดพลาดที่พบบ่อยและสาเหตุ และแนวทางการสอนหรือคำใบ้ของครู "
        "โจทย์ เฉลย ตาราง คำตอบผิด และแนวทางคำใบ้ที่ครูเขียนไว้ ให้คัดลอกตรงตัวทุกตัวอักษร ห้ามสรุปย่อ\n"
        f'ตอบเป็น JSON: {{"notes": "บันทึกเป็นข้อความธรรมดา แบ่งหัวข้อได้"}}\n<knowledge>\n{segment}\n</knowledge>'
    )


async def read_knowledge(gem_id: str) -> dict:
    """อ่านไฟล์ความรู้ทั้งหมดของ Gem คืนข้อความที่ส่งให้ AI พร้อมสถิติว่าอ่านครอบคลุมแค่ไหน"""
    docs = documents_text(gem_id)
    total = sum(len(text) for _, text in docs)
    base = {"files": len(docs), "chars": total}
    if total <= read_limit():
        reading = {**base, "mode": "full", "read": total, "text": knowledge_text(gem_id)}
        return {**reading, "memory": await remember(reading["text"])} if docs else reading
    segments = [(name, text[i:i + DIGEST_SEGMENT]) for name, text in docs for i in range(0, len(text), DIGEST_SEGMENT)]
    used = segments[:DIGEST_MAX]
    gate = asyncio.Semaphore(4)

    async def digest(i: int, name: str, segment: str) -> str:
        async with gate:
            raw = await ask_json("digest", digest_prompt(name, segment, i + 1, len(used)), 8000)
        notes = raw.get("notes") if isinstance(raw, dict) else None
        return f"### สรุปส่วนที่ {i + 1} ({name})\n{str(notes or '').strip()}"

    notes = await asyncio.gather(*(digest(i, name, seg) for i, (name, seg) in enumerate(used)))
    read = sum(len(seg) for _, seg in used)
    text = "\n\n".join(notes)
    return {**base, "mode": "digest", "read": read, "segments": len(used), "text": text, "memory": await remember(text)}


MEMORY_SHAPE = """{
  "summary": "เอกสารนี้สอนอะไร ระดับชั้น และแนวทางหลักของครู 2–3 ประโยค",
  "concepts": [{"name": "มโนทัศน์หรือกฎ", "detail": "สาระสำคัญตามเอกสาร", "source": "[ชื่อไฟล์] หัวข้อ"}],
  "teacher_items": [{"problem": "โจทย์ที่ครูเขียนไว้ คัดลอกตรงตัว", "answer": "เฉลยตามเอกสาร", "source": "[ชื่อไฟล์] หัวข้อ"}],
  "misconceptions": [{"name": "ข้อผิดพลาด", "example": "ตัวอย่างคำตอบผิดตามเอกสาร", "source": "[ชื่อไฟล์] หัวข้อ"}],
  "teaching": ["แนวทางการสอน ลำดับขั้น หรือคำใบ้ที่ครูกำหนด"]
}"""


async def remember(knowledge: str) -> dict | None:
    """ขั้น "จำ" ก่อนสร้างโจทย์: AI อ่านเอกสารทั้งหมดแล้วจดสิ่งที่ต้องใช้ ครูตรวจได้ในหน้า Gem
    และใช้เป็นรายการตรวจตอนสร้างโจทย์ จดไม่สำเร็จก็สร้างต่อได้จากต้นฉบับ"""
    try:
        raw = await ask_json("memory", (
            "อ่านเอกสารที่ครูแนบใน <knowledge> ทั้งหมดอย่างละเอียด แล้วจดทุกอย่างที่ต้องใช้สร้างบทเรียน "
            "ครบทุกไฟล์และทุกหัวข้อ โจทย์ เฉลย และตัวอย่างคำตอบผิดที่ครูเขียนให้คัดลอกตรงตัว ตอบเป็น JSON:\n"
            f"{MEMORY_SHAPE}\n<knowledge>\n{knowledge}\n</knowledge>"), 12000)
    except BuildError:
        return None
    if not isinstance(raw, dict):
        return None
    def rows(key: str) -> list:
        return [r for r in raw.get(key) or [] if r][:40]
    return {"summary": _plain_text(raw.get("summary"))[:600], "concepts": rows("concepts"), "teacher_items": rows("teacher_items"),
            "misconceptions": rows("misconceptions"), "teaching": [_plain_text(t) for t in rows("teaching")]}


def memory_block(memory: dict | None) -> str:
    if not memory:
        return ""
    return "<memory>\nสิ่งที่จดจากเอกสารก่อนสร้าง ต้องใช้ให้ครบ:\n" + json.dumps(memory, ensure_ascii=False) + "\n</memory>"


def reading_note(reading: dict) -> str | None:
    if not reading.get("files"):
        return None
    share = 100 if not reading["chars"] else round(100 * reading["read"] / reading["chars"])
    if reading["mode"] == "full":
        return f"AI อ่านไฟล์ความรู้ครบ {reading['files']} ไฟล์ {reading['chars']:,} ตัวอักษร (100%)"
    return (f"ไฟล์ความรู้ยาว {reading['chars']:,} ตัวอักษร AI สรุปทีละส่วน {reading['segments']} ส่วนก่อนสร้างบทเรียน "
            f"อ่านครอบคลุม {share}%" + ("" if share >= 100 else " ส่วนท้ายที่เกินไม่ได้อ่าน แยกเป็นหลาย Gem จะอ่านได้ครบ"))


def gem_brief(gem: dict, knowledge: str) -> str:
    lines = [f"ชื่อ Gem: {gem['name']}"]
    if gem.get("description"):
        lines.append(f"คำอธิบาย: {gem['description']}")
    lines.append(f"คำสั่งของครู:\n{gem.get('instructions') or '(ไม่มี)'}")
    if knowledge:
        lines.append(f"<knowledge>\n{knowledge}\n</knowledge>")
    return "\n".join(lines)


def parse_json(text: str) -> dict | list:
    """แยก JSON ออกจากคำตอบของ LLM (บางโมเดลห่อด้วย ```json มีข้อความนำ หรือส่งเป็น list แทน object)"""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
        if not starts:
            raise BuildError("AI ไม่ได้ตอบเป็น JSON") from None
        start = min(starts)
        end = cleaned.rfind("}" if cleaned[start] == "{" else "]")
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as error:
            raise BuildError(f"อ่าน JSON จาก AI ไม่ได้: {error}") from None


def listing(payload, key: str) -> list:
    """รายการใต้คีย์ที่สั่งไว้ ถ้า AI ส่ง list มาตรง ๆ ก็ใช้ list นั้น"""
    if isinstance(payload, list):
        return payload
    value = payload.get(key) if isinstance(payload, dict) else None
    return value if isinstance(value, list) else []


# Provider มักตอบ "มีผู้ใช้มากชั่วคราว" หรือส่ง JSON ไม่ครบเป็นครั้งคราว จึงลองใหม่ก่อนยอมแพ้
RETRY_DELAYS = (5.0, 15.0)
GEMINI_BACKUPS = providers.GEMINI_BACKUPS


async def ask_json(step: str, user: str, max_tokens: int = 12000, thinking: str = "minimal") -> dict | list:
    frames = {"role": SYSTEM, "task": user[:8000]}
    problem = "เรียก AI ไม่สำเร็จ"
    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            await asyncio.sleep(RETRY_DELAYS[attempt - 1])
        result, errors = await service._call(SYSTEM, user, max_tokens=max_tokens, json_mode=True, timeout=300.0,
                                             backup_models=GEMINI_BACKUPS, thinking=thinking)
        service._log(None, f"gem_{step}", frames, None, result, result.text[:4000] if result else "", None, errors)
        if result is None:
            problem = "; ".join(errors) or problem
            continue
        try:
            return parse_json(result.text)
        except BuildError as error:
            problem = str(error)
    raise BuildError(problem)


# ---------------------------------------------------------------- prompt ของแต่ละขั้น

def plan_prompt(gem: dict, knowledge: str, sizes: dict) -> str:
    return (
        f"{gem_brief(gem, knowledge)}\n\n"
        "ออกแบบโครงของบทเรียนนี้เป็น JSON:\n"
        "{\n"
        '  "subject_name": "ชื่อวิชาหรือหน่วย", "grade": "ระดับชั้น เช่น ม.2",\n'
        '  "target": {"name": "มโนทัศน์เป้าหมายที่บทเรียนนี้ต้องการให้ทำได้", "description": "..."},\n'
        f'  "prerequisites": [{{"name": "...", "description": "...", "grade": "..."}}]  // {sizes["prerequisites"]} เรื่อง เรียงจากพื้นฐานที่สุด,\n'
        '  "bugs": [{"id": "รหัสที่ครูกำหนด เช่น BUG-M01 (ครูไม่ได้กำหนดให้เป็น \"\")", "type": "misconception หรือ slip", "name": "...", '
        '"description": "ลักษณะและตัวอย่างคำตอบผิด", '
        '"response": "ระบบควรช่วยอย่างไร", "socratic": "คำถามนำ 1 ข้อ", "prerequisite": "ลำดับของ prerequisites ที่ควรทบทวน หรือ null"}]'
        "  // misconception 3–5 รายการ slip 1–2 รายการ ถ้าครูมีตาราง Bug Library ให้ใช้ทุกรายการของครู ชื่อ ประเภท และรหัสตามครู,\n"
        '  "walkthroughs": [{"concept": "target หรือลำดับของ prerequisites", "title": "...", "problem": "ตัวอย่างโจทย์", '
        '"steps": ["ขั้นที่ 1 ...", "ขั้นที่ 2 ...", "ตรวจคำตอบ ..."]}]  // หนึ่งตัวอย่างต่อมโนทัศน์ '
        "ถ้าครูให้ลำดับขั้นของวิธีทำไว้ ให้เขียนขั้นแบบเดียวกัน แต่ตัวอย่างโจทย์ต้องใช้ตัวเลขต่างจากโจทย์ที่ครูกำหนด "
        "เพราะโจทย์ของครูจะอยู่ในคลังโจทย์ ตัวอย่างจะเฉลยโจทย์ในคลังไม่ได้\n"
        "}"
    )


def items_prompt(gem: dict, knowledge: str, plan: dict, count: int, band: str, batch: int) -> str:
    return (
        f"{gem_brief(gem, knowledge)}\n\n{plan_summary(plan)}\n\n"
        f"สร้างโจทย์หลักของมโนทัศน์เป้าหมาย {count} ข้อ ความยากช่วง {band} (ชุดที่ {batch} ห้ามใช้ตัวเลขซ้ำกับชุดอื่น) "
        + (TEACHER_ITEMS_FIRST if batch == 1 else TEACHER_ITEMS_ELSEWHERE) +
        "คละรูปแบบคำตอบ ส่วนใหญ่เป็น numeric และมี mcq อย่างน้อย 1 ข้อ (ถ้าวิชาไม่ใช่การคำนวณ ใช้ mcq กับ short) "
        "ทุกข้อต้องมี isomorph คือโจทย์คู่ขนานที่โครงสร้างเดียวกันแต่ตัวเลขหรือรายละเอียดต่างกัน รูปแบบคำตอบเดียวกัน\n"
        f'ตอบเป็น {{"items": [ITEM พร้อมฟิลด์ "isomorph": ITEM]}} โดย ITEM มีโครงสร้าง:\n{ITEM_SHAPE}'
    )


# โจทย์ที่ครูกำหนดไว้ในคำสั่งหรือไฟล์ความรู้ ใช้ตามที่ครูให้ทุกตัวอักษร (ชุดที่ 1 เท่านั้น กันซ้ำ)
TEACHER_ITEMS_FIRST = (
    "ถ้าคำสั่งของครูหรือ <knowledge> มีโจทย์ที่ครูกำหนดไว้ (เช่น คลังโจทย์มาตรฐาน พร้อมเฉลย ลำดับขั้น หรือตารางคำตอบผิด) "
    "ให้ใส่โจทย์เหล่านั้นเป็นข้อแรก ๆ ของชุดนี้ ใช้ตัวเลข นิพจน์ และเฉลยตามที่ครูให้ทุกตัวอักษร (นับรวมในจำนวนข้อ) "
    "ใส่ wrong_answers ทุกคำตอบผิดในตารางของครู พร้อมรหัส Bug และ hints ระดับ 1–3 ตามแนวทางคำใบ้ของครู "
    "และใช้แนวทางนั้นเขียน hints ของข้อด้วย "
)
TEACHER_ITEMS_ELSEWHERE = "ห้ามใช้โจทย์ที่ครูกำหนดไว้ในคำสั่งหรือไฟล์ (ใส่ไว้ในชุดแรกแล้ว) "


def extras_prompt(gem: dict, knowledge: str, plan: dict, sizes: dict) -> str:
    prereqs = "\n".join(f"{i}. {p['name']}: {p.get('description', '')}" for i, p in enumerate(plan["prerequisites"]))
    return (
        f"{gem_brief(gem, knowledge)}\n\n{plan_summary(plan)}\n\n"
        f"1) สร้างโจทย์ทบทวนพื้นฐานเรื่องละ {sizes['remedial_per_concept']} ข้อ (ง่าย ใช้ปูพื้นก่อนกลับไปทำโจทย์หลัก) ของเรื่องต่อไปนี้:\n"
        f"{prereqs}\n"
        f"2) สร้างโจทย์ท้าทายของมโนทัศน์เป้าหมาย {sizes['challenge']} ข้อ (ยากกว่าโจทย์หลัก)\n"
        '{"remedial": [{"prerequisite": ลำดับเรื่อง, "items": [ITEM]}], "challenge": [ITEM]}\n'
        f"โดย ITEM มีโครงสร้าง:\n{ITEM_SHAPE}"
    )


def resolve_prompt(items: list[dict]) -> str:
    lines = []
    for i, it in enumerate(items):
        line = f"{i}. {it['prompt']} {it.get('math') or ''}".strip()
        if it["format"] == "mcq":
            line += " ตัวเลือก: " + " ".join(f"({o['id']}) {o['text']}" for o in it["options"])
            line += " [ตอบเป็นตัวอักษรของตัวเลือก]"
        elif it["format"] == "numeric":
            line += " [ตอบเป็นตัวเลข]"
        else:
            line += " [ตอบเป็นข้อความสั้น]"
        lines.append(line)
    return (
        "แก้โจทย์ต่อไปนี้ทุกข้ออย่างระมัดระวัง คิดทีละขั้นในใจ แล้วตอบเฉพาะคำตอบสุดท้าย\n"
        + "\n".join(lines)
        + '\n\nตอบเป็น JSON: {"answers": [{"i": ลำดับข้อ, "answer": คำตอบ}]}'
    )


def plan_summary(plan: dict) -> str:
    bugs = "\n".join(f"- {b['id']} ({b['type']}): {b['name']} — {b['description']}" for b in plan["bug_tags"])
    prereqs = ", ".join(p["name"] for p in plan["prerequisites"])
    return (
        f"มโนทัศน์เป้าหมาย: {plan['target']['name']} — {plan['target'].get('description', '')}\n"
        f"ความรู้พื้นฐาน: {prereqs}\n"
        f"Bug Library (ใช้รหัสเหล่านี้ใน wrong_answers):\n{bugs}"
    )


# ---------------------------------------------------------------- แปลงผลจาก LLM เป็นรูปที่ engine ใช้

def normalize_plan(raw: dict) -> dict:
    """ตรวจและเติมโครงจาก LLM ให้ครบ ใส่รหัสมโนทัศน์และรหัส Bug Library"""
    if not isinstance(raw, dict):
        raise BuildError("AI ส่งแผนผังความรู้ผิดรูปแบบ")
    target = raw.get("target") or {}
    if not str(target.get("name", "")).strip():
        raise BuildError("AI ไม่ได้กำหนดมโนทัศน์เป้าหมาย")
    prereqs = [p for p in raw.get("prerequisites") or [] if str(p.get("name", "")).strip()][:4]
    bugs, counters, used = [], {"misconception": 0, "slip": 0}, {g["id"] for g in GENERIC_SLIPS}
    for b in raw.get("bugs") or []:
        kind = "slip" if b.get("type") == "slip" else "misconception"
        if not str(b.get("name", "")).strip():
            continue
        counters[kind] += 1
        index = prereq_index(b.get("prerequisite"), prereqs)
        prereq = f"C-P{index + 1}" if index is not None else None
        # รหัสที่ครูกำหนด (เช่น BUG-M01) ใช้ตามครู ไม่มีหรือซ้ำก็ตั้งให้
        given = str(b.get("id") or "").strip().upper()
        bug_id = given if re.fullmatch(r"[A-Z][A-Z0-9-]{1,15}", given) and given not in used else (
            f"{'M' if kind == 'misconception' else 'S'}-{counters[kind]}")
        used.add(bug_id)
        bugs.append({
            "id": bug_id,
            "type": kind, "name": b["name"].strip(), "description": str(b.get("description", "")).strip(),
            "response": str(b.get("response", "")).strip(), "socratic": str(b.get("socratic", "")).strip(),
            "prerequisite": prereq if kind == "misconception" else None,
        })
    return {
        "subject_name": str(raw.get("subject_name") or "").strip(),
        "grade": str(raw.get("grade") or "").strip(),
        "target": {"name": target["name"].strip(), "description": str(target.get("description", "")).strip()},
        "prerequisites": prereqs,
        "bug_tags": bugs,
        "walkthroughs": raw.get("walkthroughs") or [],
    }


def _stored_number(value: Fraction):
    return int(value) if value.denominator == 1 else round(float(value), 4)


def to_item(raw: dict, item_id: str, concept: str, kind: str, bug_ids: set[str]) -> dict | None:
    """แปลงโจทย์หนึ่งข้อจาก LLM คืน None ถ้าเฉลยใช้ตรวจด้วยกฎไม่ได้"""
    if not isinstance(raw, dict) or not str(raw.get("prompt", "")).strip():
        return None
    options = [str(o).strip() for o in raw.get("options") or [] if str(o).strip()][:4]
    answer_format = raw.get("format")
    if answer_format not in ("numeric", "mcq", "short"):
        answer_format = "mcq" if options else ("short" if isinstance(raw.get("answer"), list) else "numeric")
    answer = raw.get("answer")
    item = {
        "id": item_id, "concept": concept, "kind": kind, "iso_of": None, "isomorphs": [],
        "format": answer_format,
        "prompt": str(raw["prompt"]).strip(),
        "math": plain_math(raw.get("math")),
        "difficulty": _clamp(raw.get("difficulty"), 0.0, 1.0, 0.5),
        "expected_time": int(_clamp(raw.get("expected_time"), 10, 300, 45)),
        "min_read_time": max(2, min(8, round(len(str(raw["prompt"])) / 40) + 2)),
        "socratic": [_plain_text(s) for s in raw.get("socratic") or [] if _plain_text(s)][:3],
        "source": _plain_text(raw.get("source"))[:200],
    }
    hints = [_plain_text(h) for h in raw.get("hints") or [] if _plain_text(h)][:3]
    hints += FALLBACK_HINTS[len(hints):]
    item["hints"] = {str(i + 1): text for i, text in enumerate(hints)}

    if answer_format == "numeric":
        value = parse_number(str(answer)) if answer is not None else None
        if value is None:
            return None
        item["answer"] = {"value": _stored_number(value)}
    elif answer_format == "mcq":
        if len(options) < 2:
            return None
        index = _option_index(answer, len(options))
        if index is None:
            return None
        item["options"] = [{"id": LETTERS[i], "text": text} for i, text in enumerate(options)]
        item["answer"] = {"option": LETTERS[index]}
    else:
        accepted = [str(a).strip() for a in (answer if isinstance(answer, list) else [answer]) if str(a or "").strip()]
        if not accepted:
            return None
        item["answer"] = {"accepted": accepted}

    bugs = []
    for wrong in raw.get("wrong_answers") or []:
        tag = str(wrong.get("bug", "")).strip().upper() if isinstance(wrong, dict) else ""
        if tag not in bug_ids:
            continue
        # คำใบ้เฉพาะคำตอบผิดนี้ (ตารางคำใบ้ตามลำดับของครู) ใช้แทนคำใบ้ของข้อเมื่อวินิจฉัยได้ตรงรหัสนี้
        bug_hints = [_plain_text(h) for h in wrong.get("hints") or [] if _plain_text(h)][:3]
        extra = {"hints": {str(i + 1): h for i, h in enumerate(bug_hints)}} if bug_hints else {}
        answers = wrong.get("answer")
        for one in answers if isinstance(answers, list) else [answers]:
            if answer_format == "numeric":
                value = parse_number(str(one))
                if value is not None and not same_number(value, item["answer"]["value"]):
                    bugs.append({"answer": _stored_number(value), "tag": tag, **extra})
            elif answer_format == "mcq":
                index = _option_index(one, len(options))
                if index is not None and LETTERS[index] != item["answer"]["option"]:
                    bugs.append({"answer": LETTERS[index], "tag": tag, **extra})
            elif str(one or "").strip():
                bugs.append({"answer": str(one).strip(), "tag": tag, **extra})
    item["bugs"] = bugs
    return item


def plain_math(value) -> str | None:
    """แปลงสมการที่ LLM เขียนแบบ LaTeX เป็นข้อความที่นักเรียนอ่านได้ และ sympy ตรวจได้"""
    text = str(value or "").strip().strip("$")
    text = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", text)
    text = text.replace("\\times", "×").replace("\\div", "÷").replace("\\cdot", "×").replace("\\left", "").replace("\\right", "")
    text = re.sub(r"\\[a-zA-Z]+", "", text).replace("\\", "").replace("{", "").replace("}", "")
    # ตัด "= ?" ที่ท้ายนิพจน์ โจทย์บอกอยู่แล้วว่าให้หาอะไร
    text = re.sub(r"\s*=\s*\?*\s*$", "", text).replace("?", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def prereq_index(value, prereqs: list[dict]) -> int | None:
    """ลำดับของ Prerequisite ที่ AI อ้างถึง: AI ตอบได้ทั้งเลขลำดับ ("0" หรือ 0) และชื่อเรื่อง"""
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if isinstance(value, (int, float)) or text.isdigit():
        index = int(float(text))
        return index if 0 <= index < len(prereqs) else None
    names = [str(p.get("name", "")).strip() for p in prereqs]
    if text in names:
        return names.index(text)
    close = [i for i, name in enumerate(names) if name and (name in text or text in name)]
    return close[0] if len(close) == 1 else None


def _plain_text(value) -> str:
    """ข้อความที่นักเรียนเห็น: เอา markdown ที่ LLM ชอบใส่ (` ** $) ออก"""
    return re.sub(r"[`$]|\*\*", "", str(value or "")).strip()


def _option_index(value, count: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and 0 <= int(value) < count:
        return int(value)
    text = str(value or "").strip().lower()
    if len(text) == 1 and text in LETTERS[:count]:
        return LETTERS.index(text)
    if text.isdigit() and 0 <= int(text) < count:
        return int(text)
    return None


def _clamp(value, low, high, default):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def assemble(gem: dict, version: int, plan: dict, main_batches: list[dict], extras: dict) -> dict:
    """รวมผลทุกขั้นเป็น Subject + Question Set ในรูปที่ engine ใช้"""
    subject_id, set_id = bank_ids(gem["id"], version)
    prereq_ids = [f"C-P{i + 1}" for i in range(len(plan["prerequisites"]))]
    concepts = [
        {"id": cid, "name": p["name"].strip(), "grade": str(p.get("grade", "")).strip(),
         "description": str(p.get("description", "")).strip(), "prerequisites": prereq_ids[:i][-1:]}
        for i, (cid, p) in enumerate(zip(prereq_ids, plan["prerequisites"]))
    ]
    concepts.append({"id": "C-T", "name": plan["target"]["name"], "grade": plan["grade"],
                     "description": plan["target"]["description"], "prerequisites": prereq_ids})
    bug_tags = plan["bug_tags"] + GENERIC_SLIPS
    bug_ids = {b["id"] for b in bug_tags}

    items, mains = [], []
    raw_mains = [raw for batch in main_batches for raw in listing(batch, "items")]
    for raw in raw_mains:
        main = to_item(raw, f"G-{len(mains) + 1:02d}", "C-T", "main", bug_ids)
        if main is None:
            continue
        iso = to_item(raw.get("isomorph") or {}, f"{main['id']}-I1", "C-T", "isomorphic", bug_ids)
        if iso is not None:
            iso["iso_of"] = main["id"]
            main["isomorphs"] = [iso["id"]]
        mains.append(main)
        items.extend([main] + ([iso] if iso else []))

    challenges = []
    for raw in listing(extras, "challenge"):
        item = to_item(raw, f"H-{len(challenges) + 1:02d}", "C-T", "challenge", bug_ids)
        if item:
            challenges.append(item)
    items.extend(challenges)

    for group in listing(extras, "remedial"):
        if not isinstance(group, dict):
            continue
        index = prereq_index(group.get("prerequisite"), plan["prerequisites"])
        if index is None:
            continue
        concept = prereq_ids[index]
        count = 0
        for raw in listing(group, "items"):
            item = to_item(raw, f"R-{int(index) + 1}-{count + 1:02d}", concept, "remedial", bug_ids)
            if item:
                item["difficulty"] = min(item["difficulty"], 0.35)
                items.append(item)
                count += 1

    walkthroughs = []
    for walk in plan["walkthroughs"]:
        key = walk.get("concept")
        index = prereq_index(key, plan["prerequisites"])
        concept = prereq_ids[index] if index is not None else (
            "C-T" if key in ("target", None, "") or str(key).strip() == plan["target"]["name"] else None)
        steps = [str(s).strip() for s in walk.get("steps") or [] if str(s).strip()]
        if concept and steps and concept not in {w["concept"] for w in walkthroughs}:
            walkthroughs.append({"concept": concept, "title": str(walk.get("title") or "ตัวอย่างทีละขั้น").strip(),
                                 "problem": str(walk.get("problem") or "").strip(), "steps": steps})

    return {
        "id": subject_id,
        "name": gem["name"],
        "grade": plan["grade"],
        "description": gem.get("description", ""),
        "concepts": concepts,
        "bug_tags": bug_tags,
        "items": items,
        "walkthroughs": walkthroughs,
        "question_sets": [{
            "id": set_id, "name": gem["name"], "description": gem.get("description", ""),
            "target_concept": "C-T", "main_items": [m["id"] for m in mains],
            "challenge_items": [c["id"] for c in challenges], "max_items": 20, "published": True,
        }],
        "gem": gem_meta(gem, version),
    }


def gem_meta(gem: dict, version: int) -> dict:
    """ส่วนของ Gem ที่ engine และ prompt ต้องใช้ระหว่างสอน (คัดลอกไว้ใน Subject ของคลังแต่ละรุ่น)"""
    return {
        "id": gem["id"], "bank_version": version, "name": gem["name"], "icon": gem.get("icon"),
        "color": gem.get("color"), "instructions": gem.get("instructions", ""),
        "tools": gem.get("tools", {}), "starter_prompts": gem.get("starter_prompts", []),
        "alert_rules": gem.get("alert_rules", {}), "live_cap": bank_sizes()["live_cap"],
        # Flow ที่ AI ออกแบบจากคำสั่งของครู (ADR-0004) ไม่มีก็ใช้ผังมาตรฐาน
        "flow": gem.get("flow") or flowspec.STANDARD,
    }


def apply_checks(items: list[dict], solved: dict[int, object] | None) -> list[str]:
    """ติดธงข้อที่ไม่ผ่าน Answer Key Check คืนคำเตือนของการตรวจ"""
    warnings = []
    if solved is None:
        warnings.append("ตรวจชั้นที่ 2 (ให้ AI แก้ซ้ำ) ไม่สำเร็จ ใช้ผลจาก sympy อย่างเดียว")
    for i, item in enumerate(items):
        # sympy คำนวณได้จริงเป็นผู้ตัดสิน (AI ที่แก้ซ้ำคิดเลขพลาดได้) ตรวจไม่ได้จึงใช้ผลที่ AI แก้ซ้ำ
        checked, reason = verify.sympy_check(item)
        if checked:
            reasons = [reason] if reason else []
        else:
            reasons = [r for r in (verify.check_resolved(item, solved.get(i)) if solved is not None else None,) if r]
        if reasons:
            item["flag"] = {"reasons": reasons, "at": time.time()}
            suggestion = verify.suggested_answer(item) if checked else None
            if suggestion:
                item["flag"]["suggested"] = suggestion
    return warnings


def usable(subject: dict) -> dict:
    """Subject ที่ตัด Flagged Item ออก (รวมรหัสที่อ้างถึงในชุดคำถามและข้อคู่ขนาน) ใช้ทั้งตรวจความพร้อมและตอนสอน"""
    # ข้อที่ติดธงและข้อที่ AI สร้างเพิ่มแต่ครูยังไม่อนุมัติ ไม่ถึงนักเรียน
    flagged = {it["id"] for it in subject.get("items", []) if it.get("flag") or it.get("review") == REVIEW_PENDING}
    if not flagged:
        return subject
    # โจทย์หลักที่ข้อคู่ขนานติดธงทั้งหมด ใช้ Isomorphic Test ไม่ได้ จึงพักไว้ด้วยจนครูตรวจ
    flagged |= {it["id"] for it in subject["items"]
                if it.get("isomorphs") and all(i in flagged for i in it["isomorphs"])}

    def keep(ids):
        return [i for i in ids or [] if i not in flagged]

    return {
        **subject,
        "items": [{**it, "isomorphs": keep(it.get("isomorphs"))} for it in subject["items"] if it["id"] not in flagged],
        "question_sets": [{**qs, "main_items": keep(qs.get("main_items")), "challenge_items": keep(qs.get("challenge_items"))}
                          for qs in subject.get("question_sets", [])],
    }


# ---------------------------------------------------------------- ตัวรันการสร้าง

_running: set[str] = set()


def is_running(gem_id: str) -> bool:
    return gem_id in _running


def _progress(gem: dict, step: str, status: str = "running", **extra):
    build = gem.setdefault("build", {})
    steps = build.setdefault("steps", [{"id": s, "label": label, "status": "pending"} for s, label in STEPS])
    for s in steps:
        if s["id"] == step:
            s["status"] = status
    build.update(step=step, **extra)
    db.save_gem(gem)


async def build(gem_id: str) -> None:
    """สร้าง Item Bank รุ่นใหม่ของ Gem เรียกเป็นงานเบื้องหลัง สถานะอยู่ใน gem["build"]"""
    gem = db.get_gem(gem_id)
    if gem is None or gem_id in _running:
        return
    _running.add(gem_id)
    version = int(gem.get("bank_version") or 0) + 1
    gem["build"] = {"status": "building", "started_at": time.time(), "version": version, "warnings": [],
                    "steps": [{"id": s, "label": label, "status": "pending"} for s, label in STEPS]}
    db.save_gem(gem)
    try:
        sizes = bank_sizes()
        # ผลของขั้นที่เคยผ่านแล้วใช้ซ้ำได้ ถ้าคำสั่งและไฟล์ยังเหมือนเดิม กดสร้างใหม่จึงทำต่อจากขั้นที่ค้าง
        key = _draft_key(gem, sizes)
        if (gem.get("draft") or {}).get("key") != key:
            gem["draft"] = {"key": key, "parts": {}}
        parts = gem["draft"]["parts"]

        async def part(name: str, make):
            if name not in parts:
                parts[name] = await make()
                db.save_gem(gem)
            return parts[name]

        _progress(gem, "read")
        reading = await part("knowledge", lambda: read_knowledge(gem_id))
        # ต้นฉบับก่อน (ส่วนที่เหมือนกันทุกคำขอ Gemini แคชให้) แล้วตามด้วยสิ่งที่จดไว้เป็นรายการตรวจ
        knowledge = "\n\n".join(p for p in (reading["text"], memory_block(reading.get("memory"))) if p)
        _progress(gem, "read", "done")

        _progress(gem, "plan")
        plan = normalize_plan(await part("plan", lambda: ask_json("plan", plan_prompt(gem, knowledge, sizes), 8000)))
        _progress(gem, "plan", "done")

        _progress(gem, "items")
        _progress(gem, "extras")
        redesign = flow_needs_design(gem)
        if redesign:
            _progress(gem, "flow")
        half = max(1, sizes["main"] // 2)

        async def design_flow():
            # ออกแบบ Flow ไม่สำเร็จไม่ทำให้การสร้างคลังล้ม และไม่เก็บผลที่ล้มไว้ในร่าง
            if "flow" in parts:
                return parts["flow"]
            try:
                parts["flow"] = await flowspec.design(gem, reading.get("memory"), plan["bug_tags"] + GENERIC_SLIPS)
            except BuildError as error:
                # ออกแบบไม่สำเร็จ: คลังโจทย์ยังสร้างต่อได้ Flow เดิม (ถ้ามี) ยังใช้อยู่ ครูกดออกแบบใหม่ในแท็บ Flow
                _progress(gem, "flow", "error")
                return {"error": str(error)}
            _progress(gem, "flow", "done")
            return parts["flow"]

        # รอทุกขั้นที่ทำพร้อมกันให้จบก่อนรายงานข้อผิดพลาด ขั้นที่สำเร็จจึงถูกเก็บในร่าง กดสร้างใหม่ทำต่อเฉพาะขั้นที่ล้ม
        results = await asyncio.gather(
            part("items_1", lambda: ask_json(
                "items", items_prompt(gem, knowledge, plan, half, "0.2–0.5 (ง่ายถึงปานกลาง)", 1))),
            part("items_2", lambda: ask_json(
                "items", items_prompt(gem, knowledge, plan, sizes["main"] - half, "0.5–0.85 (ปานกลางถึงยาก)", 2))),
            part("extras", lambda: ask_json("extras", extras_prompt(gem, knowledge, plan, sizes))),
            design_flow() if redesign else asyncio.sleep(0),
            return_exceptions=True,
        )
        failed = next((r for r in results if isinstance(r, BaseException)), None)
        if failed:
            raise failed
        _progress(gem, "items", "done")
        _progress(gem, "extras", "done")
        flow, flow_error = None, None
        if redesign and results[3].get("error"):
            flow_error = results[3]["error"]
        elif redesign:
            flow = {**results[3], "instructions_key": instructions_key(gem)}
            gem["flow"] = flow
        _progress(gem, "flow", "done")
        subject = assemble(gem, version, plan, list(results[:2]), results[2])
        if not subject["question_sets"][0]["main_items"]:
            raise BuildError("AI สร้างโจทย์หลักที่ตรวจด้วยกฎได้ไม่ได้เลย ลองปรับคำสั่งให้ชัดขึ้น")

        _progress(gem, "verify")
        try:
            answers = await ask_json("verify", resolve_prompt(subject["items"]), 4000)
            solved = {int(a["i"]): a.get("answer") for a in listing(answers, "answers")
                      if isinstance(a, dict) and str(a.get("i", "")).lstrip("-").isdigit()}
        except BuildError:
            solved = None
        warnings = apply_checks(subject["items"], solved)
        _progress(gem, "verify", "done")

        _progress(gem, "save")
        db.save_subject(subject)
        readiness = check_set(usable(subject), subject["question_sets"][0]["id"])
        gem = db.get_gem(gem_id) or gem
        if flow:
            gem["flow"] = flow
        gem.pop("draft", None)
        gem.update(bank_version=version, subject_id=subject["id"], set_id=subject["question_sets"][0]["id"])
        _retire_old_banks(gem_id, keep=subject["id"])
        flagged = [it["id"] for it in subject["items"] if it.get("flag")]
        # Gem สร้างข้อคู่ขนานข้อละ 1 ข้อตามที่ตกลงไว้ คำเตือน "ควรมีอย่างน้อย 2 ข้อ" จึงไม่ต้องแสดง
        notes = [w for w in readiness["warnings"] if "มี Isomorphic Item 1 ข้อ" not in w]
        gem["build"].update(
            status="ready", finished_at=time.time(), warnings=warnings + notes,
            errors=readiness["errors"], stats=bank_stats(subject),
        )
        if flagged:
            gem["build"]["warnings"].insert(0, f"ติดธง {len(flagged)} ข้อ ซ่อนจากนักเรียนจนกว่าครูยืนยัน")
        # สิ่งที่ AI อ่านจากไฟล์ความรู้ เก็บไว้ใช้ตอนสร้างโจทย์สดด้วย และบอกครูว่าอ่านครอบคลุมแค่ไหน
        gem["knowledge"] = {k: reading[k] for k in reading}
        gem["build"]["reading"] = {k: v for k, v in reading.items() if k != "text"}
        note = reading_note(reading)
        if note:
            gem["build"]["warnings"].insert(0, note)
            mains = [it for it in subject["items"] if it["kind"] in ("main", "challenge")]
            cited = sum(1 for it in mains if it.get("source"))
            gem["build"]["warnings"].insert(1, f"โจทย์หลักและโจทย์ท้าทาย {cited}/{len(mains)} ข้อระบุส่วนของเอกสารที่ใช้สร้าง")
            if reading.get("files") and not reading.get("memory"):
                gem["build"]["warnings"].insert(1, "AI จดสิ่งที่จำจากเอกสารไม่สำเร็จ สร้างจากต้นฉบับโดยตรงแทน")
        if flow_error:
            gem["build"]["warnings"].insert(0, f"ออกแบบ Flow การสอนไม่สำเร็จ: {flow_error}")
        if flow and flow.get("mode") == "custom":
            gem["build"]["warnings"].append("AI ออกแบบ Flow การสอนจากคำสั่งแล้ว ตรวจและปรับได้ในแท็บ Flow")
        elif (gem.get("flow") or {}).get("source") == "teacher":
            gem["build"]["warnings"].append("ใช้ Flow ที่ครูแก้ไว้ต่อ กดออกแบบใหม่จากคำสั่งในแท็บ Flow ได้")
        _progress(gem, "save", "done")
        service.forget_memory(gem_id)
        versions.record(gem, "AI", f"สร้างคลังโจทย์รุ่นที่ {version}")
    except Exception as error:  # noqa: BLE001 งานเบื้องหลังต้องจบด้วยสถานะเสมอ ไม่ค้างที่ "กำลังสร้าง"
        message = str(error) if isinstance(error, BuildError) else f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {type(error).__name__}: {error}"
        if not isinstance(error, BuildError):
            log.exception("สร้าง Item Bank ของ %s ไม่สำเร็จ", gem_id)
        gem = db.get_gem(gem_id) or gem
        gem["build"].update(status="error", error=message, finished_at=time.time())
        for s in gem["build"]["steps"]:
            if s["status"] == "running":
                s["status"] = "error"
        db.save_gem(gem)
    finally:
        _running.discard(gem_id)


# สถานะการตรวจของครู (Human-in-the-Loop) นอกเหนือจากธงของ Answer Key Check
# pending = AI สร้างจากปุ่ม "สร้างเพิ่ม" ยังไม่ถึงนักเรียนจนครูอนุมัติ
# check = AI สร้างสดระหว่างเรียน นักเรียนใช้ได้ทันที แต่รอครูตรวจย้อนหลัง
REVIEW_PENDING = "pending"
REVIEW_CHECK = "check"


async def generate_live(subject_id: str, request: dict) -> list[str]:
    """Live Generation: สร้างโจทย์หลักพร้อมข้อคู่ขนานระหว่างเรียน ใช้ได้ทันทีแต่รอครูตรวจย้อนหลัง"""
    return await generate_items(subject_id, request, REVIEW_CHECK)


async def generate_items(subject_id: str, request: dict, review: str) -> list[str]:
    """สร้างโจทย์หลักพร้อมข้อคู่ขนานเพิ่มเข้าคลังรุ่นนี้ ตรวจเฉลยเหมือนตอนสร้างคลัง

    คืนรหัสโจทย์หลักใหม่ที่ผ่านการตรวจ ข้อที่ไม่ผ่านเก็บไว้แบบติดธงให้ครูตรวจทีหลัง
    """
    subject = db.get_subject(subject_id)
    if not subject or not subject.get("gem"):
        raise BuildError("ชุดคำถามนี้ไม่ใช่ Gem สร้างโจทย์สดไม่ได้")
    gem = subject["gem"]
    concepts = {c["id"]: c for c in subject["concepts"]}
    target = concepts[subject["question_sets"][0]["target_concept"]]
    plan = {
        "target": {"name": target["name"], "description": target.get("description", "")},
        "prerequisites": [concepts[c] for c in target.get("prerequisites", []) if c in concepts],
        "bug_tags": subject["bug_tags"],
    }
    level = int(request.get("difficulty", 50))
    band = f"{max(0, level - 15) / 100:.2f}–{min(100, level + 15) / 100:.2f}"
    existing = "\n".join(f"- {it.get('math') or it['prompt']}" for it in subject["items"] if it["kind"] in ("main", "isomorphic"))
    knowledge = (gem.get("knowledge") or {}).get("text") or knowledge_text(gem["id"])
    prompt = (items_prompt(gem, knowledge, plan, int(request.get("count", 2)), band, 9)
              + f"\n\nโจทย์ที่มีอยู่แล้ว ห้ามซ้ำ:\n{existing}")
    raw = await ask_json("live", prompt)
    bug_ids = {b["id"] for b in subject["bug_tags"]}
    taken = {it["id"] for it in subject["items"]}
    new_items, mains = [], []
    for entry in listing(raw, "items"):
        n = 1 + sum(1 for i in taken if re.fullmatch(r"L-\d+", i))  # นับเฉพาะโจทย์หลัก ไม่นับข้อคู่ขนาน L-xx-I1
        main = to_item(entry, f"L-{n:02d}", target["id"], "main", bug_ids)
        if main is None:
            continue
        iso = to_item(entry.get("isomorph") or {}, f"{main['id']}-I1", target["id"], "isomorphic", bug_ids)
        if iso:
            iso["iso_of"] = main["id"]
            main["isomorphs"] = [iso["id"]]
        main["live"] = review == REVIEW_CHECK
        taken |= {main["id"]} | ({iso["id"]} if iso else set())
        mains.append(main)
        new_items += [main] + ([iso] if iso else [])
    if not mains:
        raise BuildError("AI ไม่ได้ส่งโจทย์ที่ตรวจด้วยกฎได้")
    try:
        answers = await ask_json("verify", resolve_prompt(new_items), 2000)
        solved = {int(a["i"]): a.get("answer") for a in listing(answers, "answers")
                  if isinstance(a, dict) and str(a.get("i", "")).lstrip("-").isdigit()}
    except BuildError:
        solved = None
    apply_checks(new_items, solved)
    for item in new_items:
        item["review"] = review
    # อ่านใหม่ก่อนบันทึก ระหว่างรอ AI ครูอาจแก้คลังหรือนักเรียนคนอื่นสร้างโจทย์เพิ่ม
    subject = db.get_subject(subject_id)
    subject["items"] += new_items
    subject["question_sets"][0]["main_items"] += [m["id"] for m in mains]
    db.save_subject(subject)
    return [m["id"] for m in mains if not m.get("flag")]


def instructions_key(gem: dict) -> str:
    raw = json.dumps([gem.get("instructions"), gem.get("tools")], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def flow_needs_design(gem: dict) -> bool:
    """ออกแบบ Flow ใหม่เมื่อคำสั่งหรือเครื่องมือเปลี่ยน แต่ไม่ทับ Flow ที่ครูแก้หรือเลือกเอง"""
    flow = gem.get("flow") or {}
    if flow.get("mode") != "custom":
        return True  # ยังไม่มี Flow ที่ออกแบบจาก prompt (ผังมาตรฐานเป็นแค่แม่แบบอ้างอิง)
    if flow.get("source") == "teacher":
        return False
    return flow.get("instructions_key") != instructions_key(gem)


def _draft_key(gem: dict, sizes: dict) -> str:
    files = [r["id"] for r in db.query("SELECT id FROM documents WHERE subject_id = ? ORDER BY id", (gem["id"],))]
    raw = json.dumps([gem["name"], gem.get("description"), gem.get("instructions"), files, sizes], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _retire_old_banks(gem_id: str, keep: str) -> None:
    """คลังรุ่นเก่าไม่แสดงให้นักเรียนเลือกแล้ว แต่ยังอยู่ให้ Session ที่ค้างทำต่อจนจบ"""
    for subject in db.list_subjects():
        if (subject.get("gem") or {}).get("id") == gem_id and subject["id"] != keep:
            for qs in subject.get("question_sets", []):
                qs["published"] = False
            db.save_subject(subject)


def bank_stats(subject: dict) -> dict:
    items = subject["items"]
    kinds = Counter(it["kind"] for it in items)
    return {
        "concepts": len(subject["concepts"]), "bugs": len(subject["bug_tags"]),
        "main": kinds["main"], "isomorphic": kinds["isomorphic"], "remedial": kinds["remedial"],
        "challenge": kinds["challenge"], "flagged": sum(1 for it in items if it.get("flag")),
        "pending": sum(1 for it in items if it.get("review") == REVIEW_PENDING and not it.get("flag")),
        "check": sum(1 for it in items if it.get("review") == REVIEW_CHECK and not it.get("flag")),
        "formats": sorted({it["format"] for it in items}),
    }
