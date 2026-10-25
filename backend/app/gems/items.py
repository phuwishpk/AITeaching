"""ครูตรวจและแก้คลังโจทย์ของ Gem ทีละข้อ (Human-in-the-Loop)

สถานะของโจทย์: ใช้งานอยู่ · ติดธง (Answer Key Check ไม่ผ่าน ซ่อนจากนักเรียน)
· รอครูอนุมัติ (AI สร้างจากปุ่มสร้างเพิ่ม ซ่อนจากนักเรียน) · สร้างสดรอตรวจย้อนหลัง (นักเรียนใช้ได้แล้ว)
ข้อที่ครูแก้หรือเพิ่มเองถือว่าครูตรวจแล้ว ธงและสถานะรอตรวจจึงหายไป ครูเป็นผู้ตัดสินสุดท้าย
"""

from .. import db
from ..content.readiness import _has_answer
from ..engine.answers import answer_display, parse_number
from . import builder, manage, verify, versions

KINDS = ("main", "isomorphic", "remedial", "challenge")
FORMATS = ("numeric", "mcq", "short")
LETTERS = "abcdefgh"


class ItemError(Exception):
    pass


def status(item: dict) -> str:
    if item.get("flag"):
        return "flagged"
    if item.get("review") == builder.REVIEW_PENDING:
        return "pending"
    if item.get("review") == builder.REVIEW_CHECK:
        return "check"
    return "active"


def _bank(gem_id: str) -> tuple[dict, dict]:
    gem = manage.get(gem_id)
    subject = db.get_subject(gem.get("subject_id") or "")
    if subject is None:
        raise ItemError("Gem นี้ยังไม่มีคลังโจทย์")
    return gem, subject


def listing(gem_id: str) -> dict:
    """ทุกข้อในคลังรุ่นปัจจุบันพร้อมเฉลย สำหรับครูตรวจและแก้"""
    _, subject = _bank(gem_id)
    concepts = {c["id"]: c["name"] for c in subject["concepts"]}
    tags = {t["id"]: t for t in subject.get("bug_tags", [])}
    rows = []
    for it in subject["items"]:
        rows.append({
            **{k: it.get(k) for k in ("id", "kind", "format", "prompt", "math", "options", "answer", "hints",
                                      "difficulty", "concept", "iso_of", "isomorphs", "flag", "live", "source")},
            "status": status(it), "answer_text": answer_display(it), "concept_name": concepts.get(it["concept"]),
            # คำตอบผิดที่ระบบรู้จักในข้อนี้ (Bug Library) และคำใบ้เฉพาะคำตอบผิดนั้น ถ้าครูกำหนดไว้
            "bugs": [{"answer": b["answer"], "tag": b["tag"], "type": (tags.get(b["tag"]) or {}).get("type"),
                      "name": (tags.get(b["tag"]) or {}).get("name", b["tag"]), "hints": b.get("hints") or {}}
                     for b in it.get("bugs", [])],
        })
    return {
        "items": rows,
        "concepts": [{"id": c["id"], "name": c["name"]} for c in subject["concepts"]],
        "target": subject["question_sets"][0]["target_concept"],
        "stats": builder.bank_stats(subject),
    }


def _clean(data: dict, existing: dict | None) -> dict:
    """ตรวจข้อมูลที่ครูกรอก แล้วแปลงเป็นรูปที่ engine ใช้"""
    answer_format = data.get("format", (existing or {}).get("format", "numeric"))
    if answer_format not in FORMATS:
        raise ItemError("รูปแบบคำตอบต้องเป็น ตัวเลข ปรนัย หรือคำตอบสั้น")
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        raise ItemError("ต้องมีคำสั่งโจทย์")
    item = {
        "prompt": prompt,
        "math": builder.plain_math(data.get("math")),
        "format": answer_format,
        "difficulty": max(0.0, min(1.0, float(data.get("difficulty", (existing or {}).get("difficulty", 0.5))))),
    }
    hints = data.get("hints") or {}
    item["hints"] = {str(level): str(hints.get(str(level), "")).strip() or builder.FALLBACK_HINTS[level - 1]
                     for level in (1, 2, 3)}
    answer = data.get("answer") or {}
    if answer_format == "numeric":
        value = parse_number(str(answer.get("value", "")))
        if value is None:
            raise ItemError("เฉลยต้องเป็นตัวเลข เช่น 4, -2.5 หรือ 3/4")
        item["answer"] = {"value": int(value) if value.denominator == 1 else round(float(value), 4)}
        item["options"] = []
    elif answer_format == "mcq":
        options = [str(o.get("text", "")).strip() for o in data.get("options") or [] if str(o.get("text", "")).strip()]
        if len(options) < 2:
            raise ItemError("ข้อปรนัยต้องมีตัวเลือกอย่างน้อย 2 ข้อ")
        item["options"] = [{"id": LETTERS[i], "text": text} for i, text in enumerate(options[:8])]
        correct = str(answer.get("option", "")).lower()
        if correct not in {o["id"] for o in item["options"]}:
            raise ItemError("เลือกตัวเลือกที่ถูกก่อนบันทึก")
        item["answer"] = {"option": correct}
    else:
        accepted = answer.get("accepted") or []
        accepted = [str(a).strip() for a in (accepted if isinstance(accepted, list) else [accepted]) if str(a).strip()]
        if not accepted:
            raise ItemError("ใส่คำตอบที่ยอมรับอย่างน้อย 1 คำ")
        item["answer"] = {"accepted": accepted}
        item["options"] = []
    if not _has_answer(item):
        raise ItemError("เฉลยไม่ครบ")
    return item


def save(gem_id: str, item_id: str | None, data: dict) -> dict:
    """เพิ่มหรือแก้โจทย์ ข้อที่ครูบันทึกถือว่าครูตรวจแล้ว คืนคำเตือนถ้า sympy คำนวณได้ไม่ตรงกับเฉลย"""
    gem, subject = _bank(gem_id)
    by_id = {it["id"]: it for it in subject["items"]}
    qs = subject["question_sets"][0]
    if item_id:
        item = by_id.get(item_id)
        if item is None:
            raise ItemError("ไม่พบโจทย์ข้อนี้")
        old_format = item.get("format")
        item.update(_clean(data, item))
        # คำตอบผิดที่บันทึกไว้ (Bug Library ของข้อนี้) ใช้กับรูปแบบเดิมเท่านั้น เปลี่ยนรูปแบบจึงล้าง
        if item["format"] != old_format:
            item["bugs"] = []
        note = f"ครูแก้โจทย์ {item_id}"
    else:
        kind = data.get("kind", "main")
        if kind not in KINDS:
            raise ItemError("ประเภทโจทย์ไม่ถูกต้อง")
        concept = data.get("concept") or qs["target_concept"]
        if concept not in {c["id"] for c in subject["concepts"]}:
            raise ItemError("ไม่พบมโนทัศน์ที่เลือก")
        parent = by_id.get(data.get("iso_of") or "")
        if kind == "isomorphic" and parent is None:
            raise ItemError("ข้อคู่ขนานต้องเลือกโจทย์หลักที่จับคู่ด้วย")
        n = 1 + sum(1 for i in by_id if i.startswith("K-") and "-I" not in i)
        item_id = f"{parent['id']}-K{len(parent.get('isomorphs', [])) + 1}" if parent and kind == "isomorphic" else f"K-{n:02d}"
        item = {"id": item_id, "kind": kind, "concept": parent["concept"] if parent else concept,
                "iso_of": parent["id"] if parent else None, "isomorphs": [], "bugs": [], "socratic": [],
                "expected_time": 45, "min_read_time": 3, **_clean(data, None)}
        subject["items"].append(item)
        if kind == "main":
            qs["main_items"].append(item_id)
        elif kind == "challenge":
            qs.setdefault("challenge_items", []).append(item_id)
        elif kind == "isomorphic":
            parent.setdefault("isomorphs", []).append(item_id)
        note = f"ครูเพิ่มโจทย์ {item_id}"
    item.pop("flag", None)
    item.pop("review", None)
    warning = verify.check_with_sympy(item)
    _save(gem, subject, note)
    return {**listing(gem_id), "saved": item_id, "warning": warning}


def use_suggested(gem_id: str, item_id: str) -> dict:
    """ครูกดใช้เฉลยที่ sympy คำนวณได้ของข้อที่ติดธง คำตอบผิดที่บันทึกไว้ซึ่งตรงกับเฉลยใหม่ถูกตัดออก"""
    gem, subject = _bank(gem_id)
    item = next((it for it in subject["items"] if it["id"] == item_id), None)
    if item is None:
        raise ItemError("ไม่พบโจทย์ข้อนี้")
    suggested = (item.get("flag") or {}).get("suggested")
    value = parse_number(str(suggested)) if suggested is not None else None
    if value is None or item.get("format") != "numeric":
        raise ItemError("ข้อนี้ไม่มีเฉลยที่ sympy คำนวณได้")
    old = item["answer"]["value"]
    item["answer"] = {"value": int(value) if value.denominator == 1 else round(float(value), 4)}
    item["bugs"] = [b for b in item.get("bugs", []) if parse_number(str(b["answer"])) != value]
    item.pop("flag", None)
    item.pop("review", None)
    _save(gem, subject, f"ครูแก้เฉลยข้อ {item_id} จาก {old} เป็น {suggested} ตามที่ sympy คำนวณ")
    return listing(gem_id)


def approve(gem_id: str, item_id: str) -> dict:
    gem, subject = _bank(gem_id)
    item = next((it for it in subject["items"] if it["id"] == item_id), None)
    if item is None:
        raise ItemError("ไม่พบโจทย์ข้อนี้")
    item.pop("flag", None)
    item.pop("review", None)
    # โจทย์หลักกับข้อคู่ขนานมาเป็นคู่ อนุมัติโจทย์หลักแล้วข้อคู่ขนานที่รออยู่ผ่านด้วย (ข้อที่ติดธงยังต้องตรวจเอง)
    for iso in subject["items"]:
        if iso["id"] in item.get("isomorphs", []) and not iso.get("flag"):
            iso.pop("review", None)
    _save(gem, subject, f"ครูอนุมัติโจทย์ {item_id}")
    return listing(gem_id)


def remove(gem_id: str, item_id: str) -> dict:
    """ลบโจทย์ ถ้าเป็นโจทย์หลักลบข้อคู่ขนานของข้อนั้นด้วย"""
    gem, subject = _bank(gem_id)
    item = next((it for it in subject["items"] if it["id"] == item_id), None)
    if item is None:
        raise ItemError("ไม่พบโจทย์ข้อนี้")
    removed = {item_id} | set(item.get("isomorphs", []))
    subject["items"] = [it for it in subject["items"] if it["id"] not in removed]
    for it in subject["items"]:
        it["isomorphs"] = [i for i in it.get("isomorphs", []) if i not in removed]
    for qs in subject["question_sets"]:
        qs["main_items"] = [i for i in qs["main_items"] if i not in removed]
        qs["challenge_items"] = [i for i in qs.get("challenge_items", []) if i not in removed]
    _save(gem, subject, f"ครูลบโจทย์ {item_id}")
    return listing(gem_id)


async def generate(gem_id: str, count: int) -> dict:
    """ปุ่ม "สร้างเพิ่ม": AI สร้างโจทย์หลักพร้อมข้อคู่ขนาน แต่ยังไม่ถึงนักเรียนจนครูอนุมัติ"""
    gem, subject = _bank(gem_id)
    try:
        await builder.generate_items(subject["id"], {"difficulty": 50, "count": max(1, min(6, count))},
                                     builder.REVIEW_PENDING)
    except builder.BuildError as error:
        raise ItemError(str(error)) from error
    gem, subject = _bank(gem_id)
    _save(gem, subject, f"AI สร้างโจทย์เพิ่ม {count} ข้อ รอครูอนุมัติ")
    return listing(gem_id)


def _save(gem: dict, subject: dict, note: str) -> None:
    db.save_subject(subject)
    gem.setdefault("build", {})["stats"] = builder.bank_stats(subject)
    db.save_gem(gem)
    versions.record(gem, "teacher" if note.startswith("ครู") else "AI", note)
    manage._invalidate()
