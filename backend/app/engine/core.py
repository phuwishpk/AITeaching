"""engine หลัก: รับเหตุการณ์ของนักเรียน แล้วตัดสินว่าจะย้ายไป Flow Position ไหน

engine ไม่แตะฐานข้อมูลและไม่เรียก AI เอง ทุกฟังก์ชันรับ state (dict) กับ Ctx แล้วคืน Fx
ซึ่งบอกว่าต้องบันทึก Decision Trace อะไร แจ้งครูเรื่องอะไร และต้องขอคำใบ้ระดับไหน
service จะเป็นคนทำงานเหล่านั้นต่อ แยกแบบนี้เพื่อให้ทดสอบตรรกะได้ด้วยนาฬิกาจำลอง
"""

import copy
from dataclasses import dataclass, field

from ..config import DEFAULT_PARAMS, SCALED_PARAMS, WEIGHTS
from ..ml import fuzzy
from . import flow as F
from .answers import check_answer, match_bug

PATH_LABELS = {"FAST_TRACK": "Fast-Track", "STANDARD": "Standard Flow", "SUPPORTED": "Supported Flow"}

STUDENT_LABELS = {
    F.ANSWERING: "กำลังทำโจทย์",
    F.DELAY: "ลองตรวจคำตอบด้วยตัวเองก่อนนะ",
    F.LOCK: "อ่านโจทย์ให้ครบอีกครั้ง",
    F.HINT_L1: "มีคำใบ้ช่วยแล้ว",
    F.HINT_L2: "มีคำใบ้ช่วยแล้ว",
    F.HINT_L3: "มีคำใบ้ช่วยแล้ว",
    F.ISO: "ข้อทดสอบความเข้าใจ",
    F.IMPASSE: "กำลังเตรียมโจทย์ทบทวน",
    F.REMEDIAL: "ทบทวนพื้นฐาน",
    F.CB: "พักสายตาสักครู่",
    F.WALK: "ดูตัวอย่างทีละขั้น",
    F.IDLE: "พักอยู่",
    F.CHOOSE: "เลือกทางต่อ",
    F.SAFETY: "ครูกำลังมาช่วย",
    F.DEADLOCK: "รอครูช่วยในข้อนี้",
    F.DONE: "จบชุดแล้ว",
    F.ENDED: "จบรอบนี้แล้ว",
}

BLOCK_MESSAGES = {
    F.LOCK: "ระบบพักปุ่มตอบไว้สักครู่ ลองอ่านโจทย์อีกครั้งนะ",
    F.CB: "ตอนนี้เป็นช่วงพักสายตา",
    F.WALK: "อ่านตัวอย่างให้จบก่อนนะ",
    F.IDLE: "กดทำต่อเมื่อพร้อม",
    F.CHOOSE: "เลือกทางต่อก่อนนะ",
    F.SAFETY: "ครูกำลังมาช่วย",
    F.DEADLOCK: "ครูกำลังจะมาช่วยในข้อนี้",
    F.DONE: "ทำชุดนี้จบแล้ว",
    F.ENDED: "จบรอบนี้แล้ว",
}


class Content:
    """ตัวช่วยค้นข้อมูลในวิชาหนึ่งวิชา (Subject) และชุดคำถาม (Question Set) ที่กำลังทำ"""

    def __init__(self, subject: dict, set_id: str):
        self.subject = subject
        self.qs = next(q for q in subject["question_sets"] if q["id"] == set_id)
        self.items = {it["id"]: it for it in subject["items"]}
        self.concepts = {c["id"]: c for c in subject["concepts"]}
        self.tags = {t["id"]: t for t in subject.get("bug_tags", [])}
        self.walks = {w["concept"]: w for w in subject.get("walkthroughs", [])}

    @property
    def target(self) -> str:
        return self.qs["target_concept"]

    def item(self, item_id: str) -> dict:
        return self.items[item_id]

    def concept_name(self, concept_id: str) -> str:
        concept = self.concepts.get(concept_id)
        return concept["name"] if concept else concept_id

    def main_items(self) -> list[dict]:
        return [self.items[i] for i in self.qs.get("main_items", []) if i in self.items]

    def challenge_items(self) -> list[dict]:
        return [self.items[i] for i in self.qs.get("challenge_items", []) if i in self.items]

    def isomorphs(self, item_id: str) -> list[dict]:
        item = self.items.get(item_id, {})
        ids = item.get("isomorphs") or [i for i, it in self.items.items() if it.get("iso_of") == item_id]
        return [self.items[i] for i in ids if i in self.items]

    def remedial_items(self, concept_id: str) -> list[dict]:
        return [it for it in self.items.values() if it["concept"] == concept_id and it["kind"] == "remedial"]

    def prerequisites(self, concept_id: str) -> list[str]:
        concept = self.concepts.get(concept_id)
        return list(concept.get("prerequisites", [])) if concept else []

    def walkthrough(self, concept_id: str | None) -> dict | None:
        return self.walks.get(concept_id) if concept_id else None

    def tag(self, tag_id: str | None) -> dict | None:
        return self.tags.get(tag_id) if tag_id else None


@dataclass
class Ctx:
    content: Content
    params: dict = field(default_factory=dict)
    time_scale: float = 1.0
    now: float = 0.0

    def p(self, key: str) -> float:
        return self.params.get(key, DEFAULT_PARAMS[key])

    def dur(self, key: str) -> float:
        value = self.p(key)
        return value * self.time_scale if key in SCALED_PARAMS else value


class Fx:
    """ผลของเหตุการณ์หนึ่งครั้ง ให้ service นำไปบันทึกและส่งต่อ"""

    def __init__(self):
        self.decisions: list[dict] = []
        self.traces: list[dict] = []
        self.alerts: list[dict] = []
        self.hint_requests: list[dict] = []
        self.tag_requests: list[dict] = []
        self.session_end: str | None = None
        self.result: dict = {}

    def trace(self, action: str, target: str | None, data: dict | None = None, ts: float = 0.0):
        self.traces.append({"action": action, "target": target, "data": data or {}, "ts": ts})


# ---------------------------------------------------------------- state

def new_state(code: str, subject_id: str, set_id: str, session_id: int, now: float) -> dict:
    return {
        "code": code,
        "subject_id": subject_id,
        "set_id": set_id,
        "session_id": session_id,
        "position": F.ANSWERING,
        "position_since": now,
        "path": "STANDARD",
        "item": None,
        "timers": {"delay_until": None, "lock_until": None, "break_until": None, "cooldown_until": None},
        "resume_position": None,
        "idle_since": None,
        "mastery": {},
        "format_stats": {},
        "done_items": [],
        "main_done": [],
        "used_iso": [],
        "challenge_correct": False,
        "items_count": 0,
        "iso_fail_streak": {},
        "remedial": None,
        "remedial_rounds": {},
        "after_walk": None,
        "walk_concept": None,
        "hint_presses": [],
        "hint_abuse_index": 0,
        "hints_shown": 0,
        "hints_useful": 0,
        "rapid_streak": 0,
        "rapid_total": 0,
        "idle_count": 0,
        "alerts_sent": [],
        "attempts_total": 0,
        "correct_total": 0,
        "first_attempt_correct": 0,
        "items_finished": 0,
        "rt_sum": 0.0,
        "rt_count": 0,
        "content_revisits": 0,
        "remedial_started": 0,
        "remedial_passed": 0,
        "started_at": now,
        "last_activity": now,
        "ended": False,
        "end_reason": None,
        "last_decision": None,
        "message": None,
    }


def new_item(item: dict, mode: str, now: float, iso_source: str | None = None) -> dict:
    return {
        "id": item["id"],
        "mode": mode,
        "concept": item["concept"],
        "format": item["format"],
        "started_at": now,
        "ready_at": now,
        "error_count": 0,
        "hint_level": 0,
        "hint_floor": 0,
        "pending_hint": 0,
        "hints": {},
        "rts": [],
        "attempts": [],
        "voided": False,
        "undo": None,
        "undo_used": False,
        "last_submit": None,
        "last_tag": None,
        "last_class": None,
        "iso_source": iso_source,
        "iso_attempts": 0,
        "socratic_index": 0,
        "hint_seen_before_attempt": False,
    }


def answer_position(state: dict) -> str:
    item = state.get("item")
    if not item:
        return F.ANSWERING
    if item["mode"] == "isomorphic":
        return F.ISO
    if item["mode"] == "remedial":
        return F.REMEDIAL
    if item["hint_level"] >= 1:
        return F.HINT_POSITIONS[min(item["hint_level"], 3)]
    return F.ANSWERING


def move(state: dict, ctx: Ctx, fx: Fx, to: str, edges: list[str], rule: str, detail: dict | None = None):
    decision = {
        "ts": ctx.now,
        "from": state["position"],
        "to": to,
        "edges": [e for e in edges if e],
        "rule": rule,
        "detail": detail or {},
        "item": state["item"]["id"] if state.get("item") else None,
    }
    state["position"] = to
    state["position_since"] = ctx.now
    state["last_decision"] = decision
    fx.decisions.append(decision)


def alert(fx: Fx, state: dict, level: str, kind: str, message: str, dedupe: bool = True):
    key = f"{state['session_id']}:{kind}"
    if dedupe and key in state["alerts_sent"]:
        return
    state["alerts_sent"].append(key)
    fx.alerts.append({"level": level, "kind": kind, "message": message})


def submit_edge(position: str) -> str:
    return {
        F.HINT_L1: "e_submit_l1",
        F.HINT_L2: "e_submit_l2",
        F.HINT_L3: "e_submit_l3",
        F.ISO: "e_submit_iso",
        F.REMEDIAL: "e_submit_rem",
        F.DELAY: "e_submit_delay",
    }.get(position, "e_submit")


# ---------------------------------------------------------------- Mastery

def item_weight(item: dict) -> float:
    if item["hint_level"] >= 1:
        return WEIGHTS[min(item["hint_level"], 3)]
    if item["error_count"] > 0:
        return WEIGHTS["self"]
    return WEIGHTS["first"]


def record_format(state: dict, concept: str, answer_format: str, correct: bool):
    stats = state["format_stats"].setdefault(concept, {})
    history = stats.setdefault(answer_format, [])
    history.append(1 if correct else 0)
    del history[:-6]


def cross_format_flag(state: dict, concept: str) -> bool:
    """Cross-Format Check: ปรนัยได้ดี แต่โจทย์เติมคำทำไม่ได้ แปลว่าที่ผ่านมาอาจเป็นการเดา"""
    stats = state["format_stats"].get(concept, {})
    mcq = stats.get("mcq", [])
    other = stats.get("numeric", []) + stats.get("short", [])
    if len(mcq) >= 2 and len(other) >= 2:
        return sum(mcq) / len(mcq) >= 0.8 and sum(other) / len(other) <= 0.34
    return False


def mastery_value(state: dict, ctx: Ctx, concept: str) -> float | None:
    entries = state["mastery"].get(concept, [])[-int(ctx.p("mastery_window")):]
    if not entries:
        return None
    penalize = cross_format_flag(state, concept)
    total = sum(e["w"] * (0.5 if penalize and e["fmt"] == "mcq" else 1.0) for e in entries)
    return round(total / len(entries), 4)


def add_mastery(state: dict, concept: str, weight: float, item_id: str, answer_format: str):
    state["mastery"].setdefault(concept, []).append({"w": weight, "fmt": answer_format, "item": item_id})


def zero_entry(state: dict, concept: str, item_id: str):
    for entry in reversed(state["mastery"].get(concept, [])):
        if entry["item"] == item_id:
            entry["w"] = 0.0
            return


def mastery_map(state: dict, ctx: Ctx) -> dict:
    return {c: mastery_value(state, ctx, c) for c in ctx.content.concepts}


# ---------------------------------------------------------------- เลือกโจทย์

def mode_for(content: Content, item_id: str) -> str:
    kind = content.item(item_id)["kind"]
    return {"main": "main", "challenge": "challenge", "remedial": "remedial"}.get(kind, "extra")


def serve(state: dict, ctx: Ctx, item: dict, mode: str, iso_source: str | None = None):
    state["item"] = new_item(item, mode, ctx.now, iso_source)
    state["items_count"] += 1
    if mode in ("isomorphic", "extra") and item["id"] not in state["used_iso"]:
        state["used_iso"].append(item["id"])
    state["timers"]["delay_until"] = None
    state["timers"]["lock_until"] = None


def pick_isomorph(state: dict, ctx: Ctx, item_id: str) -> dict | None:
    for iso in ctx.content.isomorphs(item_id):
        if iso["id"] not in state["used_iso"]:
            return iso
    return None


def extra_pool(state: dict, ctx: Ctx) -> list[dict]:
    """ฝึกเพิ่มเมื่อโจทย์หลักหมด: ใช้ Isomorphic Item ของข้อที่ทำไปแล้วที่ยังไม่เคยใช้"""
    pool = []
    for main in ctx.content.main_items():
        for iso in ctx.content.isomorphs(main["id"]):
            if iso["id"] not in state["used_iso"] and iso["id"] not in state["done_items"]:
                pool.append(iso)
    return pool


def select_next(state: dict, ctx: Ctx, path: str, target_difficulty: float) -> tuple[dict | None, str]:
    done = set(state["done_items"])
    current = state["item"]["id"] if state.get("item") else None
    mains = [it for it in ctx.content.main_items() if it["id"] not in done and it["id"] != current]
    if path == "FAST_TRACK":
        challenges = [it for it in ctx.content.challenge_items() if it["id"] not in done]
        pool = challenges or mains[:3]
    elif path == "SUPPORTED":
        pool = sorted(mains, key=lambda it: it["difficulty"])[:2]
    else:
        pool = mains[:3]
    if not pool:
        pool = extra_pool(state, ctx)
    if not pool:
        return None, "main"
    goal = target_difficulty / 100
    chosen = min(pool, key=lambda it: (abs(it["difficulty"] - goal), pool.index(it)))
    return chosen, mode_for(ctx.content, chosen["id"])


def choose_path(state: dict, ctx: Ctx, rt: float, expected: float) -> tuple[str, float | None, float]:
    target = ctx.content.target
    m = mastery_value(state, ctx, target)
    count = len(state["mastery"].get(target, []))
    slowness = rt / max(expected, 1.0)
    if m is not None and count >= 2 and m >= ctx.p("fast_track_mastery") and slowness < 1.0:
        return "FAST_TRACK", m, slowness
    if m is None or m >= ctx.p("standard_mastery"):
        return "STANDARD", m, slowness
    return "SUPPORTED", m, slowness


def finished(state: dict, ctx: Ctx) -> bool:
    target = ctx.content.target
    entries = state["mastery"].get(target, [])
    m = mastery_value(state, ctx, target)
    if len(entries) < ctx.p("finish_min_items") or m is None or m < ctx.p("finish_mastery"):
        return False
    mains = {it["id"] for it in ctx.content.main_items()}
    return mains.issubset(set(state["main_done"])) or state["challenge_correct"]


def next_remedial_item(state: dict, ctx: Ctx) -> dict | None:
    rem = state["remedial"]
    pool = ctx.content.remedial_items(rem["concept"])
    if rem.get("root") and not pool:
        suspended = ctx.content.item(rem["suspended"])
        pool = [
            it for it in ctx.content.main_items() + extra_pool(state, ctx)
            if it["id"] != suspended["id"] and it["difficulty"] <= suspended["difficulty"]
        ]
    if not pool:
        return None
    fresh = [it for it in pool if it["id"] not in rem["used"]]
    if not fresh:
        rem["used"] = []
        fresh = pool
    chosen = fresh[0]
    rem["used"].append(chosen["id"])
    return chosen


def choose_prerequisite(state: dict, ctx: Ctx, concept: str, tag: str | None) -> str | None:
    """เลือก Prerequisite: ตัวที่ผูกกับ Misconception ที่พบ ถ้าไม่มีใช้ตัวที่ Mastery ต่ำสุด"""
    options = [c for c in ctx.content.prerequisites(concept) if ctx.content.remedial_items(c)]
    if not options:
        return None
    linked = (ctx.content.tag(tag) or {}).get("prerequisite")
    if linked in options:
        return linked

    def score(c: str):
        m = mastery_value(state, ctx, c)
        return (0.4 if m is None else m, options.index(c))

    return min(options, key=score)


def next_socratic(state: dict, ctx: Ctx) -> str:
    item = state["item"]
    it = ctx.content.item(item["id"])
    questions = []
    tag = ctx.content.tag(item.get("last_tag"))
    if tag and tag.get("socratic"):
        questions.append(tag["socratic"])
    questions += it.get("socratic", [])
    if not questions:
        return "ลองบอกครูหน่อยว่าตอนนี้คิดถึงขั้นไหนแล้ว"
    question = questions[item["socratic_index"] % len(questions)]
    item["socratic_index"] += 1
    return question


# ---------------------------------------------------------------- เวลา

def resolve_timers(state: dict, ctx: Ctx, fx: Fx):
    """เปลี่ยนตำแหน่งที่ขึ้นกับเวลา: ครบ Deliberate Delay, ครบเวลาล็อก, ครบเวลาพัก"""
    for _ in range(3):
        timers = state["timers"]
        position = state["position"]
        now = ctx.now
        if position == F.DELAY and timers["delay_until"] and now >= timers["delay_until"]:
            item = state["item"]
            level = item["pending_hint"] or 1
            # คำใบ้ขึ้นจอตอนครบเวลา เวลาคิดครั้งถัดไปจึงเริ่มนับจากตอนนั้น
            item["ready_at"] = max(item["ready_at"], timers["delay_until"])
            reveal(state, level)
            edge = "e_delay_l2" if level >= 2 else "e_delay_l1"
            move(state, ctx, fx, answer_position(state), [edge], f"ครบ Deliberate Delay แสดงคำใบ้ระดับ {level}")
            continue
        if position == F.LOCK and timers["lock_until"] and now >= timers["lock_until"]:
            state["item"]["ready_at"] = timers["lock_until"]
            timers["lock_until"] = None
            back = state.get("resume_position") or answer_position(state)
            state["resume_position"] = None
            move(state, ctx, fx, back, ["e_lock_done"], "ครบเวลาล็อก กลับมาตอบได้")
            continue
        if position == F.CB and timers["break_until"] and now >= timers["break_until"]:
            timers["break_until"] = None
            move(state, ctx, fx, F.WALK, ["e_cb_done"], "พักครบแล้ว ไปอ่านตัวอย่างทีละขั้น")
            continue
        break


def reveal(state: dict, level: int):
    item = state["item"]
    if item["hint_level"] == 0 and level >= 1:
        state["hints_shown"] += 1  # ใช้คำนวณ Hint Utility Rate
    item["hint_level"] = max(item["hint_level"], min(level, 3))
    item["pending_hint"] = 0
    state["timers"]["delay_until"] = None


def need_hints(state: dict, fx: Fx, upto: int):
    """ขอข้อความคำใบ้ทุกระดับที่ยังไม่มี จนถึงระดับ upto (เช่น Floor = L2 ต้องมีทั้ง L1 และ L2)"""
    item = state["item"]
    for level in range(1, min(upto, 3) + 1):
        if str(level) not in item["hints"]:
            item["hints"][str(level)] = {"status": "pending"}
            fx.hint_requests.append({"level": level, "item_id": item["id"]})


def end_session(state: dict, ctx: Ctx, fx: Fx, position: str, edges: list[str], rule: str, reason: str):
    move(state, ctx, fx, position, edges, rule)
    state["ended"] = True
    state["end_reason"] = reason
    fx.session_end = reason


# ---------------------------------------------------------------- เริ่มชุดคำถาม

def begin(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    first, mode = select_next(state, ctx, state.get("path", "STANDARD"), 30)
    if first is None:
        end_session(state, ctx, fx, F.ENDED, [], "ชุดคำถามนี้ยังไม่มีโจทย์", "no_items")
        return fx
    serve(state, ctx, first, mode)
    state["ended"] = False
    state["end_reason"] = None
    move(state, ctx, fx, F.ANSWERING, ["e_start"], "เริ่มชุดคำถาม เส้นทาง Standard Flow", {"item": first["id"]})
    return fx


# ---------------------------------------------------------------- ส่งคำตอบ: กฎ 3 ด่าน

def submit(state: dict, ctx: Ctx, raw) -> Fx:
    """รับคำตอบหนึ่งครั้งแล้วไล่ด่าน 1 → 2 → 3 ด้วยเงื่อนไขซ้อนกัน (สไลด์หัวข้อ 3.1)"""
    fx = _submit(state, ctx, raw)
    check_burnout_risk(state, ctx, fx)
    return fx


def check_burnout_risk(state: dict, ctx: Ctx, fx: Fx):
    """Burnout Signal จาก Risk Score: แจ้งครูแบบเงียบเท่านั้น ไม่หยุดกิจกรรมของนักเรียน (กัน Algorithmic Determinism)"""
    if state["attempts_total"] < 5:
        return
    score = risk_score(state)["output"]
    if score >= ctx.p("burnout_risk"):
        alert(fx, state, "silent", "burnout_risk", f"Risk Score {score:.0f} ถึงเกณฑ์ Burnout Signal")


def _submit(state: dict, ctx: Ctx, raw) -> Fx:
    fx = Fx()
    now = ctx.now
    resolve_timers(state, ctx, fx)
    state["last_activity"] = now
    position = state["position"]
    item = state["item"]
    if position not in F.CAN_ANSWER or item is None:
        fx.result = {"kind": "blocked", "message": BLOCK_MESSAGES.get(position, "ตอนนี้ยังตอบไม่ได้")}
        return fx
    it = ctx.content.item(item["id"])
    raw_text = "" if raw is None else str(raw).strip()

    # ก่อนเข้าด่าน: กรองการส่งซ้ำจากเว็บกระตุก และคำตอบผิดรูปแบบ
    last = item["last_submit"]
    if last and last["raw"] == raw_text and now - last["ts"] < ctx.p("duplicate_window"):
        fx.trace("duplicate_ignored", item["id"], {"raw": raw_text}, now)
        fx.result = {"kind": "duplicate", "message": "ระบบรับคำตอบนี้ไปแล้ว"}
        return fx
    check = check_answer(it, raw_text)
    if not check.valid:
        fx.trace("invalid_answer", item["id"], {"raw": raw_text}, now)
        fx.result = {"kind": "invalid", "message": check.message}
        return fx

    snapshot = _snapshot(state)  # สภาพก่อนรับคำตอบนี้ ใช้กับปุ่มยกเลิกคำตอบล่าสุด
    item["last_submit"] = {"raw": raw_text, "ts": now}
    rt_raw = max(0.0, now - item["ready_at"])
    rt = min(rt_raw, ctx.p("rt_cap"))  # Data Cleaning: ตัดเวลาส่วนที่เกิน 5 นาทีทิ้ง
    first_attempt = not any(a["kind"] in ("correct", "wrong") for a in item["attempts"])
    attempt = {"ts": now, "raw": raw_text, "rt": round(rt, 2), "rt_raw": round(rt_raw, 2), "hint_level": item["hint_level"]}
    state["attempts_total"] += 1
    edges = [submit_edge(position), "e_clean_ok", "e_g1_pass"]
    base = {"item": it["id"], "rt": round(rt, 2), "rt_raw": round(rt_raw, 2), "error_count": item["error_count"]}

    # ---------- ด่าน 1: ตอบถูกไหม ----------
    if check.correct:
        attempt["kind"] = "correct"
        item["attempts"].append(attempt)
        _count_rt(state, rt)
        state["correct_total"] += 1
        state["rapid_streak"] = 0
        if item["hint_level"] >= 1:
            state["hints_useful"] += 1
        if first_attempt:
            record_format(state, it["concept"], it["format"], True)
            if item["hint_level"] == 0:
                state["first_attempt_correct"] += 1
        fx.trace("answer", it["id"], {**base, "correct": True, "raw": raw_text}, now)
        on_correct(state, ctx, fx, it, rt, edges + ["e_g1_correct"], base)
        return fx

    edges.append("e_g1_wrong")

    # ---------- ข้อทดสอบคู่ขนาน (Isomorphic Test) ไม่มีคำใบ้ ----------
    if item["mode"] == "isomorphic":
        attempt["kind"] = "wrong"
        item["attempts"].append(attempt)
        _count_rt(state, rt)
        fx.trace("answer", it["id"], {**base, "correct": False, "raw": raw_text, "isomorphic": True}, now)
        on_iso_wrong(state, ctx, fx, it, edges, base)
        return fx
    edges.append("e_iso_no")

    # ---------- ด่าน 2: ตอบเร็วเกินเวลาอ่านขั้นต่ำไหม (Rapid Guess) ----------
    min_read = it.get("min_read_time") or ctx.p("rapid_guess_threshold")
    if rt < min_read:
        attempt["kind"] = "rapid"
        item["attempts"].append(attempt)
        item["undo"] = {"ts": now, "state": snapshot}
        fx.trace("answer", it["id"], {**base, "correct": False, "raw": raw_text, "rapid": True}, now)
        on_rapid_guess(state, ctx, fx, it, rt, min_read, edges + ["e_g2_fast"], base)
        return fx
    edges.append("e_g2_normal")

    attempt["kind"] = "wrong"
    item["attempts"].append(attempt)
    item["undo"] = {"ts": now, "state": snapshot}
    item["ready_at"] = now  # เวลาคิดของครั้งถัดไปเริ่มนับจากตอนนี้
    _count_rt(state, rt)
    state["rapid_streak"] = 0
    if first_attempt:
        record_format(state, it["concept"], it["format"], False)

    # ---------- วินิจฉัยกับ Bug Library แล้วตั้ง Hint Floor ----------
    diag = diagnose(state, ctx, it, check.value)
    attempt["diagnosis"] = diag
    item["hint_floor"] = max(item["hint_floor"], diag["floor"])
    item["last_tag"] = diag["tag"] or item["last_tag"]
    item["last_class"] = diag["class"]
    edges.append("e_diag")
    item["error_count"] += 1
    item["rts"].append(rt)
    count = item["error_count"]
    detail = {**base, "error_count": count, "diagnosis": diag, "hint_floor": item["hint_floor"]}
    fx.trace("answer", it["id"], {**base, "correct": False, "raw": raw_text, "diagnosis": diag}, now)
    if diag["class"] == "misconception":
        fx.trace("misconception", it["id"], {"tag": diag["tag"]}, now)
    elif diag["class"] == "unclassified":
        fx.tag_requests.append({"item_id": it["id"], "answer": raw_text})
    feedback = _wrong_message(diag)

    # ---------- ด่าน 3: ผิดเป็นครั้งที่เท่าไรในข้อนี้ ----------
    if count == 1:
        level = max(1, item["hint_floor"])
        item["pending_hint"] = level
        state["timers"]["delay_until"] = now + ctx.dur("deliberate_delay")
        need_hints(state, fx, level)  # เตรียมข้อความคำใบ้ระหว่างหน่วงเวลา
        move(state, ctx, fx, F.DELAY, edges + ["e_g3_1"],
             f"ผิดครั้งแรก หน่วงเวลา {ctx.dur('deliberate_delay'):.0f} วินาทีก่อนแสดงคำใบ้ระดับ {level}", detail)
    elif count == 2:
        level = max(2, item["hint_floor"])
        reveal(state, level)
        need_hints(state, fx, level)
        move(state, ctx, fx, answer_position(state), edges + ["e_g3_2"], f"ผิดครั้งที่ 2 แสดงคำใบ้ระดับ {level}", detail)
    elif count == 3:
        result = fuzzy.impasse(item["rts"], it.get("expected_time", 45))
        detail["fuzzy"] = compact_fuzzy(result)
        if result["output"] >= ctx.p("impasse_threshold"):
            enter_impasse(state, ctx, fx, edges + ["e_g3_3", "e_trend_yes"],
                          f"ผิดครั้งที่ 3 และเวลาคิดยาวขึ้นต่อเนื่อง (Fuzzy = {result['output']:.0f}) จึงเป็น Impasse", detail)
            feedback = "ไม่เป็นไรนะ ลองทบทวนพื้นฐานก่อนแล้วค่อยกลับมาข้อนี้"
        else:
            reveal(state, 3)
            need_hints(state, fx, 3)
            move(state, ctx, fx, answer_position(state), edges + ["e_g3_3", "e_trend_no"],
                 f"ผิดครั้งที่ 3 เวลาคิดไม่ได้ยาวขึ้นต่อเนื่อง (Fuzzy = {result['output']:.0f}) แสดงคำใบ้ระดับ 3", detail)
    else:
        enter_impasse(state, ctx, fx, edges + ["e_g3_4"], "ยังผิดหลังได้คำใบ้ระดับ 3 จึงเป็น Impasse", detail)
        feedback = "ไม่เป็นไรนะ ลองทบทวนพื้นฐานก่อนแล้วค่อยกลับมาข้อนี้"
    fx.result = {"kind": "wrong", "message": feedback, "diagnosis": diag["class"]}
    return fx


def _count_rt(state: dict, rt: float):
    state["rt_sum"] += rt
    state["rt_count"] += 1


def _snapshot(state: dict) -> dict:
    saved = copy.deepcopy({k: v for k, v in state.items() if k != "item"})
    item = copy.deepcopy(state["item"])
    item["undo"] = None
    saved["item"] = item
    return saved


def _wrong_message(diag: dict) -> str:
    if diag["class"] == "slip":
        return "เกือบแล้ว ลองตรวจการคำนวณอีกรอบนะ"
    return "ยังไม่ใช่ ลองตรวจดูอีกครั้งนะ"


def diagnose(state: dict, ctx: Ctx, it: dict, value) -> dict:
    """เทียบคำตอบผิดกับ Bug Library: Misconception → Floor L2, Slip ที่มีประวัติทำถูก → Floor L1"""
    tag_id = match_bug(it, value)
    tag = ctx.content.tag(tag_id)
    concept_mastery = mastery_value(state, ctx, it["concept"])
    if tag and tag["type"] == "misconception":
        return {"class": "misconception", "tag": tag_id, "tag_name": tag["name"], "floor": 2, "mastery": concept_mastery}
    if concept_mastery is not None and concept_mastery >= ctx.p("slip_mastery"):
        return {"class": "slip", "tag": tag_id, "tag_name": tag["name"] if tag else "คำนวณคลาดเคลื่อน",
                "floor": 1, "mastery": concept_mastery}
    return {"class": "unclassified", "tag": tag_id if tag else None, "tag_name": tag["name"] if tag else None,
            "floor": 0, "mastery": concept_mastery}


def compact_fuzzy(result: dict) -> dict:
    return {
        "system": result["system"],
        "inputs": result["inputs"],
        "memberships": result["memberships"],
        "rules": [r for r in result["rules"] if r["strength"] > 0],
        "output": result["output"],
    }


def on_correct(state: dict, ctx: Ctx, fx: Fx, it: dict, rt: float, edges: list[str], base: dict):
    item = state["item"]
    mode = item["mode"]
    concept = it["concept"]
    state["timers"]["delay_until"] = None
    item["pending_hint"] = 0
    if it["id"] not in state["done_items"]:
        state["done_items"].append(it["id"])
    state["items_finished"] += 1
    weight = None if item["voided"] else item_weight(item)
    detail = {**base, "weight": weight, "hint_level": item["hint_level"]}

    if mode == "isomorphic":
        add_mastery(state, concept, 1.0 if item["iso_attempts"] == 0 else WEIGHTS["self"], it["id"], it["format"])
        state["iso_fail_streak"][concept] = 0
        fx.result = {"kind": "correct", "message": "เยี่ยมมาก ทำข้อนี้ได้ด้วยตัวเองโดยไม่ใช้คำใบ้"}
        advance(state, ctx, fx, it, rt, edges + ["e_mastery_finish"], detail)
        return

    if mode == "remedial":
        if weight is not None:
            add_mastery(state, concept, weight, it["id"], it["format"])
        rem = state["remedial"]
        rem["streak"] += 1
        if rem["streak"] >= ctx.p("remedial_pass_streak"):
            suspended = ctx.content.item(rem["suspended"])
            state["remedial"] = None
            state["remedial_passed"] += 1
            serve(state, ctx, suspended, rem.get("suspended_mode", "main"))
            move(state, ctx, fx, F.ANSWERING, edges + ["e_remedial_pass"],
                 f"ทบทวนผ่านแล้ว ({rem['streak']} ข้อติดกัน) กลับไปข้อเดิม Error Count เริ่มนับใหม่", detail)
            fx.result = {"kind": "correct", "message": "ดีมาก ทบทวนพื้นฐานครบแล้ว กลับไปลองข้อเดิมกันอีกครั้ง"}
            return
        nxt = next_remedial_item(state, ctx)
        serve(state, ctx, nxt, "remedial")
        move(state, ctx, fx, F.REMEDIAL, edges + ["e_remedial_next"],
             f"ทบทวนถูก {rem['streak']} ข้อ ทำข้อทบทวนถัดไป", detail)
        fx.result = {"kind": "correct", "message": "ถูกต้อง ไปต่อข้อทบทวนถัดไปกัน"}
        return

    if weight is not None:
        add_mastery(state, concept, weight, it["id"], it["format"])
        if mode == "challenge" and concept != ctx.content.target:
            # โจทย์ท้าทายต้องใช้ทักษะของ Target Concept ด้วย จึงนับเข้า Mastery ของเป้าหมาย
            add_mastery(state, ctx.content.target, weight, it["id"], it["format"])
    if mode == "main" and it["id"] not in state["main_done"]:
        state["main_done"].append(it["id"])
    if mode == "challenge":
        state["challenge_correct"] = True

    if item["hint_level"] >= 1 and not item["voided"]:
        iso = pick_isomorph(state, ctx, it["id"])
        if iso:
            serve(state, ctx, iso, "isomorphic", iso_source=it["id"])
            move(state, ctx, fx, F.ISO, edges + ["e_mastery_iso"],
                 f"ผ่านด้วยคำใบ้ระดับ {item['hint_level']} ข้อถัดไปเป็น Isomorphic Test (ปิดคำใบ้)", detail)
            fx.result = {"kind": "correct", "message": "ถูกต้อง ข้อถัดไปลองทำด้วยตัวเองโดยไม่มีคำใบ้นะ"}
            return
    fx.result = {"kind": "correct", "message": _praise(item)}
    advance(state, ctx, fx, it, rt, edges + ["e_mastery_finish"], detail)


def _praise(item: dict) -> str:
    if item["hint_level"] == 0 and item["error_count"] == 0:
        return "ถูกต้อง เก่งมาก"
    if item["hint_level"] == 0:
        return "ถูกต้อง แก้ได้ด้วยตัวเองเลย"
    return "ถูกต้อง พยายามได้ดีมาก"


def advance(state: dict, ctx: Ctx, fx: Fx, it: dict, rt: float, edges: list[str], detail: dict):
    """หลังตอบถูก: ตรวจเกณฑ์จบชุด ถ้ายังไม่จบให้เลือก Learning Path และข้อถัดไป"""
    if finished(state, ctx):
        end_session(state, ctx, fx, F.DONE, edges + ["e_finish_yes"], "ถึงเกณฑ์จบชุด", "completed")
        fx.result = {"kind": "correct", "message": "ยอดเยี่ยม ทำชุดนี้สำเร็จแล้ว"}
        return
    max_items = ctx.content.qs.get("max_items") or ctx.p("max_items")
    if state["items_count"] >= max_items:
        end_session(state, ctx, fx, F.ENDED, edges + ["e_finish_cap"],
                    f"ทำครบ {max_items} ข้อแล้วยังไม่ถึงเกณฑ์จบชุด บันทึกความคืบหน้าไว้", "cap")
        alert(fx, state, "silent", "cap", f"ทำครบ {max_items} ข้อแล้วยังไม่ถึงเกณฑ์จบชุด")
        fx.result = {"kind": "correct", "message": "วันนี้ทำไปเยอะมากแล้ว ระบบบันทึกความคืบหน้าไว้ให้ พักก่อนนะ"}
        return
    path, m, slowness = choose_path(state, ctx, rt, it.get("expected_time", 45))
    difficulty = fuzzy.difficulty(m, slowness)
    state["path"] = path
    nxt, mode = select_next(state, ctx, path, difficulty["output"])
    if nxt is None:
        end_session(state, ctx, fx, F.ENDED, edges + ["e_finish_cap"], "โจทย์ในชุดหมดแล้ว", "no_items")
        return
    serve(state, ctx, nxt, mode)
    move(state, ctx, fx, F.ANSWERING, edges + ["e_finish_no", "e_path_next"],
         f"เส้นทาง {PATH_LABELS[path]} · ความยากเป้าหมาย {difficulty['output']:.0f}",
         {**detail, "mastery": m, "slowness": round(slowness, 3), "path": path,
          "fuzzy": compact_fuzzy(difficulty), "next_item": nxt["id"]})


def on_iso_wrong(state: dict, ctx: Ctx, fx: Fx, it: dict, edges: list[str], base: dict):
    item = state["item"]
    item["iso_attempts"] += 1
    if item["iso_attempts"] < ctx.p("iso_attempts"):
        item["ready_at"] = ctx.now
        move(state, ctx, fx, F.ISO, edges + ["e_iso_retry"], "ผิดครั้งแรกในข้อคู่ขนาน ให้ลองอีกครั้ง (ไม่มีคำใบ้)", base)
        fx.result = {"kind": "wrong", "message": "ยังไม่ใช่ ลองตรวจอีกครั้งนะ ข้อนี้ไม่มีคำใบ้"}
        return
    concept = item["concept"]
    source = item["iso_source"]
    zero_entry(state, concept, source)
    streak = state["iso_fail_streak"].get(concept, 0) + 1
    state["iso_fail_streak"][concept] = streak
    detail = {**base, "iso_source": source, "iso_fail_streak": streak}
    if streak >= 2:
        state["iso_fail_streak"][concept] = 0
        enter_impasse(state, ctx, fx, edges + ["e_iso_impasse"], "ไม่ผ่าน Isomorphic Test 2 รอบติดกันใน Concept เดียว", detail,
                      suspended=source)
        fx.result = {"kind": "wrong", "message": "ไม่เป็นไรนะ ลองทบทวนพื้นฐานก่อนแล้วค่อยกลับมา"}
        return
    state["path"] = "STANDARD"
    nxt, mode = select_next(state, ctx, "STANDARD", 40)
    if nxt is None:
        nxt, mode = ctx.content.item(source), "extra"
    serve(state, ctx, nxt, mode)
    move(state, ctx, fx, F.ANSWERING, edges + ["e_iso_fail"],
         "ไม่ผ่านข้อคู่ขนาน ข้อก่อนหน้าได้น้ำหนัก 0 เปิดคำใบ้คืนแล้วฝึกต่อ", detail)
    fx.result = {"kind": "wrong", "message": "ไม่เป็นไร มาฝึกโจทย์แบบเดียวกันอีกข้อ คราวนี้มีคำใบ้ช่วย"}


def on_rapid_guess(state: dict, ctx: Ctx, fx: Fx, it: dict, rt: float, min_read: float, edges: list[str], base: dict):
    item = state["item"]
    item["voided"] = True
    state["rapid_streak"] += 1
    state["rapid_total"] += 1
    lock = ctx.dur("rapid_guess_lock")
    state["timers"]["lock_until"] = ctx.now + lock
    state["resume_position"] = state["position"]
    move(state, ctx, fx, F.LOCK, edges,
         f"ตอบผิดภายใน {rt:.1f} วินาที เร็วกว่าเวลาอ่านขั้นต่ำ {min_read:g} วินาที "
         f"คะแนนข้อนี้เป็นโมฆะ ไม่เพิ่ม Error Count และล็อกปุ่มตอบ {lock:.0f} วินาที", base)
    fx.result = {"kind": "rapid", "message": "ลองอ่านโจทย์ให้ครบอีกครั้งนะ ระบบพักปุ่มตอบไว้สักครู่"}
    if state["rapid_streak"] >= ctx.p("burnout_rapid_streak"):
        alert(fx, state, "silent", "burnout_rapid", "ตอบเร็วผิดปกติติดกันหลายข้อ (Burnout Signal)")


# ---------------------------------------------------------------- Impasse และ Remedial Loop

def enter_impasse(state: dict, ctx: Ctx, fx: Fx, edges: list[str], rule: str, detail: dict | None = None,
                  suspended: str | None = None):
    item = state["item"]
    move(state, ctx, fx, F.IMPASSE, edges, rule, detail)
    if item and item["mode"] == "remedial":
        state["after_walk"] = {"action": "close_round"}
        state["walk_concept"] = item["concept"]
        state["timers"]["break_until"] = ctx.now + ctx.dur("circuit_breaker_break")
        move(state, ctx, fx, F.CB, ["e_remedial_impasse"],
             "เกิด Impasse ซ้ำระหว่าง Remedial Loop จึงพักสายตา (Circuit Breaker)")
        return
    if suspended is None:
        suspended = item["iso_source"] if item["mode"] == "isomorphic" else item["id"]
    start_round(state, ctx, fx, suspended, item.get("last_tag") if item else None, ["e_impasse"])


def start_round(state: dict, ctx: Ctx, fx: Fx, suspended: str, tag: str | None, edges: list[str]):
    rounds = state["remedial_rounds"].get(suspended, 0)
    if rounds >= ctx.p("remedial_max_rounds"):
        state["remedial"] = None
        move(state, ctx, fx, F.DEADLOCK, edges + ["e_rounds_full"],
             f"ส่งซ่อมเสริมข้อนี้ครบ {rounds} รอบแล้วยังติด หยุดลูปและแจ้งครู", {"suspended": suspended})
        alert(fx, state, "normal", "deadlock", f"ติด Stagnation Deadlock ที่ข้อ {suspended} ต้องให้ครูช่วย", dedupe=False)
        fx.result = {"kind": "wrong", "message": "ข้อนี้ยากจริง ๆ ครูกำลังจะมาช่วยนะ"}
        return
    state["remedial_rounds"][suspended] = rounds + 1
    state["remedial_started"] += 1
    concept = ctx.content.item(suspended)["concept"]
    prereq = choose_prerequisite(state, ctx, concept, tag)
    remedial = {
        "concept": prereq or concept,
        "round": rounds + 1,
        "streak": 0,
        "suspended": suspended,
        "suspended_mode": mode_for(ctx.content, suspended),
        "used": [],
        "root": prereq is None,
    }
    state["remedial"] = remedial
    if prereq is None:
        state["after_walk"] = {"action": "root_practice"}
        state["walk_concept"] = concept
        move(state, ctx, fx, F.WALK, edges + ["e_rounds_root"],
             "Concept นี้ไม่มี Prerequisite ให้อ่านตัวอย่างทีละขั้นแล้วทำโจทย์ที่ง่ายลง", {"suspended": suspended})
        return
    nxt = next_remedial_item(state, ctx)
    serve(state, ctx, nxt, "remedial")
    move(state, ctx, fx, F.REMEDIAL, edges + ["e_rounds_ok"],
         f"Remedial Loop รอบที่ {rounds + 1}: ทบทวน {ctx.content.concept_name(prereq)}",
         {"suspended": suspended, "prerequisite": prereq, "tag": tag})
    fx.result = {"kind": "wrong", "message": f"มาทบทวนเรื่อง{ctx.content.concept_name(prereq)}กันก่อน แล้วค่อยกลับไปข้อเดิม"}


def walkthrough_done(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    resolve_timers(state, ctx, fx)
    if state["position"] != F.WALK:
        fx.result = {"kind": "blocked", "message": BLOCK_MESSAGES.get(state["position"], "")}
        return fx
    action = (state.get("after_walk") or {}).get("action", "easier")
    state["after_walk"] = None
    fx.trace("walkthrough_done", state.get("walk_concept"), {"action": action}, ctx.now)
    if action == "close_round" and state.get("remedial"):
        suspended = state["remedial"]["suspended"]
        state["remedial"] = None
        start_round(state, ctx, fx, suspended, None, ["e_walk_round"])
    elif action in ("root_practice", "resume_remedial") and state.get("remedial"):
        nxt = next_remedial_item(state, ctx)
        serve(state, ctx, nxt, "remedial")
        move(state, ctx, fx, F.REMEDIAL, ["e_walk_easier"], "อ่านตัวอย่างจบแล้ว ฝึกโจทย์ทบทวนต่อ")
    else:
        state["path"] = "SUPPORTED"
        nxt, mode = select_next(state, ctx, "SUPPORTED", 20)
        if nxt is None:
            end_session(state, ctx, fx, F.ENDED, [], "โจทย์ในชุดหมดแล้ว", "no_items")
        else:
            serve(state, ctx, nxt, mode)
            move(state, ctx, fx, F.ANSWERING, ["e_walk_easier"], "หลังพัก ให้ทำโจทย์ที่ง่ายลงก่อน (Supported Flow)")
    fx.result = fx.result or {"kind": "ok"}
    return fx


# ---------------------------------------------------------------- ปุ่มขอคำใบ้

def request_hint(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    now = ctx.now
    resolve_timers(state, ctx, fx)
    state["last_activity"] = now
    position = state["position"]
    item = state["item"]
    if item is None or position not in F.CAN_ANSWER:
        fx.result = {"kind": "blocked", "message": BLOCK_MESSAGES.get(position, "")}
        return fx
    if item["mode"] == "isomorphic":
        fx.result = {"kind": "hidden", "message": "ข้อนี้เป็นข้อทดสอบความเข้าใจ ลองทำด้วยตัวเองนะ"}
        return fx
    timers = state["timers"]
    if timers["cooldown_until"] and now < timers["cooldown_until"]:
        fx.result = {"kind": "cooldown", "remaining": round(timers["cooldown_until"] - now, 1),
                     "message": "ปุ่มคำใบ้พักสักครู่ ระหว่างนี้ลองตอบคำถามนำนี้ดูก่อน",
                     "socratic": next_socratic(state, ctx)}
        return fx
    presses = [t for t in state["hint_presses"] if now - t <= ctx.p("hint_abuse_window")] + [now]
    state["hint_presses"] = presses
    fx.trace("hint_request", item["id"], {"presses_in_window": len(presses)}, now)
    if len(presses) >= ctx.p("hint_abuse_presses"):
        state["hint_abuse_index"] += 1
        state["hint_presses"] = []
        cooldown = ctx.dur("hint_abuse_cooldown")
        timers["cooldown_until"] = now + cooldown
        fx.trace("hint_abuse", item["id"], {"index": state["hint_abuse_index"]}, now)
        fx.result = {"kind": "abuse", "remaining": round(cooldown, 1),
                     "message": "ลองคิดตามคำถามนี้ก่อนนะ ปุ่มคำใบ้จะกลับมาในอีกสักครู่",
                     "socratic": next_socratic(state, ctx)}
        if state["hint_abuse_index"] >= 3:
            alert(fx, state, "silent", "hint_abuse", "กดขอคำใบ้รัว ๆ หลายครั้ง (Gaming the System)")
        return fx
    if position == F.DELAY:
        fx.result = {"kind": "delay", "remaining": round((timers["delay_until"] or now) - now, 1),
                     "message": "ลองตรวจคำตอบด้วยตัวเองก่อน อีกครู่คำใบ้จะขึ้นเอง"}
        return fx
    if item["hint_level"] == 0 and item["error_count"] == 0:
        thinking = now - item["started_at"]
        wait = ctx.dur("hint_unlock_wait")
        if thinking < wait:
            fx.result = {"kind": "wait", "remaining": round(wait - thinking, 1), "message": "ลองคิดอีกนิดนะ"}
            return fx
        reveal(state, 1)
        item["hint_seen_before_attempt"] = True
        item["ready_at"] = now
        need_hints(state, fx, 1)
        move(state, ctx, fx, answer_position(state), ["e_hint_button"],
             f"คิดมาแล้ว {thinking:.0f} วินาที ปลดคำใบ้ระดับ 1 ก่อนลองตอบ")
        fx.result = {"kind": "hint", "level": 1}
        return fx
    fx.result = {"kind": "socratic", "level": item["hint_level"], "socratic": next_socratic(state, ctx),
                 "message": "คำใบ้ระดับถัดไปจะปลดเมื่อลองตอบใหม่ ระหว่างนี้ลองคิดตามคำถามนี้"}
    return fx


# ---------------------------------------------------------------- ปุ่มยกเลิก / เริ่มใหม่ / พัก

def undo(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    item = state.get("item")
    if not item or not item.get("undo"):
        fx.result = {"kind": "blocked", "message": "ไม่มีคำตอบที่ยกเลิกได้"}
        return fx
    if item["undo_used"]:
        fx.result = {"kind": "blocked", "message": "ข้อนี้ใช้การยกเลิกไปแล้ว"}
        return fx
    if ctx.now - item["undo"]["ts"] > ctx.p("undo_window"):
        fx.result = {"kind": "blocked", "message": "เลยเวลาที่ยกเลิกได้แล้ว"}
        return fx
    cancelled = item["attempts"][-1] if item["attempts"] else {}
    restored = copy.deepcopy(item["undo"]["state"])
    restored["item"]["undo_used"] = True
    restored["item"]["attempts"].append({"ts": ctx.now, "kind": "undone", "raw": cancelled.get("raw")})
    keep = {k: state[k] for k in ("hint_presses", "hint_abuse_index", "alerts_sent")}
    state.clear()
    state.update(restored)
    state.update(keep)
    fx.trace("undo", item["id"], {"raw": cancelled.get("raw")}, ctx.now)
    move(state, ctx, fx, state["position"], [], "ยกเลิกคำตอบล่าสุด (ปัญหาทางเทคนิค) ไม่นับใน Error Count")
    fx.result = {"kind": "undone", "message": "ยกเลิกคำตอบล่าสุดแล้ว ตอบใหม่ได้เลย"}
    return fx


def restart_item(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    item = state.get("item")
    if not item or state["position"] not in F.CAN_ANSWER:
        fx.result = {"kind": "blocked", "message": BLOCK_MESSAGES.get(state["position"], "")}
        return fx
    item["ready_at"] = ctx.now
    item["last_submit"] = None
    fx.trace("restart_item", item["id"], {"error_count": item["error_count"]}, ctx.now)
    fx.result = {"kind": "restarted", "message": "เริ่มข้อนี้ใหม่แล้ว ประวัติการตอบยังอยู่ครบ"}
    return fx


def idle(state: dict, ctx: Ctx, reason: str = "idle") -> Fx:
    fx = Fx()
    resolve_timers(state, ctx, fx)
    if state["position"] not in F.CAN_ANSWER:
        fx.result = {"kind": "ignored"}
        return fx
    state["resume_position"] = state["position"]
    state["idle_since"] = ctx.now
    state["idle_count"] += 1
    rule = (f"ไม่มีการกระทำนานเกิน {ctx.dur('idle_timeout'):.0f} วินาที พักบทเรียนอัตโนมัติ"
            if reason == "idle" else "นักเรียนขอพัก")
    move(state, ctx, fx, F.IDLE, ["e_idle"], rule)
    if state["idle_count"] >= ctx.p("burnout_idle"):
        alert(fx, state, "silent", "burnout_idle", "พักเพราะหน้าจอนิ่งหลายครั้งใน Session เดียว (Burnout Signal)")
    fx.result = {"kind": "paused"}
    return fx


def resume(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    if state["position"] != F.IDLE:
        fx.result = {"kind": "ignored"}
        return fx
    paused = ctx.now - (state["idle_since"] or ctx.now)
    if state.get("item"):
        state["item"]["ready_at"] += paused
        state["item"]["started_at"] += paused
    if state["timers"]["delay_until"]:
        state["timers"]["delay_until"] += paused
    back = state.get("resume_position") or answer_position(state)
    state["resume_position"] = None
    state["idle_since"] = None
    move(state, ctx, fx, back, ["e_idle_back"], f"กลับมาเรียนต่อหลังพัก {paused:.0f} วินาที")
    fx.result = {"kind": "resumed"}
    return fx


def revisit(state: dict, ctx: Ctx, concept: str | None) -> Fx:
    fx = Fx()
    state["content_revisits"] += 1
    fx.trace("content_revisit", concept, {}, ctx.now)
    fx.result = {"kind": "ok"}
    return fx


# ---------------------------------------------------------------- ข้อความทุกข์ใจและการเลือกทางต่อ

def on_distress(state: dict, ctx: Ctx, level: str, source: str = "keyword") -> Fx:
    fx = Fx()
    resolve_timers(state, ctx, fx)
    now = ctx.now
    if level == "self_harm":
        state["resume_position"] = state["position"]
        move(state, ctx, fx, F.SAFETY, ["e_safety"], "ข้อความสื่อถึงการทำร้ายตนเอง หยุดทันทีและแจ้งครูด่วน", {"source": source})
        alert(fx, state, "urgent", "self_harm", "นักเรียนพิมพ์ข้อความที่สื่อถึงการทำร้ายตนเอง ต้องการครูด่วน", dedupe=False)
    elif level == "quit":
        if state["position"] in (F.SAFETY, F.DEADLOCK, F.DONE, F.ENDED):
            return fx
        state["resume_position"] = answer_position(state)
        move(state, ctx, fx, F.CHOOSE, ["e_quit"], "นักเรียนบอกว่าไม่อยากเรียนต่อ ให้เลือกทางต่อเอง", {"source": source})
        alert(fx, state, "normal", "quit", "นักเรียนบอกว่าไม่อยากเรียนต่อ")
    elif level == "stress":
        if state["position"] in (F.SAFETY, F.DEADLOCK, F.DONE, F.ENDED, F.CB):
            return fx
        state["after_walk"] = {"action": "resume_remedial" if state.get("remedial") else "easier"}
        state["walk_concept"] = state["item"]["concept"] if state.get("item") else None
        state["timers"]["break_until"] = now + ctx.dur("circuit_breaker_break")
        state["timers"]["delay_until"] = None
        move(state, ctx, fx, F.CB, ["e_distress"], "พบข้อความเครียดหรือท้อ จึงพักสายตา (Circuit Breaker)", {"source": source})
        alert(fx, state, "normal", "stress", "นักเรียนพิมพ์ข้อความแสดงความเครียดหรือท้อแท้")
    fx.result = {"kind": "distress", "level": level}
    return fx


def choose(state: dict, ctx: Ctx, option: str) -> Fx:
    fx = Fx()
    if state["position"] != F.CHOOSE:
        fx.result = {"kind": "blocked", "message": ""}
        return fx
    fx.trace("choose_path", option, {}, ctx.now)
    if option == "rest":
        state["idle_since"] = ctx.now
        move(state, ctx, fx, F.IDLE, ["e_idle"], "นักเรียนเลือกพักก่อน")
    elif option == "easier":
        state["path"] = "SUPPORTED"
        nxt, mode = select_next(state, ctx, "SUPPORTED", 20)
        if nxt is None:
            end_session(state, ctx, fx, F.ENDED, ["e_choose_stop"], "โจทย์ในชุดหมดแล้ว", "no_items")
        else:
            serve(state, ctx, nxt, mode)
            move(state, ctx, fx, F.ANSWERING, ["e_choose_on"], "นักเรียนเลือกทำต่อแบบง่ายลง (Supported Flow)")
    else:
        end_session(state, ctx, fx, F.ENDED, ["e_choose_stop"], "นักเรียนเลือกหยุดวันนี้ บันทึกความคืบหน้าไว้", "student_stop")
    fx.result = {"kind": "ok"}
    return fx


# ---------------------------------------------------------------- Manual Override ของครู

def override(state: dict, ctx: Ctx, action: str, params: dict) -> Fx:
    fx = Fx()
    timers = state["timers"]
    for key in timers:
        if key != "cooldown_until":
            timers[key] = None
    edge = "e_teacher_safety" if state["position"] == F.SAFETY else (
        "e_teacher_release" if state["position"] == F.DEADLOCK else "e_override")
    if action in ("release", "reset_item", "resume"):
        target = state["remedial"]["suspended"] if state.get("remedial") else (state["item"]["id"] if state.get("item") else None)
        state["remedial"] = None
        state["after_walk"] = None
        if action == "release" and target:
            state["remedial_rounds"][target] = 0
        state["ended"] = False
        state["end_reason"] = None
        if target:
            serve(state, ctx, ctx.content.item(target), mode_for(ctx.content, target))
            move(state, ctx, fx, F.ANSWERING, [edge], "ครูสั่ง Manual Override ให้เริ่มข้อนี้ใหม่", {"action": action})
        else:
            fx.decisions.extend(begin(state, ctx).decisions)
    elif action == "set_item":
        item_id = params["item_id"]
        state["remedial"] = None
        state["ended"] = False
        serve(state, ctx, ctx.content.item(item_id), mode_for(ctx.content, item_id))
        move(state, ctx, fx, F.ANSWERING, [edge], f"ครูเปลี่ยนโจทย์เป็น {item_id}", {"action": action})
    elif action == "set_path":
        state["path"] = params["path"]
        move(state, ctx, fx, state["position"], [], f"ครูตั้งเส้นทางเป็น {PATH_LABELS.get(params['path'], params['path'])}")
    elif action == "set_mastery":
        concept = params["concept"]
        value = max(0.0, min(1.0, float(params["value"])))
        state["mastery"][concept] = [{"w": value, "fmt": "override", "item": "teacher"}]
        move(state, ctx, fx, state["position"], [], f"ครูแก้ Mastery ของ {ctx.content.concept_name(concept)} เป็น {value:.2f}")
    elif action == "end_session":
        end_session(state, ctx, fx, F.ENDED, ["e_override"], "ครูสั่งจบ Session", "teacher_end")
    fx.result = {"kind": "ok"}
    return fx


# ---------------------------------------------------------------- มุมมองสำหรับหน้าจอ

def remaining(until: float | None, now: float) -> float | None:
    return round(max(0.0, until - now), 1) if until and until > now else None


def item_payload(it: dict) -> dict:
    """ข้อมูลโจทย์ที่ส่งให้หน้าจอนักเรียน (ไม่มีคำตอบ ไม่มี Bug Library)"""
    return {
        "id": it["id"],
        "prompt": it["prompt"],
        "math": it.get("math"),
        "format": it["format"],
        "options": [{"id": o["id"], "text": o["text"]} for o in it.get("options", [])],
        "concept": it["concept"],
    }


def student_view(state: dict, ctx: Ctx) -> dict:
    """สิ่งที่นักเรียนเห็น: ไม่มีตัวเลขความเสี่ยง ไม่มีชื่อกลุ่ม (Anti-Labeling)"""
    now = ctx.now
    content = ctx.content
    item = state.get("item")
    it = content.item(item["id"]) if item else None
    target = content.target
    hints = []
    if item:
        for level in range(1, item["hint_level"] + 1):
            entry = item["hints"].get(str(level)) or {"status": "pending"}
            hints.append({"level": level, "text": entry.get("text"), "status": entry.get("status", "pending")})
    walk = None
    if state["position"] == F.WALK:
        walk = content.walkthrough(state.get("walk_concept") or (item["concept"] if item else target))
    can_undo = bool(
        item and item.get("undo") and not item["undo_used"] and now - item["undo"]["ts"] <= ctx.p("undo_window")
    )
    thinking = now - item["started_at"] if item else 0
    return {
        "position": state["position"],
        "label": STUDENT_LABELS.get(state["position"], ""),
        "set": {"id": content.qs["id"], "name": content.qs["name"], "subject": content.subject["name"]},
        "target": {"id": target, "name": content.concept_name(target)},
        "mastery": mastery_value(state, ctx, target) or 0.0,
        "item": item_payload(it) if it else None,
        "item_mode": item["mode"] if item else None,
        "concept_name": content.concept_name(it["concept"]) if it else None,
        "item_number": state["items_count"],
        "error_count": item["error_count"] if item else 0,
        "hints": hints,
        "hint_button": {
            "visible": bool(item and item["mode"] != "isomorphic"),
            "cooldown": remaining(state["timers"]["cooldown_until"], now),
            "unlock_in": (round(max(0.0, ctx.dur("hint_unlock_wait") - thinking), 1)
                          if item and item["hint_level"] == 0 and item["error_count"] == 0 else 0),
        },
        "timers": {
            "delay": remaining(state["timers"]["delay_until"], now),
            "lock": remaining(state["timers"]["lock_until"], now),
            "break": remaining(state["timers"]["break_until"], now),
        },
        "can_undo": can_undo,
        "undo_window": ctx.p("undo_window"),
        "idle_timeout": ctx.dur("idle_timeout"),
        "walkthrough": walk,
        "remedial": {"concept_name": content.concept_name(state["remedial"]["concept"]), "round": state["remedial"]["round"]}
        if state.get("remedial") else None,
        "ended": state["ended"],
        "end_reason": state["end_reason"],
    }


def staff_view(state: dict, ctx: Ctx) -> dict:
    """สิ่งที่ครูและ Admin เห็น (ยังไม่มีชื่อจริง ชื่อจริงอยู่ใน Roster ฝั่งครู)"""
    now = ctx.now
    item = state.get("item")
    content = ctx.content
    accuracy = state["correct_total"] / state["attempts_total"] if state["attempts_total"] else None
    return {
        "code": state["code"],
        "set_id": state["set_id"],
        "position": state["position"],
        "position_label": F.POSITION_LABELS.get(state["position"], state["position"]),
        "teacher_text": F.TEACHER_TEXT.get(state["position"], ""),
        "position_since": state["position_since"],
        "path": state["path"],
        "item": {
            "id": item["id"],
            "mode": item["mode"],
            "concept": item["concept"],
            "error_count": item["error_count"],
            "hint_level": item["hint_level"],
            "hint_floor": item["hint_floor"],
            "last_tag": item["last_tag"],
            "last_class": item["last_class"],
            "rts": item["rts"],
        } if item else None,
        "mastery": mastery_map(state, ctx),
        "cross_format": {c: cross_format_flag(state, c) for c in content.concepts},
        "remedial": state.get("remedial"),
        "remedial_rounds": state["remedial_rounds"],
        "timers": {k: remaining(v, now) for k, v in state["timers"].items()},
        "items_count": state["items_count"],
        "attempts": state["attempts_total"],
        "accuracy": round(accuracy, 3) if accuracy is not None else None,
        "avg_rt": round(state["rt_sum"] / state["rt_count"], 2) if state["rt_count"] else None,
        "first_attempt_success": state["first_attempt_correct"],
        "hint_abuse_index": state["hint_abuse_index"],
        "rapid_total": state["rapid_total"],
        "idle_count": state["idle_count"],
        "content_revisits": state["content_revisits"],
        "ended": state["ended"],
        "end_reason": state["end_reason"],
        "last_decision": state.get("last_decision"),
        "last_activity": state["last_activity"],
    }


def risk_inputs(state: dict) -> dict:
    attempts = state["attempts_total"]
    error_rate = 1 - state["correct_total"] / attempts if attempts else 0.0
    rapid_rate = state["rapid_total"] / attempts if attempts else 0.0
    disengagement = min(1.0, 0.4 * min(rapid_rate * 2, 1.0) + 0.3 * min(state["idle_count"] / 3, 1.0)
                        + 0.3 * min(state["hint_abuse_index"] / 3, 1.0))
    avg_rt = state["rt_sum"] / state["rt_count"] if state["rt_count"] else 45.0
    return {"error_rate": round(error_rate, 4), "disengagement": round(disengagement, 4), "slowness": round(avg_rt / 45.0, 4)}


def risk_score(state: dict) -> dict:
    values = risk_inputs(state)
    return fuzzy.risk(values["error_rate"], values["disengagement"], values["slowness"])
