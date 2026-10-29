"""ครูตรวจและปรับ Flow ที่ AI ออกแบบจากคำสั่ง (Human-in-the-Loop ของ Flow, ADR-0004)

AI ออกแบบตอนสร้างคลังโจทย์ หรือเมื่อครูกด "ออกแบบใหม่จากคำสั่ง" Flow ใช้กับนักเรียนทันทีเหมือนคลังโจทย์
แต่ขึ้นป้าย "ยังไม่ได้ตรวจ" จนครูกดยืนยัน ครูแก้ขั้น เส้น เงื่อนไข และตัวเลขได้ ทุกครั้งต้องผ่าน flowspec.validate
และบันทึกเป็นเวอร์ชันของ Gem ย้อนกลับได้ ครูเลือกกลับไปใช้ผังมาตรฐานของระบบได้เสมอ
"""

import asyncio
import logging

from .. import db
from . import builder, flowspec, manage, simulate, versions


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
    checked = flowspec.validate(raw, [b["id"] for b in bugs] if bugs is not None else None)
    if checked["spec"] and not checked["errors"]:
        checked["warnings"] += flowspec.leak_warnings(checked["spec"], _items(gem))
        missing = flowspec.missing_keywords(checked["spec"], flowspec.teacher_keywords(gem.get("instructions", "")))
        checked["warnings"] += flowspec.mismatched_asks(checked["spec"])
        if missing:
            checked["warnings"].append(f"คำที่ครูเขียนไว้ใน prompt ให้จับในแชตยังไม่ถูกจับ: {', '.join(missing)} "
                                       "เพิ่มในแท็บแชต AI หรือกดออกแบบใหม่")
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
        # แม่แบบอ้างอิง ครูเปิดดูเป็นแนวทางเขียนคำสั่ง ไม่ใช้เป็น Flow ของ Gem
        "reference_map": flowspec.map_view(flowspec.validate(flowspec.standard_template())["spec"]),
        "outdated": "instructions_key" in flow and builder.flow_needs_design(gem),
        # คำที่ครูเขียนไว้ใน prompt ให้จับในแชต หน้า Flow ทำเครื่องหมายว่าคำไหนมาจากครู
        "teacher_keywords": flowspec.teacher_keywords(gem.get("instructions", "")),
        # ผลที่ AI ตรวจทีละแนวทางของครูกับตารางจำลอง (ตอนออกแบบ หรือครูกดตรวจอีกครั้ง ครูแก้เองแล้วผลนี้หายไป)
        **audit_status(gem),
        # ระบบจำลองว่านักเรียนแต่ละแบบจะไปขั้นไหน ให้ครูเทียบกับคำสั่งของตัวเอง
        "table": simulate.table(checked["spec"]) if checked and checked["spec"] else [],
    }


def check(gem: dict, raw: dict) -> dict:
    checked = _validate(gem, raw)
    ok = checked["spec"] and not checked["errors"]
    return {**checked, "map": flowspec.map_view(checked["spec"]) if ok else None,
            "table": simulate.table(checked["spec"]) if ok else []}


def save(gem_id: str, raw: dict, actor: str) -> dict:
    gem = manage.get(gem_id)
    checked = _validate(gem, raw)
    if checked["errors"]:
        raise manage.GemError("Flow นี้ยังบันทึกไม่ได้: " + " · ".join(checked["errors"]))
    gem["flow"] = flowspec.record(checked["spec"], "teacher", checked["warnings"], reviewed=True)
    return _store(gem, actor, "ครูแก้ Flow การสอน")


def approve(gem_id: str, actor: str) -> dict:
    gem = manage.get(gem_id)
    if (gem.get("flow") or {}).get("mode") != "custom":
        raise manage.GemError("ติวเตอร์นี้ใช้ผังมาตรฐานอยู่แล้ว")
    gem["flow"]["reviewed"] = True
    return _store(gem, actor, "ครูตรวจ Flow การสอนแล้ว")


async def redesign(gem_id: str, actor: str) -> dict:
    gem = manage.get(gem_id)
    flow = await flowspec.design(gem, (gem.get("knowledge") or {}).get("memory"), _bugs(gem), _items(gem))
    flow["instructions_key"] = builder.instructions_key(gem)
    gem = manage.get(gem_id)
    gem["flow"] = flow
    return _store(gem, "AI", "AI ออกแบบ Flow การสอนจากคำสั่ง")


async def write_widget(gem_id: str, step_id: str, actor: str) -> dict:
    """ครูกดให้ AI เขียนหน้าเว็บของ Widget custom ใหม่ (ตามคำบรรยายที่บันทึกไว้)"""
    gem = manage.get(gem_id)
    flow = gem.get("flow") or {}
    step = next((s for s in (flow.get("spec") or {}).get("steps", []) if s["id"] == step_id), None)
    if not step or step["kind"] != "widget" or step["widget"] != "custom":
        raise manage.GemError("ขั้นนี้ไม่ใช่ Widget ที่ AI เขียนเอง (บันทึก Flow ก่อนแล้วลองใหม่)")
    try:
        html = await flowspec.write_widget(gem, step, (gem.get("knowledge") or {}).get("memory"), _items(gem))
    except builder.BuildError as error:
        raise manage.GemError(str(error)) from error
    gem = manage.get(gem_id)
    step = next(s for s in gem["flow"]["spec"]["steps"] if s["id"] == step_id)
    step["config"] = {"html": html}
    gem["flow"]["warnings"] = [w for w in gem["flow"].get("warnings") or [] if step.get("label", "") not in w]
    gem["flow"]["reviewed"] = False
    return _store(gem, actor, f"AI เขียน Widget \"{step.get('label', step_id)}\"")


# ติวเตอร์ที่ AI กำลังตรวจแนวทางกับการจำลองอยู่ (งานเบื้องหลัง ครูกดจากแท็บ Flow)
_auditing: set[str] = set()
log = logging.getLogger(__name__)


def audit_status(gem: dict) -> dict:
    flow = gem.get("flow") or {}
    return {"auditing": gem["id"] in _auditing, "audit": flow.get("audit") or [], "audit_error": flow.get("audit_error")}


def start_audit(gem_id: str) -> dict:
    """ครูกดให้ AI ตรวจแนวทางกับการจำลองของ Flow ปัจจุบันอีกครั้ง โดยไม่ออกแบบใหม่ ทำเป็นงานเบื้องหลัง
    เพราะ AI ใช้เวลาเป็นนาที นานกว่าที่ Cloudflare รอคำขอเดียว (100 วินาที) หน้าเว็บถามสถานะจาก audit_status"""
    gem = manage.get(gem_id)
    flow = gem.get("flow") or {}
    if flow.get("mode") != "custom" or not flow.get("spec"):
        raise manage.GemError("ติวเตอร์นี้ยังไม่มี Flow ที่ออกแบบจากคำสั่ง ให้ AI ออกแบบก่อน")
    if gem_id not in _auditing:
        _auditing.add(gem_id)
        asyncio.create_task(audit(gem_id, flow["spec"]))
    return audit_status(gem)


async def audit(gem_id: str, spec: dict) -> None:
    try:
        try:
            checks, problem = await flowspec.audit_flow(manage.get(gem_id), spec), None
        except Exception as error:  # noqa: BLE001 งานเบื้องหลังต้องจบด้วยสถานะเสมอ ไม่ค้างที่ "กำลังตรวจ"
            if not isinstance(error, builder.BuildError):
                log.exception("AI ตรวจแนวทางของ %s ไม่สำเร็จ", gem_id)
            checks, problem = None, str(error)
        gem = manage.get(gem_id)
        flow = gem.get("flow") or {}
        if flow.get("spec") != spec:
            return  # ครูแก้ Flow ระหว่างตรวจ ผลนี้ไม่ตรงกับ Flow ปัจจุบันแล้ว
        if checks is None:
            flow["audit_error"] = problem
        else:
            flow["audit"] = checks
            flow.pop("audit_error", None)
        db.save_gem(gem)
        manage._sync_bank(gem)
    finally:
        _auditing.discard(gem_id)


def _store(gem: dict, actor: str, note: str) -> dict:
    db.save_gem(gem)
    versions.record(gem, actor, note)
    manage._sync_bank(gem)
    return detail(gem)
