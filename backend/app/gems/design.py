"""Flow ที่ครูออกแบบใน Gem: แปลงการตั้งค่าของ Gem เป็นสิ่งที่ผังตรรกะในหน้า Admin แสดง (Q24)

กล่องของเครื่องมือที่ครูปิดจะจางลงพร้อมเหตุผล ส่วนกล่องที่ Alert Rule ส่งแจ้งเตือนจะมีกระดิ่ง (แจ้งอย่างเดียว)
หรือมือ (หยุดรอครู) การจับคู่ด้านล่างต้องตรงกับที่ engine ใช้จริง (core.py และ services.py)
"""

from .. import db
from ..tutor import prompt
from . import alerts, builder, manage, versions

# เครื่องมือที่ปิด → กล่องที่ไม่ถูกใช้ (engine › Content.tool)
TOOL_NODES = {
    "hints": ["DELIBERATE_DELAY", "HINT_L1", "HINT_L2", "HINT_L3", "G_TREND"],
    "isomorphic": ["ISOMORPHIC_TEST", "G_ISOCHK"],
    "walkthrough": ["WALKTHROUGH"],
    "remedial": ["REMEDIAL"],
    "chat": ["TEACHER_REVIEW"],
}
TOOL_REASON = {
    "hints": "ครูปิดบันไดคำใบ้ ตอบผิดแล้วลองใหม่เอง (เส้น ครูปิดบันไดคำใบ้)",
    "isomorphic": "ครูปิด Isomorphic Test ผ่านด้วยคำใบ้แล้วไปข้อถัดไปเลย",
    "walkthrough": "ครูปิด Walkthrough เส้นทางผ่านกล่องนี้ไปทันที",
    "remedial": "ครูปิดทบทวนพื้นฐาน Impasse ส่งต่อครูทันที",
    "chat": "ครูปิดแชต นักเรียนไม่มีช่องคุยกับ AI",
}

# สถานการณ์แจ้งเตือน → กล่องในผังที่สถานการณ์นั้นเกิด
SITUATION_NODES = {
    "self_harm": ["SAFETY_STOP"],
    "ask_teacher": ["TEACHER_REVIEW"],
    "deadlock": ["STAGNATION_DEADLOCK"],
    "stress": ["CIRCUIT_BREAKER"],
    "quit": ["CHOOSING_PATH"],
    "ai_outage": ["AI_OUTAGE"],
    "off_topic": ["TEACHER_REVIEW"],
    "new_misconception": ["G_DIAG"],
    "guard_blocked": ["HINT_L1", "HINT_L2", "HINT_L3"],
    "burnout": ["IDLE_PAUSE", "RAPID_GUESS_LOCK"],
    "hint_abuse": ["HINT_L1"],
    "cap": ["SESSION_ENDED"],
}


def flow_marks(gem: dict) -> dict:
    tools = {**manage.TOOLS, **(gem.get("tools") or {})}
    disabled = {}
    for tool, nodes in TOOL_NODES.items():
        if not tools.get(tool, True):
            for node in nodes:
                disabled[node] = TOOL_REASON[tool]
    labels = {s["key"]: s["label"] for s in alerts.SITUATIONS}
    marks: dict[str, list[dict]] = {}
    for key, rule in alerts.normalize(gem.get("alert_rules")).items():
        if not rule["enabled"]:
            continue
        for node in SITUATION_NODES.get(key, []):
            marks.setdefault(node, []).append({"key": key, "label": labels[key], **rule})
    return {"disabled": disabled, "alerts": marks}


def frames(gem: dict) -> dict:
    """prompt 4 กรอบที่ Gem นี้ส่งให้ AI: Role มาจากคำสั่งของครู Constraints ล็อกไว้ อีกสองกรอบเติมตอนสอน"""
    subject = db.get_subject(gem["subject_id"]) if gem.get("subject_id") else None
    base = subject or {"name": gem["name"], "grade": ""}
    return {
        "role": prompt.role_frame({**base, "gem": {"instructions": gem.get("instructions", "")}}),
        "context": "เติมตอนสอนจาก Student Model: โจทย์ปัจจุบัน ครั้งที่ผิด เวลาคิด ผลวินิจฉัย Bug Library "
                   "และย่อหน้าที่ RAG ค้นได้จาก Knowledge File ของ Gem",
        "task": "เติมตอนสอน: " + " · ".join(prompt.LEVEL_TASK.values()) + " หรือคำถามนำแบบ Socratic เมื่อนักเรียนพิมพ์แชต",
        "constraints": prompt.constraints_frame(),
    }


def students(gem_id: str) -> list[str]:
    sets = {s["question_sets"][0]["id"] for s in db.list_subjects()
            if (s.get("gem") or {}).get("id") == gem_id and s.get("question_sets")}
    codes = {state["code"] for state in db.all_states() if state["set_id"] in sets}
    test = {r["code"] for r in db.query("SELECT code FROM students WHERE kind = 'test'")}
    return sorted(codes - test)


def build(gem_id: str) -> dict:
    gem = manage.get(gem_id)
    detail = manage.detail(gem)
    return {
        **{k: detail[k] for k in ("id", "name", "description", "instructions", "icon", "color", "tools",
                                  "starter_prompts", "alert_rules", "bank_version", "build", "files", "bank", "versions")},
        "flow": flow_marks(gem),
        "frames": frames(gem),
        "students": students(gem_id),
        "situations": alerts.catalog(),
        "live_cap": builder.bank_sizes()["live_cap"],
        "version": versions.history(gem_id)[0]["n"] if detail["versions"] else None,
    }
