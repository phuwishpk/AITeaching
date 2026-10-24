"""ชั้น service: เชื่อม engine กับฐานข้อมูล AI Tutor และ WebSocket

ทุกเหตุการณ์ของนักเรียนวิ่งผ่าน run_event: โหลด state → ให้ engine ตัดสิน → บันทึกผล
→ ส่งต่อให้หน้าครูและ Admin แบบสด → ขอข้อความคำใบ้จาก AI Tutor เบื้องหลัง
"""

import asyncio
import time

from . import analytics, db, settings_store
from .engine import core as engine
from .engine import flow as F
from .engine.answers import answer_display
from .engine.core import Content, Ctx, Fx
from .hub import hub
from .tutor import distress, pii
from .tutor import service as tutor

_locks: dict[str, asyncio.Lock] = {}
_content: dict[tuple[str, str], Content] = {}

DISTRESS_REPLY = {
    "self_harm": (
        "ขอบคุณที่บอกนะ ครูได้รับแจ้งแล้วและกำลังมาคุยด้วย ถ้าอยากคุยกับผู้เชี่ยวชาญตอนนี้เลย "
        "โทรสายด่วนสุขภาพจิต 1323 ได้ตลอด 24 ชั่วโมง"
    ),
    "quit": "เข้าใจนะ บางวันก็เหนื่อย ลองเลือกดูว่าอยากไปต่อแบบไหน",
    "stress": "พักสายตาสักครู่กันนะ เดี๋ยวค่อยกลับมาลองด้วยกันใหม่",
}


class NotFound(Exception):
    pass


def lock(code: str) -> asyncio.Lock:
    return _locks.setdefault(code, asyncio.Lock())


def invalidate_content():
    _content.clear()


def find_set(set_id: str) -> tuple[dict, dict]:
    for subject in db.list_subjects():
        for qs in subject.get("question_sets", []):
            if qs["id"] == set_id:
                return subject, qs
    raise NotFound(f"ไม่พบชุดคำถาม {set_id}")


def content_for(subject_id: str, set_id: str) -> Content:
    key = (subject_id, set_id)
    if key not in _content:
        subject = db.get_subject(subject_id)
        if not subject:
            raise NotFound(f"ไม่พบวิชา {subject_id}")
        _content[key] = Content(subject, set_id)
    return _content[key]


def make_ctx(content: Content, now: float | None = None, time_scale: float | None = None) -> Ctx:
    return Ctx(
        content=content,
        params=settings_store.params(),
        time_scale=settings_store.time_scale() if time_scale is None else time_scale,
        now=time.time() if now is None else now,
    )


def student_kind(code: str) -> str:
    row = db.query_one("SELECT kind FROM students WHERE code = ?", (code,))
    return row["kind"] if row else "real"


def new_session(code: str, set_id: str, now: float) -> int:
    return db.execute(
        "INSERT INTO sessions (code, set_id, started_at) VALUES (?, ?, ?)", (code, set_id, now)
    ).lastrowid


def roster_names() -> list[str]:
    return [r["name"] for r in db.query("SELECT name FROM roster")]


# ---------------------------------------------------------------- บันทึกและส่งต่อ

def persist(state: dict, fx: Fx, now: float | None = None) -> list[dict]:
    code = state["code"]
    now = now or time.time()
    if fx.decisions:
        db.executemany(
            "INSERT INTO decisions (ts, code, set_id, from_pos, to_pos, edges, rule, detail) VALUES (?,?,?,?,?,?,?,?)",
            [(d["ts"], code, state["set_id"], d["from"], d["to"], db.dumps(d["edges"]), d["rule"], db.dumps(d["detail"]))
             for d in fx.decisions],
        )
    if fx.traces:
        db.executemany(
            "INSERT INTO traces (ts, code, action, target, data) VALUES (?,?,?,?,?)",
            [(t["ts"] or now, code, t["action"], t["target"], db.dumps(t["data"])) for t in fx.traces],
        )
    alerts = []
    for a in fx.alerts:
        cursor = db.execute(
            "INSERT INTO alerts (ts, code, level, kind, message) VALUES (?,?,?,?,?)",
            (now, code, a["level"], a["kind"], a["message"]),
        )
        alerts.append({**a, "id": cursor.lastrowid, "code": code, "ts": now, "acknowledged": 0})
    if fx.session_end:
        db.execute(
            "UPDATE sessions SET ended_at = ?, end_reason = ?, items = ? WHERE id = ?",
            (now, fx.session_end, state["items_count"], state["session_id"]),
        )
    db.save_state(state)
    return alerts


def staff_payload(state: dict, content: Content, ctx: Ctx) -> dict:
    view = engine.staff_view(state, ctx)
    view["risk"] = analytics.risk_for(state)
    view["kind"] = student_kind(state["code"])
    view["subject_id"] = state["subject_id"]
    view["set_name"] = content.qs["name"]
    view["target"] = content.target
    view["item_concept_name"] = content.concept_name(view["item"]["concept"]) if view.get("item") else None
    if state.get("remedial"):
        view["remedial_concept_name"] = content.concept_name(state["remedial"]["concept"])
    return view


async def broadcast(state: dict, content: Content, ctx: Ctx, fx: Fx, alerts: list[dict]):
    await hub.to_staff({
        "type": "update",
        "code": state["code"],
        "view": staff_payload(state, content, ctx),
        "decisions": fx.decisions,
        "alerts": alerts,
    })
    await hub.to_student(state["code"], {"type": "state", "view": engine.student_view(state, ctx)})


def _student_vars(state: dict) -> dict:
    item = state.get("item") or {}
    attempts = [a for a in item.get("attempts", []) if a["kind"] in ("wrong", "correct")]
    last = attempts[-1] if attempts else {}
    return {
        "error_count": item.get("error_count", 0),
        "response_time": last.get("rt", 0) or 0,
        "diagnosis": last.get("diagnosis") or {},
    }


def plan_hints(state: dict, content: Content, fx: Fx, use_ai: bool) -> list:
    """ใส่คำใบ้ต้นฉบับทันทีถ้า Offline หรือเป็นนักเรียนจำลอง ไม่อย่างนั้นสร้างงานให้ AI Tutor"""
    jobs = []
    item_state = state.get("item")
    for request in fx.hint_requests:
        if not item_state or item_state["id"] != request["item_id"]:
            continue
        it = content.item(request["item_id"])
        level = request["level"]
        authored = it.get("hints", {}).get(str(level)) or tutor.LEVEL_FALLBACK[level]
        if not use_ai:
            item_state["hints"][str(level)] = {"text": authored, "source": "authored", "status": "ready"}
            continue
        item_state["hints"][str(level)] = {"status": "pending"}
        jobs.append(
            fill_hint(state["code"], state["set_id"], content, it, level, _student_vars(state),
                      content.tag(item_state.get("last_tag")))
        )
    return jobs


def ai_enabled_for(code: str) -> bool:
    return settings_store.ai_settings()["active"] != "offline" and student_kind(code) == "real"


async def fill_hint(code: str, set_id: str, content: Content, it: dict, level: int, student: dict, tag: dict | None):
    result = await tutor.generate_hint(content.subject, it, content.concept_name(it["concept"]), level, student, tag, code)
    async with lock(code):
        state = db.load_state(code, set_id)
        if state and state.get("item") and state["item"]["id"] == it["id"]:
            state["item"]["hints"][str(level)] = {
                "text": result["text"], "source": result["source"], "status": "ready", "log_id": result["log_id"],
            }
            db.save_state(state)
            ctx = make_ctx(content)
            await hub.to_student(code, {"type": "state", "view": engine.student_view(state, ctx)})
    await hub.to_staff({"type": "ai_log", "code": code, "log_id": result["log_id"]})


async def suggest_tags(code: str, content: Content, requests: list[dict]):
    for request in requests:
        it = content.item(request["item_id"])
        suggestion = await tutor.suggest_tag(content.subject, it, request["answer"], code)
        if not suggestion:
            continue
        cursor = db.execute(
            "INSERT INTO suggested_tags (ts, code, item_id, answer, tag, rationale) VALUES (?,?,?,?,?,?)",
            (time.time(), code, it["id"], request["answer"], suggestion["tag"], suggestion["reason"]),
        )
        await hub.to_staff({"type": "suggested_tag", "id": cursor.lastrowid, "code": code})


async def run_event(code: str, set_id: str, action, *args) -> tuple[dict, Content, Ctx, Fx]:
    async with lock(code):
        state = db.load_state(code, set_id)
        if not state:
            raise NotFound("ยังไม่ได้เริ่มชุดคำถามนี้")
        content = content_for(state["subject_id"], set_id)
        ctx = make_ctx(content)
        fx = action(state, ctx, *args)
        use_ai = ai_enabled_for(code)
        jobs = plan_hints(state, content, fx, use_ai)
        alerts = persist(state, fx, ctx.now)
    await broadcast(state, content, ctx, fx, alerts)
    for job in jobs:
        asyncio.create_task(job)
    if fx.tag_requests and use_ai:
        asyncio.create_task(suggest_tags(code, content, fx.tag_requests))
    return state, content, ctx, fx


# ---------------------------------------------------------------- เหตุการณ์ของนักเรียน

async def start(code: str, set_id: str, restart: bool = False) -> dict:
    subject, qs = find_set(set_id)
    content = content_for(subject["id"], set_id)
    fx = Fx()
    async with lock(code):
        now = time.time()
        ctx = make_ctx(content, now)
        state = db.load_state(code, set_id)
        if state is None or restart:
            state = engine.new_state(code, subject["id"], set_id, new_session(code, set_id, now), now)
            fx = engine.begin(state, ctx)
        elif state["ended"] and state["end_reason"] != "completed":
            # จบ Session ไปแล้ว เริ่ม Session ใหม่ต่อจากความคืบหน้าเดิม
            state.update(session_id=new_session(code, set_id, now), items_count=0, idle_count=0,
                         started_at=now, ended=False, end_reason=None, remedial=None, after_walk=None)
            fx = engine.begin(state, ctx)
        else:
            # กลับมาหลังเน็ตหลุดหรือปิดหน้าไป: ทำต่อจากจุดเดิม ไม่บันทึกคะแนนเป็นศูนย์
            engine.resolve_timers(state, ctx, fx)
            fx.trace("resume_session", set_id, {"position": state["position"]}, now)
        jobs = plan_hints(state, content, fx, ai_enabled_for(code))
        alerts = persist(state, fx, now)
    await broadcast(state, content, ctx, fx, alerts)
    for job in jobs:
        asyncio.create_task(job)
    return engine.student_view(state, ctx)


async def get_state(code: str, set_id: str) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, _resolve_only)
    return engine.student_view(state, ctx)


def _resolve_only(state: dict, ctx: Ctx) -> Fx:
    fx = Fx()
    engine.resolve_timers(state, ctx, fx)
    return fx


async def submit(code: str, set_id: str, answer) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, engine.submit, answer)
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def hint(code: str, set_id: str) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, engine.request_hint)
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def simple(code: str, set_id: str, action, *args) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, action, *args)
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def chat(code: str, set_id: str, message: str) -> dict:
    message = (message or "").strip()[:600]
    scrubbed, found = pii.scrub(message, roster_names())
    detected = distress.detect(message)
    await post_message(code, set_id, "student", scrubbed)
    if detected["level"]:
        state, content, ctx, fx = await run_event(
            code, set_id, lambda s, c: _distress_with_trace(s, c, detected, scrubbed, found)
        )
        await post_message(code, set_id, "system", DISTRESS_REPLY[detected["level"]])
        return {"reply": DISTRESS_REPLY[detected["level"]], "source": "safety", "distress": detected["level"],
                "view": engine.student_view(state, ctx)}

    paused = db.load_state(code, set_id)
    if paused and paused["position"] not in F.CAN_ANSWER:
        # ระบบหยุดรอครูหรือนักเรียนกำลังพัก: ข้อความส่งถึงครูโดยตรง AI ไม่ตอบ
        content = content_for(paused["subject_id"], set_id)
        return {"reply": None, "to_teacher": True, "view": engine.student_view(paused, make_ctx(content))}

    async with lock(code):
        state = db.load_state(code, set_id)
        if not state:
            raise NotFound("ยังไม่ได้เริ่มชุดคำถามนี้")
        content = content_for(state["subject_id"], set_id)
        ctx = make_ctx(content)
        fx = Fx()
        fx.trace("chat", state["item"]["id"] if state.get("item") else None,
                 {"message": scrubbed, "pii_removed": found}, ctx.now)
        fallback = engine.next_socratic(state, ctx) if state.get("item") else "ตอนนี้ยังไม่มีโจทย์ ลองเริ่มชุดคำถามก่อนนะ"
        item_state = state.get("item")
        it = content.item(item_state["id"]) if item_state else None
        hints_shown = [
            (item_state["hints"].get(str(l)) or {}).get("text") or ""
            for l in range(1, (item_state or {}).get("hint_level", 0) + 1)
        ] if item_state else []
        tag = content.tag(item_state.get("last_tag")) if item_state else None
        student = _student_vars(state)
        persist(state, fx, ctx.now)
    if ai_enabled_for(code):
        reply = await tutor.chat_reply(content.subject, it, content.concept_name(it["concept"]) if it else "",
                                       student, scrubbed, tag, [h for h in hints_shown if h], fallback, code)
    else:
        reply = {"text": fallback, "source": "authored"}
    if reply.get("trigger"):
        state, content, ctx, fx = await run_event(
            code, set_id, lambda s, c: engine.on_distress(s, c, "stress", "llm")
        )
        await post_message(code, set_id, "system", DISTRESS_REPLY["stress"])
        return {"reply": DISTRESS_REPLY["stress"], "source": "safety", "distress": "stress",
                "view": engine.student_view(state, ctx)}
    if chat_mode(code) == "teacher":
        # ครูอยู่ในแชต: คำตอบของ AI เป็นแค่ร่างให้ครูตรวจ แก้ หรือทิ้ง ก่อนถึงนักเรียน (Human-in-the-Loop)
        await post_message(code, set_id, "draft", reply["text"])
        await hub.to_staff({"type": "chat", "code": code, "log_id": reply.get("log_id")})
        return {"reply": None, "to_teacher": True, "view": engine.student_view(state, ctx)}
    await post_message(code, set_id, "tutor", reply["text"])
    await hub.to_staff({"type": "chat", "code": code, "log_id": reply.get("log_id")})
    return {"reply": reply["text"], "source": reply["source"], "view": engine.student_view(state, ctx)}


def _distress_with_trace(state: dict, ctx: Ctx, detected: dict, scrubbed: str, found: list) -> Fx:
    fx = engine.on_distress(state, ctx, detected["level"], "keyword")
    fx.trace("chat", state["item"]["id"] if state.get("item") else None,
             {"message": scrubbed, "pii_removed": found, "distress": detected}, ctx.now)
    return fx


# ---------------------------------------------------------------- ฝั่งครู

async def override(code: str, set_id: str, action: str, params: dict, reason: str, actor: str) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, engine.override, action, params)
    db.execute(
        "INSERT INTO overrides (ts, actor, code, action, reason, detail) VALUES (?,?,?,?,?,?)",
        (time.time(), actor, code, action, reason, db.dumps(params)),
    )
    await hub.to_staff({"type": "override", "code": code, "action": action})
    return staff_payload(state, content, ctx)


def staff_overview() -> list[dict]:
    result = []
    states = analytics.latest_states()
    students = analytics.student_rows()
    for student in students:
        if student["kind"] == "test":
            continue
        state = states.get(student["code"])
        if not state:
            result.append({"code": student["code"], "kind": student["kind"], "persona": student["persona"],
                           "position": None, "teacher_text": "ยังไม่เริ่มเรียน"})
            continue
        try:
            content = content_for(state["subject_id"], state["set_id"])
        except (NotFound, StopIteration):
            continue
        ctx = make_ctx(content)
        view = staff_payload(state, content, ctx)
        view["persona"] = student["persona"]
        view["cluster"] = analytics.cluster_of(student["code"])
        result.append(view)
    return result


def all_positions() -> list[dict]:
    positions = []
    for state in analytics.latest_states().values():
        kind = student_kind(state["code"])
        if kind == "test":
            continue
        positions.append({
            "code": state["code"],
            "kind": kind,
            "set_id": state["set_id"],
            "position": state["position"],
            "path": state["path"],
            "item": state["item"]["id"] if state.get("item") else None,
            "hint_level": state["item"]["hint_level"] if state.get("item") else 0,
            "remedial_round": state["remedial"]["round"] if state.get("remedial") else None,
            "last_edges": (state.get("last_decision") or {}).get("edges", []),
            "last_rule": (state.get("last_decision") or {}).get("rule"),
            "since": state["position_since"],
        })
    return positions


# ---------------------------------------------------------------- โจทย์และคำตอบสำหรับหน้าครูและ Admin

def item_lookup() -> dict[str, dict]:
    """รหัสโจทย์ → โจทย์ จากทุกวิชา (รหัสโจทย์ไม่ซ้ำกันภายในวิชา)"""
    return {it["id"]: it for subject in db.list_subjects() for it in subject.get("items", [])}


def item_brief(it: dict | None) -> dict | None:
    """โจทย์ในรูปที่ครูและ Admin อ่าน: คำสั่ง สมการ ตัวเลือก และคำตอบที่ถูก"""
    if not it:
        return None
    return {
        "id": it["id"], "prompt": it.get("prompt", ""), "math": it.get("math"), "format": it.get("format"),
        "kind": it.get("kind"), "options": [{"id": o["id"], "text": o["text"]} for o in it.get("options", [])],
        "correct": answer_display(it), "correct_option": (it.get("answer") or {}).get("option"),
    }


def answer_sheet(code: str, limit: int = 40) -> dict:
    """โจทย์ที่นักเรียนกำลังทำ และคำตอบที่ส่งมาแต่ละครั้งพร้อมตัวโจทย์"""
    items = item_lookup()
    states = db.states_for(code)
    state = max(states, key=lambda s: s["last_activity"]) if states else None
    current = None
    if state and state.get("item"):
        item = state["item"]
        current = {
            **item_brief(items.get(item["id"])), "mode": item["mode"], "error_count": item["error_count"],
            "hint_level": item["hint_level"],
            "attempts": [{"raw": a.get("raw"), "kind": a["kind"], "rt": a.get("rt")} for a in item["attempts"]],
        }
    answers = []
    for row in db.query("SELECT ts, target, data FROM traces WHERE code = ? AND action IN ('answer', 'invalid_answer') "
                        "ORDER BY ts DESC LIMIT ?", (code, limit)):
        data = db.loads(row["data"], {})
        answers.append({"ts": row["ts"], "item": item_brief(items.get(row["target"])), "raw": data.get("raw"),
                        "correct": data.get("correct"), "rapid": data.get("rapid", False),
                        "invalid": "correct" not in data, "rt": data.get("rt"), "diagnosis": data.get("diagnosis"),
                        "isomorphic": data.get("isomorphic", False)})
    return {"current": current, "answers": answers, "position": state["position"] if state else None}


# ---------------------------------------------------------------- ข้อความระหว่างนักเรียน AI Tutor และครู

async def post_message(code: str, set_id: str | None, sender: str, text: str) -> dict:
    """บันทึกข้อความหนึ่งรายการ แล้วส่งให้ครูแบบสด ข้อความจากครูส่งถึงนักเรียนด้วย
    sender: student (ลบข้อมูลส่วนตัวแล้ว) · tutor (AI Tutor หรือคำถามนำต้นฉบับ) · system (ข้อความดูแลความปลอดภัย) · teacher"""
    now = time.time()
    cursor = db.execute("INSERT INTO messages (ts, code, set_id, sender, text) VALUES (?,?,?,?,?)",
                        (now, code, set_id, sender, text))
    row = {"id": cursor.lastrowid, "ts": now, "code": code, "set_id": set_id, "sender": sender, "text": text}
    await hub.to_staff({"type": "message", "code": code, "message": row})
    if sender == "teacher":
        await hub.to_student(code, {"type": "message", "message": row})
    return row


def messages_for(code: str, limit: int = 80, include_drafts: bool = False) -> list[dict]:
    """บทสนทนาของนักเรียนหนึ่งคน ร่างคำตอบของ AI เห็นได้เฉพาะครู"""
    hide = "" if include_drafts else "AND sender != 'draft'"
    rows = db.query(f"SELECT * FROM messages WHERE code = ? {hide} ORDER BY ts DESC, id DESC LIMIT ?", (code, limit))
    return list(reversed(rows))


def chat_mode(code: str) -> str:
    """ai = AI Tutor ตอบเอง · teacher = ครูเข้าร่วมแชต AI ร่างคำตอบให้ครูตรวจก่อน"""
    row = db.query_one("SELECT mode FROM chat_modes WHERE code = ?", (code,))
    return row["mode"] if row else "ai"


async def set_chat_mode(code: str, mode: str) -> dict:
    db.execute("INSERT OR REPLACE INTO chat_modes (code, mode, since) VALUES (?,?,?)", (code, mode, time.time()))
    states = db.states_for(code)
    set_id = max(states, key=lambda s: s["last_activity"])["set_id"] if states else None
    text = ("ครูเข้ามาในแชตแล้ว ถามครูได้เลย" if mode == "teacher"
            else "ครูออกจากแชตแล้ว ครูผู้ช่วย (AI) จะตอบต่อ ครูยังอ่านข้อความได้เสมอ")
    message = await post_message(code, set_id, "system", text)
    await hub.to_student(code, {"type": "message", "message": message})
    await hub.to_student(code, {"type": "chat_mode", "mode": mode})
    return {"mode": mode}


async def send_draft(draft_id: int, text: str | None) -> dict:
    """ครูส่งร่างของ AI ตามเดิมหรือแก้แล้ว ข้อความที่ส่งเป็นของครู (ครูรับผิดชอบเนื้อหา)"""
    draft = db.query_one("SELECT * FROM messages WHERE id = ? AND sender = 'draft'", (draft_id,))
    if not draft:
        raise NotFound("ไม่พบร่างนี้ อาจถูกส่งหรือลบไปแล้ว")
    db.execute("DELETE FROM messages WHERE id = ?", (draft_id,))
    return await post_message(draft["code"], draft["set_id"], "teacher", (text or draft["text"]).strip())


def inbox() -> list[dict]:
    """ทุกคนที่มีบทสนทนา พร้อมข้อความล่าสุด จำนวนร่างที่รอครู และโหมดแชต"""
    rows = db.query(
        "SELECT m.* FROM messages m JOIN (SELECT code, MAX(id) AS id FROM messages WHERE sender != 'draft' GROUP BY code) "
        "latest ON latest.id = m.id ORDER BY m.ts DESC"
    )
    drafts = {r["code"]: r["n"] for r in db.query(
        "SELECT code, COUNT(*) AS n FROM messages WHERE sender = 'draft' GROUP BY code")}
    modes = {r["code"]: r["mode"] for r in db.query("SELECT code, mode FROM chat_modes")}
    return [{"code": r["code"], "last": r, "drafts": drafts.get(r["code"], 0), "mode": modes.get(r["code"], "ai")}
            for r in rows]
