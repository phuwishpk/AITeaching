"""ตัวรัน Flow ที่ AI ออกแบบจากคำสั่งของครูใน Gem (ADR-0004)

Flow คือกราฟของขั้น (step) จากคลังขั้นที่ engine รันได้ และเส้น (edge) ที่มีเงื่อนไขเป็นกฎอ่านออกได้
ขั้นแบบรอ (ทำโจทย์ อ่านบทเรียนย่อ อธิบายความคิด พัก รอครู) หยุดรอเหตุการณ์ของนักเรียนหรือเวลา
ขั้นแบบผ่าน (คำใบ้ แจ้งครู ด่านตัดสินใจ) ทำงานแล้วไล่เส้นต่อทันที เส้นแรกที่เงื่อนไขเป็นจริงชนะ

สิ่งที่ล็อกไว้ทุก Flow และไม่อยู่ในกราฟ (ครูและ AI แก้ไม่ได้):
ตรวจถูกผิดด้วยกฎจากเฉลย และคำใบ้ผ่าน Answer-Leak Guard · ข้อความทำร้ายตนเองหยุดทันที และครูสั่ง Manual Override ได้เสมอ
· กรองการส่งซ้ำ คำตอบผิดรูปแบบ ตัดเวลาคิดส่วนเกิน และล็อก Rapid Guess · Idle Pause และเพดานจำนวนข้อ
นอกจากนี้ผิดข้อเดียวกันครบ STUCK_LIMIT ครั้งจะส่งต่อครู กัน Flow ที่ไม่มีทางออก
"""

import copy
import re

from ..config import WEIGHTS
from ..ml import fuzzy
from ..tutor import guard
from . import core as C
from . import flow as F
from . import widgets as W
from .answers import normalize
from .conditions import describe, evaluate, names

STUCK_LIMIT = 6
MAX_HOPS = 30

# วิธีเลือกโจทย์ของขั้นทำโจทย์
PICKS = {
    "adaptive": "เลือกตาม Mastery และเวลาคิด (Fuzzy) แบบผังมาตรฐาน",
    "main": "โจทย์หลักข้อถัดไปตามลำดับ",
    "easier": "ข้อที่ง่ายลง",
    "harder": "ข้อที่ยากขึ้นหรือโจทย์ท้าทาย",
    "isomorphic": "ข้อคู่ขนานของข้อที่เพิ่งทำถูก",
    "prerequisite": "โจทย์ทบทวนพื้นฐาน (Prerequisite) พักข้อที่ยังไม่ถูกไว้ก่อน",
}
PICK_SHORT = {"adaptive": "ตาม Mastery", "main": "โจทย์หลัก", "easier": "ง่ายลง", "harder": "ยากขึ้น",
              "isomorphic": "ข้อคู่ขนาน", "prerequisite": "ทบทวนพื้นฐาน"}

# ตำแหน่งของกลไกที่ล็อกไว้ ใช้บอกว่านักเรียนอยู่ที่กล่องไหนในผังของ Gem
GUARD_POSITIONS = {F.LOCK, F.IDLE, F.SAFETY, F.CHOOSE, F.LIVE, F.OUTAGE}
# กล่องแชตในผังของ Gem (flowspec.CHAT): ชิปอยู่ที่นี่ตั้งแต่ส่งข้อความจนกลับมาทำบนจอหลัก
CHAT = "chat"
# ตำแหน่งที่นักเรียนกำลังทำขั้นหนึ่งอยู่ (ไม่ได้พัก หยุดรอครู หรือจบแล้ว) แชตจึงย้ายชิปไปกล่องแชตได้
WORKING = F.CAN_ANSWER | {F.LESSON, F.REFLECT, F.ACTIVITY, F.WIDGET}
# AI ตอบแชตนานกว่านี้ถือว่าไม่ได้คิดอยู่แล้ว (กันชิปขึ้น "กำลังคิด" ค้างเมื่อการเรียก AI ล้มกลางทาง)
THINK_LIMIT = 90.0
# กลไกที่ล็อกไว้ซึ่งพักแล้วกลับขั้นเดิม: ชิปอยู่ที่ขั้นเดิมพร้อมป้ายนี้ กล่องของกลไกในผังติดไฟ
# (พักเพราะเครียดที่ครูกำหนดทางหลังพักไว้เป็นกล่องเต็มในผัง ชิปจึงไปอยู่ที่กล่องนั้น)
STATUS = {
    F.IDLE: "พัก · หน้าจอนิ่ง",
    F.LOCK: "ล็อก Rapid Guess",
    F.LIVE: "รอ AI สร้างโจทย์",
    F.OUTAGE: "AI ขัดข้อง รอลองใหม่",
    F.CB: "พักเพราะเครียด",
}


# ---------------------------------------------------------------- ข้อมูลของ Flow

def spec(ctx: C.Ctx) -> dict:
    return ctx.content.spec


def step_of(ctx: C.Ctx, step_id: str | None) -> dict | None:
    return ctx.content.steps.get(step_id) if step_id else None


def edges_from(ctx: C.Ctx, step_id: str) -> list[dict]:
    return [e for e in spec(ctx)["edges"] if e["from"] == step_id]


def fs(state: dict) -> dict:
    flow = state.get("flow")
    if not flow:
        flow = state["flow"] = {"step": None, "item_step": None, "visits": {}, "solved_here": 0,
                                "streak": 0, "last": {}, "pending": None, "last_solved": None}
    return flow


def flow_step(state: dict, ctx: C.Ctx) -> dict | None:
    return step_of(ctx, fs(state).get("step"))


def map_node(state: dict, ctx: C.Ctx) -> str | None:
    """กล่องในผังของ Gem ที่นักเรียนอยู่: ขั้นของ Flow หรือกล่องของกลไกที่ล็อกไว้"""
    position = state["position"]
    flow = fs(state)
    if position in GUARD_POSITIONS:
        return position
    if position == F.CB and (flow.get("pending") or {}).get("kind") == "stress":
        return F.CB
    if position == F.DEADLOCK and flow.get("stuck"):
        return F.DEADLOCK
    if position == F.ENDED and state.get("end_reason") in ("cap", "no_items", "teacher_end", "student_stop"):
        return F.ENDED
    if flow.get("chat"):
        return CHAT
    return flow.get("step")


def chip_node(state: dict, ctx: C.Ctx) -> str | None:
    """กล่องที่ชิปของนักเรียนอยู่บนผัง: แชตและกลไกที่พักแล้วกลับขั้นเดิมไม่พาชิปออกจากขั้น (บอกเป็นสถานะแทน)
    ส่วน map_node คือกล่องที่การขยับไปถึงจริง ใช้วาดเส้นทาง"""
    node = map_node(state, ctx)
    if node == CHAT or (node in STATUS and not (node == F.CB and spec(ctx).get("after_stress"))):
        return fs(state).get("step") or node
    return node


def status(state: dict, ctx: C.Ctx) -> dict | None:
    """สิ่งที่ทำให้นักเรียนยังไม่ได้ทำขั้นนั้นตามปกติ (ป้ายใต้ชิป): กล่องที่ต้นเหตุอยู่ เวลาเริ่ม และเวลาที่จะจบถ้ามี
    None = ทำขั้นนั้นตามปกติ"""
    node = map_node(state, ctx)
    timers = state["timers"]
    flow = fs(state)
    if node == CHAT:
        thinking = chat_thinking(state, ctx)
        return {"key": "chat", "label": "คุยกับ AI · กำลังคิด" if thinking else "คุยกับ AI", "box": CHAT,
                "since": flow["chat"].get("since"), "until": None, "thinking": thinking}
    if node in STATUS:
        until = {F.LOCK: timers.get("lock_until"), F.OUTAGE: timers.get("retry_at"), F.CB: timers.get("break_until")}.get(node)
        return {"key": node, "label": STATUS[node], "box": node, "since": state["position_since"], "until": until}
    position = state["position"]
    if position == F.DELAY:
        return {"key": "delay", "label": "รอคำใบ้", "box": None, "since": state["position_since"], "until": timers.get("delay_until")}
    if position == F.CB:
        return {"key": "break", "label": "พักสายตา", "box": None, "since": state["position_since"], "until": timers.get("break_until")}
    if position == F.ACTIVITY and (flow.get("activity") or {}).get("status") == "pending":
        return {"key": "activity", "label": "AI กำลังเตรียมกิจกรรม", "box": None, "since": state["position_since"], "until": None}
    return None


def where(state: dict, ctx: C.Ctx) -> dict:
    """นักเรียนอยู่ส่วนไหนของขั้น: ทำข้อไหน ผิดกี่ครั้ง เห็นคำใบ้ระดับไหน ถามแชตกี่ครั้ง กำลังทำอะไร และมาถึงขั้นนี้ยังไง"""
    flow = fs(state)
    item = state.get("item")
    content = ctx.content
    facts = []
    brief = []
    if item and not state["ended"]:
        mains = [m["id"] for m in content.main_items()]
        if item["id"] in mains:
            which = f"โจทย์หลักข้อ {mains.index(item['id']) + 1} จาก {len(mains)}"
            brief.append(f"ข้อ {mains.index(item['id']) + 1}/{len(mains)}")
        else:
            which = {"isomorphic": "ข้อคู่ขนาน", "remedial": "ข้อทบทวนพื้นฐาน"}.get(item["mode"], "ข้อเพิ่มเติม")
            brief.append(which)
        facts.append({"label": "ข้อที่ทำอยู่", "value": f"{which} ({item['id']})"})
        facts.append({"label": "ผิดในข้อนี้", "value": f"{item['error_count']} ครั้ง"})
        facts.append({"label": "คำใบ้ที่เห็นแล้ว", "value": f"ระดับ {item['hint_level']}" if item["hint_level"] else "ยังไม่เห็น"})
        facts.append({"label": "ถามแชตเรื่องข้อนี้", "value": f"{item.get('chat_help', 0)} ครั้ง"})
        brief += [text for value, text in ((item["error_count"], f"ผิด {item['error_count']}"),
                                           (item["hint_level"], f"ใบ้ L{item['hint_level']}"),
                                           (item.get("chat_help", 0), f"แชต {item.get('chat_help', 0)}")) if value]
    facts.append({"label": "ทำเสร็จแล้วใน Session นี้", "value": f"{state['items_finished']} ข้อ"})
    mastery = C.mastery_value(state, ctx, content.target)
    if mastery is not None:
        facts.append({"label": "Mastery เรื่องเป้าหมาย", "value": f"{mastery:.2f}"})
    current = status(state, ctx)
    entered = flow.get("entered") or {}
    return {
        "status": current,
        "doing": current["label"] if current else F.TEACHER_TEXT.get(state["position"], state["position"]),
        "brief": " · ".join(brief),
        "facts": facts,
        "came": {**entered, "from_label": node_label(ctx, entered.get("from")),
                 "via_labels": [node_label(ctx, n) for n in entered.get("via", [])]} if entered else None,
        "next": None,
    }


def node_label(ctx: C.Ctx, node: str | None) -> str | None:
    if node is None:
        return None
    if node == CHAT:
        return "แชตกับ AI"
    return label(step_of(ctx, node)) or STATUS.get(node) or F.POSITION_LABELS.get(node, node)


def preview(state: dict, ctx: C.Ctx, answers: dict[str, str]) -> dict | None:
    """ถ้านักเรียนตอบตอนนี้ (ด้วยเวลาคิดปกติของข้อ) จะไปเส้นไหน: รัน engine จริงบนสำเนาของ state ผลจึงตรงกับที่จะเกิด
    answers คือคำตอบตัวอย่างต่อกรณี เช่น {"correct": ..., "wrong": ...}"""
    item = state.get("item")
    item_step = fs(state).get("item_step")
    if item is None or item_step is None or state["position"] not in F.CAN_ANSWER:
        return None
    it = ctx.content.item(item["id"])
    out = {"step": item_step}
    targets = {e["id"]: e["to"] for e in edges_from(ctx, item_step)}
    for case, raw in answers.items():
        trial_state = copy.deepcopy(state)
        now = max(ctx.now, item["ready_at"] + float(it.get("expected_time", 45)))
        trial = C.Ctx(ctx.content, ctx.params, ctx.time_scale, now)
        fx = submit(trial_state, trial, raw)
        edge = next((e for d in fx.decisions for e in d["edges"] if e in targets), None)
        # ขั้นปลายเส้น และที่ชิปไปหยุดจริง (ต่างกันเมื่อขั้นปลายเส้นผ่านไปทันที เช่น คำใบ้ที่ไม่หน่วง)
        end = chip_node(trial_state, trial)
        to = item_step if edge and targets[edge] == "back" else targets[edge] if edge else end
        out[case] = {"edge": edge, "to": to, "to_label": node_label(trial, to),
                     "then": end if end != to else None, "then_label": node_label(trial, end) if end != to else None}
    return out


def track(state: dict, ctx: C.Ctx, fx: C.Fx, decision: dict):
    """เส้นทางบนผังของการย้ายครั้งนี้: กล่องที่ชิปอยู่ก่อน ขั้นที่ผ่าน (รวมขั้นที่ผ่านไปทันที) และกล่องที่ไปอยู่
    การย้ายตำแหน่งทุกครั้งพาชิปออกจากกล่องแชต และถ้าเข้าขั้นใหม่ จำไว้ว่ามาจากไหนด้วยเส้นอะไร"""
    flow = fs(state)
    flow["chat"] = None
    path = [n for n in [flow.get("map_at"), *fx.map_steps] if n]
    if fx.map_steps and fx.map_steps[-1] == flow.get("step"):
        # เส้นของ Flow ที่การย้ายครั้งนี้ผ่าน (ไม่นับเส้นกลับขั้นทำโจทย์ที่ไม่มีชื่อ) ไม่มีเลยใช้เหตุผลข้อแรกของการตัดสินใจ
        known = {e["id"]: e for e in spec(ctx)["edges"]}
        used = [known[e] for e in decision["edges"] if e in known and (known[e].get("label") or known[e]["to"] != "back")]
        flow["entered"] = {"ts": ctx.now, "from": path[0] if len(path) > 1 else None, "via": path[1:-1],
                           "edge": used[0]["id"] if used else None,
                           "label": " → ".join(edge_text(e) for e in used) or decision["rule"].split(" · ")[0]}
    fx.map_steps = []
    to = map_node(state, ctx)
    if to and (not path or path[-1] != to):
        path.append(to)
    flow["map_at"] = path[-1] if path else None
    decision["detail"]["map_path"] = path


def shift(state: dict, ctx: C.Ctx, fx: C.Fx, edges: list[str], rule: str):
    """ชิปขยับบนผังโดย Flow Position ไม่เปลี่ยน (เข้าและออกจากกล่องแชต) บันทึกเป็น Decision Trace เหมือนการย้าย"""
    flow = fs(state)
    to = map_node(state, ctx)
    path = [n for n in (flow.get("map_at"), to) if n]
    flow["map_at"] = to
    decision = {"ts": ctx.now, "from": state["position"], "to": state["position"], "edges": edges, "rule": rule,
                "detail": {"step": flow.get("step"), "step_label": label(step_of(ctx, flow.get("step"))), "map_path": path},
                "item": state["item"]["id"] if state.get("item") else None}
    state["last_decision"] = decision
    fx.decisions.append(decision)


def label(step: dict | None) -> str:
    return (step or {}).get("label") or (step or {}).get("id") or ""


# ---------------------------------------------------------------- ตัวแปรของเงื่อนไข

def solved(item: dict | None) -> bool:
    return bool(item) and any(a["kind"] == "correct" for a in item["attempts"])


def values(state: dict, ctx: C.Ctx, step_id: str) -> dict:
    flow = fs(state)
    item = state.get("item")
    it = ctx.content.item(item["id"]) if item else None
    last = flow.get("last") or {}
    rts = item["rts"] if item else []
    source = (state.get("remedial") or {}).get("suspended") or (
        item["iso_source"] if item and item["mode"] == "isomorphic" else item["id"] if item else None)
    mains = ctx.content.main_items()
    return {
        "correct": bool(last.get("correct")),
        "wrong": bool(last.get("wrong")),
        "misconception": bool(last.get("misconception")),
        "slip": bool(last.get("slip")),
        "first_try": bool(last.get("first_try")),
        "rt": last.get("rt", 0.0),
        "rt_ratio": last.get("rt_ratio", 0.0),
        "slow": bool(last.get("slow")),
        "judge_pass": last.get("judge_pass"),
        "judge_score": last.get("judge_score"),
        "error_count": item["error_count"] if item else 0,
        "hint_level": C.help_level(item) if item else 0,
        "chat_help": item.get("chat_help", 0) if item else 0,
        "impasse": round(fuzzy.impasse(rts, it.get("expected_time", 45))["output"], 1) if len(rts) >= 2 else 0.0,
        "mastery": C.mastery_value(state, ctx, ctx.content.target) or 0.0,
        "concept_mastery": (C.mastery_value(state, ctx, it["concept"]) or 0.0) if it else 0.0,
        "items_done": state["items_finished"],
        "items_count": state["items_count"],
        "streak": flow.get("streak", 0),
        "solved_here": flow.get("solved_here", 0),
        "rounds": state["remedial_rounds"].get(source, 0) if source else 0,
        "has_prerequisite": bool(it) and any(ctx.content.remedial_items(c) for c in ctx.content.prerequisites(it["concept"])),
        "mains_left": len([m for m in mains if m["id"] not in state["main_done"]]),
        "challenge_done": bool(state["challenge_correct"]),
        "visits": flow["visits"].get(step_id, 0),
        "widget_pass": bool(last.get("widget_pass")),
        "widget_tries": last.get("widget_tries", 0),
        "bug": last.get("bug") or "",
        "bug_type": last.get("bug_type") or "",
    }


def edge_values(state: dict, current: dict, edge: dict) -> dict:
    """ตัวแปรของเส้นนี้: target_visits = เคยเข้าขั้นปลายทางกี่ครั้ง (แนวทางที่ทำครั้งเดียว เช่น หลังครบ 3 ข้อ)"""
    target = fs(state).get("item_step") if edge["to"] == "back" else edge["to"]
    return {**current, "target_visits": fs(state)["visits"].get(target, 0)}


def choose_edge(state: dict, ctx: C.Ctx, step_id: str) -> dict | None:
    current = values(state, ctx, step_id)
    for edge in edges_from(ctx, step_id):
        if evaluate(edge.get("when"), edge_values(state, current, edge)):
            return edge
    return None


def edge_text(edge: dict) -> str:
    return edge.get("label") or describe(edge.get("when"))


# ---------------------------------------------------------------- เดินตามกราฟ

def begin(state: dict, ctx: C.Ctx) -> C.Fx:
    fx = C.Fx()
    state["flow"] = None
    fs(state)
    state["ended"] = False
    state["end_reason"] = None
    enter(state, ctx, fx, spec(ctx)["start"], ["g_start"], ["เริ่ม Flow ที่ครูออกแบบในติวเตอร์"])
    return fx


def follow(state: dict, ctx: C.Ctx, fx: C.Fx, from_step: str, edges: list[str], notes: list[str], hops: int = 0):
    """ไล่เส้นออกจากขั้น from_step ด้วยตัวแปรล่าสุด แล้วเข้าขั้นปลายทาง"""
    edge = choose_edge(state, ctx, from_step)
    step = step_of(ctx, from_step)
    if edge is None:
        # ไม่มีเส้นที่เงื่อนไขเป็นจริง: ขั้นทำโจทย์อยู่ที่เดิม (ถูกแล้วได้ข้อใหม่ ผิดก็ลองข้อเดิมต่อ) ขั้นอื่นกลับไปขั้นทำโจทย์ล่าสุด
        # Widget ที่ยังทำไม่ถูกให้ลองที่เดิม
        retry = step and (step["kind"] == "item" or (step["kind"] == "widget" and not fs(state)["last"].get("widget_pass")))
        target = from_step if retry else fs(state).get("item_step") or spec(ctx)["start"]
        notes.append(f"ไม่มีเส้นออกจาก \"{label(step)}\" ที่เงื่อนไขเป็นจริง ใช้ทางเริ่มต้นของระบบ")
        enter(state, ctx, fx, target, edges, notes, hops + 1)
        return
    target = edge["to"]
    if target == "back":
        # กลับไปขั้นทำโจทย์ที่นักเรียนมา (ขั้นคำใบ้หรือบทเรียนที่หลายขั้นโจทย์ใช้ร่วมกัน)
        target = fs(state).get("item_step") or spec(ctx)["start"]
    notes.append(f"{edge_text(edge)} → {label(step_of(ctx, target))}")
    if step and step["kind"] == "item":
        for extra in follow_ups(state, ctx, from_step, edge):
            fs(state).setdefault("queue", []).append(
                {"origin": from_step, "to": extra["to"], "edge": extra["id"], "label": edge_text(extra)})
            notes.append(f"\"{edge_text(extra)}\" เป็นจริงด้วย จะทำต่อเมื่อกลับมาที่ขั้นนี้")
    enter(state, ctx, fx, target, edges + [edge["id"]], notes, hops + 1)


def follow_ups(state: dict, ctx: C.Ctx, step_id: str, chosen: dict) -> list[dict]:
    """เส้นตอบถูกเส้นอื่นที่เป็นจริงพร้อมกับเส้นที่เลือก และเป็นแนวทางคนละเรื่อง (ใช้ตัวแปรคนละตัว)
    เช่น ถูกหลังใช้คำใบ้ → ข้อคู่ขนาน กับ ครบ 2 ข้อ → อธิบายความคิด ทำเส้นแรกก่อน แล้วพาไปทำเส้นที่เหลือต่อ
    ไม่ให้แนวทางของครูหายไปเงียบ ๆ เพราะเส้นแรกที่เป็นจริงชนะ"""
    picked = names(chosen.get("when")) - {"correct"}
    target = step_of(ctx, chosen["to"])
    if "correct" not in names(chosen.get("when")) or "wrong" in picked or not picked or (target and target["kind"] == "end"):
        return []
    current = values(state, ctx, step_id)
    out, after = [], False
    for edge in edges_from(ctx, step_id):
        if edge is chosen:
            after = True
            continue
        used = names(edge.get("when"))
        other = used - {"correct"}
        goal = step_of(ctx, edge["to"])
        if (after and "correct" in used and "wrong" not in used and other and goal and goal["kind"] != "end"
                and edge["to"] not in (step_id, chosen["to"]) and not other <= picked and not picked <= other
                and evaluate(edge["when"], edge_values(state, current, edge))):
            out.append(edge)
    return out


def go(state: dict, ctx: C.Ctx, fx: C.Fx, position: str, edges: list[str], notes: list[str], detail: dict | None = None):
    flow = fs(state)
    C.move(state, ctx, fx, position, edges, " · ".join(n for n in notes if n),
           {**(detail or {}), "step": flow.get("step"), "step_label": label(step_of(ctx, flow.get("step")))})


def enter(state: dict, ctx: C.Ctx, fx: C.Fx, step_id: str, edges: list[str], notes: list[str], hops: int = 0,
          pick: str | None = None):
    flow = fs(state)
    queue = flow.get("queue") or []
    if queue and step_id == queue[0]["origin"]:
        # กลับมาที่ขั้นทำโจทย์ที่มีแนวทางค้างไว้ (เส้นตอบถูกอีกเส้นที่เป็นจริงพร้อมกัน): ทำแนวทางนั้นก่อนได้ข้อใหม่
        pending = queue.pop(0)
        notes.append(f"ต่อด้วยแนวทางที่ค้างไว้: {pending['label']}")
        edges = edges + [pending["edge"]]
        step_id = pending["to"]
    step = step_of(ctx, step_id)
    if hops > MAX_HOPS or step is None:
        stuck(state, ctx, fx, edges, notes + ["Flow วนผ่านขั้นที่ไม่หยุดรอนานเกินไป ส่งต่อครู"])
        return
    previous = flow.get("step")
    flow["step"] = step_id
    flow["visits"][step_id] = flow["visits"].get(step_id, 0) + 1
    fx.map_steps.append(step_id)
    kind = step["kind"]
    tools = ctx.content.tool

    if kind == "item":
        enter_item(state, ctx, fx, step, edges, notes, pick)
    elif kind == "hint":
        item = state.get("item")
        if item is None or not tools("hints"):
            notes.append("ข้ามคำใบ้ (ครูปิดบันไดคำใบ้ หรือยังไม่มีโจทย์)")
            follow(state, ctx, fx, step_id, edges, notes, hops)
            return
        level = hint_level(state, step)
        delay = float(step.get("delay") or 0) * ctx.time_scale
        need_level = max(level, item["hint_level"])
        C.need_hints(state, fx, need_level)
        if delay > 0:
            item["pending_hint"] = level
            state["timers"]["delay_until"] = ctx.now + delay
            flow["pending"] = {"kind": "hint", "step": step_id, "level": level}
            go(state, ctx, fx, F.DELAY, edges, notes + [f"หน่วงเวลา {delay:.0f} วินาทีก่อนแสดงคำใบ้ระดับ {level}"])
            return
        C.reveal(state, level)
        notes.append(f"แสดงคำใบ้ระดับ {level}")
        follow(state, ctx, fx, step_id, edges, notes, hops)
    elif kind == "lesson":
        if step.get("walkthrough") and not step.get("text") and not tools("walkthrough"):
            notes.append("ข้ามตัวอย่างทีละขั้น (ครูปิด Walkthrough)")
            follow(state, ctx, fx, step_id, edges, notes, hops)
            return
        leaked = lesson_leak(ctx.content, step.get("text") or "", (state.get("item") or {}).get("id"))
        if leaked:
            notes.append(f"Answer-Leak Guard ซ่อนเนื้อหาของบทเรียนย่อ เพราะมีคำตอบของข้อ {leaked}")
        go(state, ctx, fx, F.LESSON, edges, notes + [f"แสดงบทเรียนย่อ \"{label(step)}\""])
    elif kind == "activity":
        # เนื้อหาสร้างโดย AI ตามคำบรรยายของขั้น (services ทำหลังบันทึก) ระหว่างรอหน้าจอขึ้นว่ากำลังเตรียม
        flow["activity"] = {"step": step_id, "status": "pending", "text": None, "question": None}
        fx.activity = {"step": step_id}
        go(state, ctx, fx, F.ACTIVITY, edges, notes + [f"AI สร้างกิจกรรม \"{label(step)}\""])
    elif kind == "widget":
        skip = None
        if step["widget"] == "custom" and not step["config"].get("html"):
            skip = "ข้าม Widget (AI ยังไม่ได้เขียนหน้าเว็บของขั้นนี้)"
        else:
            pending = [it for it in ctx.content.items.values() if it["id"] not in state["done_items"]]
            leaked = leaked_item(W.text_of(step["widget"], step["config"]), pending, (state.get("item") or {}).get("id"))
            if leaked:
                skip = f"Answer-Leak Guard ข้าม Widget เพราะมีคำตอบของข้อ {leaked}"
        if skip:
            flow["last"] = {"widget_pass": True, "widget_tries": 0}
            notes.append(skip)
            follow(state, ctx, fx, step_id, edges, notes, hops)
            return
        # กลับมาที่ Widget เดิมทันที (ลองใหม่) นับครั้งต่อ เข้าจากขั้นอื่นนับใหม่
        if previous != step_id or (flow.get("widget") or {}).get("step") != step_id:
            flow["widget"] = {"step": step_id, "tries": 0}
        go(state, ctx, fx, F.WIDGET, edges, notes + [f"แสดง Widget \"{label(step)}\" ({W.WIDGETS[step['widget']]['label']})"])
    elif kind == "reflect":
        go(state, ctx, fx, F.REFLECT, edges, notes + ["ให้นักเรียนอธิบายความคิด" + (" แล้วให้ AI ประเมินตามเกณฑ์ของครู" if step.get("judge") else "")])
    elif kind == "break":
        seconds = float(step.get("seconds") or 60) * ctx.time_scale
        state["timers"]["break_until"] = ctx.now + seconds
        flow["pending"] = {"kind": "break", "step": step_id}
        go(state, ctx, fx, F.CB, edges, notes + [f"พักสายตา {seconds:.0f} วินาที"])
    elif kind == "notify":
        text = step.get("text") or label(step)
        fx.alerts.append({"level": step.get("level", "normal"), "kind": "flow_notify", "message": text, "own_level": True})
        notes.append(f"แจ้งครู: {text}")
        follow(state, ctx, fx, step_id, edges, notes, hops)
    elif kind == "teacher":
        text = step.get("text") or label(step)
        fx.alerts.append({"level": "normal", "kind": "flow_teacher", "message": text})
        go(state, ctx, fx, F.DEADLOCK, edges, notes + [f"หยุดรอครู: {text}"])
    elif kind == "check":
        follow(state, ctx, fx, step_id, edges, notes, hops)
    else:  # end
        completed = step.get("result", "completed") == "completed"
        C.end_session(state, ctx, fx, F.DONE if completed else F.ENDED, edges, " · ".join(notes + [label(step)]),
                      "completed" if completed else "student_stop")
        fx.decisions[-1]["detail"].update(step=step_id, step_label=label(step))
        fx.result = {"kind": "correct" if completed else "ok", "message": step.get("text") or "ยอดเยี่ยม ทำชุดนี้สำเร็จแล้ว"}


def hint_level(state: dict, step: dict) -> int:
    level = step.get("level", "auto")
    if level == "auto":
        item = state["item"]
        return max(1, min(3, max(item["error_count"], item["hint_floor"])))
    return max(1, min(3, int(level)))


def stuck(state: dict, ctx: C.Ctx, fx: C.Fx, edges: list[str], notes: list[str]):
    flow = fs(state)
    flow["stuck"] = True
    go(state, ctx, fx, F.DEADLOCK, edges + ["g_stuck"], notes)
    C.alert(fx, state, "normal", "deadlock", notes[-1], dedupe=False)
    fx.result = {"kind": "wrong", "message": "ข้อนี้ยากจริง ๆ ครูกำลังจะมาช่วยนะ"}


# ---------------------------------------------------------------- ขั้นทำโจทย์

def enter_item(state: dict, ctx: C.Ctx, fx: C.Fx, step: dict, edges: list[str], notes: list[str], pick: str | None):
    flow = fs(state)
    item = state.get("item")
    if item and flow.get("item_step") == step["id"] and not solved(item) and not pick:
        # กลับมาขั้นเดิมขณะที่ข้อยังไม่ถูก = ทำข้อเดิมต่อ (เช่น หลังได้คำใบ้)
        go(state, ctx, fx, C.answer_position(state), edges, notes + [f"ทำข้อ {item['id']} ต่อ"])
        return
    if flow.get("item_step") != step["id"]:
        flow["solved_here"] = 0
    abandon(state, ctx)
    pick = pick or step.get("pick", "adaptive")
    max_items = ctx.content.qs.get("max_items") or ctx.p("max_items")
    if state["items_count"] >= max_items:
        # เพดานจำนวนข้อ (ล็อกไว้ทุก Flow)
        C.end_session(state, ctx, fx, F.ENDED, edges + ["g_cap"],
                      " · ".join(notes + [f"ทำครบ {max_items} ข้อแล้ว บันทึกความคืบหน้าไว้"]), "cap")
        C.alert(fx, state, "silent", "cap", f"ทำครบ {max_items} ข้อแล้วยังไม่จบ Flow")
        fx.result = {"kind": "ok", "message": "วันนี้ทำไปเยอะมากแล้ว ระบบบันทึกความคืบหน้าไว้ให้ พักก่อนนะ"}
        return
    chosen, mode, note = choose_item(state, ctx, pick)
    if note:
        notes.append(note)
    if chosen is None:
        if state.get("live_count", 0) < ctx.content.live_cap():
            request = {"path": state.get("path", "STANDARD"), "difficulty": 50 if pick != "easier" else 25, "count": 2}
            state["live_request"] = request
            flow["pending"] = {"kind": "live", "step": step["id"], "pick": pick}
            go(state, ctx, fx, F.LIVE, edges + ["g_live"], notes + ["โจทย์ในคลังหมด ให้ AI สร้างโจทย์ใหม่"], request)
            fx.generate = request
            return
        C.end_session(state, ctx, fx, F.ENDED, edges, " · ".join(notes + ["โจทย์ในชุดหมดแล้ว"]), "no_items")
        return
    C.serve(state, ctx, chosen, mode, iso_source=flow.get("last_solved") if mode == "isomorphic" else None)
    flow["item_step"] = step["id"]
    go(state, ctx, fx, C.answer_position(state), edges, notes + [f"ข้อ {chosen['id']} ({PICK_SHORT.get(pick, pick)})"],
       {"next_item": chosen["id"]})


def abandon(state: dict, ctx: C.Ctx):
    """ออกจากข้อที่ยังทำไม่ถูก: Mastery ของข้อนั้นเป็น 0 ถ้าเป็นข้อคู่ขนาน ข้อต้นทางได้น้ำหนัก 0 ด้วย"""
    item = state.get("item")
    if not item or solved(item) or item["voided"] or not item["attempts"]:
        return
    C.add_mastery(state, item["concept"], 0.0, item["id"], item["format"])
    if item["mode"] == "isomorphic" and item.get("iso_source"):
        C.zero_entry(state, item["concept"], item["iso_source"])
    fs(state)["streak"] = 0


def choose_item(state: dict, ctx: C.Ctx, pick: str) -> tuple[dict | None, str, str | None]:
    flow = fs(state)
    content = ctx.content
    item = state.get("item")
    note = None
    # กลับจากการทบทวนพื้นฐาน: ทำข้อที่พักไว้ก่อน Error Count เริ่มนับใหม่
    rem = state.get("remedial")
    if rem and pick != "prerequisite":
        suspended = content.item(rem["suspended"]) if rem.get("suspended") in content.items else None
        state["remedial"] = None
        state["remedial_passed"] += 1
        if suspended:
            return suspended, rem.get("suspended_mode", "main"), "ทบทวนพื้นฐานจบแล้ว กลับไปข้อที่พักไว้"
    if pick == "prerequisite" and not content.tool("remedial"):
        pick, note = "easier", "ครูปิดทบทวนพื้นฐาน ใช้ข้อที่ง่ายลงแทน"
    if pick == "isomorphic" and not content.tool("isomorphic"):
        pick, note = "adaptive", "ครูปิด Isomorphic Test ใช้ข้อถัดไปตาม Mastery แทน"
    if pick == "isomorphic":
        iso = C.pick_isomorph(state, ctx, flow.get("last_solved") or "") if flow.get("last_solved") else None
        if iso:
            return iso, "isomorphic", note
        pick, note = "adaptive", "ไม่มีข้อคู่ขนานที่ยังไม่ใช้ ใช้ข้อถัดไปตาม Mastery แทน"
    if pick == "prerequisite":
        return prerequisite(state, ctx, item)
    if pick == "main":
        done = set(state["done_items"])
        mains = [m for m in content.main_items() if m["id"] not in done]
        pool = mains or C.extra_pool(state, ctx)
        return (pool[0], C.mode_for(content, pool[0]["id"]), note) if pool else (None, "main", note)
    if pick == "easier":
        chosen, mode = C.select_next(state, ctx, "SUPPORTED", 20)
        state["path"] = "SUPPORTED"
        return chosen, mode, note
    if pick == "harder":
        chosen, mode = C.select_next(state, ctx, "FAST_TRACK", 85)
        state["path"] = "FAST_TRACK"
        return chosen, mode, note
    # adaptive: เส้นทางและความยากจาก Mastery กับเวลาคิด (Fuzzy) เหมือนผังมาตรฐาน
    last = flow.get("last") or {}
    it = content.item(item["id"]) if item else None
    expected = it.get("expected_time", 45) if it else 45
    rt = last.get("rt") or expected
    path, m, slowness = C.choose_path(state, ctx, rt, expected)
    difficulty = fuzzy.difficulty(m, slowness)
    state["path"] = path
    chosen, mode = C.select_next(state, ctx, path, difficulty["output"])
    return chosen, mode, (note + " · " if note else "") + f"{C.PATH_LABELS[path]} ความยาก {difficulty['output']:.0f}"


def prerequisite(state: dict, ctx: C.Ctx, item: dict | None) -> tuple[dict | None, str, str | None]:
    """โจทย์ทบทวนพื้นฐาน: ครั้งแรกพักข้อที่ยังไม่ถูกไว้ (Remedial Loop) แล้วเลือก Prerequisite จาก Bug Library"""
    content = ctx.content
    rem = state.get("remedial")
    if rem is None:
        suspended = None
        if item and item["mode"] != "remedial" and not solved(item):
            suspended = item["iso_source"] if item["mode"] == "isomorphic" and item.get("iso_source") else item["id"]
        concept = content.item(suspended)["concept"] if suspended else (content.item(item["id"])["concept"] if item else content.target)
        prereq = C.choose_prerequisite(state, ctx, concept, item.get("last_tag") if item else None)
        if suspended:
            state["remedial_rounds"][suspended] = state["remedial_rounds"].get(suspended, 0) + 1
        state["remedial_started"] += 1
        # ไม่มี Prerequisite: ฝึกโจทย์ที่ง่ายกว่าข้อที่พักไว้ในเรื่องเดิม (เหมือนผังมาตรฐาน)
        rem = {"concept": prereq or concept, "round": state["remedial_rounds"].get(suspended, 1) if suspended else 1,
               "streak": 0, "suspended": suspended,
               "suspended_mode": C.mode_for(content, suspended) if suspended else "main", "used": [],
               "root": prereq is None and suspended is not None}
        state["remedial"] = rem
        note = f"ทบทวน {content.concept_name(rem['concept'])}" + (f" พักข้อ {suspended} ไว้" if suspended else "")
    else:
        note = f"ทบทวน {content.concept_name(rem['concept'])} ข้อถัดไป"
    chosen = C.next_remedial_item(state, ctx) if (content.remedial_items(rem["concept"]) or rem.get("root")) else None
    if chosen is None:
        chosen, mode = C.select_next(state, ctx, "SUPPORTED", 20)
        return chosen, mode, note + " · ไม่มีโจทย์ทบทวน ใช้ข้อที่ง่ายลงแทน"
    return chosen, "remedial", note


# ---------------------------------------------------------------- เหตุการณ์

def submit(state: dict, ctx: C.Ctx, raw) -> C.Fx:
    fx = C.Fx()
    flow = fs(state)
    data = C.intake(state, ctx, fx, raw)
    if data is None:
        return fx
    item, it, check, rt, attempt, base = data["item"], data["it"], data["check"], data["rt"], data["attempt"], data["base"]
    now = ctx.now
    if state["position"] == F.DELAY:
        # ตอบระหว่างหน่วงเวลา: ยกเลิกคำใบ้ที่รออยู่ แล้วตัดสินด้วยเส้นของขั้นทำโจทย์
        state["timers"]["delay_until"] = None
        item["pending_hint"] = 0
        flow["pending"] = None
    expected = max(float(it.get("expected_time", 45)), 1.0)
    edges = ["g_clean"]
    notes = []
    if check.correct:
        attempt["kind"] = "correct"
        item["attempts"].append(attempt)
        C._count_rt(state, rt)
        state["correct_total"] += 1
        state["rapid_streak"] = 0
        if C.help_level(item) >= 1:
            state["hints_useful"] += 1
        # ถามครูผู้ช่วยในแชตแล้วตอบถูก ไม่นับว่าถูกตั้งแต่ครั้งแรก (นับเท่าใช้คำใบ้)
        first_try = data["first_attempt"] and C.help_level(item) == 0
        if data["first_attempt"]:
            C.record_format(state, it["concept"], it["format"], True)
            if C.help_level(item) == 0:
                state["first_attempt_correct"] += 1
        fx.trace("answer", it["id"], {**base, "correct": True, "raw": data["raw"]}, now)
        on_solved(state, ctx, it)
        flow["streak"] = flow.get("streak", 0) + 1 if first_try else 0
        flow["last"] = {"correct": True, "first_try": first_try, "rt": round(rt, 2), "rt_ratio": round(rt / expected, 3),
                        "slow": rt > expected}
        fx.result = {"kind": "correct", "message": C._praise(item)}
        notes.append(f"ตอบข้อ {it['id']} ถูก")
        follow(state, ctx, fx, flow.get("item_step") or spec(ctx)["start"], edges, notes)
        fx.result = {**fx.result, "kind": "correct"}
        return fx

    # Rapid Guess (ล็อกไว้ทุก Flow): ผิดเร็วกว่าเวลาอ่านขั้นต่ำ คะแนนเป็นโมฆะและล็อกปุ่มตอบ
    min_read = it.get("min_read_time") or ctx.p("rapid_guess_threshold")
    if rt < min_read:
        attempt["kind"] = "rapid"
        item["attempts"].append(attempt)
        item["undo"] = {"ts": now, "state": data["snapshot"]}
        fx.trace("answer", it["id"], {**base, "correct": False, "raw": data["raw"], "rapid": True}, now)
        C.on_rapid_guess(state, ctx, fx, it, rt, min_read, edges + ["g_rapid"], {**base, "step": flow.get("step")})
        return fx

    attempt["kind"] = "wrong"
    item["attempts"].append(attempt)
    item["undo"] = {"ts": now, "state": data["snapshot"]}
    item["ready_at"] = now
    C._count_rt(state, rt)
    state["rapid_streak"] = 0
    if data["first_attempt"]:
        C.record_format(state, it["concept"], it["format"], False)
    diag = C.diagnose(state, ctx, it, check.value)
    attempt["diagnosis"] = diag
    item["hint_floor"] = max(item["hint_floor"], diag["floor"])
    item["last_tag"] = diag["tag"] or item["last_tag"]
    item["last_class"] = diag["class"]
    item["error_count"] += 1
    item["rts"].append(rt)
    flow["streak"] = 0
    fx.trace("answer", it["id"], {**base, "correct": False, "raw": data["raw"], "diagnosis": diag}, now)
    if diag["class"] == "misconception":
        fx.trace("misconception", it["id"], {"tag": diag["tag"]}, now)
    elif diag["class"] == "unclassified" and not diag["tag"]:
        fx.tag_requests.append({"item_id": it["id"], "answer": data["raw"]})
    tag = ctx.content.tag(diag["tag"])
    flow["last"] = {"wrong": True, "misconception": diag["class"] == "misconception", "slip": diag["class"] == "slip",
                    "bug": diag["tag"] or "", "bug_type": (tag or {}).get("type", ""),
                    "rt": round(rt, 2), "rt_ratio": round(rt / expected, 3), "slow": rt > expected}
    fx.result = {"kind": "wrong", "message": C._wrong_message(diag), "diagnosis": diag["class"]}
    notes.append(f"ตอบข้อ {it['id']} ผิดครั้งที่ {item['error_count']}"
                 + (f" ({diag['tag_name']})" if diag.get("tag_name") else ""))
    if item["error_count"] >= STUCK_LIMIT:
        stuck(state, ctx, fx, edges, notes + [f"ผิดข้อ {it['id']} ครบ {STUCK_LIMIT} ครั้ง ส่งต่อครู (เพดานที่ล็อกไว้)"])
        return fx
    before = item["id"]
    follow(state, ctx, fx, flow.get("item_step") or spec(ctx)["start"], edges, notes)
    after = state.get("item")
    if state["position"] in (F.LESSON, F.REFLECT, F.CB):
        fx.result["message"] = "มาพักทบทวนกันสักครู่ แล้วค่อยลองต่อนะ"
    elif after and after["id"] != before:
        fx.result["message"] = ("มาทบทวนพื้นฐานกันก่อน แล้วค่อยกลับไปข้อเดิม" if after["mode"] == "remedial"
                                else "ไม่เป็นไรนะ มาลองอีกข้อกัน")
    return fx


def on_solved(state: dict, ctx: C.Ctx, it: dict):
    item = state["item"]
    flow = fs(state)
    if it["id"] not in state["done_items"]:
        state["done_items"].append(it["id"])
    state["items_finished"] += 1
    flow["solved_here"] = flow.get("solved_here", 0) + 1
    flow["last_solved"] = it["id"]
    if item["mode"] == "remedial" and state.get("remedial"):
        state["remedial"]["streak"] += 1
    if item["voided"]:
        return
    weight = ((1.0 if item["error_count"] == 0 else WEIGHTS["self"]) if not item.get("chat_help") else WEIGHTS[1]) \
        if item["mode"] == "isomorphic" else C.item_weight(item)
    C.add_mastery(state, it["concept"], weight, it["id"], it["format"])
    if item["mode"] == "challenge" and it["concept"] != ctx.content.target:
        C.add_mastery(state, ctx.content.target, weight, it["id"], it["format"])
    if item["mode"] == "main" and it["id"] not in state["main_done"]:
        state["main_done"].append(it["id"])
    if item["mode"] == "challenge":
        state["challenge_correct"] = True


def resolve_timers(state: dict, ctx: C.Ctx, fx: C.Fx):
    flow = fs(state)
    for _ in range(4):
        timers = state["timers"]
        position = state["position"]
        now = ctx.now
        pending = flow.get("pending") or {}
        if position == F.DELAY and timers["delay_until"] and now >= timers["delay_until"]:
            item = state["item"]
            item["ready_at"] = max(item["ready_at"], timers["delay_until"])
            level = pending.get("level") or item["pending_hint"] or 1
            C.reveal(state, level)
            flow["pending"] = None
            flow["step"] = pending.get("step") or flow["step"]
            follow(state, ctx, fx, flow["step"], [], [f"ครบเวลาหน่วง แสดงคำใบ้ระดับ {level}"])
            continue
        if position == F.LOCK and timers["lock_until"] and now >= timers["lock_until"]:
            state["item"]["ready_at"] = timers["lock_until"]
            timers["lock_until"] = None
            back = state.get("resume_position") or C.answer_position(state)
            state["resume_position"] = None
            go(state, ctx, fx, back, ["g_rapid_back"], ["ครบเวลาล็อก กลับมาตอบได้"])
            continue
        if position == F.OUTAGE and timers.get("retry_at") and now >= timers["retry_at"]:
            timers["retry_at"] = None
            go(state, ctx, fx, F.LIVE, ["g_outage_retry"], [f"ครบ {C.OUTAGE_RETRY:.0f} วินาที ลองให้ AI สร้างโจทย์ใหม่อีกครั้ง"])
            fx.generate = state.get("live_request") or {"path": state.get("path", "STANDARD"), "difficulty": 50, "count": 2}
            continue
        if position == F.CB and timers["break_until"] and now >= timers["break_until"]:
            timers["break_until"] = None
            flow["pending"] = None
            if pending.get("kind") == "break":
                flow["last"] = {}
                follow(state, ctx, fx, pending["step"], [], ["พักครบแล้ว"])
            elif step_of(ctx, spec(ctx).get("after_stress")):
                # ครูให้ไปขั้นที่กำหนดหลังพักเพราะเครียด (เช่น ดูตัวอย่างทีละขั้นก่อนทำต่อ เหมือนผังมาตรฐาน)
                flow["last"] = {}
                enter(state, ctx, fx, spec(ctx)["after_stress"], ["g_stress_back"], ["พักครบแล้ว ไปขั้นที่ครูกำหนดหลังพัก"])
            else:
                back_to_item(state, ctx, fx, ["g_stress_back"], "พักครบแล้ว กลับมาทำต่อ")
            continue
        break


def back_to_item(state: dict, ctx: C.Ctx, fx: C.Fx, edges: list[str], note: str):
    flow = fs(state)
    if state.get("item") and not solved(state["item"]):
        flow["step"] = flow.get("item_step") or flow["step"]
        state["item"]["ready_at"] = ctx.now
        go(state, ctx, fx, C.answer_position(state), edges, [note])
    else:
        enter(state, ctx, fx, flow.get("item_step") or spec(ctx)["start"], edges, [note])


def lesson_done(state: dict, ctx: C.Ctx) -> C.Fx:
    fx = C.Fx()
    resolve_timers(state, ctx, fx)
    if state["position"] not in (F.LESSON, F.ACTIVITY):
        fx.result = {"kind": "blocked", "message": C.BLOCK_MESSAGES.get(state["position"], "")}
        return fx
    step = flow_step(state, ctx)
    fx.trace("lesson_done" if state["position"] == F.LESSON else "activity_done", step["id"] if step else None,
             {"label": label(step)}, ctx.now)
    fs(state)["last"] = {}
    note = "อ่านบทเรียนย่อจบแล้ว" if state["position"] == F.LESSON else "ทำกิจกรรมจบแล้ว"
    if step is None:
        back_to_item(state, ctx, fx, [], note)
    else:
        follow(state, ctx, fx, step["id"], [], [note])
    fx.result = fx.result or {"kind": "ok"}
    return fx


def reflect(state: dict, ctx: C.Ctx, text: str, verdict: dict | None) -> C.Fx:
    """นักเรียนส่งคำอธิบาย verdict มาจาก AI (ถ้าขั้นนี้ให้ประเมิน) และถูกบันทึกเป็นร่องรอยให้ครูตรวจ"""
    fx = C.Fx()
    resolve_timers(state, ctx, fx)
    if state["position"] not in (F.REFLECT, F.ACTIVITY):
        fx.result = {"kind": "blocked", "message": C.BLOCK_MESSAGES.get(state["position"], "")}
        return fx
    step = flow_step(state, ctx)
    verdict = verdict or {}
    fx.trace("reflect", step["id"], {"question": question_of(state, step), "text": text, "judge": verdict}, ctx.now)
    fs(state)["last"] = {"judge_pass": verdict.get("pass"), "judge_score": verdict.get("score")}
    notes = ["นักเรียนส่งคำตอบของกิจกรรม" if step["kind"] == "activity" else "นักเรียนส่งคำอธิบาย"]
    if judged(step):
        notes.append(f"AI ประเมิน: {'ผ่าน' if verdict.get('pass') else 'ยังไม่ผ่าน' if verdict.get('pass') is False else 'ประเมินไม่ได้'}"
                     + (f" ({verdict['score']})" if verdict.get("score") is not None else ""))
    follow(state, ctx, fx, step["id"], [], notes)
    fx.result = fx.result or {"kind": "ok", "message": "บันทึกคำอธิบายแล้ว"}
    if fx.result.get("kind") == "ok":
        fx.result["message"] = "ขอบคุณที่อธิบายนะ"
    return fx


def widget(state: dict, ctx: C.Ctx, response: dict) -> C.Fx:
    """ตรวจคำตอบของ Widget ด้วยกฎ บันทึกร่องรอยให้ครู นับเข้า Mastery (เฉพาะ Widget ในคลัง) แล้วไปตามเส้นของ Flow"""
    fx = C.Fx()
    resolve_timers(state, ctx, fx)
    if state["position"] != F.WIDGET:
        fx.result = {"kind": "blocked", "message": C.BLOCK_MESSAGES.get(state["position"], "")}
        return fx
    step = flow_step(state, ctx)
    flow = fs(state)
    kind = step["widget"]
    result = W.check(kind, step["config"], response)
    tracked = flow.setdefault("widget", {"step": step["id"], "tries": 0})
    tracked["tries"] += 1
    graded = W.WIDGETS[kind]["graded"]
    item = state.get("item")
    concept = ctx.content.item(item["id"])["concept"] if item else ctx.content.target
    if graded:
        # ถูกตั้งแต่ครั้งแรก = 1 แก้จนถูก = 0.5 ยังไม่ถูก = 0 (หนึ่งค่าต่อการเข้าขั้นหนึ่งครั้ง) และนับเป็นรูปแบบไม่ใช่ปรนัย
        key = f"widget:{step['id']}"
        if tracked["tries"] == 1:
            C.record_format(state, concept, "widget", result["correct"])
            C.add_mastery(state, concept, 1.0 if result["correct"] else 0.0, key, "widget")
        elif result["correct"]:
            entry = next((e for e in reversed(state["mastery"].get(concept, [])) if e["item"] == key), None)
            if entry and entry["w"] == 0.0:
                entry["w"] = 0.5
    fx.trace("widget", step["id"], {"widget": kind, "value": result["value"], "correct": result["correct"] if graded else None,
                                    "tries": tracked["tries"], "label": label(step)}, ctx.now)
    flow["last"] = {"widget_pass": result["correct"], "widget_tries": tracked["tries"]}
    verdict = ("ทำถูก" if result["correct"] else "ยังไม่ถูก") if graded else "ทำเสร็จ"
    follow(state, ctx, fx, step["id"], [], [f"ส่ง Widget \"{label(step)}\": {verdict} ({result['value']})"])
    if not fx.result:
        again = state["position"] == F.WIDGET and flow.get("step") == step["id"]
        fx.result = {"kind": "correct" if result["correct"] else "wrong", "marks": result["marks"] if again else None,
                     "message": "ถูกต้อง เก่งมาก" if result["correct"] and graded else
                     "ยังไม่ถูก ลองดูใหม่อีกครั้งนะ" if again else "บันทึกแล้ว ไปต่อกันเลย"}
    return fx


# ข้อความที่เป็นการถามขอความช่วยเหลือเรื่องโจทย์ (ไม่ใช่ทักทายหรือขอบคุณ) ตรวจด้วยคำ อธิบายได้ว่าทำไมนับ
HELP_WORDS = re.compile(r"\?|ไหม|มั้ย|ยังไง|อย่างไร|ทำไม|อะไร|เท่าไ|ตรงไหน|ช่วย|ไม่เข้าใจ|ไม่รู้|งง|คำใบ้|hint|เฉลย|คำตอบ|"
                        r"ขั้นแรก|ต้องทำ|ทำต่อ|ตัวอย่าง|อธิบาย|สอน", re.I)


def is_help(message: str) -> bool:
    return bool(HELP_WORDS.search(message or ""))


def chat_help(state: dict, ctx: C.Ctx) -> C.Fx:
    """นักเรียนถามครูผู้ช่วยในแชตเรื่องข้อที่กำลังทำ: นับเป็นการขอคำใบ้ (ปิดได้ในแนวทางแชตของครู)
    ไม่อย่างนั้นถาม AI จนได้คำตอบแล้วยังนับว่าถูกตั้งแต่ครั้งแรก ได้ Mastery เต็ม และข้ามข้อคู่ขนาน"""
    fx = C.Fx()
    item = state.get("item")
    chat = (spec(ctx) or {}).get("chat") or {}
    if item is None or state["position"] not in F.CAN_ANSWER or chat.get("count_as_hint") is False:
        return fx
    item["chat_help"] = item.get("chat_help", 0) + 1
    fx.trace("chat_help", item["id"], {"count": item["chat_help"]}, ctx.now)
    fx.result = {"kind": "counted", "count": item["chat_help"]}
    return fx


def chat_intent(flow_spec: dict | None, message: str) -> dict | None:
    """สิ่งที่นักเรียนพิมพ์ที่ครูกำหนดไว้ในแนวทางแชต จับด้วยคำ (อธิบายได้ ไม่ใช้ AI ตัดสิน) ข้อแรกที่ตรงชนะ"""
    flat = normalize(message or "").lower().replace(" ", "")
    for intent in ((flow_spec or {}).get("chat") or {}).get("intents", []):
        if any(k.replace(" ", "") in flat for k in intent["keywords"]):
            return intent
    return None


def chat_goto(state: dict, ctx: C.Ctx, intent: dict) -> C.Fx:
    """แชตพาไปขั้นที่ครูกำหนด (เช่น ขอตัวอย่าง → กิจกรรม) เฉพาะตอนกำลังทำโจทย์ ขั้นนั้นกลับมาข้อเดิมตามเส้นของมันเอง"""
    fx = C.Fx()
    resolve_timers(state, ctx, fx)
    step = step_of(ctx, intent.get("goto"))
    if step is None or state["position"] not in F.CAN_ANSWER:
        return fx
    fx.trace("chat_intent", step["id"], {"intent": intent["id"], "label": intent["label"]}, ctx.now)
    # chat_<id> คือเส้นจากกล่องแชตในผัง (flowspec.map_view) ให้เส้นนั้นติดไฟ
    enter(state, ctx, fx, step["id"], ["g_chat", f"chat_{intent['id']}"],
          [f"นักเรียนพิมพ์ในแชต: {intent['label']} → {label(step)}"])
    return fx


def chat_open(state: dict, ctx: C.Ctx) -> C.Fx:
    """นักเรียนส่งข้อความในแชต: ชิปบนผังย้ายไปกล่องแชตและขึ้นว่า AI กำลังคิด อยู่ที่นั่นจนกลับมาทำบนจอหลัก
    Flow Position ไม่เปลี่ยน (ยังตอบโจทย์ได้ ตรรกะเดิมไม่ต้องรู้จักแชต) ถ้าอยู่ในกลไกที่ล็อกไว้ เช่น พักหรือหยุดรอครู ชิปอยู่ที่เดิม"""
    fx = C.Fx()
    flow = fs(state)
    node = map_node(state, ctx)
    if state["position"] not in WORKING or (node != CHAT and node not in ctx.content.steps):
        return fx
    flow["chat"] = {"since": ctx.now, "thinking": True}
    if node != CHAT:
        shift(state, ctx, fx, ["g_chat_in"], f"นักเรียนพิมพ์ถามครูผู้ช่วย AI ระหว่างขั้น \"{label(step_of(ctx, node))}\"")
    return fx


def chat_replied(state: dict, ctx: C.Ctx) -> C.Fx:
    chat = fs(state).get("chat")
    if chat:
        chat["thinking"] = False
    return C.Fx()


def leave_chat(state: dict, ctx: C.Ctx, fx: C.Fx):
    """นักเรียนกลับมาทำบนจอหลัก (ส่งคำตอบ กดคำใบ้ อ่านจบ ฯลฯ): ชิปออกจากกล่องแชตกลับขั้นที่ทำอยู่"""
    flow = fs(state)
    if flow.get("chat"):
        flow["chat"] = None
        shift(state, ctx, fx, ["g_chat_back"], f"กลับมาทำต่อที่ขั้น \"{label(flow_step(state, ctx))}\"")


def chat_thinking(state: dict, ctx: C.Ctx) -> bool:
    chat = fs(state).get("chat") or {}
    return bool(chat.get("thinking")) and ctx.now - chat.get("since", 0) < THINK_LIMIT


def judged(step: dict | None) -> bool:
    """ขั้นที่ให้ AI ประเมินคำตอบที่นักเรียนพิมพ์: อธิบายความคิดที่ครูเปิดประเมิน หรือกิจกรรมที่ให้พิมพ์ตอบ"""
    return bool(step) and (bool(step.get("judge")) or (step["kind"] == "activity" and step.get("response") == "text"))


def question_of(state: dict, step: dict | None) -> str:
    if step and step["kind"] == "activity":
        return (fs(state).get("activity") or {}).get("question") or step.get("goal", "")
    return (step or {}).get("question", "")


def set_activity(state: dict, step_id: str, text: str, question: str | None, status: str = "ready") -> bool:
    """services ใส่เนื้อหาที่ AI สร้างแล้ว คืน False ถ้านักเรียนออกจากขั้นนั้นไปแล้ว"""
    activity = fs(state).get("activity") or {}
    if state["position"] != F.ACTIVITY or activity.get("step") != step_id:
        return False
    activity.update(text=text, question=question or None, status=status)
    return True


def stress(state: dict, ctx: C.Ctx, source: str) -> C.Fx:
    """ข้อความเครียดหรือท้อ: พักสายตาตามเวลาของระบบ แล้วกลับมาทำขั้นเดิมต่อ"""
    fx = C.Fx()
    if state["position"] in (F.SAFETY, F.DEADLOCK, F.DONE, F.ENDED, F.CB):
        return fx
    fs(state)["pending"] = {"kind": "stress"}
    state["timers"]["break_until"] = ctx.now + ctx.dur("circuit_breaker_break")
    state["timers"]["delay_until"] = None
    go(state, ctx, fx, F.CB, ["g_stress"], ["พบข้อความเครียดหรือท้อ จึงพักสายตา (Circuit Breaker)"], {"source": source})
    C.alert(fx, state, "normal", "stress", "นักเรียนพิมพ์ข้อความแสดงความเครียดหรือท้อแท้")
    fx.result = {"kind": "distress", "level": "stress"}
    return fx


def choose_easier(state: dict, ctx: C.Ctx, fx: C.Fx):
    enter(state, ctx, fx, fs(state).get("item_step") or spec(ctx)["start"], ["g_choose"],
          ["นักเรียนเลือกทำต่อแบบง่ายลง"], pick="easier")


def override(state: dict, ctx: C.Ctx, action: str, params: dict) -> C.Fx:
    """Manual Override (ล็อกไว้ทุก Flow): ปล่อยขั้นรอครู เริ่มข้อเดิมใหม่ หรือเปลี่ยนโจทย์"""
    fx = C.Fx()
    flow = fs(state)
    for key in state["timers"]:
        if key != "cooldown_until":
            state["timers"][key] = None
    flow["pending"] = None
    flow["queue"] = []
    state["ended"] = False
    state["end_reason"] = None
    step = flow_step(state, ctx)
    if action == "set_item":
        item_id = params["item_id"]
        state["remedial"] = None
        C.serve(state, ctx, ctx.content.item(item_id), C.mode_for(ctx.content, item_id))
        go(state, ctx, fx, F.ANSWERING, ["g_teacher"], [f"ครูเปลี่ยนโจทย์เป็น {item_id}"], {"action": action})
    elif state["position"] == F.DEADLOCK and step and step["kind"] == "teacher" and not flow.get("stuck"):
        flow["last"] = {}
        follow(state, ctx, fx, step["id"], ["g_teacher"], ["ครูดูแลแล้ว ปล่อยให้เรียนต่อ"])
    else:
        flow["stuck"] = False
        item = state.get("item")
        if item:
            if action == "release":
                state["remedial_rounds"][item["id"]] = 0
            C.serve(state, ctx, ctx.content.item(item["id"]), item["mode"], item.get("iso_source"))
            flow["step"] = flow.get("item_step") or flow["step"]
            go(state, ctx, fx, C.answer_position(state), ["g_teacher"], ["ครูสั่ง Manual Override ให้เริ่มข้อนี้ใหม่"],
               {"action": action})
        else:
            fx.decisions.extend(begin(state, ctx).decisions)
    fx.result = {"kind": "ok"}
    return fx


def after_live(state: dict, ctx: C.Ctx, new_ids: list[str], error: str | None) -> C.Fx:
    fx = C.Fx()
    if state["position"] != F.LIVE:
        return fx
    flow = fs(state)
    state["live_count"] = state.get("live_count", 0) + len(new_ids)
    pending = flow.get("pending") or {}
    if not new_ids:
        reason = error or "AI สร้างโจทย์ที่ตรวจเฉลยผ่านไม่ได้"
        state["outage_error"] = reason
        state["timers"]["retry_at"] = ctx.now + C.OUTAGE_RETRY
        go(state, ctx, fx, F.OUTAGE, ["g_live_fail"],
           [f"สร้างโจทย์สดไม่สำเร็จ: {reason} · หยุดชั่วคราวและลองใหม่ทุก {C.OUTAGE_RETRY:.0f} วินาที"])
        C.alert(fx, state, "normal", "ai_outage", f"AI ขัดข้องตอนสร้างโจทย์สด นักเรียนหยุดชั่วคราว: {reason}")
        fx.result = {"kind": "outage", "message": reason}
        return fx
    state["outage_error"] = None
    state["timers"]["retry_at"] = None
    flow["pending"] = None
    enter(state, ctx, fx, pending.get("step") or flow.get("item_step") or spec(ctx)["start"], ["g_live_ok"],
          [f"AI สร้างโจทย์ใหม่ {len(new_ids)} ข้อ"], pick=None if pending.get("pick") in (None, "adaptive") else pending["pick"])
    fx.result = {"kind": "ok"}
    return fx


# ---------------------------------------------------------------- มุมมอง

def features(flow_spec: dict | None) -> dict:
    """ฟีเจอร์ที่ Flow นี้ใช้จริง หน้านักเรียน ครู และ Admin แสดงเฉพาะส่วนเหล่านี้ (ไม่มีใน Flow ก็ไม่แสดง)
    ไม่มี Flow (ชุดคำถามที่ครูเขียนเองตามผังมาตรฐาน) = ใช้ทุกอย่าง"""
    if not flow_spec:
        return {"all": True}
    steps = flow_spec.get("steps") or []
    kinds = {s["kind"] for s in steps}
    picks = {s.get("pick") for s in steps if s["kind"] == "item"}
    hint_button = any(s.get("hint_button") for s in steps if s["kind"] == "item")
    return {
        "all": False,
        "kinds": sorted(kinds),
        "picks": sorted(p for p in picks if p),
        "hint_button": hint_button,
        "hints": hint_button or "hint" in kinds,
        "lesson": "lesson" in kinds,
        "walkthrough": any(s.get("walkthrough") for s in steps if s["kind"] == "lesson"),
        "reflect": "reflect" in kinds,
        "activity": "activity" in kinds,
        "break": "break" in kinds,
        "notify": "notify" in kinds or any(i.get("notify") for i in (flow_spec.get("chat") or {}).get("intents", [])),
        "teacher": "teacher" in kinds,
        "widget": "widget" in kinds,
        "chat_flow": bool(flow_spec.get("chat")),
        "widgets": sorted({s["widget"] for s in steps if s["kind"] == "widget"}),
        "isomorphic": "isomorphic" in picks,
        "remedial": "prerequisite" in picks,
    }


def hint_allowed(state: dict, ctx: C.Ctx) -> bool:
    step = step_of(ctx, fs(state).get("item_step"))
    return bool(step and step.get("hint_button", True) and ctx.content.tool("hints"))


def leaked_item(text: str, items, current_id: str | None = None) -> str | None:
    """Answer-Leak Guard ของบทเรียนย่อ (ล็อกไว้ทุก Flow): คืนรหัสโจทย์ที่ข้อความนี้เฉลย
    ตรวจข้อที่กำลังทำทุกกฎ และตรวจข้ออื่นเมื่อข้อความยกโจทย์ข้อนั้นมาทั้งข้อ"""
    if not text:
        return None
    flat = normalize(text).replace(" ", "")
    for it in items:
        math = normalize(it.get("math") or "").replace(" ", "")
        if (it["id"] == current_id or (len(math) >= 3 and math in flat)) and guard.check(text, it).blocked:
            return it["id"]
    return None


def safe_walkthrough(state: dict, content: C.Content, walk: dict | None) -> dict | None:
    """ตัวอย่างทีละขั้นที่เฉลยโจทย์ในคลังซึ่งนักเรียนยังทำไม่ได้ ไม่แสดง (Answer-Leak Guard ใช้ทั้งผังมาตรฐานและ Flow ของ Gem)"""
    if not walk:
        return walk
    text = " ".join([walk.get("problem", "")] + list(walk.get("steps", [])))
    current = (state.get("item") or {}).get("id")
    pending = [it for it in content.items.values() if it["id"] not in state["done_items"]]
    return None if leaked_item(text, pending, current) else walk


def lesson_leak(content: C.Content, text: str, current_id: str | None) -> str | None:
    cache = content.__dict__.setdefault("_lesson_leaks", {})
    key = (text, current_id)
    if key not in cache:
        cache[key] = leaked_item(text, content.items.values(), current_id)
    return cache[key]


def student_extras(state: dict, ctx: C.Ctx) -> dict:
    step = flow_step(state, ctx)
    item = state.get("item")
    extras: dict = {"hint_visible": bool(item and state["position"] in F.CAN_ANSWER and hint_allowed(state, ctx)),
                    "features": features(ctx.content.spec)}
    if state["position"] == F.LESSON and step:
        concept = item["concept"] if item else ctx.content.target
        walk = ctx.content.walkthrough(concept) if step.get("walkthrough") and ctx.content.tool("walkthrough") else None
        walk = safe_walkthrough(state, ctx.content, walk)
        text = step.get("text") or ""
        if lesson_leak(ctx.content, text, item["id"] if item else None):
            text = "ลองย้อนดูวิธีคิดของข้อนี้อีกครั้งทีละขั้น แล้วกลับไปลองใหม่นะ"
        extras["lesson"] = {"title": step.get("title") or label(step), "text": text, "walkthrough": walk}
    if state["position"] == F.REFLECT and step:
        extras["reflect"] = {"question": step.get("question") or "อธิบายว่าคิดอย่างไร"}
    if state["position"] == F.ACTIVITY and step:
        activity = fs(state).get("activity") or {}
        extras["activity"] = {"title": step.get("title") or label(step), "status": activity.get("status", "pending"),
                              "text": activity.get("text"), "question": activity.get("question"),
                              "response": step.get("response", "none")}
    if state["position"] == F.WIDGET and step:
        kind = step["widget"]
        extras["widget"] = {"type": kind, "title": step.get("title") or label(step), "prompt": step.get("prompt") or "",
                            "graded": W.WIDGETS[kind]["graded"], "tries": (fs(state).get("widget") or {}).get("tries", 0),
                            "data": W.public(kind, step["config"], f"{step['id']}:{fs(state)['visits'].get(step['id'], 0)}")}
    if state["position"] == F.CB and (fs(state).get("pending") or {}).get("kind") == "break" and step:
        extras["break_text"] = step.get("text")
    return extras


def staff_extras(state: dict, ctx: C.Ctx) -> dict:
    step = flow_step(state, ctx)
    # map_node ของหน้าเว็บคือกล่องที่ชิปอยู่ (chip_node) ส่วนสิ่งที่ทำอยู่ในขั้นนั้น services เติมเป็น where
    return {"flow_step": {"id": step["id"], "label": label(step), "kind": step["kind"]} if step else None,
            "map_node": chip_node(state, ctx), "chat_thinking": chat_thinking(state, ctx)}
