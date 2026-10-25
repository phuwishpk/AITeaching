"""Flow ที่ครูออกแบบใน Gem: ผังตรรกะของ Gem แต่ละตัว ไม่ใช่ผังตายตัวชุดเดียว (Q24)

กล่องของเครื่องมือที่ครูปิดไม่อยู่ในผัง และเส้นทางต่อตรงไปขั้นที่ engine ใช้จริงเมื่อปิดเครื่องมือนั้น
ส่วนกล่องที่ Alert Rule ส่งแจ้งเตือนจะมีกระดิ่ง (แจ้งอย่างเดียว) หรือมือ (หยุดรอครู)
การตัดและต่อเส้นด้านล่างต้องตรงกับที่ engine ทำจริง (core.py › Content.tool และ services.py)
"""

from ..engine import flow as F

from .. import db
from ..tutor import prompt
from . import alerts, builder, flowspec, manage, versions

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


# เมื่อปิดเครื่องมือ: กล่องที่หายจากผัง เส้นที่ไม่เกิดแล้ว เส้นที่ไปปลายทางใหม่ และป้ายบนเส้นที่ความหมายเปลี่ยน
TOOL_FLOW = {
    "hints": {"hide_edges": ["e_hint_button"], "labels": {"e_g3_4": "ครั้งที่ 3 ขึ้นไป"}},
    # engine ยังผ่านด่าน "อยู่ใน Isomorphic Test?" แต่คำตอบเป็น "ไม่ใช่" เสมอ จึงวาดเป็นผิดแล้วไปด่าน 2 เลย
    "isomorphic": {"retarget": {"e_g1_wrong": "G2"}, "labels": {"e_mastery_finish": "ผ่าน"}},
    # Walkthrough ถูกข้ามทันที: พักครบแล้วไปทำโจทย์ที่ง่ายลง ไม่มี Prerequisite ก็ฝึกเรื่องเดิมต่อ
    "walkthrough": {"retarget": {"e_cb_done": "ANSWERING", "e_rounds_root": "REMEDIAL"},
                    "labels": {"e_cb_done": "พักครบ ทำโจทย์ง่ายลง", "e_rounds_root": "ไม่มี Prerequisite ฝึกเรื่องเดิม"}},
    "remedial": {"hide_edges": ["e_rounds_root", "e_walk_round", "e_remedial_pass", "e_remedial_next"],
                 "labels": {"e_rounds_full": "ส่งต่อครูทันที"}},
    # ไม่มีแชต: กล่องที่เกิดจากข้อความของนักเรียนไม่เกิดขึ้น
    "chat": {"hide_nodes": ["CHOOSING_PATH", "SAFETY_STOP"], "hide_edges": ["e_distress"]},
}
# เส้นที่มีเฉพาะเมื่อปิดเครื่องมือ
ONLY_WHEN_OFF = {"e_g3_nohint": "hints"}


def flow_view(gem: dict) -> dict:
    """กล่องและเส้นของผังที่ Gem นี้ใช้จริง พร้อมรายการกล่องที่ครูปิดและเหตุผล"""
    tools = {**manage.TOOLS, **(gem.get("tools") or {})}
    off = [tool for tool in TOOL_NODES if not tools.get(tool, True)]
    hidden = {node: TOOL_REASON[tool] for tool in off for node in TOOL_NODES[tool] + TOOL_FLOW.get(tool, {}).get("hide_nodes", [])}
    drop = {e for tool in off for e in TOOL_FLOW.get(tool, {}).get("hide_edges", [])}
    drop |= {edge for edge, tool in ONLY_WHEN_OFF.items() if tool not in off}
    retarget = {e: t for tool in off for e, t in TOOL_FLOW.get(tool, {}).get("retarget", {}).items()}
    labels = {e: label for tool in off for e, label in TOOL_FLOW.get(tool, {}).get("labels", {}).items()}
    edges = []
    for edge in F.EDGES:
        if edge.get("hidden") or edge["id"] in drop:
            continue
        edge = {**edge, "target": retarget.get(edge["id"], edge["target"]), "label": labels.get(edge["id"], edge["label"])}
        if edge["source"] in hidden or edge["target"] in hidden:
            continue
        edges.append(edge)
    return {"nodes": [n for n in F.NODES if n["id"] not in hidden], "edges": edges, "hidden": hidden}


def custom_flow(gem: dict) -> dict | None:
    """Flow ที่ AI ออกแบบจากคำสั่งของครู (ADR-0004): ขั้น เส้น ตัวเลข และกลไกที่ล็อกไว้ ไม่ใช่ผังตายตัว"""
    flow = gem.get("flow") or {}
    if flow.get("mode") != "custom" or not flow.get("spec"):
        return None
    spec = flow["spec"]
    return {
        "custom": True, **flowspec.map_view(spec),
        "summary": spec.get("summary", ""), "source": flow.get("source"), "reviewed": bool(flow.get("reviewed")),
        "warnings": flow.get("warnings") or [], "locked": flowspec.LOCKED,
        "params": [{"key": k, "label": flowspec.PARAM_LABELS[k], "value": v} for k, v in (spec.get("params") or {}).items()
                   if v != flowspec.DEFAULT_PARAMS.get(k)],
        "disabled": {}, "alerts": {},
    }


def flow_marks(gem: dict) -> dict:
    custom = custom_flow(gem)
    if custom:
        return custom
    view = flow_view(gem)
    disabled = view["hidden"]
    labels = {s["key"]: s["label"] for s in alerts.SITUATIONS}
    marks: dict[str, list[dict]] = {}
    for key, rule in alerts.normalize(gem.get("alert_rules")).items():
        if not rule["enabled"]:
            continue
        for node in SITUATION_NODES.get(key, []):
            if node not in disabled:
                marks.setdefault(node, []).append({"key": key, "label": labels[key], **rule})
    return {"nodes": view["nodes"], "edges": view["edges"], "disabled": disabled, "alerts": marks}


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
