"""ครูตรวจและปรับ Flow ที่ AI ออกแบบจากคำสั่ง (Human-in-the-Loop ของ Flow, ADR-0004)

AI ออกแบบตอนสร้างคลังโจทย์ หรือเมื่อครูกด "ออกแบบใหม่จากคำสั่ง" Flow ใช้กับนักเรียนทันทีเหมือนคลังโจทย์
แต่ขึ้นป้าย "ยังไม่ได้ตรวจ" จนครูกดยืนยัน ครูแก้ขั้น เส้น เงื่อนไข และตัวเลขได้ ทุกครั้งต้องผ่าน flowspec.validate
และบันทึกเป็นเวอร์ชันของ Gem ย้อนกลับได้ ครูเลือกกลับไปใช้ผังมาตรฐานของระบบได้เสมอ
"""

from .. import db
from . import builder, flowspec, manage, versions


def _subject(gem: dict) -> dict | None:
    return db.get_subject(gem.get("subject_id") or "")


def _items(gem: dict) -> list[dict]:
    subject = _subject(gem)
    return subject["items"] if subject else []


def _bugs(gem: dict) -> list[dict] | None:
    subject = _subject(gem)
    return subject.get("bug_tags", []) if subject else None


def _validate(gem: dict, raw: dict) -> dict:
    bugs = _bugs(gem)
    checked = flowspec.validate(raw, gem.get("tools"), [b["id"] for b in bugs] if bugs is not None else None)
    if checked["spec"] and not checked["errors"]:
        checked["warnings"] += flowspec.leak_warnings(checked["spec"], _items(gem))
    return checked


def detail(gem: dict) -> dict:
    flow = gem.get("flow") or flowspec.STANDARD
    spec = flow.get("spec") if flow.get("mode") == "custom" else None
    checked = _validate(gem, spec) if spec else None
    return {
        "mode": flow.get("mode", "standard"),
        "source": flow.get("source"),
        "reviewed": bool(flow.get("reviewed")),
        "updated_at": flow.get("updated_at"),
        "warnings": list(dict.fromkeys((flow.get("warnings") or []) + (checked["warnings"] if checked else []))),
        "summary": (spec or {}).get("summary") or flow.get("summary") or "",
        "spec": checked["spec"] if checked else None,
        "map": flowspec.map_view(checked["spec"]) if checked and checked["spec"] else None,
        "template": flowspec.standard_template(),
        "outdated": "instructions_key" in flow and builder.flow_needs_design(gem),
    }


def check(gem: dict, raw: dict) -> dict:
    checked = _validate(gem, raw)
    return {**checked, "map": flowspec.map_view(checked["spec"]) if checked["spec"] and not checked["errors"] else None}


def save(gem_id: str, raw: dict, actor: str) -> dict:
    gem = manage.get(gem_id)
    checked = _validate(gem, raw)
    if checked["errors"]:
        raise manage.GemError("Flow นี้ยังบันทึกไม่ได้: " + " · ".join(checked["errors"]))
    gem["flow"] = flowspec.record(checked["spec"], "teacher", checked["warnings"], reviewed=True)
    return _store(gem, actor, "ครูแก้ Flow การสอน")


def use_standard(gem_id: str, actor: str) -> dict:
    gem = manage.get(gem_id)
    gem["flow"] = {**flowspec.STANDARD, "source": "teacher"}
    return _store(gem, actor, "ครูเลือกใช้ผังมาตรฐานของระบบ")


def approve(gem_id: str, actor: str) -> dict:
    gem = manage.get(gem_id)
    if (gem.get("flow") or {}).get("mode") != "custom":
        raise manage.GemError("Gem นี้ใช้ผังมาตรฐาน อยู่แล้ว")
    gem["flow"]["reviewed"] = True
    return _store(gem, actor, "ครูตรวจ Flow การสอนแล้ว")


async def redesign(gem_id: str, actor: str) -> dict:
    gem = manage.get(gem_id)
    flow = await flowspec.design(gem, (gem.get("knowledge") or {}).get("memory"), _bugs(gem))
    flow["instructions_key"] = builder.instructions_key(gem)
    gem = manage.get(gem_id)
    gem["flow"] = flow
    return _store(gem, "AI", "AI ออกแบบ Flow การสอนจากคำสั่ง")


def _store(gem: dict, actor: str, note: str) -> dict:
    db.save_gem(gem)
    versions.record(gem, actor, note)
    manage._sync_bank(gem)
    return detail(gem)
