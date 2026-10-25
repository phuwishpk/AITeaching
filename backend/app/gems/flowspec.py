"""Flow ที่ AI ออกแบบจากคำสั่งของครูใน Gem: รูปแบบ ตัวตรวจ แม่แบบ และ prompt (ADR-0004)

Flow เป็น JSON: ขั้น (steps) จากคลังขั้นที่ engine รันได้ เส้น (edges) ที่มีเงื่อนไขเป็นกฎ และตัวเลข (params)
ทุกครั้งที่ AI ออกแบบหรือครูแก้ ต้องผ่าน validate ก่อนบันทึก: ตัดตัวเลขให้อยู่ในช่วงที่ปลอดภัย ตรวจเงื่อนไข
ตรวจว่าทุกขั้นมีทางออกและไปถึงขั้นจบได้ และไม่มีวงที่วนโดยไม่หยุดรอนักเรียน
สิ่งที่ล็อกไว้ (LOCKED) ไม่อยู่ในกราฟ engine บังคับใช้เองทุก Flow (engine/gemflow.py)
"""

import json
import re
import time

from ..config import DEFAULT_PARAMS, PARAM_LABELS
from ..engine import conditions
from ..engine import flow as F
from ..engine.gemflow import PICKS, STUCK_LIMIT, features  # noqa: F401 (หน้าเว็บใช้ผ่าน flowspec)

KINDS = {
    "item": {"label": "ทำโจทย์", "lane": "correct", "wait": True,
             "about": "ให้โจทย์หนึ่งข้อแล้วรอคำตอบ ตรวจถูกผิดด้วยกฎจากเฉลย เส้นออกตัดสินจากผลการตอบ"},
    "hint": {"label": "คำใบ้", "lane": "help", "wait": False,
             "about": "แสดงคำใบ้ระดับ 1–3 ของข้อปัจจุบัน (หรือ auto ตามครั้งที่ผิดและผลวินิจฉัย) หน่วงเวลาก่อนแสดงได้"},
    "lesson": {"label": "บทเรียนย่อ", "lane": "help", "wait": True,
               "about": "หน้าอ่านเนื้อหาสั้น ๆ หรือตัวอย่างทีละขั้น (Walkthrough) นักเรียนกดอ่านจบแล้วไปต่อ"},
    "reflect": {"label": "อธิบายความคิด", "lane": "help", "wait": True,
                "about": "ให้นักเรียนพิมพ์อธิบายวิธีคิด เปิดให้ AI ประเมินตามเกณฑ์ของครูได้ (บันทึกทุกครั้งให้ครูตรวจ)"},
    "break": {"label": "พักสายตา", "lane": "care", "wait": True, "about": "หยุดกิจกรรมตามจำนวนวินาทีแล้วไปต่อ"},
    "notify": {"label": "แจ้งครู", "lane": "human", "wait": False, "about": "ส่งแจ้งเตือนถึงครูแล้วไปต่อทันที นักเรียนไม่หยุด"},
    "teacher": {"label": "หยุดรอครู", "lane": "human", "wait": True,
                "about": "หยุดกิจกรรมและแจ้งครู ไปต่อเมื่อครูกดปล่อยในหน้าครู (Human-in-the-Loop)"},
    "check": {"label": "ด่านตัดสินใจ", "lane": "wrong", "wait": False, "about": "ไม่ทำอะไร ใช้แยกทางด้วยเงื่อนไขบนเส้น"},
    "activity": {"label": "กิจกรรมที่ AI สร้าง", "lane": "help", "wait": True,
                 "about": "ขั้นที่คลังขั้นไม่มี: บรรยายใน goal ว่าต้องการกิจกรรมแบบไหน (เช่น ให้เรียงลำดับขั้น PEMDAS "
                          "อธิบายด้วยตัวอย่างใหม่ ตั้งคำถามชวนสังเกต) AI สร้างเนื้อหาจริงตอนนักเรียนมาถึงจากเอกสารของครู "
                          "นักเรียนอ่านแล้วไปต่อ หรือพิมพ์ตอบให้ AI ประเมินตาม rubric"},
    "end": {"label": "จบ", "lane": "correct", "wait": True, "about": "จบชุดคำถาม (สำเร็จ หรือหยุดไว้ก่อน)"},
}

# ตัวเลขที่ Flow ตั้งเองได้จากคำสั่งของครู และช่วงที่ปลอดภัย (ค่าเริ่มต้นมาจากหน้า Admin)
PARAM_RANGES = {
    "rapid_guess_threshold": (1, 10),
    "rapid_guess_lock": (5, 60),
    "hint_unlock_wait": (0, 120),
    "hint_abuse_cooldown": (5, 60),
    "idle_timeout": (60, 600),
    "circuit_breaker_break": (30, 300),
    "max_items": (5, 40),
    "mastery_window": (3, 10),
}
STEP_NUMBERS = {"delay": (0, 60), "seconds": (15, 300)}

LOCKED = [
    {"title": "ตรวจถูกผิดด้วยกฎ ไม่เฉลยคำตอบ",
     "text": "ทุกคำตอบตรวจด้วยกฎจากเฉลยในคลังโจทย์ คำใบ้และแชตของ AI ผ่าน Answer-Leak Guard ก่อนถึงนักเรียน"},
    {"title": "หยุดเมื่อมีข้อความทำร้ายตนเอง และ Manual Override",
     "text": "ข้อความที่สื่อถึงการทำร้ายตนเองหยุดทันทีและแจ้งครูด่วน ครูสั่งหยุด เปลี่ยนโจทย์ หรือปล่อยต่อได้ทุกเมื่อ"},
    {"title": "กรองข้อมูลและจับเดาสุ่ม",
     "text": "ส่งซ้ำนับครั้งเดียว คำตอบผิดรูปแบบไม่นับ ตัดเวลาคิดส่วนเกิน ผิดเร็วกว่าเวลาอ่านขั้นต่ำเป็นโมฆะและล็อกปุ่มตอบ"},
    {"title": "พักเมื่อหน้าจอนิ่ง และเพดานจำนวนข้อ",
     "text": f"ไม่มีการกระทำนานเกินกำหนดพักบทเรียนเอง ครบเพดานข้อจบ Session และผิดข้อเดียวกันครบ {STUCK_LIMIT} ครั้งส่งต่อครู"},
]

# กล่องของกลไกที่ล็อกไว้ แสดงในผังของ Gem ทุกตัว (นักเรียนที่อยู่ในกลไกเหล่านี้จะอยู่ที่กล่องนี้)
GUARDS = [
    {"id": F.LOCK, "label": "ล็อก Rapid Guess", "text": "ผิดเร็วกว่าเวลาอ่านขั้นต่ำ คะแนนเป็นโมฆะ พักปุ่มตอบแล้วกลับขั้นเดิม"},
    {"id": F.IDLE, "label": "Idle Pause", "text": "หน้าจอนิ่งเกินกำหนดหรือนักเรียนขอพัก กลับมาทำขั้นเดิมต่อ"},
    {"id": F.CB, "label": "พักเพราะเครียด", "text": "พิมพ์ข้อความเครียดหรือท้อ พักสายตาแล้วกลับขั้นเดิม"},
    {"id": F.CHOOSE, "label": "เลือกทางต่อ", "text": "บอกว่าไม่อยากเรียนต่อ ให้เลือกพัก ทำแบบง่ายลง หรือหยุด"},
    {"id": F.SAFETY, "label": "หยุดเพื่อความปลอดภัย", "text": "ข้อความทำร้ายตนเอง หยุดทันทีและแจ้งครูด่วน"},
    {"id": F.DEADLOCK, "label": "ติดเกินเพดาน รอครู", "text": f"ผิดข้อเดียวกันครบ {STUCK_LIMIT} ครั้ง หรือ Flow วนไม่จบ ส่งต่อครู"},
    {"id": F.LIVE, "label": "สร้างโจทย์สด", "text": "คลังหมดระหว่างทาง AI สร้างโจทย์ใหม่แล้วกลับขั้นเดิม"},
    {"id": F.OUTAGE, "label": "AI ขัดข้อง", "text": "สร้างโจทย์สดไม่สำเร็จ หยุดชั่วคราวและลองใหม่เอง"},
    {"id": F.ENDED, "label": "จบเพราะเพดานข้อ", "text": "ครบเพดานจำนวนข้อ หรือโจทย์หมด บันทึกความคืบหน้าไว้"},
]

BACK = "back"
START_KINDS = ("item", "lesson", "activity", "reflect")


class FlowError(Exception):
    pass


# ---------------------------------------------------------------- แม่แบบมาตรฐาน

def standard_template() -> dict:
    """ผังมาตรฐาน เขียนเป็น Flow ของ Gem: ใช้เป็นตัวอย่างให้ AI และเป็นจุดเริ่มของครู"""
    return {
        "summary": "แม่แบบมาตรฐาน: ตอบผิดได้คำใบ้ทีละระดับ ผ่านด้วยคำใบ้ต้องทำข้อคู่ขนาน ติดหล่มทบทวนพื้นฐาน ซ่อมเสริมครบ 2 รอบแจ้งครู",
        "start": "practice",
        "params": {},
        "steps": [
            {"id": "practice", "kind": "item", "label": "ทำโจทย์", "pick": "adaptive", "hint_button": True},
            {"id": "hint1", "kind": "hint", "label": "หน่วงเวลาแล้วใบ้ L1", "level": "auto", "delay": 15},
            {"id": "hint2", "kind": "hint", "label": "คำใบ้ L2", "level": 2},
            {"id": "hint3", "kind": "hint", "label": "คำใบ้ L3", "level": 3},
            {"id": "iso", "kind": "item", "label": "ข้อคู่ขนาน (ไม่มีคำใบ้)", "pick": "isomorphic", "hint_button": False},
            {"id": "review", "kind": "item", "label": "ทบทวนพื้นฐาน", "pick": "prerequisite", "hint_button": True},
            {"id": "review_hint", "kind": "hint", "label": "คำใบ้ข้อทบทวน", "level": "auto"},
            {"id": "rest", "kind": "break", "label": "พักสายตา", "seconds": 60},
            {"id": "example", "kind": "lesson", "label": "ตัวอย่างทีละขั้น", "title": "ดูตัวอย่างทีละขั้น",
             "text": "", "walkthrough": True},
            {"id": "teacher", "kind": "teacher", "label": "รอครูช่วย", "text": "ซ่อมเสริมครบ 2 รอบแล้วยังติด ต้องให้ครูช่วย"},
            {"id": "done", "kind": "end", "label": "จบชุด", "result": "completed", "text": "ยอดเยี่ยม ทำชุดนี้สำเร็จแล้ว"},
        ],
        "edges": [
            {"from": "practice", "to": "done", "when": "correct and mastery >= 0.8 and items_done >= 3 and (mains_left == 0 or challenge_done)",
             "label": "ถึงเกณฑ์จบชุด"},
            {"from": "practice", "to": "iso", "when": "correct and hint_level >= 1", "label": "ผ่านด้วยคำใบ้"},
            {"from": "practice", "to": "practice", "when": "correct", "label": "ข้อถัดไป"},
            {"from": "practice", "to": "teacher", "when": "wrong and error_count >= 4 and rounds >= 2", "label": "ซ่อมเสริมครบ 2 รอบ"},
            {"from": "practice", "to": "hint1", "when": "wrong and error_count == 1", "label": "ผิดครั้งแรก"},
            {"from": "practice", "to": "hint2", "when": "wrong and error_count == 2", "label": "ผิดครั้งที่ 2"},
            {"from": "practice", "to": "hint3", "when": "wrong and error_count == 3 and impasse < 55", "label": "ผิดครั้งที่ 3"},
            {"from": "practice", "to": "review", "when": "wrong", "label": "ติดหล่ม (Impasse)"},
            {"from": "hint1", "to": "practice", "when": "", "label": "ลองข้อเดิม"},
            {"from": "hint2", "to": "practice", "when": "", "label": "ลองข้อเดิม"},
            {"from": "hint3", "to": "practice", "when": "", "label": "ลองข้อเดิม"},
            {"from": "iso", "to": "practice", "when": "correct", "label": "เข้าใจจริง"},
            {"from": "iso", "to": "iso", "when": "wrong and error_count < 2", "label": "ลองอีกครั้ง"},
            {"from": "iso", "to": "practice", "when": "wrong", "label": "ไม่ผ่าน ฝึกต่อ"},
            {"from": "review", "to": "practice", "when": "correct and solved_here >= 2", "label": "ทบทวนผ่าน กลับข้อเดิม"},
            {"from": "review", "to": "review", "when": "correct", "label": "ข้อทบทวนถัดไป"},
            {"from": "review", "to": "rest", "when": "wrong and error_count >= 3", "label": "ติดซ้ำระหว่างทบทวน"},
            {"from": "review", "to": "review_hint", "when": "wrong", "label": "ผิด"},
            {"from": "review_hint", "to": "review", "when": "", "label": "ลองข้อเดิม"},
            {"from": "rest", "to": "example", "when": "", "label": "พักครบ"},
            {"from": "example", "to": "practice", "when": "", "label": "อ่านจบ"},
            {"from": "teacher", "to": "practice", "when": "", "label": "ครูปล่อยต่อ"},
        ],
    }


# ---------------------------------------------------------------- ตรวจและทำให้เป็นรูปเดียวกัน

def _text(value, limit: int) -> str:
    return re.sub(r"[*#`$]+", "", str(value or "")).strip()[:limit]


def _number(value, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _slug(value, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")[:24]
    return slug or fallback


def normalize(raw: dict) -> tuple[dict, list[str]]:
    """แปลง Flow ที่ AI หรือครูส่งมาให้เป็นรูปเดียวกัน ตัวเลขที่เกินช่วงถูกตัดและบอกไว้ในคำเตือน"""
    if not isinstance(raw, dict):
        raise FlowError("Flow ต้องเป็น JSON object")
    notes: list[str] = []
    steps, seen, renamed = [], set(), {}
    for i, s in enumerate(raw.get("steps") or []):
        if not isinstance(s, dict):
            continue
        original = str(s.get("id") or f"s{i + 1}")
        sid = _slug(original, f"s{i + 1}")
        while sid in seen:
            sid = f"{sid[:20]}_{i + 1}"
        seen.add(sid)
        renamed[original] = sid
        kind = s.get("kind") if s.get("kind") in KINDS else None
        if kind is None:
            raise FlowError(f"ขั้น \"{original}\" ใช้ชนิด \"{s.get('kind')}\" ที่ engine ไม่รู้จัก")
        step = {"id": sid, "kind": kind, "label": _text(s.get("label"), 40) or KINDS[kind]["label"]}
        # ที่มาของขั้นนี้ในคำสั่งของครูหรือเอกสาร (ทุกขั้นต้องมาจาก prompt ครูตรวจได้ทีละขั้น)
        if _text(s.get("reason"), 240):
            step["reason"] = _text(s.get("reason"), 240)
        if kind == "item":
            step["pick"] = s.get("pick") if s.get("pick") in PICKS else "adaptive"
            # ปุ่มขอคำใบ้มีเฉพาะเมื่อคำสั่งของครูให้นักเรียนกดขอเองได้ (ไม่มีก็ไม่แสดง)
            step["hint_button"] = bool(s.get("hint_button", False))
        elif kind == "hint":
            level = s.get("level", "auto")
            step["level"] = level if level == "auto" else int(_number(level, 1, 3, 1))
            step["delay"] = _clamp_step(s, "delay", 0, notes, step["label"])
        elif kind == "lesson":
            step["title"] = _text(s.get("title"), 60) or step["label"]
            step["text"] = _text(s.get("text"), 1200)
            step["walkthrough"] = bool(s.get("walkthrough"))
            if not step["text"] and not step["walkthrough"]:
                step["walkthrough"] = True
        elif kind == "reflect":
            step["question"] = _text(s.get("question"), 300) or "อธิบายว่าเราคิดข้อนี้อย่างไร"
            step["judge"] = bool(s.get("judge"))
            step["rubric"] = _text(s.get("rubric"), 600)
        elif kind == "break":
            step["seconds"] = _clamp_step(s, "seconds", 60, notes, step["label"])
            step["text"] = _text(s.get("text"), 200)
        elif kind == "notify":
            step["level"] = s.get("level") if s.get("level") in ("urgent", "normal", "silent") else "normal"
            step["text"] = _text(s.get("text"), 200) or step["label"]
        elif kind == "teacher":
            step["text"] = _text(s.get("text"), 200) or step["label"]
        elif kind == "activity":
            step["title"] = _text(s.get("title"), 60) or step["label"]
            step["goal"] = _text(s.get("goal"), 800) or step["label"]
            step["response"] = "text" if s.get("response") == "text" else "none"
            step["rubric"] = _text(s.get("rubric"), 600)
        elif kind == "end":
            step["result"] = "stopped" if s.get("result") == "stopped" else "completed"
            step["text"] = _text(s.get("text"), 200)
        steps.append(step)
    edges = []
    for i, e in enumerate(raw.get("edges") or []):
        if not isinstance(e, dict):
            continue
        source = renamed.get(str(e.get("from")), _slug(e.get("from"), ""))
        # "back" = กลับไปขั้นทำโจทย์ที่นักเรียนมาจริง ใช้กับขั้นคำใบ้หรือบทเรียนที่หลายขั้นโจทย์ใช้ร่วมกัน
        target = BACK if str(e.get("to")).strip().lower() == BACK else renamed.get(str(e.get("to")), _slug(e.get("to"), ""))
        edges.append({"id": f"f{len(edges) + 1}", "from": source, "to": target,
                      "when": str(e.get("when") or "").strip()[:200], "label": _text(e.get("label"), 40)})
    params = {}
    for key, value in (raw.get("params") or {}).items():
        if key not in PARAM_RANGES:
            continue
        low, high = PARAM_RANGES[key]
        number = _number(value, low, high, DEFAULT_PARAMS[key])
        try:
            if float(value) != number:
                notes.append(f"{PARAM_LABELS[key]} {value} อยู่นอกช่วงที่ปลอดภัย {low}–{high} ใช้ {number:g} แทน")
        except (TypeError, ValueError):
            pass
        if number == DEFAULT_PARAMS[key]:
            continue  # เท่ากับค่าเริ่มต้นอยู่แล้ว ไม่นับเป็นตัวเลขที่ครูกำหนด
        params[key] = int(number) if key in ("max_items", "mastery_window") else number
    start = renamed.get(str(raw.get("start")), _slug(raw.get("start"), ""))
    if start not in seen:
        start = next((s["id"] for s in steps if s["kind"] in START_KINDS), "")
    spec = {"summary": _text(raw.get("summary"), 400), "start": start, "params": params, "steps": steps, "edges": edges}
    # แนวทางของครูแต่ละข้อ และขั้นที่ทำแนวทางนั้น (AI เขียนก่อนออกแบบ ครูใช้ตรวจว่าครบ)
    guidelines = []
    for g in raw.get("guidelines") or []:
        if isinstance(g, dict) and _text(g.get("text"), 300):
            where = [renamed.get(str(x), _slug(x, "")) for x in g.get("steps") or [] if str(x).strip()]
            guidelines.append({"text": _text(g.get("text"), 300), "steps": [w for w in where if w]})
    if guidelines:
        spec["guidelines"] = guidelines[:30]
    return spec, notes


def _clamp_step(step: dict, key: str, default: float, notes: list[str], label: str) -> float:
    low, high = STEP_NUMBERS[key]
    value = step.get(key, default)
    number = _number(value, low, high, default)
    try:
        if float(value) != number:
            notes.append(f"ขั้น \"{label}\": {value} วินาทีอยู่นอกช่วงที่ปลอดภัย {low}–{high} ใช้ {number:g} แทน")
    except (TypeError, ValueError):
        pass
    return number


def validate(raw: dict, bugs: list[str] | None = None) -> dict:
    """คืน {"spec", "errors", "warnings"} ถ้ามี errors ห้ามบันทึก Flow นี้ bugs = รหัสใน Bug Library ของคลัง (ถ้ารู้)"""
    try:
        spec, warnings = normalize(raw)
    except FlowError as error:
        return {"spec": None, "errors": [str(error)], "warnings": []}
    errors: list[str] = []
    steps = {s["id"]: s for s in spec["steps"]}
    if not steps:
        return {"spec": spec, "errors": ["Flow ต้องมีอย่างน้อยหนึ่งขั้น"], "warnings": warnings}
    # เริ่มได้ด้วยขั้นที่นักเรียนทำเองได้ เช่น ทำโจทย์ อ่านบทเรียนย่อก่อน หรือกิจกรรม (ไม่ใช่ขั้นจบ พัก หรือรอครู)
    if not spec["start"] or steps[spec["start"]]["kind"] not in START_KINDS:
        errors.append("ขั้นแรกของ Flow ต้องเป็นขั้นทำโจทย์ บทเรียนย่อ อธิบายความคิด หรือกิจกรรม")
    elif not any(s["kind"] == "item" for s in steps.values()):
        errors.append("Flow ต้องมีขั้นทำโจทย์อย่างน้อยหนึ่งขั้น")
    out: dict[str, list[dict]] = {sid: [] for sid in steps}
    for edge in spec["edges"]:
        if edge["from"] not in steps or (edge["to"] not in steps and edge["to"] != BACK):
            errors.append(f"เส้น \"{edge['label'] or edge['id']}\" ชี้ไปขั้นที่ไม่มีใน Flow")
            continue
        try:
            used = conditions.names(edge["when"])
        except conditions.ConditionError as error:
            errors.append(str(error))
            continue
        edge["text"] = conditions.describe(edge["when"])
        if bugs is not None:
            for code in re.findall(r"bug\s*[!=]=\s*[\"']([^\"']+)[\"']", edge["when"]):
                if code not in bugs:
                    warnings.append(f"เส้น \"{edge['label'] or edge['id']}\" อ้างรหัส {code} ที่ไม่มีใน Bug Library ของคลังโจทย์")
        kind = steps[edge["from"]]["kind"]
        answer_vars = used & {"correct", "wrong", "misconception", "slip", "first_try", "rt", "rt_ratio", "slow"}
        if answer_vars and kind not in ("item", "hint", "check", "notify"):
            warnings.append(f"เส้นจาก \"{steps[edge['from']]['label']}\" ใช้ผลการตอบ ({', '.join(sorted(answer_vars))}) "
                            "แต่ขั้นนี้ไม่ได้รับคำตอบ ค่าจะเป็นของคำตอบล่าสุด")
        if used & {"judge_pass", "judge_score"} and kind not in ("reflect", "activity"):
            warnings.append(f"เส้นจาก \"{steps[edge['from']]['label']}\" ใช้ผลการประเมินคำอธิบาย แต่ไม่ใช่ขั้นอธิบายความคิด")
        out[edge["from"]].append(edge)
    for sid, step in steps.items():
        if step["kind"] != "end" and not out[sid]:
            errors.append(f"ขั้น \"{step['label']}\" ไม่มีเส้นออก นักเรียนจะติดอยู่ที่ขั้นนี้")
        if step["kind"] == "activity" and step.get("response") == "text" and not step.get("rubric"):
            warnings.append(f"ขั้น \"{step['label']}\" ให้นักเรียนพิมพ์ตอบแต่ยังไม่มีเกณฑ์ประเมิน AI จะประเมินตามเป้าหมายของกิจกรรม")
        if step["kind"] == "reflect" and step.get("judge") and not step.get("rubric"):
            warnings.append(f"ขั้น \"{step['label']}\" ให้ AI ประเมินแต่ยังไม่มีเกณฑ์ของครู")
        catch_all = [i for i, e in enumerate(out[sid]) if not (e["when"] or "").strip() or e["when"].strip() in conditions.ALWAYS]
        if catch_all and catch_all[0] < len(out[sid]) - 1:
            warnings.append(f"ขั้น \"{step['label']}\": เส้นหลัง \"{out[sid][catch_all[0]]['label'] or 'ทุกกรณี'}\" ไม่มีวันถูกใช้ "
                            "เพราะเส้นนั้นผ่านเสมอ")
    if errors:
        return {"spec": spec, "errors": errors, "warnings": warnings}
    reachable = _reachable(spec["start"], out)
    for sid, step in steps.items():
        if sid not in reachable:
            warnings.append(f"ขั้น \"{step['label']}\" ไปไม่ถึงจากขั้นแรก")
    if not any(steps[s]["kind"] == "end" for s in reachable):
        errors.append("Flow ต้องไปถึงขั้นจบได้ (เพดานจำนวนข้อยังจบ Session ให้อยู่แล้ว แต่ควรมีเกณฑ์จบของครู)")
    for g in spec.get("guidelines", []):
        if not any(sid in steps for sid in g["steps"]):
            errors.append(f"แนวทาง \"{g['text'][:80]}\" ยังไม่มีขั้นใน Flow ที่ทำแนวทางนี้ (ใส่ id ของขั้นใน steps ของแนวทาง)")
    loop = _instant_loop(steps, out)
    if loop:
        errors.append("มีวงที่วนผ่าน " + " → ".join(steps[s]["label"] for s in loop)
                      + " โดยไม่หยุดรอนักเรียน ต้องมีขั้นทำโจทย์หรือขั้นรออยู่ในวง")
    for sid, step in steps.items():
        if step["kind"] == "item":
            warnings += _coverage(step, out[sid])
    return {"spec": spec, "errors": errors, "warnings": list(dict.fromkeys(warnings))}


def _reachable(start: str, out: dict[str, list[dict]]) -> set[str]:
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node in seen or node not in out:
            continue
        seen.add(node)
        stack += [e["to"] for e in out[node] if e["to"] != BACK]
    return seen


def _waits(step: dict) -> bool:
    if step["kind"] == "hint":
        return float(step.get("delay") or 0) > 0
    return KINDS[step["kind"]]["wait"]


def _instant_loop(steps: dict, out: dict[str, list[dict]]) -> list[str] | None:
    """หาวงที่ทุกขั้นเป็นขั้นแบบผ่าน (engine จะวนไม่หยุด)"""
    instant = {sid for sid, s in steps.items() if not _waits(s)}
    state: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for edge in out[node]:
            nxt = edge["to"]
            if nxt == BACK or nxt not in instant:
                continue
            if state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        state[node] = 2
        path.pop()
        return None

    for node in instant:
        if node not in state:
            found = visit(node)
            if found:
                return found
    return None


def _coverage(step: dict, edges: list[dict]) -> list[str]:
    """ลองค่าตัวอย่างของคำตอบถูกและผิด ถ้าไม่มีเส้นไหนรับ engine จะใช้ทางเริ่มต้น (บอกครูไว้)"""
    base = {k: ("" if v[1] == "text" else 0) for k, v in conditions.VARS.items()}
    base.update(mastery=0.5, concept_mastery=0.5, visits=1, judge_pass=None, judge_score=None)
    # ตอนตัดสินเส้นหลังตอบถูก ข้อนี้นับเป็นข้อที่ทำถูกแล้ว (items_done, solved_here, streak รวมข้อนี้)
    cases = [("ตอบถูก", {**base, "correct": True, "first_try": True, "items_done": 1, "solved_here": 1, "streak": 1})]
    cases += [(f"ผิดครั้งที่ {n}", {**base, "wrong": True, "error_count": n, "misconception": m})
              for n in range(1, STUCK_LIMIT) for m in (False, True)]
    notes = []
    targets = []
    for name, values in cases:
        match = next((e for e in edges if conditions.evaluate(e["when"], values)), None)
        if match is None:
            notes.append(f"ขั้น \"{step['label']}\" ไม่มีเส้นรับกรณี{name} engine จะ"
                         + ("ให้ข้อถัดไปในขั้นเดิม" if values.get("correct") else "ให้ลองข้อเดิมต่อ"))
            break
        if values.get("wrong"):
            targets.append(match["to"])
    if targets and set(targets) == {step["id"]}:
        notes.append(f"ขั้น \"{step['label']}\": ตอบผิดกี่ครั้งก็ลองข้อเดิมที่ขั้นเดิม ไม่มีคำใบ้หรือทางออก "
                     f"จนผิดครบ {STUCK_LIMIT} ครั้งระบบจึงส่งต่อครู")
    return notes


def leak_warnings(spec: dict, items: list[dict]) -> list[str]:
    """บทเรียนย่อที่ยกโจทย์ในคลังมาพร้อมคำตอบ ระบบจะซ่อนข้อความนั้นจากนักเรียน (Answer-Leak Guard)"""
    from ..engine.gemflow import leaked_item

    notes = []
    for step in spec["steps"]:
        if step["kind"] == "lesson":
            found = leaked_item(step.get("text") or "", items)
            if found:
                notes.append(f"บทเรียนย่อ \"{step['label']}\" มีโจทย์ข้อ {found} พร้อมคำตอบ ระบบจะซ่อนข้อความนี้จากนักเรียน "
                             "แก้ให้เป็นตัวอย่างที่ไม่อยู่ในคลังโจทย์")
    return notes


# ---------------------------------------------------------------- สิ่งที่หน้าเว็บใช้

def catalog() -> dict:
    """คลังขั้น ตัวแปร วิธีเลือกโจทย์ ช่วงตัวเลข และสิ่งที่ล็อกไว้ สำหรับแท็บ Flow ของครู"""
    return {
        "kinds": [{"key": k, **v} for k, v in KINDS.items()],
        "picks": [{"key": k, "label": v} for k, v in PICKS.items()],
        "vars": [{"key": k, "label": v[0], "type": v[1]} for k, v in conditions.VARS.items()],
        "params": [{"key": k, "label": PARAM_LABELS[k], "min": lo, "max": hi, "default": DEFAULT_PARAMS[k]}
                   for k, (lo, hi) in PARAM_RANGES.items()],
        "step_numbers": {k: {"min": lo, "max": hi} for k, (lo, hi) in STEP_NUMBERS.items()},
        "locked": LOCKED,
        "guards": GUARDS,
    }


def map_view(spec: dict) -> dict:
    """กล่องและเส้นสำหรับวาดผังของ Gem (หน้าเว็บจัดตำแหน่งเองด้วย dagre)"""
    nodes = [{"id": s["id"], "label": s["label"], "kind": s["kind"], "lane": KINDS[s["kind"]]["lane"],
              "about": describe_step(s), "start": s["id"] == spec["start"]} for s in spec["steps"]]
    # เส้น "back" วาดเป็นสัญลักษณ์วนกลับที่กล่องต้นทาง (กลับขั้นทำโจทย์ที่นักเรียนมา)
    edges = [{"id": e["id"], "source": e["from"], "target": e["from"] if e["to"] == BACK else e["to"],
              "label": e.get("label") or ("กลับขั้นทำโจทย์เดิม" if e["to"] == BACK else ""),
              "when": e.get("when") or "", "text": conditions.describe(e.get("when"))} for e in spec["edges"]]
    return {"nodes": nodes, "edges": edges, "guards": GUARDS}


def describe_step(step: dict) -> str:
    about = _describe(step)
    return f"{about} · มาจาก: {step['reason']}" if step.get("reason") else about


def _describe(step: dict) -> str:
    kind = step["kind"]
    if kind == "item":
        return f"{PICKS[step['pick']]} · " + ("กดขอคำใบ้ได้" if step.get("hint_button") else "ไม่มีปุ่มคำใบ้")
    if kind == "hint":
        level = "ตามครั้งที่ผิดและผลวินิจฉัย" if step["level"] == "auto" else f"ระดับ {step['level']}"
        return f"คำใบ้{level}" + (f" หลังหน่วง {step['delay']:g} วินาที" if step.get("delay") else " ทันที")
    if kind == "lesson":
        return (step.get("text") or "")[:120] + (" (พร้อมตัวอย่างทีละขั้น)" if step.get("walkthrough") else "")
    if kind == "reflect":
        return step["question"] + (" · AI ประเมินตามเกณฑ์ของครู" if step.get("judge") else "")
    if kind == "break":
        return f"พัก {step['seconds']:g} วินาที"
    if kind in ("notify", "teacher"):
        return step.get("text") or ""
    if kind == "activity":
        return step.get("goal", "") + (" · นักเรียนพิมพ์ตอบ AI ประเมินตามเกณฑ์" if step.get("response") == "text" else "")
    if kind == "end":
        return "จบชุด (สำเร็จ)" if step.get("result") == "completed" else "หยุดไว้ก่อน บันทึกความคืบหน้า"
    return KINDS[kind]["about"]


def record(flow_spec: dict, source: str, warnings: list[str], reviewed: bool) -> dict:
    """Flow ที่เก็บใน Gem (gem["flow"])"""
    return {"mode": "custom", "spec": flow_spec, "source": source, "warnings": warnings, "reviewed": reviewed,
            "updated_at": time.time()}


# Gem ที่ยังไม่มี Flow ที่ออกแบบจาก prompt (นักเรียนยังเริ่มเรียนไม่ได้) ผังมาตรฐานเป็นแค่แม่แบบอ้างอิง
# ของหัวข้อ 3–6 และ Stress Test ไม่ใช้เป็น Flow ของ Gem
STANDARD = {"mode": "standard"}


# ---------------------------------------------------------------- prompt ให้ AI ออกแบบ Flow

def design_prompt(gem: dict, errors: list[str] | None = None, previous: dict | None = None,
                  memory: dict | None = None, bugs: list[dict] | None = None) -> str:
    kinds = "\n".join(f"- {k}: {v['about']}" for k, v in KINDS.items())
    picks = "\n".join(f"  - {k}: {v}" for k, v in PICKS.items())
    variables = "\n".join(f"- {k}: {v[0]}" for k, v in conditions.VARS.items())
    params = "\n".join(f"- {k}: {PARAM_LABELS[k]} ช่วง {lo}–{hi} (ค่าเริ่มต้น {DEFAULT_PARAMS[k]:g})"
                       for k, (lo, hi) in PARAM_RANGES.items())
    text = (
        "คุณออกแบบ Flow การสอนของติวเตอร์ภาษาไทยจากคำสั่งของครู Flow คือกราฟของขั้นที่ engine รันได้จริง\n\n"
        f"ชื่อ Gem: {gem.get('name', '')}\nคำอธิบาย: {gem.get('description', '')}\n"
        f"คำสั่งของครู:\n\"\"\"\n{gem.get('instructions', '')}\n\"\"\"\n"
        + (f"สิ่งที่ AI จดจากเอกสารของครู (แนวทางการสอน ข้อผิดพลาด โจทย์ของครู):\n{json.dumps(memory, ensure_ascii=False)[:12000]}\n"
           if memory else "")
        + ("Bug Library ของคลังโจทย์ (ใช้รหัสเหล่านี้ในเงื่อนไข bug == \"รหัส\"):\n"
           + "\n".join(f"- {b['id']} ({b['type']}): {b['name']}" for b in bugs) + "\n" if bugs else "")
        + "\n"
        f"ชนิดขั้นที่ใช้ได้:\n{kinds}\n"
        f"ขั้น item มี pick (วิธีเลือกโจทย์):\n{picks}\n"
        "เส้นที่ to เป็น \"back\" = กลับไปขั้นทำโจทย์ที่นักเรียนเพิ่งมาจาก (ทำข้อเดิมต่อ) ใช้กับขั้นคำใบ้ บทเรียน หรือกิจกรรม "
        "ที่หลายขั้นโจทย์ใช้ร่วมกัน ไม่ต้องเดาด้วยเงื่อนไข\n"
        "ขั้น item มี hint_button (true เฉพาะเมื่อคำสั่งของครูให้นักเรียนกดขอคำใบ้เองได้ ไม่ได้สั่ง = false ไม่ต้องใส่ปุ่ม), hint มี level (1, 2, 3 หรือ \"auto\") และ delay "
        "(หน่วงเวลาหลังตอบผิดก่อนแสดงคำใบ้ วินาที 0–60 เช่น \"ผิดแล้วให้คิดเองก่อน 20 วินาที\" = delay 20 ไม่ใช่ params), "
        "lesson มี title, text (เนื้อหาสั้น ๆ ไม่เกิน 5 บรรทัด ห้ามมีคำตอบของโจทย์) และ walkthrough (true = แสดงตัวอย่างทีละขั้นของมโนทัศน์), "
        "reflect มี question, judge (true เฉพาะเมื่อครูสั่งให้ประเมินคำอธิบาย) และ rubric (เกณฑ์ของครู), "
        "break มี seconds (15–300) และ text, notify มี level (urgent/normal/silent) และ text, teacher มี text, "
        "end มี result (completed/stopped) และ text, "
        "activity มี title, goal (บรรยายให้ชัดว่า AI ต้องสร้างกิจกรรมอะไร อิงเอกสารของครู), response (\"none\" หรือ \"text\") "
        "และ rubric (เกณฑ์ประเมินเมื่อ response เป็น text)\n\n"
        "กติกาของขั้นทำโจทย์: กลับมาที่ขั้น item เดิมขณะที่ข้อยังไม่ถูก = ทำข้อเดิมต่อ (ใช้หลังให้คำใบ้) "
        "ถ้าข้อถูกแล้วหรือมาจากขั้น item อื่น = ได้ข้อใหม่ตาม pick "
        "หลังทบทวนพื้นฐาน (pick prerequisite) ขั้น item ถัดไปจะให้ข้อที่พักไว้ก่อนเสมอ\n\n"
        "เงื่อนไขบนเส้น (when) เขียนแบบ Python ใช้ได้แค่ and, or, not, ==, !=, <, <=, >, >=, ตัวเลข ข้อความในเครื่องหมายคำพูด "
        "และตัวแปรเหล่านี้ (แยกทางตามข้อผิดพลาดได้ เช่น wrong and bug == \"BUG-M01\" หรือ bug_type == \"slip\"):\n"
        f"{variables}\n"
        "เส้นออกจากขั้นเดียวกันเรียงตามลำดับ เส้นแรกที่เป็นจริงชนะ ให้เส้นสุดท้ายเป็น \"\" (ทุกกรณีที่เหลือ) เสมอ\n\n"
        f"ตัวเลขของทั้ง Flow (params) ใส่เฉพาะที่คำสั่งของครูพูดถึงตรง ๆ ต้องอยู่ในช่วง "
        f"(hint_unlock_wait คือเวลาที่ต้องคิดก่อนกดขอคำใบ้เองได้ ก่อนลองตอบครั้งแรก):\n{params}\n"
        "ตัวเลขในขั้นและในเงื่อนไขให้เอามาจากคำสั่งของครู ถ้าครูไม่ได้บอกให้ใช้ค่าของแม่แบบ\n\n"
        "สิ่งที่ระบบล็อกไว้ ไม่ต้องใส่ใน Flow: " + " · ".join(l["title"] for l in LOCKED) + "\n\n"
        "ออกแบบ Flow เฉพาะของบทเรียนนี้เสมอ ไม่ลอกแม่แบบ: อ่านคำสั่งและสิ่งที่จดจากเอกสาร แล้วแปลงทุกแนวทางเป็นขั้นและเส้น "
        "เพิ่ม ตัด หรือสลับขั้นได้อิสระ ถ้าแนวทางของครูต้องการสิ่งที่ชนิดขั้นอื่นทำไม่ได้ ให้ใช้ขั้น activity และบรรยายใน goal\n"
        "สิ่งที่ระบบทำให้เองแล้ว ไม่ต้องสร้างขั้นแยก: ข้อความคำใบ้ของแต่ละระดับถูกเลือกตามรหัสข้อผิดพลาดของคำตอบล่าสุดอัตโนมัติ "
        "(ตารางคำใบ้ของครูต่อรหัส) จึงใช้ขั้น hint ระดับละหนึ่งขั้นร่วมกันทุกรหัส แยกเส้นด้วย bug หรือ bug_type "
        "เฉพาะเมื่อระดับคำใบ้หรือทางต่อไปต่างกัน เช่น Slip ที่ครูให้แค่สะกิด = bug_type == \"slip\" ไปคำใบ้ระดับ 1 เสมอ "
        "Misconception ที่ไล่ทีละระดับ = error_count 1, 2, 3 ไปคำใบ้ระดับ 1, 2, 3\n"
        "ออกแบบตาม prompt ของครูทั้งหมด: ทุกขั้นและทุกเส้นต้องมาจากคำสั่งของครูหรือเอกสารที่แนบเท่านั้น "
        "(1) ไล่แนวทางทุกข้อจากคำสั่ง สิ่งที่จดจากเอกสาร และตารางข้อผิดพลาด (เช่น ระดับคำใบ้ของแต่ละรหัส Slip ให้แค่สะกิด "
        "ลำดับขั้นวิธีทำ กิจกรรมที่ครูอยากให้ทำ เกณฑ์จบ) (2) ทำให้ทุกข้อเป็นขั้นหรือเส้นจริง ห้ามตกหล่น "
        "(3) ห้ามเพิ่มขั้นที่ครูไม่ได้สั่งและเอกสารไม่ได้พูดถึง เช่น ข้อคู่ขนาน ทบทวนพื้นฐาน พัก หรือรอครู "
        "ถ้าครูไม่ได้สั่งไว้ ไม่ต้องใส่ แม้แม่แบบมาตรฐานจะมี\n"
        "ทุกขั้นต้องมี reason = ข้อความจากคำสั่งหรือเอกสารที่เป็นที่มาของขั้นนั้น (ยกมาสั้น ๆ)\n"
        "เขียน guidelines ก่อนออกแบบ: รายการแนวทางทุกข้อของครู (หนึ่งข้อต่อหนึ่งแนวทาง เช่น \"Slip ให้คำใบ้ระดับ 1 อย่างเดียว\" "
        "\"BUG-M01 ผิดครั้งที่ 2 ให้คำใบ้ระดับ 2\") แต่ละข้อมี steps = id ของขั้นที่ทำแนวทางนั้น ทุกข้อต้องมีขั้นรองรับจริง "
        "แล้วตรวจเงื่อนไขบนเส้นด้วยการไล่สถานการณ์จริง เช่น ผิดครั้งแรก (error_count == 1, hint_level == 0) ต้องไปขั้นที่ครูกำหนด\n"
        "กรณีที่ครูไม่ได้บอกว่าต้องทำอะไร ให้ใช้ทางที่เรียบง่ายที่สุดที่สอดคล้องกับแนวทางของครู โดยไม่สร้างขั้นใหม่ "
        "เช่น ผิดแบบที่ครูไม่ได้พูดถึง = ใช้คำใบ้แบบที่ครูกำหนดไว้แล้ว หรือลองข้อเดิม เกณฑ์จบที่ครูไม่ได้บอก = correct and mains_left == 0 "
        "ระบบมีกลไกที่ล็อกไว้รองรับอยู่แล้ว (ผิดข้อเดียวกันครบ 6 ครั้งส่งต่อครู เพดานจำนวนข้อ เดาสุ่ม หน้าจอนิ่ง) ไม่ต้องเติมขั้นกันพลาดเอง\n"
        "ทุกขั้นต้องมีทางออก และต้องไปถึงขั้น end ได้\n"
        f"ตัวอย่างรูปแบบ JSON (ดูแค่รูปแบบ ห้ามลอกเนื้อหา):\n{json.dumps(FORMAT_EXAMPLE, ensure_ascii=False)}\n\n"
        "ตอบเป็น JSON รูปเดียวกับตัวอย่างเท่านั้น: guidelines, summary (สรุปให้ครูอ่าน 2–4 ประโยค), "
        "start, params, steps (ทุกขั้นมี reason), edges ป้าย (label) ของขั้นและเส้นสั้นไม่เกิน 4 คำ ภาษาไทย"
    )
    if errors and previous:
        text += ("\n\nFlow ที่คุณส่งมารอบก่อนตรวจไม่ผ่าน แก้ข้อผิดพลาดเหล่านี้แล้วส่งใหม่ทั้งหมด:\n- " + "\n- ".join(errors)
                 + f"\nFlow รอบก่อน:\n{json.dumps(previous, ensure_ascii=False)[:6000]}")
    return text


# ตัวอย่างรูปแบบ JSON ที่สั้นและไม่เกี่ยวกับบทเรียนใด ไม่ให้ AI ยึดติดกับโครงของแม่แบบมาตรฐาน
FORMAT_EXAMPLE = {
    "guidelines": [
        {"text": "ทำโจทย์ทีละข้อตามลำดับ", "steps": ["work"]},
        {"text": "ผิดให้ดูตัวอย่างก่อนลองใหม่", "steps": ["show"]},
        {"text": "ทำครบทุกข้อแล้วจบ", "steps": ["done"]},
    ],
    "summary": "ครูสั่งให้ทำโจทย์ทีละข้อ ผิดให้ดูตัวอย่างก่อนลองใหม่ ทำครบทุกข้อแล้วจบ",
    "start": "work", "params": {},
    "steps": [
        {"id": "work", "kind": "item", "label": "ทำโจทย์", "pick": "main", "hint_button": False,
         "reason": "ทำโจทย์ทีละข้อตามลำดับ"},
        {"id": "show", "kind": "lesson", "label": "ดูตัวอย่าง", "title": "ตัวอย่าง", "text": "", "walkthrough": True,
         "reason": "ผิดให้ดูตัวอย่างก่อนลองใหม่"},
        {"id": "done", "kind": "end", "label": "จบ", "result": "completed", "text": "ทำครบแล้ว",
         "reason": "ทำครบทุกข้อแล้วจบ"},
    ],
    "edges": [
        {"from": "work", "to": "done", "when": "correct and mains_left == 0", "label": "ครบทุกข้อ"},
        {"from": "work", "to": "work", "when": "correct", "label": "ข้อถัดไป"},
        {"from": "work", "to": "show", "when": "", "label": "ผิด"},
        {"from": "show", "to": "work", "when": "", "label": "ลองใหม่"},
    ],
}


async def design(gem: dict, memory: dict | None = None, bugs: list[dict] | None = None) -> dict:
    """ให้ AI ออกแบบ Flow เฉพาะของ Gem จากคำสั่งของครูและสิ่งที่จดจากเอกสาร ตรวจผ่านแล้วคืน gem["flow"]
    แก้สองรอบแล้วยังตรวจไม่ผ่าน ใช้ผังมาตรฐานของระบบ (บอกครูในคำเตือน)"""
    from . import builder  # builder import ไฟล์นี้ตอนสร้างคลังโจทย์

    errors, previous = None, None
    bug_ids = [b["id"] for b in bugs] if bugs else None
    for _ in range(3):
        # ออกแบบ Flow ต้องไล่แนวทางของครูทีละข้อ จึงให้โมเดลคิดเต็มที่ (โทเคนที่ใช้คิดนับรวมใน max_tokens)
        raw = await builder.ask_json("flow", design_prompt(gem, errors, previous, memory, bugs), 32000, thinking="high")
        raw = raw if isinstance(raw, dict) else {}
        checked = validate(raw, bug_ids)
        if not checked["errors"]:
            return record(checked["spec"], "ai", checked["warnings"], reviewed=False)
        errors, previous = checked["errors"], raw
    # ผังมาตรฐานเป็นแค่แม่แบบอ้างอิง ไม่ใช้แทน Flow ของ Gem: ออกแบบไม่ผ่านก็แจ้งให้ออกแบบใหม่
    raise builder.BuildError("AI ออกแบบ Flow ที่ตรวจผ่านไม่ได้ 3 รอบ (" + "; ".join(errors or [])[:300] + ") "
                             "กดให้ AI ออกแบบใหม่ในแท็บ Flow หรือเขียนคำสั่งให้ชัดขึ้น")
