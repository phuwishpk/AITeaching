"""สร้าง แก้ และลบ Gem รวมถึงไฟล์ความรู้และการยืนยัน Flagged Item

ข้อมูลของ Gem (ชื่อ คำสั่ง เครื่องมือ) อยู่ในตาราง gems ส่วน Item Bank แต่ละรุ่นอยู่ในตาราง subjects
เมื่อครูแก้ชื่อ คำอธิบาย คำสั่ง หรือเครื่องมือโดยไม่สร้างคลังใหม่ จะคัดลอกค่าใหม่ไปที่คลังรุ่นปัจจุบันด้วย
"""

import secrets
import time

from .. import db, settings_store
from ..content.readiness import check_set
from ..engine.answers import answer_display
from ..tutor.prompt import constraints_frame
from . import alerts, builder, versions

ICONS = ["sparkles", "calculator", "book", "flask", "globe", "code", "palette", "music"]
COLORS = ["teal", "blue", "violet", "amber", "rose", "green"]
TOOLS = {"chat": True, "hints": True, "isomorphic": True, "walkthrough": True, "remedial": True}
EDITABLE = ("name", "description", "instructions", "icon", "color", "tools", "starter_prompts", "alert_rules")


class GemError(Exception):
    pass


def clean_fields(data: dict) -> dict:
    out = {}
    if "name" in data:
        out["name"] = str(data["name"] or "").strip()[:80]
    if "description" in data:
        out["description"] = str(data["description"] or "").strip()[:500]
    if "instructions" in data:
        out["instructions"] = str(data["instructions"] or "").strip()[:8000]
    if "icon" in data:
        out["icon"] = data["icon"] if data["icon"] in ICONS else ICONS[0]
    if "color" in data:
        out["color"] = data["color"] if data["color"] in COLORS else COLORS[0]
    if "tools" in data:
        tools = data["tools"] or {}
        out["tools"] = {key: bool(tools.get(key, default)) for key, default in TOOLS.items()}
    if "starter_prompts" in data:
        out["starter_prompts"] = [str(p).strip()[:120] for p in data["starter_prompts"] or [] if str(p).strip()][:4]
    if "alert_rules" in data:
        out["alert_rules"] = alerts.normalize(data["alert_rules"])
    return out


def create(data: dict, actor: str) -> dict:
    fields = clean_fields(data)
    if not fields.get("name"):
        raise GemError("Gem ต้องมีชื่อ")
    now = time.time()
    gem = {
        "id": f"gem-{secrets.token_hex(3)}",
        "name": fields["name"], "description": "", "instructions": "", "icon": ICONS[0], "color": COLORS[0],
        "tools": dict(TOOLS), "starter_prompts": [], "alert_rules": alerts.defaults(),
        "bank_version": 0, "subject_id": None, "set_id": None,
        "build": {"status": "idle"}, "created_at": now, "created_by": actor,
    }
    gem.update(fields)
    db.save_gem(gem)
    versions.record(gem, actor, "สร้าง Gem")
    return gem


def update(gem_id: str, data: dict, actor: str = "teacher") -> dict:
    gem = get(gem_id)
    fields = clean_fields(data)
    if "name" in fields and not fields["name"]:
        raise GemError("Gem ต้องมีชื่อ")
    before = {**gem, "alert_rules": alerts.normalize(gem.get("alert_rules"))}
    gem.update(fields)
    db.save_gem(gem)
    changed = versions.changes(before, gem)
    if changed:
        versions.record(gem, actor, "แก้" + " ".join(changed))
    _sync_bank(gem)
    return gem


def restore(gem_id: str, n: int, actor: str) -> dict:
    """ย้อนกลับไปเวอร์ชันเก่า: คืนชื่อ คำสั่ง เครื่องมือ และคลังโจทย์รุ่นที่ใช้ในเวอร์ชันนั้น"""
    gem = get(gem_id)
    if gem.get("build", {}).get("status") == "building":
        raise GemError("กำลังสร้างคลังโจทย์อยู่ รอให้เสร็จก่อนย้อนกลับ")
    snap = versions.get(gem_id, n)
    if snap is None:
        raise GemError("ไม่พบเวอร์ชันนี้")
    gem.update({key: snap.get(key) for key in versions.FIELDS})
    subject = db.get_subject(snap["subject_id"]) if snap.get("subject_id") else None
    if subject:
        gem.update({key: snap.get(key) for key in versions.BANK})
        for qs in subject.get("question_sets", []):
            qs["published"] = True
        db.save_subject(subject)
        builder._retire_old_banks(gem_id, keep=subject["id"])
        gem.setdefault("build", {})["stats"] = builder.bank_stats(subject)
    db.save_gem(gem)
    _sync_bank(gem)
    versions.record(gem, actor, f"ย้อนกลับไปเวอร์ชัน {n}")
    return gem


def _sync_bank(gem: dict) -> None:
    """คัดลอกชื่อ คำสั่ง และเครื่องมือไปที่คลังรุ่นปัจจุบัน นักเรียนจึงเห็นค่าใหม่โดยไม่ต้องสร้างคลังใหม่"""
    subject = db.get_subject(gem["subject_id"]) if gem.get("subject_id") else None
    if not subject:
        return
    subject["name"] = gem["name"]
    subject["description"] = gem.get("description", "")
    subject["gem"] = builder.gem_meta(gem, gem["bank_version"])
    for qs in subject.get("question_sets", []):
        qs["name"], qs["description"] = gem["name"], gem.get("description", "")
    db.save_subject(subject)
    _invalidate()


def get(gem_id: str) -> dict:
    gem = db.get_gem(gem_id)
    if gem is None:
        raise GemError("ไม่พบ Gem นี้")
    build = gem.get("build") or {}
    if build.get("status") == "building" and not builder.is_running(gem_id):
        # server เริ่มใหม่ระหว่างสร้าง งานเบื้องหลังหายไปแล้ว
        build.update(status="error", error="การสร้างหยุดกลางคันเพราะ server เริ่มใหม่ กดสร้างคลังโจทย์อีกครั้ง")
        db.save_gem(gem)
    return gem


def delete(gem_id: str) -> None:
    get(gem_id)
    for subject in db.list_subjects():
        if (subject.get("gem") or {}).get("id") == gem_id:
            db.delete_subject(subject["id"])
    db.execute("DELETE FROM documents WHERE subject_id = ?", (gem_id,))
    db.delete_gem(gem_id)
    _invalidate()


def can_build() -> str | None:
    """คืนเหตุผลถ้ายังเรียก AI ไม่ได้"""
    ai = settings_store.ai_settings()
    if ai["active"] == "offline":
        return "ระบบอยู่ใน Offline Mode สร้าง Gem ไม่ได้ ให้ Admin เปิด Provider ก่อน"
    if not any(settings_store.api_key(p)[0] for p in ("gemini", "claude")):
        return "ยังไม่มี API key ให้ Admin ใส่ Gemini API key ในหน้าตั้งค่าก่อน"
    return None


def files(gem_id: str) -> list[dict]:
    rows = db.query(
        "SELECT id, filename, kind, chars, warning, uploaded_at, chunks, reader FROM documents WHERE subject_id = ? ORDER BY uploaded_at",
        (gem_id,),
    )
    for row in rows:
        row["chunks"] = len(db.loads(row.pop("chunks"), []))
    return rows


def summary(gem: dict) -> dict:
    """ข้อมูลสำหรับการ์ดในรายการ Gem"""
    build = gem.get("build") or {}
    # นับจากคลังจริง ครูอาจแก้หรือลบข้อในแท็บคลังโจทย์หลังสร้างเสร็จ
    subject = db.get_subject(gem["subject_id"]) if gem.get("subject_id") else None
    return {
        "id": gem["id"], "name": gem["name"], "description": gem.get("description", ""),
        "icon": gem.get("icon"), "color": gem.get("color"), "bank_version": gem.get("bank_version", 0),
        "status": build.get("status", "idle"), "stats": builder.bank_stats(subject) if subject else None,
        "files": len(files(gem["id"])),
        "updated_at": db.query_one("SELECT updated_at FROM gems WHERE id = ?", (gem["id"],))["updated_at"],
    }


def detail(gem: dict) -> dict:
    """ข้อมูลเต็มสำหรับหน้าแก้ Gem: ฟอร์ม สถานะการสร้าง ไฟล์ และสรุปคลังโจทย์รุ่นปัจจุบัน"""
    subject = db.get_subject(gem["subject_id"]) if gem.get("subject_id") else None
    bank = None
    if subject:
        qs = subject["question_sets"][0]
        concepts = {c["id"]: c["name"] for c in subject["concepts"]}
        bank = {
            "subject_id": subject["id"], "set_id": qs["id"], "grade": subject.get("grade", ""),
            "target": concepts.get(qs["target_concept"]),
            "concepts": [{"id": c["id"], "name": c["name"], "prerequisites": c.get("prerequisites", [])}
                         for c in subject["concepts"]],
            "bugs": [{"id": b["id"], "type": b["type"], "name": b["name"]} for b in subject["bug_tags"]],
            "stats": builder.bank_stats(subject),
            "readiness": check_set(builder.usable(subject), qs["id"]),
            "flagged": [_brief(it, concepts) for it in subject["items"] if it.get("flag")],
            "samples": [_brief(it, concepts) for it in subject["items"] if it["kind"] == "main" and not it.get("flag")][:3],
        }
    return {
        **{k: gem.get(k) for k in ("id", "bank_version", "build", "created_at") + EDITABLE},
        "alert_rules": alerts.normalize(gem.get("alert_rules")),
        "files": files(gem["id"]),
        "bank": bank,
        "versions": versions.history(gem["id"]) or _first_version(gem),
        "locked_constraints": constraints_frame(),
        # สิ่งที่ AI อ่านและจดจากไฟล์ความรู้ก่อนสร้างคลังโจทย์รุ่นนี้ (ไม่ส่งต้นฉบับเต็มกลับไปที่หน้าเว็บ)
        "knowledge": {k: v for k, v in (gem.get("knowledge") or {}).items() if k != "text"} or None,
        "options": {"icons": ICONS, "colors": COLORS, "alert_situations": alerts.catalog()},
    }


def _first_version(gem: dict) -> list[dict]:
    """Gem ที่สร้างก่อนมีประวัติเวอร์ชัน: บันทึกสภาพปัจจุบันเป็นเวอร์ชันแรก"""
    versions.record(gem, "ระบบ", "บันทึกเวอร์ชันแรก")
    return versions.history(gem["id"])


def _brief(item: dict, concepts: dict) -> dict:
    return {
        "id": item["id"], "kind": item["kind"], "format": item["format"], "prompt": item["prompt"],
        "math": item.get("math"), "answer": answer_display(item), "concept": concepts.get(item["concept"]),
        "options": item.get("options"), "flag": item.get("flag"),
    }


def resolve_flag(gem_id: str, item_id: str, keep: bool) -> dict:
    """ครูยืนยันว่าเฉลยถูก (เอาธงออก) หรือลบข้อนั้นออกจากคลัง"""
    gem = get(gem_id)
    subject = db.get_subject(gem.get("subject_id") or "")
    item = next((it for it in (subject or {}).get("items", []) if it["id"] == item_id), None)
    if item is None:
        raise GemError("ไม่พบโจทย์ข้อนี้ในคลังรุ่นปัจจุบัน")
    if keep:
        item.pop("flag", None)
    else:
        removed = {item_id} | set(item.get("isomorphs", []))
        subject["items"] = [it for it in subject["items"] if it["id"] not in removed]
        for it in subject["items"]:
            it["isomorphs"] = [i for i in it.get("isomorphs", []) if i not in removed]
        for qs in subject["question_sets"]:
            qs["main_items"] = [i for i in qs["main_items"] if i not in removed]
            qs["challenge_items"] = [i for i in qs.get("challenge_items", []) if i not in removed]
    db.save_subject(subject)
    gem["build"]["stats"] = builder.bank_stats(subject)
    db.save_gem(gem)
    _invalidate()
    return detail(gem)


def _invalidate() -> None:
    from .. import services  # services import builder อยู่แล้ว import ตรงนี้กันวน
    services.invalidate_content()


def adopt_legacy() -> list[str]:
    """แปลงวิชาที่ครูเขียนเองแบบเดิม (ไม่มี Gem) เป็น Gem โดยใช้โจทย์เดิมเป็นคลังรุ่นที่ 1 (Q17)

    ไฟล์เอกสารของวิชาย้ายไปผูกกับ Gem ส่วนรหัสชุดคำถามไม่เปลี่ยน Session ที่ค้างอยู่จึงทำต่อได้
    วิชาที่มีหลายชุดคำถามข้ามไป เพราะ Gem หนึ่งตัวคือชุดคำถามหนึ่งชุด
    """
    adopted = []
    for subject in db.list_subjects():
        sets = subject.get("question_sets", [])
        if subject.get("gem") or len(sets) != 1:
            continue
        qs = sets[0]
        gem = create({"name": qs["name"], "description": qs.get("description") or subject.get("description", ""),
                      "icon": "calculator"}, "ระบบ")
        gem.update(bank_version=1, subject_id=subject["id"], set_id=qs["id"])
        gem["build"] = {"status": "ready", "finished_at": time.time(), "warnings": [], "errors": [],
                        "stats": builder.bank_stats(subject), "adopted": True}
        db.save_gem(gem)
        subject["gem"] = builder.gem_meta(gem, 1)
        db.save_subject(subject)
        db.execute("UPDATE documents SET subject_id = ? WHERE subject_id = ?", (gem["id"], subject["id"]))
        versions.record(gem, "ระบบ", "แปลงจากชุดคำถามที่ครูเขียนเอง")
        adopted.append(gem["id"])
    if adopted:
        _invalidate()
    return adopted
