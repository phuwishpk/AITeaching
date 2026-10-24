import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import activity, analytics, db, demo, node_info, principles, seed, services, settings_store
from ..config import PARAM_LABELS
from ..engine import core as engine
from ..engine import flow as F
from ..ml import fuzzy
from ..tutor import pii, providers, rag
from ..tutor import service as tutor
from .deps import require

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin = require("admin")


class FuzzyInput(BaseModel):
    system: str
    inputs: dict[str, float]


class Preview(BaseModel):
    item_id: str
    level: int = 1
    tag: str | None = None


class TokenizeBody(BaseModel):
    text: str
    query: str | None = None


class SettingsBody(BaseModel):
    ai: dict | None = None
    params: dict | None = None
    demo: dict | None = None


class SecretBody(BaseModel):
    provider: str
    key: str | None = None


class PinBody(BaseModel):
    role: str
    pin: str


class TickBody(BaseModel):
    students: int = 10


class ScrubBody(BaseModel):
    text: str


def _sample_subject() -> dict:
    subjects = db.list_subjects()
    if not subjects:
        raise HTTPException(404, "ยังไม่มีวิชาในระบบ")
    return next((s for s in subjects if s["id"] == "math-m2"), subjects[0])


# ---------------------------------------------------------------- ผังตรรกะและตำแหน่งนักเรียน (แท็บ 3)

@router.get("/flow")
def flow(auth: dict = Depends(admin)):
    return {
        "nodes": F.NODES,
        "edges": [e for e in F.EDGES if not e.get("hidden")],
        "labels": F.POSITION_LABELS,
        "cards": principles.NODE_CARDS,
        "positions": services.all_positions(),
        "now": time.time(),
    }


@router.get("/flow/nodes/{node_id}")
def flow_node(node_id: str, auth: dict = Depends(admin)):
    """กล่องหนึ่งในผัง: คืออะไร ทำหน้าที่อะไร ใช้ข้อมูลอะไร ปรับค่าอะไรได้ และใครอยู่ตรงนี้"""
    info = node_info.describe(node_id, services.all_positions())
    if info is None:
        raise HTTPException(404, "ไม่พบขั้นนี้ในผัง")
    return info


@router.get("/students")
def students(auth: dict = Depends(admin)):
    rows = db.query("SELECT code, kind, persona FROM students WHERE kind != 'test' ORDER BY kind, code")
    positions = {p["code"]: p for p in services.all_positions()}
    for row in rows:
        row["position"] = positions.get(row["code"], {}).get("position")
    return rows


@router.get("/students/{code}")
def student(code: str, auth: dict = Depends(admin)):
    views = []
    for state in db.states_for(code):
        content = services.content_for(state["subject_id"], state["set_id"])
        ctx = services.make_ctx(content)
        view = services.staff_payload(state, content, ctx)
        view["risk_detail"] = engine.compact_fuzzy(engine.risk_score(state))
        view["concept_names"] = {c: content.concept_name(c) for c in content.concepts}
        view["student_view"] = engine.student_view(state, ctx)
        views.append(view)
    decisions = db.query("SELECT * FROM decisions WHERE code = ? ORDER BY ts DESC, id DESC LIMIT 80", (code,))
    for d in decisions:
        d["edges"] = db.loads(d["edges"], [])
        d["detail"] = db.loads(d["detail"], {})
    traces = db.query("SELECT ts, action, target, data FROM traces WHERE code = ? ORDER BY ts DESC LIMIT 60", (code,))
    for t in traces:
        t["data"] = db.loads(t["data"], {})
    row = db.query_one("SELECT kind, persona FROM students WHERE code = ?", (code,))
    return {
        "code": code,
        "kind": row["kind"] if row else None,
        "persona": row["persona"] if row else None,
        "states": views,
        "decisions": decisions,
        "traces": traces,
        "features": analytics.features(code),
        "cluster": analytics.cluster_of(code),
    }


@router.get("/activity")
def student_activity(code: str | None = None, include_sim: bool = False, limit: int = 40, auth: dict = Depends(admin)):
    """สิ่งที่นักเรียนป้อนเข้ามาแต่ละครั้ง และเส้นทางที่การกระทำนั้นผ่านในผังตรรกะ"""
    return activity.events(code, include_sim, max(1, min(limit, 150)))


@router.get("/students/{code}/answers")
def student_answers(code: str, auth: dict = Depends(admin)):
    """โจทย์ที่กำลังทำ และคำตอบแต่ละครั้งพร้อมตัวโจทย์และคำตอบที่ถูก"""
    return services.answer_sheet(code)


@router.get("/topics")
def topics(auth: dict = Depends(admin)):
    return {"topics": principles.TOPICS, "cards": principles.NODE_CARDS}


@router.get("/knowledge-map")
def knowledge_map(code: str | None = None, auth: dict = Depends(admin)):
    subject = _sample_subject()
    mastery = {}
    if code:
        for state in db.states_for(code):
            content = services.content_for(state["subject_id"], state["set_id"])
            mastery = engine.mastery_map(state, services.make_ctx(content))
    qs = subject["question_sets"][0] if subject.get("question_sets") else {}
    return {
        "subject": {"id": subject["id"], "name": subject["name"]},
        "target": qs.get("target_concept"),
        "concepts": subject["concepts"],
        "mastery": mastery,
        "items": {c["id"]: sum(1 for it in subject["items"] if it["concept"] == c["id"]) for c in subject["concepts"]},
    }


@router.get("/sample")
def sample(auth: dict = Depends(admin)):
    """โจทย์และ Bug Library ของวิชาตัวอย่าง สำหรับเลือกในตัวตรวจ prompt"""
    subject = _sample_subject()
    return {
        "id": subject["id"],
        "name": subject["name"],
        "items": [{k: it.get(k) for k in ("id", "concept", "kind", "format", "prompt", "math")} for it in subject["items"]],
        "bug_tags": subject.get("bug_tags", []),
        "concepts": subject.get("concepts", []),
    }


@router.get("/bug-library")
def bug_library(auth: dict = Depends(admin)):
    return analytics.bug_hits(_sample_subject())


# ---------------------------------------------------------------- AI (แท็บ 4)

@router.get("/fuzzy")
def fuzzy_systems(auth: dict = Depends(admin)):
    return {name: system.describe() for name, system in fuzzy.SYSTEMS.items()}


@router.post("/fuzzy/evaluate")
def fuzzy_evaluate(body: FuzzyInput, auth: dict = Depends(admin)):
    system = fuzzy.SYSTEMS.get(body.system)
    if not system:
        raise HTTPException(404, "ไม่พบระบบนี้")
    return system.evaluate(body.inputs)


@router.get("/clusters")
def clusters(force: bool = False, auth: dict = Depends(admin)):
    return analytics.clusters(force)


@router.get("/ai/logs")
def ai_logs(limit: int = 30, auth: dict = Depends(admin)):
    rows = db.query("SELECT * FROM ai_logs ORDER BY ts DESC LIMIT ?", (min(limit, 200),))
    for row in rows:
        for key in ("frames", "retrieved", "guard"):
            row[key] = db.loads(row[key])
    return rows


@router.get("/ai/stats")
def ai_stats(auth: dict = Depends(admin)):
    rows = db.query(
        "SELECT provider, COUNT(*) AS calls, SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out, "
        "AVG(latency_ms) AS latency FROM ai_logs GROUP BY provider"
    )
    blocked = db.query_one("SELECT COUNT(*) AS n FROM ai_logs WHERE guard LIKE '%\"blocked\":true%'")["n"]
    today = time.time() - 86400
    today_rows = db.query(
        "SELECT provider, SUM(tokens_in + tokens_out) AS tokens FROM ai_logs WHERE ts > ? GROUP BY provider", (today,)
    )
    return {"providers": rows, "guard_blocked": blocked, "today": {r["provider"]: r["tokens"] for r in today_rows}}


@router.post("/ai/preview")
async def ai_preview(body: Preview, auth: dict = Depends(admin)):
    subject = _sample_subject()
    content = services.content_for(subject["id"], subject["question_sets"][0]["id"])
    if body.item_id not in content.items:
        raise HTTPException(404, "ไม่พบโจทย์นี้")
    item = content.item(body.item_id)
    result = await tutor.preview(subject, item, content.concept_name(item["concept"]), max(1, min(3, body.level)),
                                 content.tag(body.tag))
    log = db.query_one("SELECT * FROM ai_logs WHERE id = ?", (result.get("log_id"),))
    if log:
        for key in ("frames", "retrieved", "guard"):
            log[key] = db.loads(log[key])
    return {**result, "log": log}


@router.post("/ai/tokenize")
def tokenize(body: TokenizeBody, auth: dict = Depends(admin)):
    subject = _sample_subject()
    index = rag.get_index(subject["id"])
    query_terms, results = (index.search(body.query, 3) if index and body.query else ([], []))
    return {"tokens": rag.tokenize_demo(body.text), "query_terms": query_terms, "results": results}


# ---------------------------------------------------------------- สาธิตและทดสอบ (แท็บ 5, 6)

@router.get("/scenarios")
def scenarios(auth: dict = Depends(admin)):
    return [{"id": k, "title": v["title"], "description": v["description"], "code": v["code"],
             "steps": len(v["steps"])} for k, v in demo.SCENARIOS.items()]


@router.post("/scenario/{name}")
async def run_scenario(name: str, auth: dict = Depends(admin)):
    if name not in demo.SCENARIOS:
        raise HTTPException(404, "ไม่พบสถานการณ์นี้")
    asyncio.create_task(demo.run_scenario(name))
    return {"started": name, "code": demo.SCENARIOS[name]["code"]}


@router.get("/stress")
def stress_list(auth: dict = Depends(admin)):
    return [{"id": key, "title": fn.__name__} for key, fn in demo.STRESS_TESTS.items()]


@router.post("/stress/{case}")
def stress(case: str, auth: dict = Depends(admin)):
    if case not in demo.STRESS_TESTS:
        raise HTTPException(404, "ไม่พบกรณีทดสอบนี้")
    return demo.run_stress(case)


@router.post("/cohort/tick")
async def cohort_tick(body: TickBody, auth: dict = Depends(admin)):
    return {"moved": await demo.cohort_tick(body.students)}


@router.post("/cohort/reset")
def cohort_reset(auth: dict = Depends(admin)):
    codes = [r["code"] for r in db.query("SELECT code FROM students WHERE kind = 'sim'")]
    for code in codes:
        for table in ("states", "decisions", "alerts", "traces", "sessions"):
            db.execute(f"DELETE FROM {table} WHERE code = ?", (code,))
    db.execute("DELETE FROM students WHERE kind = 'sim'")
    count = demo.seed_cohort(seed=int(time.time()) % 10_000)
    analytics.clusters(force=True)
    return {"students": count}


# ---------------------------------------------------------------- จริยธรรมและความเป็นส่วนตัว (แท็บ 7)

@router.get("/logs")
def logs(auth: dict = Depends(admin)):
    return {
        "overrides": db.query("SELECT * FROM overrides ORDER BY ts DESC LIMIT 100"),
        "alerts": db.query("SELECT * FROM alerts ORDER BY ts DESC LIMIT 100"),
    }


@router.get("/privacy/{code}")
def privacy(code: str, auth: dict = Depends(admin)):
    """ข้อมูลที่ระบบเก็บของนักเรียนหนึ่งคน ดูจากมุม Admin ซึ่งไม่มีสิทธิ์อ่าน Roster"""
    counts = {
        table: db.query_one(f"SELECT COUNT(*) AS n FROM {table} WHERE code = ?", (code,))["n"]
        for table in ("traces", "decisions", "sessions", "alerts", "ai_logs")
    }
    sample = db.query("SELECT ts, action, target, data FROM traces WHERE code = ? ORDER BY ts DESC LIMIT 5", (code,))
    for s in sample:
        s["data"] = db.loads(s["data"], {})
    ai = db.query("SELECT ts, purpose, frames FROM ai_logs WHERE code = ? ORDER BY ts DESC LIMIT 1", (code,))
    sent_to_provider = db.loads(ai[0]["frames"], {}).get("context") if ai else None
    return {
        "code": code,
        "counts": counts,
        "sample_traces": sample,
        "name_visible": False,
        "roster_note": "ชื่อจริงเก็บในตาราง roster ซึ่ง API ของ Admin ไม่มีสิทธิ์อ่าน",
        "last_prompt_context": sent_to_provider,
    }


@router.post("/privacy/scrub")
def privacy_scrub(body: ScrubBody, auth: dict = Depends(admin)):
    """ลองลบข้อมูลส่วนตัวแบบเดียวกับก่อนส่งแชตให้ Provider
    ใช้เฉพาะชื่อสมมติของนักเรียนสาธิต เพื่อไม่ให้หน้านี้กลายเป็นช่องทางเดาชื่อใน Roster จริง"""
    text, found = pii.scrub(body.text, [name for _, name in seed.DEMO_STUDENTS])
    return {"text": text, "found": sorted(set(found))}


@router.get("/anti-labeling/{code}")
def anti_labeling(code: str, auth: dict = Depends(admin)):
    states = db.states_for(code)
    if not states:
        raise HTTPException(404, "นักเรียนคนนี้ยังไม่เริ่มเรียน")
    state = max(states, key=lambda s: s["last_activity"])
    content = services.content_for(state["subject_id"], state["set_id"])
    ctx = services.make_ctx(content)
    return {"student_view": engine.student_view(state, ctx), "staff_view": services.staff_payload(state, content, ctx)}


# ---------------------------------------------------------------- ตั้งค่า

@router.get("/settings")
def get_settings(auth: dict = Depends(admin)):
    return {
        "ai": settings_store.ai_settings(),
        "keys": {p: settings_store.masked(p) for p in ("claude", "gemini")},
        "params": settings_store.params(),
        "param_labels": PARAM_LABELS,
        "demo": settings_store.demo(),
        "pins_default": {r: settings_store.pin_is_default(r) for r in ("teacher", "admin")},
    }


@router.put("/settings")
def put_settings(body: SettingsBody, auth: dict = Depends(admin)):
    if body.ai:
        if body.ai.get("active") not in (None, "claude", "gemini", "offline"):
            raise HTTPException(400, "Provider ไม่ถูกต้อง")
        settings_store.save_ai_settings(body.ai)
    if body.params:
        errors = node_info.validate_params(body.params)
        if errors:
            raise HTTPException(400, " · ".join(errors))
        settings_store.save_params(body.params)
    if body.demo:
        settings_store.save_demo(body.demo)
    return get_settings(auth)


@router.put("/secrets")
def put_secret(body: SecretBody, auth: dict = Depends(admin)):
    if body.provider not in ("claude", "gemini"):
        raise HTTPException(400, "Provider ไม่ถูกต้อง")
    settings_store.save_api_key(body.provider, body.key)
    return settings_store.masked(body.provider)


@router.post("/providers/{provider}/test")
async def test_provider(provider: str, auth: dict = Depends(admin)):
    key, _ = settings_store.api_key(provider)
    if not key:
        return {"ok": False, "error": "ยังไม่ได้ใส่ API key"}
    started = time.perf_counter()
    try:
        models = await (providers.list_claude_models(key) if provider == "claude" else providers.list_gemini_models(key))
    except providers.ProviderError as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000), "models": models}


@router.put("/pins")
def put_pin(body: PinBody, auth: dict = Depends(admin)):
    if body.role not in ("teacher", "admin") or not body.pin.strip().isdigit() or len(body.pin.strip()) < 4:
        raise HTTPException(400, "PIN ต้องเป็นตัวเลขอย่างน้อย 4 หลัก")
    settings_store.set_pin(body.role, body.pin.strip())
    return {"ok": True}
