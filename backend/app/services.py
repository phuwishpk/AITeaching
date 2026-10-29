"""ชั้น service: เชื่อม engine กับฐานข้อมูล AI Tutor และ WebSocket

ทุกเหตุการณ์ของนักเรียนวิ่งผ่าน run_event: โหลด state → ให้ engine ตัดสิน → บันทึกผล
→ ส่งต่อให้หน้าครูและ Admin แบบสด → ขอข้อความคำใบ้จาก AI Tutor เบื้องหลัง
"""

import asyncio
import re
import time

from . import analytics, db, scope, settings_store
from .gems import alerts as gem_alerts
from .gems import builder as gem_builder
from .engine import core as engine
from .engine import flow as F
from .engine import gemflow
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


CHAT_MEMORY = 12


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
        # Flagged Item ของ Gem ไม่ถูกส่งให้นักเรียนจนกว่าครูยืนยัน (ADR-0003)
        _content[key] = Content(gem_builder.usable(subject), set_id)
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

# ขอคุยกับครูจริง ๆ ไม่นับการเรียกครูอย่างสุภาพ เช่น "ครูครับ"
ASK_TEACHER = re.compile(r"(ขอ|อยาก)(คุย|ถาม|ปรึกษา)(กับ)?ครู|เรียกครู|ครูช่วย(หน่อย|ด้วย)")


async def live_generate(code: str, set_id: str, subject_id: str, request: dict):
    """สร้างโจทย์สดให้นักเรียนที่คลังหมด แล้วพากลับไปทำต่อ หรือหยุดชั่วคราวถ้า AI ขัดข้อง"""
    try:
        new_ids, error = await gem_builder.generate_live(subject_id, request), None
    except gem_builder.BuildError as failure:
        new_ids, error = [], str(failure)
    invalidate_content()
    try:
        await run_event(code, set_id, engine.after_live, new_ids, error)
    except NotFound:
        pass


def ai_failed(result: dict) -> bool:
    """AI ถูกเรียกแต่ไม่สำเร็จทุก Provider (ไม่นับ Offline Mode ที่ตั้งใจปิด AI)
    AI ตอบได้แต่ Answer-Leak Guard บล็อก ไม่ใช่การขัดข้อง (เคยแสดงว่า "ตอบไม่ได้ชั่วคราว" ผิด เพราะ errors
    มีบรรทัดของ Provider ที่ถูกข้ามติดมา เช่น claude ที่ไม่ได้ใส่ key)"""
    errors = result.get("errors") or []
    if (result.get("guard") or {}).get("blocked"):
        return False
    return result.get("source") == "authored" and bool(errors) and errors != ["Offline Mode"]


def failure_reason(errors: list[str]) -> str:
    """สาเหตุที่อ่านแล้วตรง: ข้าม Provider ที่ไม่ได้ใส่ key (ถูกข้ามตามปกติ) ใช้ error ของตัวที่ลองจริง"""
    real = [e for e in errors if "ยังไม่ได้ใส่ API key" not in e] or errors
    return real[-1].split(": ", 1)[-1] if real else "ไม่ทราบสาเหตุ"


async def raise_alert(code: str, set_id: str, kind: str, message: str, level: str = "normal", dedupe: bool = True):
    """แจ้งเตือนที่เกิดนอก engine (แชต AI) ผ่านเส้นทางเดียวกับ engine จึงใช้ Alert Rule ของ Gem เหมือนกัน"""
    def make(state: dict, ctx: Ctx) -> Fx:
        fx = Fx()
        engine.alert(fx, state, level, kind, message, dedupe=dedupe)
        return fx

    try:
        await run_event(code, set_id, make)
    except NotFound:
        pass


def _place(state: dict) -> dict:
    """ชิปของนักเรียนบนผังของ Gem: กล่องที่อยู่ AI กำลังคิดคำตอบแชตไหม และอยู่ส่วนไหนของขั้น"""
    try:
        content = content_for(state["subject_id"], state["set_id"])
    except (NotFound, StopIteration):
        return {"step": None, "thinking": False, "where": None}
    if not content.spec:
        return {"step": None, "thinking": False, "where": None}
    ctx = make_ctx(content)
    return {"step": gemflow.chip_node(state, ctx), "thinking": gemflow.chat_thinking(state, ctx),
            "where": _where(state, content, ctx)}


def _where(state: dict, content: Content, ctx: Ctx) -> dict:
    """นักเรียนอยู่ส่วนไหนของขั้นใน Flow ของ Gem พร้อมพรีวิวว่าถ้าตอบถูกหรือผิดตอนนี้จะไปเส้นไหน"""
    from . import demo  # demo import services จึง import ตอนเรียก

    info = gemflow.where(state, ctx)
    item = state.get("item")
    if item and not state["ended"]:
        try:
            it = content.item(item["id"])
            info["next"] = gemflow.preview(state, ctx, {"correct": demo.correct_raw(it), "wrong": demo.other_wrong(it)})
        except Exception:  # noqa: BLE001 พรีวิวใช้แสดงผลอย่างเดียว พังแล้วต้องไม่ทำให้การอัปเดตสดของครูหยุด
            info["next"] = None
    return info


def _gem_of(state: dict) -> dict | None:
    try:
        return content_for(state["subject_id"], state["set_id"]).subject.get("gem")
    except (NotFound, StopIteration):
        return None


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
    # นักเรียนทดสอบ (พรีวิวของครูในหน้าสร้าง Gem) ไม่ส่งแจ้งเตือนถึงครู
    gem = _gem_of(state) if fx.alerts else None
    for a in fx.alerts if student_kind(code) != "test" else []:
        # Alert Rule ของ Gem: ครูปิดสถานการณ์นี้ไว้ หรือเปลี่ยนระดับ หรือให้หยุดรอครู
        rule = gem_alerts.resolve(gem, a["kind"])
        if rule is None:
            continue
        level = a["level"] if a.pop("own_level", False) else rule["level"]
        a = {**a, "level": level, "pause": rule["mode"] == "pause"}
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
    if content.spec:
        view["where"] = _where(state, content, ctx)
    if state.get("remedial"):
        view["remedial_concept_name"] = content.concept_name(state["remedial"]["concept"])
    return view


async def broadcast(state: dict, content: Content, ctx: Ctx, fx: Fx, alerts: list[dict]):
    if student_kind(state["code"]) == "test":
        await hub.to_student(state["code"], {"type": "state", "view": engine.student_view(state, ctx)})
        return
    if any(a.get("pause") for a in alerts) and chat_mode(state["code"]) != "teacher":
        # Alert Rule แบบ "หยุดรอครู": คำตอบของ AI กลายเป็นร่างรอครูอนุมัติก่อนถึงนักเรียน
        await set_chat_mode(state["code"], "teacher", PAUSE_TEXT)
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
        authored = tutor.authored_hint(it, level, item_state.get("last_tag"))
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
    # นักเรียนทดสอบในพรีวิวของ Gem ใช้ AI จริง ครูจะได้เห็น prompt ที่ส่งไปจริง
    return settings_store.ai_settings()["active"] != "offline" and student_kind(code) in ("real", "test")


async def fill_hint(code: str, set_id: str, content: Content, it: dict, level: int, student: dict, tag: dict | None):
    result = await tutor.generate_hint(content.subject, it, content.concept_name(it["concept"]), level, student, tag, code)
    if ai_failed(result):
        # เกลาคำใบ้ไม่สำเร็จ นักเรียนได้คำใบ้ต้นฉบับอยู่แล้ว แค่แจ้งครู
        await raise_alert(code, set_id, "ai_outage", f"AI ขัดข้องตอนเขียนคำใบ้ ใช้คำใบ้ต้นฉบับแทน: {'; '.join(result['errors'])}")
    elif (result.get("guard") or {}).get("blocked") and not result.get("trigger"):
        await raise_alert(code, set_id, "guard_blocked", f"Answer-Leak Guard บล็อกคำใบ้ระดับ {level} ของ AI ใช้คำใบ้ต้นฉบับแทน")
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


async def fill_activity(code: str, set_id: str, step_id: str):
    """เนื้อหาของขั้น "กิจกรรม" ใน Flow ของ Gem: AI สร้างตามเป้าหมาย ไม่สำเร็จใช้ข้อความสำรองและแจ้งครู"""
    state = db.load_state(code, set_id)
    if not state:
        return
    content = content_for(state["subject_id"], set_id)
    step = content.steps.get(step_id) or {}
    item_state = state.get("item")
    it = content.item(item_state["id"]) if item_state else None
    result = None
    if ai_enabled_for(code):
        result = await tutor.make_activity(content.subject, step, it, content.concept_name(it["concept"]) if it else "",
                                           _student_vars(state), content.tag((item_state or {}).get("last_tag")), code)
        # เอกสารของครูอาจมีโจทย์ในคลังพร้อมเฉลย ตรวจซ้ำกับข้อที่นักเรียนยังทำไม่ได้
        if result and gemflow.leaked_item(f"{result['text']} {result['question']}",
                                          [i for i in content.items.values() if i["id"] not in state["done_items"]],
                                          it["id"] if it else None):
            result = None
        if result is None:
            await raise_alert(code, set_id, "ai_outage", f"AI สร้างกิจกรรม \"{step.get('label', step_id)}\" ไม่สำเร็จ ใช้กิจกรรมสำรอง")
    asks = step.get("response") == "text"
    text = result["text"] if result else (
        f"{step.get('title') or step.get('label', '')}: ลองทบทวนวิธีคิดของข้อที่เพิ่งทำทีละขั้น ว่าแต่ละขั้นทำเพราะอะไร")
    question = result["question"] if result else ("สรุปสั้น ๆ ว่าข้อนี้ต้องคิดอย่างไร" if asks else "")
    async with lock(code):
        state = db.load_state(code, set_id)
        if state and gemflow.set_activity(state, step_id, text, question, "ready" if result else "fallback"):
            db.save_state(state)
            await hub.to_student(code, {"type": "state", "view": engine.student_view(state, make_ctx(content))})


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


def has_flow(subject: dict) -> bool:
    """Gem เรียนได้เมื่อมี Flow ที่ออกแบบจาก prompt ของครู (ผังมาตรฐานเป็นแค่แม่แบบอ้างอิง ไม่ใช้แทน)
    ชุดคำถามที่ไม่ใช่ Gem ใช้ engine เดิม"""
    gem = subject.get("gem")
    return not gem or (gem.get("flow") or {}).get("mode") == "custom"


def bill_to_gem_owner(subject: dict | None) -> None:
    """งาน AI ระหว่างนักเรียนเรียน (คำใบ้ แชต ประเมินคำอธิบาย สร้างโจทย์สด) คิดกับ API key ของเจ้าของ Gem"""
    gem_id = ((subject or {}).get("gem") or {}).get("id")
    gem = db.get_gem(gem_id) if gem_id else None
    if gem and gem.get("owner"):
        settings_store.use_keys_of(gem["owner"])


async def run_event(code: str, set_id: str, action, *args) -> tuple[dict, Content, Ctx, Fx]:
    async with lock(code):
        state = db.load_state(code, set_id)
        if not state:
            raise NotFound("ยังไม่ได้เริ่มชุดคำถามนี้")
        content = content_for(state["subject_id"], set_id)
        bill_to_gem_owner(content.subject)
        ctx = make_ctx(content)
        fx = action(state, ctx, *args)
        for request in fx.tag_requests:
            engine.alert(fx, state, "silent", "new_misconception",
                         f"คำตอบผิดแบบใหม่ที่ยังไม่อยู่ใน Bug Library: ข้อ {request['item_id']} ตอบ {request['answer']}")
        use_ai = ai_enabled_for(code)
        jobs = plan_hints(state, content, fx, use_ai)
        alerts = persist(state, fx, ctx.now)
    await broadcast(state, content, ctx, fx, alerts)
    for job in jobs:
        asyncio.create_task(job)
    if fx.generate:
        asyncio.create_task(live_generate(code, set_id, state["subject_id"], fx.generate))
    if fx.activity:
        asyncio.create_task(fill_activity(code, set_id, fx.activity["step"]))
    if fx.tag_requests and use_ai:
        asyncio.create_task(suggest_tags(code, content, fx.tag_requests))
    return state, content, ctx, fx


# ---------------------------------------------------------------- เหตุการณ์ของนักเรียน

async def start(code: str, set_id: str, restart: bool = False) -> dict:
    subject, qs = find_set(set_id)
    if not scope.may_learn(code, subject):
        raise NotFound("ไม่พบชุดคำถามนี้")  # Gem ของครูคนอื่น
    if not has_flow(subject):
        raise NotFound("บทเรียนนี้ยังไม่มี Flow การสอน ครูต้องให้ AI ออกแบบ Flow จากคำสั่งก่อน")
    bill_to_gem_owner(subject)
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


def on_screen(action):
    """การกระทำบนจอหลักของนักเรียน: ถ้าชิปบนผังของ Gem อยู่ที่กล่องแชต ให้กลับขั้นที่ทำอยู่ก่อน แล้วจึงทำการกระทำนั้น"""
    def run(state: dict, ctx: Ctx, *args) -> Fx:
        back = engine.leave_chat(state, ctx)
        fx = action(state, ctx, *args)
        fx.decisions[:0] = back.decisions
        return fx
    return run


async def submit(code: str, set_id: str, answer) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, on_screen(engine.submit), answer)
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def hint(code: str, set_id: str) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, on_screen(engine.request_hint))
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def simple(code: str, set_id: str, action, *args) -> dict:
    state, content, ctx, fx = await run_event(code, set_id, action, *args)
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def chat(code: str, set_id: str, message: str) -> dict:
    message = (message or "").strip()[:600]
    try:
        bill_to_gem_owner(find_set(set_id)[0])
    except NotFound:
        pass
    scrubbed, found = pii.scrub(message, roster_names())
    detected = distress.detect(message)
    await post_message(code, set_id, "student", scrubbed)
    if ASK_TEACHER.search(message):
        # นักเรียนขอคุยกับครู: แจ้งครูตาม Alert Rule (ค่าเริ่มต้นคือหยุดรอครู คำตอบ AI เป็นร่างให้ครูตรวจ)
        await raise_alert(code, set_id, "ask_teacher", f"นักเรียนขอคุยกับครู: \"{scrubbed[:80]}\"", dedupe=False)
    if detected["level"]:
        state, content, ctx, fx = await run_event(
            code, set_id, lambda s, c: _distress_with_trace(s, c, detected, scrubbed, found)
        )
        await post_message(code, set_id, "system", DISTRESS_REPLY[detected["level"]])
        return {"reply": DISTRESS_REPLY[detected["level"]], "source": "safety", "distress": detected["level"],
                "view": engine.student_view(state, ctx)}

    paused = db.load_state(code, set_id)
    if paused and paused["position"] not in F.CAN_ANSWER | {F.LESSON, F.REFLECT, F.ACTIVITY, F.WIDGET} and (
            paused["position"] == F.SAFETY or teacher_watching(code)):
        # ระบบหยุดรอครูหรือนักเรียนกำลังพัก และครูเปิดแชตนี้อยู่: ข้อความส่งถึงครูโดยตรง AI ไม่ตอบ
        # หยุดเพราะข้อความทำร้ายตนเอง ครูดูแลคนเดียวเสมอ (ล็อกไว้) ที่เหลือถ้าครูไม่อยู่ AI ช่วยตอบเรื่องบทเรียนไปก่อน
        content = content_for(paused["subject_id"], set_id)
        return {"reply": None, "to_teacher": True, "view": engine.student_view(paused, make_ctx(content))}

    async with lock(code):
        state = db.load_state(code, set_id)
        if not state:
            raise NotFound("ยังไม่ได้เริ่มชุดคำถามนี้")
        content = content_for(state["subject_id"], set_id)
        ctx = make_ctx(content)
        # ชิปบนผังของ Gem ย้ายไปกล่องแชตและขึ้นว่า AI กำลังคิด จนกว่านักเรียนจะกลับมาทำบนจอหลัก
        fx = engine.chat_open(state, ctx)
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
        alerts = persist(state, fx, ctx.now)
    await broadcast(state, content, ctx, fx, alerts)
    # แนวทางการตอบแชตที่ครูกำหนดใน Flow (ไม่มี = แบบอัตโนมัติ) และสิ่งที่นักเรียนพิมพ์ที่ครูให้รับมือเป็นพิเศษ
    chat_spec = (content.spec or {}).get("chat")
    intent = gemflow.chat_intent(content.spec, scrubbed)
    if intent and intent.get("notify"):
        await raise_alert(code, set_id, "flow_notify", f"แชต ({intent['label']}): \"{scrubbed[:80]}\"", dedupe=False)
    if intent and intent.get("goto"):
        state, content, ctx, _ = await run_event(code, set_id, engine.chat_goto, intent)
    if ai_enabled_for(code):
        history = chat_memory(code, set_id)
        # ข้อความก่อนเริ่มข้อนี้เป็นของโจทย์ข้อก่อน (เจอจาก AI จริง: ทำข้อใหม่แล้วยังพูดถึงตัวเลขของข้อเก่า)
        started = (item_state or {}).get("started_at")
        for message in history:
            message["earlier"] = bool(started) and (message.get("ts") or 0) < started
        reply = await tutor.chat_reply(content.subject, it, content.concept_name(it["concept"]) if it else "",
                                       student, scrubbed, tag, [h for h in hints_shown if h], fallback, code, history,
                                       chat_spec, intent)
    else:
        reply = {"text": fallback, "source": "authored"}
    if content.spec:
        state, content, ctx, _ = await run_event(code, set_id, engine.chat_replied)
    if ai_failed(reply):
        await raise_alert(code, set_id, "ai_outage", f"AI ขัดข้องตอนตอบแชต: {'; '.join(reply['errors'])}")
    teacher_here = chat_mode(code) == "teacher" and teacher_watching(code)
    if ai_failed(reply) and not teacher_here:
        # AI Outage: แชตบอก error ตรง ๆ แต่ทำโจทย์ต่อได้ และแจ้งครูพร้อมข้อความ error (Q22)
        # ถ้าครูอยู่ในแชตแล้ว ครูเป็นคนตอบ นักเรียนไม่ต้องเห็น error
        reason = failure_reason(reply["errors"])
        text = f"ครูผู้ช่วยตอบไม่ได้ชั่วคราว ({reason}) ทำโจทย์ต่อได้เลย ครูได้รับแจ้งแล้ว"
        await post_message(code, set_id, "system", text)
        return {"reply": text, "source": "error", "view": engine.student_view(state, ctx)}
    if reply.get("off_topic"):
        await raise_alert(code, set_id, "off_topic", f"ถามนอกบทเรียน: \"{scrubbed[:80]}\"")
    if (reply.get("guard") or {}).get("blocked") and not reply.get("trigger"):
        await raise_alert(code, set_id, "guard_blocked", "Answer-Leak Guard บล็อกคำตอบแชตของ AI ใช้คำถามนำต้นฉบับแทน")
    if reply.get("trigger"):
        state, content, ctx, fx = await run_event(
            code, set_id, lambda s, c: engine.on_distress(s, c, "stress", "llm")
        )
        await post_message(code, set_id, "system", DISTRESS_REPLY["stress"])
        return {"reply": DISTRESS_REPLY["stress"], "source": "safety", "distress": "stress",
                "view": engine.student_view(state, ctx)}
    # ถามเรื่องโจทย์ในแชตแล้วได้ความช่วยเหลือ นับเป็นการขอคำใบ้ (ถูกหลังถาม = ถูกหลังใช้คำใบ้ Mastery ไม่เต็ม)
    counted = None
    if content.spec and not reply.get("off_topic") and gemflow.is_help(scrubbed):
        state, content, ctx, helped = await run_event(code, set_id, engine.chat_help)
        counted = (helped.result or {}).get("count")
    if teacher_here:
        # ครูอยู่ในแชตและเปิดหน้าแชตนี้อยู่: คำตอบของ AI เป็นแค่ร่างให้ครูตรวจ แก้ หรือทิ้ง ก่อนถึงนักเรียน (Human-in-the-Loop)
        # ครูไม่ได้เปิดหน้าแชต: AI ตอบเองในขอบเขตบทเรียน นักเรียนไม่ต้องรอ ครูอ่านย้อนหลังได้ทุกข้อความ
        await post_message(code, set_id, "draft", reply["text"])
        await hub.to_staff({"type": "chat", "code": code, "log_id": reply.get("log_id")})
        return {"reply": None, "to_teacher": True, "counted_hint": counted, "view": engine.student_view(state, ctx)}
    await post_message(code, set_id, "tutor", reply["text"])
    await hub.to_staff({"type": "chat", "code": code, "log_id": reply.get("log_id")})
    return {"reply": reply["text"], "source": reply["source"], "counted_hint": counted, "view": engine.student_view(state, ctx)}


async def reflect(code: str, set_id: str, text: str) -> dict:
    """ขั้น "อธิบายความคิด" ของ Flow ใน Gem: ถ้าครูสั่งให้ประเมิน AI ตัดสินตามเกณฑ์ของครู แล้วบันทึกให้ครูตรวจ"""
    text = (text or "").strip()[:1000]
    if distress.detect(text)["level"]:
        return await chat(code, set_id, text)
    scrubbed, _ = pii.scrub(text, roster_names())
    state = db.load_state(code, set_id)
    if not state:
        raise NotFound("ยังไม่ได้เริ่มชุดคำถามนี้")
    content = content_for(state["subject_id"], set_id)
    bill_to_gem_owner(content.subject)
    step = gemflow.flow_step(state, make_ctx(content)) if content.spec else None
    verdict = None
    if gemflow.judged(step) and state["position"] in (F.REFLECT, F.ACTIVITY):
        it = content.item(state["item"]["id"]) if state.get("item") else None
        # กิจกรรม: คำถามมาจากที่ AI สร้าง เกณฑ์มาจาก rubric หรือเป้าหมายของกิจกรรม
        judging = {**step, "question": gemflow.question_of(state, step),
                   "rubric": step.get("rubric") or (f"ตอบได้ตามเป้าหมายของกิจกรรม: {step.get('goal')}" if step.get("goal") else "")}
        if ai_enabled_for(code):
            verdict = await tutor.judge_reflection(content.subject, it, judging, scrubbed, code)
        else:
            verdict = {"pass": None, "score": None, "reason": "AI ปิดอยู่ ครูตรวจคำอธิบายเอง"}
        if verdict.get("error"):
            await raise_alert(code, set_id, "ai_outage", f"AI ขัดข้องตอนประเมินคำอธิบาย: {verdict['error']}")
    state, content, ctx, fx = await run_event(code, set_id, on_screen(engine.reflect), scrubbed, verdict)
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


async def widget(code: str, set_id: str, response: dict) -> dict:
    """ขั้น Widget ของ Flow ใน Gem: ตรวจด้วยกฎ (engine/widgets.py) ไม่ใช้ AI"""
    state, content, ctx, fx = await run_event(code, set_id, on_screen(engine.widget), response if isinstance(response, dict) else {})
    return {"result": fx.result, "view": engine.student_view(state, ctx)}


def _distress_with_trace(state: dict, ctx: Ctx, detected: dict, scrubbed: str, found: list) -> Fx:
    # บนผังของ Gem: ขั้นที่ทำอยู่ → แชตกับ AI → กลไกที่ข้อความนั้นพาไป (พักเพราะเครียด เลือกทางต่อ หยุดเพื่อความปลอดภัย)
    opened = engine.chat_open(state, ctx)
    fx = engine.on_distress(state, ctx, detected["level"], "keyword")
    engine.chat_replied(state, ctx)
    fx.decisions[:0] = opened.decisions
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


def staff_overview(owner: str | None = None) -> list[dict]:
    """นักเรียนทุกคนของผู้ใช้ (owner) พร้อมสถานะล่าสุด"""
    result = []
    states = analytics.latest_states(owner)
    students = analytics.student_rows(owner)
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
        view["cluster"] = analytics.cluster_of(student["code"], owner)
        result.append(view)
    return result


def all_positions(owner: str | None = None) -> list[dict]:
    positions = []
    for state in analytics.latest_states(owner).values():
        kind = student_kind(state["code"])
        if kind == "test":
            continue
        place = _place(state)
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
            # Flow ของ Gem: กล่องในผังของ Gem ที่นักเรียนอยู่ (ขั้นของ Flow หรือกลไกที่ล็อกไว้)
            "step": place["step"],
            "thinking": place["thinking"],
            # อยู่ส่วนไหนของขั้น: กำลังทำอะไร ข้อไหน ผิดกี่ครั้ง มาถึงยังไง และถ้าตอบตอนนี้จะไปเส้นไหน
            "where": place["where"],
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
    if student_kind(code) != "test":
        await hub.to_staff({"type": "message", "code": code, "message": row})
    if sender == "teacher":
        await hub.to_student(code, {"type": "message", "message": row})
    return row


def messages_for(code: str, limit: int = 80, include_drafts: bool = False) -> list[dict]:
    """บทสนทนาของนักเรียนหนึ่งคน ร่างคำตอบของ AI เห็นได้เฉพาะครู"""
    hide = "" if include_drafts else "AND sender != 'draft'"
    rows = db.query(f"SELECT * FROM messages WHERE code = ? {hide} ORDER BY ts DESC, id DESC LIMIT ?", (code, limit))
    return list(reversed(rows))


def chat_memory(code: str, set_id: str) -> list[dict]:
    """บทสนทนาล่าสุดใน Gem เดียวกัน (ทุกรุ่นของคลัง) ให้ AI จำได้ ไม่รวมข้อความที่เพิ่งส่ง และไม่ปนแชตของบทเรียนอื่น"""
    gem_prefix = set_id.split("-b")[0] if set_id.startswith("gem-") else set_id
    rows = db.query("SELECT sender, text, set_id, ts FROM messages WHERE code = ? AND sender != 'draft' "
                    "AND (set_id = ? OR set_id LIKE ? OR set_id IS NULL) ORDER BY ts DESC, id DESC LIMIT ?",
                    (code, set_id, f"{gem_prefix}-b%", CHAT_MEMORY + 1))
    return list(reversed(rows))[:-1]


def teacher_history(code: str, before: float | None = None, limit: int = 60, hints: bool = True) -> dict:
    """ประวัติที่นักเรียนคุยกับ AI และกับครู สำหรับหน้าครู ย้อนหลังได้ทีละหน้า (before = เวลาของข้อความเก่าสุดที่เห็นแล้ว)

    รวมคำใบ้ที่ AI ให้นักเรียน (จาก ai_logs) เข้าไปตามเวลา และบอกว่าแต่ละข้อความอยู่ใน Gem หรือชุดคำถามไหน
    ร่างคำตอบของ AI ที่รอครูตรวจอยู่ในหน้าล่าสุดเท่านั้น
    """
    window = "AND ts < ?" if before is not None else ""
    params = (code,) + ((before,) if before is not None else ())
    drafts = "" if before is None else "AND sender != 'draft'"
    rows = db.query(f"SELECT * FROM messages WHERE code = ? {window} {drafts} ORDER BY ts DESC, id DESC LIMIT ?",
                    (*params, limit + 1))
    entries = [{**r, "id": f"m{r['id']}", "draft_id": r["id"] if r["sender"] == "draft" else None} for r in rows]
    if hints:
        logs = db.query(f"SELECT id, ts, purpose, provider, final_text FROM ai_logs WHERE code = ? AND purpose LIKE 'hint_l%' "
                        f"{window} ORDER BY ts DESC LIMIT ?", (*params, limit + 1))
        entries += [{"id": f"h{r['id']}", "ts": r["ts"], "sender": "hint", "text": r["final_text"], "set_id": None,
                     "level": int(r["purpose"][-1]), "authored": r["provider"] == "offline"} for r in logs]
    entries.sort(key=lambda e: e["ts"], reverse=True)
    page = list(reversed(entries[:limit]))
    names: dict[str, str] = {}
    for entry in page:
        set_id = entry.get("set_id")
        if set_id and set_id not in names:
            try:
                names[set_id] = find_set(set_id)[1]["name"]
            except NotFound:
                names[set_id] = set_id
        entry["set_name"] = names.get(set_id)
    return {"messages": page, "has_more": len(entries) > limit}


# ครูที่เปิดหน้าแชตของนักเรียนคนนี้อยู่ (หน้าแชตส่งสัญญาณทุก 20 วินาทีขณะแท็บแสดงอยู่) เก็บในหน่วยความจำ worker เดียว
WATCH_TIMEOUT = 45.0
_watching: dict[str, float] = {}


async def delete_student(code: str) -> None:
    """ลบนักเรียนจริงออกจากระบบถาวร (ครูเจ้าของสั่ง) ผังสดของ Admin เอาชิปออก แล้วล้างสิ่งที่จำไว้ในหน่วยความจำ"""
    owner = scope.student_owner(code)
    # ส่งก่อนลบ: hub หาเจ้าของนักเรียนจากฐานข้อมูล
    await hub.to_staff({"type": "removed", "code": code})
    async with lock(code):
        db.delete_student(code)
    _watching.pop(code, None)
    analytics.forget_clusters(owner)


def mark_watching(code: str) -> None:
    _watching[code] = time.time()


def teacher_watching(code: str) -> bool:
    return time.time() - _watching.get(code, 0.0) < WATCH_TIMEOUT


def chat_mode(code: str) -> str:
    """ai = AI Tutor ตอบเอง · teacher = ครูเข้าร่วมแชต AI ร่างคำตอบให้ครูตรวจก่อน"""
    row = db.query_one("SELECT mode FROM chat_modes WHERE code = ?", (code,))
    return row["mode"] if row else "ai"


PAUSE_TEXT = ("ครูได้รับแจ้งแล้ว ครูจะอ่านและตอบในแชตนี้ ระหว่างที่ครูยังไม่เข้ามา ครูผู้ช่วย (AI) "
              "ช่วยตอบเรื่องบทเรียนไปก่อน ทำโจทย์ต่อได้ตามปกตินะ")


async def set_chat_mode(code: str, mode: str, text: str | None = None) -> dict:
    db.execute("INSERT OR REPLACE INTO chat_modes (code, mode, since) VALUES (?,?,?)", (code, mode, time.time()))
    states = db.states_for(code)
    set_id = max(states, key=lambda s: s["last_activity"])["set_id"] if states else None
    text = text or ("ครูเข้ามาในแชตแล้ว ถามครูได้เลย" if mode == "teacher"
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
    sent = (text or draft["text"]).strip()
    log_teacher(draft["code"], "draft_sent", {"draft": draft["text"], "sent": sent, "edited": sent != draft["text"].strip()})
    return await post_message(draft["code"], draft["set_id"], "teacher", sent)


def log_teacher(code: str, kind: str, detail: dict | None = None) -> None:
    """บันทึกการทำงานของครูต่อนักเรียนหนึ่งคน (เปิดดู ตอบแชต อนุมัติร่าง ฯลฯ) ให้ Admin เห็นในไทม์ไลน์ (Q4)"""
    db.execute("INSERT INTO teacher_actions (ts, code, kind, detail) VALUES (?,?,?,?)",
               (time.time(), code, kind, db.dumps(detail or {})))


def inbox(owner: str | None = None) -> list[dict]:
    """นักเรียนของผู้ใช้ทุกคนที่มีบทสนทนา พร้อมข้อความล่าสุด จำนวนร่างที่รอครู และโหมดแชต"""
    clause, params = scope.where(owner, "m.code")
    rows = db.query(
        "SELECT m.* FROM messages m JOIN (SELECT code, MAX(id) AS id FROM messages WHERE sender != 'draft' GROUP BY code) "
        f"latest ON latest.id = m.id WHERE {clause} ORDER BY m.ts DESC", params
    )
    drafts = {r["code"]: r["n"] for r in db.query(
        "SELECT code, COUNT(*) AS n FROM messages WHERE sender = 'draft' GROUP BY code")}
    modes = {r["code"]: r["mode"] for r in db.query("SELECT code, mode FROM chat_modes")}
    return [{"code": r["code"], "last": r, "drafts": drafts.get(r["code"], 0), "mode": modes.get(r["code"], "ai")}
            for r in rows if student_kind(r["code"]) != "test"]
