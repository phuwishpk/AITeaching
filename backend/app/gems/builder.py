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
from ..engine.answers import parse_number
from ..tutor import providers, service
from . import verify, versions

log = logging.getLogger(__name__)

STEPS = [
    ("plan", "วางแผนผังความรู้และ Bug Library"),
    ("items", "สร้างโจทย์หลักและข้อคู่ขนาน"),
    ("extras", "สร้างโจทย์ทบทวนพื้นฐานและโจทย์ท้าทาย"),
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
    "ทำตามคำสั่งของครูผู้สร้าง Gem และอ้างอิงเนื้อหาจาก <knowledge> เมื่อมี"
)

ITEM_SHAPE = """{
  "prompt": "คำสั่งของโจทย์ เช่น จงหาค่าของ x จากสมการ",
  "math": "สมการหรือนิพจน์แบบข้อความธรรมดา ห้ามใช้ LaTeX ใช้ / แทนเศษส่วน เช่น 2x + 3 = 11 หรือ 1/2 + 1/4 (ไม่มีให้ใส่ \\"\\")",
  "format": "numeric | mcq | short",
  "answer": "numeric: ตัวเลข เช่น 4 หรือ 2.5 · mcq: ลำดับตัวเลือกที่ถูก 0–3 · short: รายการคำตอบที่ยอมรับ เช่น [\\"สมบัติการเท่ากัน\\"]",
  "options": ["ตัวเลือก 4 ข้อ ใส่เฉพาะ mcq"],
  "difficulty": 0.5,
  "expected_time": 45,
  "hints": ["ระดับ 1 สะกิดจุดสังเกต", "ระดับ 2 อธิบายกฎสั้น ๆ", "ระดับ 3 แสดงเฉพาะขั้นแรก"],
  "socratic": ["คำถามนำสั้น ๆ 2 ข้อ"],
  "wrong_answers": [{"answer": "คำตอบผิดที่พบบ่อย (mcq ใช้ลำดับตัวเลือก)", "bug": "รหัส Bug Library เช่น M-1"}]
}"""


class BuildError(Exception):
    pass


def bank_sizes() -> dict:
    return {**BANK_DEFAULTS, **(db.get_setting("gem_bank", {}) or {})}


def bank_ids(gem_id: str, version: int) -> tuple[str, str]:
    subject_id = f"{gem_id}-b{version}"
    return subject_id, f"{subject_id}-set"


def knowledge_text(gem_id: str, limit: int = 12000) -> str:
    rows = db.query("SELECT filename, chunks FROM documents WHERE subject_id = ? ORDER BY uploaded_at", (gem_id,))
    parts, used = [], 0
    for row in rows:
        for chunk in db.loads(row["chunks"], []):
            if used + len(chunk) > limit:
                return "\n".join(parts)
            parts.append(f"[{row['filename']}] {chunk}")
            used += len(chunk)
    return "\n".join(parts)


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


async def ask_json(step: str, user: str, max_tokens: int = 12000) -> dict | list:
    frames = {"role": SYSTEM, "task": user[:8000]}
    problem = "เรียก AI ไม่สำเร็จ"
    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            await asyncio.sleep(RETRY_DELAYS[attempt - 1])
        result, errors = await service._call(SYSTEM, user, max_tokens=max_tokens, json_mode=True, timeout=180.0,
                                             backup_models=GEMINI_BACKUPS)
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
        '  "bugs": [{"type": "misconception หรือ slip", "name": "...", "description": "ลักษณะและตัวอย่างคำตอบผิด", '
        '"response": "ระบบควรช่วยอย่างไร", "socratic": "คำถามนำ 1 ข้อ", "prerequisite": "ลำดับของ prerequisites ที่ควรทบทวน หรือ null"}]'
        "  // misconception 3–5 รายการ slip 1–2 รายการ,\n"
        '  "walkthroughs": [{"concept": "target หรือลำดับของ prerequisites", "title": "...", "problem": "ตัวอย่างโจทย์", '
        '"steps": ["ขั้นที่ 1 ...", "ขั้นที่ 2 ...", "ตรวจคำตอบ ..."]}]  // หนึ่งตัวอย่างต่อมโนทัศน์\n'
        "}"
    )


def items_prompt(gem: dict, knowledge: str, plan: dict, count: int, band: str, batch: int) -> str:
    return (
        f"{gem_brief(gem, knowledge)}\n\n{plan_summary(plan)}\n\n"
        f"สร้างโจทย์หลักของมโนทัศน์เป้าหมาย {count} ข้อ ความยากช่วง {band} (ชุดที่ {batch} ห้ามใช้ตัวเลขซ้ำกับชุดอื่น) "
        "คละรูปแบบคำตอบ ส่วนใหญ่เป็น numeric และมี mcq อย่างน้อย 1 ข้อ (ถ้าวิชาไม่ใช่การคำนวณ ใช้ mcq กับ short) "
        "ทุกข้อต้องมี isomorph คือโจทย์คู่ขนานที่โครงสร้างเดียวกันแต่ตัวเลขหรือรายละเอียดต่างกัน รูปแบบคำตอบเดียวกัน\n"
        f'ตอบเป็น {{"items": [ITEM พร้อมฟิลด์ "isomorph": ITEM]}} โดย ITEM มีโครงสร้าง:\n{ITEM_SHAPE}'
    )


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
    bugs, counters = [], {"misconception": 0, "slip": 0}
    for b in raw.get("bugs") or []:
        kind = "slip" if b.get("type") == "slip" else "misconception"
        if not str(b.get("name", "")).strip():
            continue
        counters[kind] += 1
        index = b.get("prerequisite")
        prereq = f"C-P{int(index) + 1}" if isinstance(index, (int, float)) and 0 <= int(index) < len(prereqs) else None
        bugs.append({
            "id": f"{'M' if kind == 'misconception' else 'S'}-{counters[kind]}",
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
        "socratic": [str(s).strip() for s in raw.get("socratic") or [] if str(s).strip()][:3],
    }
    hints = [str(h).strip() for h in raw.get("hints") or [] if str(h).strip()][:3]
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
        tag = str(wrong.get("bug", "")).strip() if isinstance(wrong, dict) else ""
        if tag not in bug_ids:
            continue
        if answer_format == "numeric":
            value = parse_number(str(wrong.get("answer")))
            if value is not None:
                bugs.append({"answer": _stored_number(value), "tag": tag})
        elif answer_format == "mcq":
            index = _option_index(wrong.get("answer"), len(options))
            if index is not None and LETTERS[index] != item["answer"]["option"]:
                bugs.append({"answer": LETTERS[index], "tag": tag})
        elif str(wrong.get("answer", "")).strip():
            bugs.append({"answer": str(wrong["answer"]).strip(), "tag": tag})
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
        index = group.get("prerequisite")
        if not isinstance(index, (int, float)) or not 0 <= int(index) < len(prereq_ids):
            continue
        concept = prereq_ids[int(index)]
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
        concept = "C-T" if key in ("target", None) else (
            prereq_ids[int(key)] if isinstance(key, (int, float)) and 0 <= int(key) < len(prereq_ids) else None)
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
    }


def apply_checks(items: list[dict], solved: dict[int, object] | None) -> list[str]:
    """ติดธงข้อที่ไม่ผ่าน Answer Key Check คืนคำเตือนของการตรวจ"""
    warnings = []
    if solved is None:
        warnings.append("ตรวจชั้นที่ 2 (ให้ AI แก้ซ้ำ) ไม่สำเร็จ ใช้ผลจาก sympy อย่างเดียว")
    for i, item in enumerate(items):
        reasons = [r for r in (verify.check_with_sympy(item),
                               verify.check_resolved(item, solved.get(i)) if solved is not None else None) if r]
        if reasons:
            item["flag"] = {"reasons": reasons, "at": time.time()}
    return warnings


def usable(subject: dict) -> dict:
    """Subject ที่ตัด Flagged Item ออก (รวมรหัสที่อ้างถึงในชุดคำถามและข้อคู่ขนาน) ใช้ทั้งตรวจความพร้อมและตอนสอน"""
    flagged = {it["id"] for it in subject.get("items", []) if it.get("flag")}
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
        knowledge = knowledge_text(gem_id)
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

        _progress(gem, "plan")
        plan = normalize_plan(await part("plan", lambda: ask_json("plan", plan_prompt(gem, knowledge, sizes), 8000)))
        _progress(gem, "plan", "done")

        _progress(gem, "items")
        _progress(gem, "extras")
        half = max(1, sizes["main"] // 2)
        results = await asyncio.gather(
            part("items_1", lambda: ask_json(
                "items", items_prompt(gem, knowledge, plan, half, "0.2–0.5 (ง่ายถึงปานกลาง)", 1))),
            part("items_2", lambda: ask_json(
                "items", items_prompt(gem, knowledge, plan, sizes["main"] - half, "0.5–0.85 (ปานกลางถึงยาก)", 2))),
            part("extras", lambda: ask_json("extras", extras_prompt(gem, knowledge, plan, sizes))),
        )
        _progress(gem, "items", "done")
        _progress(gem, "extras", "done")
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
        _progress(gem, "save", "done")
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
        "formats": sorted({it["format"] for it in items}),
    }
