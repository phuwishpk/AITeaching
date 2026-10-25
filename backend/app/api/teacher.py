import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import analytics, db, seed, services
from ..content.readiness import check_set
from ..engine import flow as F
from ..tutor import rag
from .deps import require

router = APIRouter(prefix="/api/teacher", tags=["teacher"])
teacher = require("teacher")
# จัดการวิชา โจทย์ และเอกสาร ทำได้ทั้งครูและ Admin (ไม่มีข้อมูลนักเรียน) ส่วนอื่นของหน้าครูยังเป็นของครูคนเดียว
# ครูคนเดียวแก้คลังโจทย์ได้ Admin ดู Gem และคลังโจทย์ได้อย่างเดียวผ่าน /api/gems (ADR-0003)
content_editor = require("teacher")


class Override(BaseModel):
    set_id: str
    action: str
    params: dict = {}
    reason: str = ""


class RosterEntry(BaseModel):
    code: str | None = None
    name: str


class TagDecision(BaseModel):
    decision: str


# การแจ้งเตือนของนักเรียนจำลองไม่ขึ้นหน้าครู (ใช้ประกอบผังในหน้า Admin เท่านั้น)
CLASS_ALERTS = (
    "SELECT a.* FROM alerts a JOIN students s ON s.code = a.code WHERE s.kind != 'sim' ORDER BY a.ts DESC"
)


def roster_map() -> dict[str, str]:
    return {r["code"]: r["name"] for r in db.query("SELECT code, name FROM roster")}


@router.get("/overview")
def overview(auth: dict = Depends(teacher)):
    names = roster_map()
    students = services.staff_overview()
    for s in students:
        s["name"] = names.get(s["code"])
    alerts = db.query(CLASS_ALERTS + " LIMIT 100")
    model = analytics.clusters()
    return {
        "students": students,
        "alerts": alerts,
        "telemetry": analytics.telemetry(),
        "clusters": model.get("centroids", []),
        "pending_tags": db.query_one("SELECT COUNT(*) AS n FROM suggested_tags WHERE status = 'pending'")["n"],
        "now": time.time(),
    }


@router.get("/clusters")
def clusters(auth: dict = Depends(teacher)):
    names = roster_map()
    model = dict(analytics.clusters())
    model["points"] = [{**p, "name": names.get(p["code"])} for p in model.get("points", [])]
    return model


@router.get("/students/{code}")
def student_detail(code: str, auth: dict = Depends(teacher)):
    names = roster_map()
    views = []
    for state in db.states_for(code):
        content = services.content_for(state["subject_id"], state["set_id"])
        view = services.staff_payload(state, content, services.make_ctx(content))
        view["concept_names"] = {c: content.concept_name(c) for c in content.concepts}
        views.append(view)
    decisions = db.query(
        "SELECT ts, set_id, from_pos, to_pos, rule FROM decisions WHERE code = ? ORDER BY ts DESC, id DESC LIMIT 60", (code,)
    )
    for d in decisions:
        d["from_text"] = F.TEACHER_TEXT.get(d["from_pos"], d["from_pos"])
        d["to_text"] = F.TEACHER_TEXT.get(d["to_pos"], d["to_pos"])
    answers = []
    for row in db.query("SELECT ts, target, data FROM traces WHERE code = ? AND action = 'answer' ORDER BY ts DESC LIMIT 30", (code,)):
        data = db.loads(row["data"], {})
        answers.append({"ts": row["ts"], "item": row["target"], **data})
    logs = db.query(
        "SELECT id, ts, purpose, provider, model, final_text, guard, error FROM ai_logs WHERE code = ? ORDER BY ts DESC LIMIT 20",
        (code,),
    )
    for log in logs:
        log["guard"] = db.loads(log["guard"])
    return {
        "code": code,
        "name": names.get(code),
        "states": views,
        "decisions": decisions,
        "answers": answers,
        "ai_logs": logs,
        "alerts": db.query("SELECT * FROM alerts WHERE code = ? ORDER BY ts DESC LIMIT 20", (code,)),
        "cluster": analytics.cluster_of(code),
    }


class TeacherMessage(BaseModel):
    text: str


class ChatMode(BaseModel):
    mode: str


class DraftSend(BaseModel):
    text: str | None = None


@router.get("/students/{code}/messages")
def student_messages(code: str, before: float | None = None, hints: bool = True, auth: dict = Depends(teacher)):
    """ประวัติแชตกับ AI และครู ย้อนหลังได้ด้วย before (เวลาของข้อความเก่าสุดที่เห็นแล้ว)"""
    return {**services.teacher_history(code, before, hints=hints), "mode": services.chat_mode(code)}


@router.post("/students/{code}/chat-mode")
async def chat_mode(code: str, body: ChatMode, auth: dict = Depends(teacher)):
    if body.mode not in ("ai", "teacher"):
        raise HTTPException(400, "โหมดแชตไม่ถูกต้อง")
    services.log_teacher(code, "chat_mode", {"mode": body.mode})
    return await services.set_chat_mode(code, body.mode)


@router.post("/drafts/{draft_id}/send")
async def send_draft(draft_id: int, body: DraftSend, auth: dict = Depends(teacher)):
    return await services.send_draft(draft_id, body.text)


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: int, auth: dict = Depends(teacher)):
    draft = db.query_one("SELECT code, text FROM messages WHERE id = ? AND sender = 'draft'", (draft_id,))
    db.execute("DELETE FROM messages WHERE id = ? AND sender = 'draft'", (draft_id,))
    if draft:
        services.log_teacher(draft["code"], "draft_discarded", {"draft": draft["text"]})
    return {"ok": True}


@router.post("/students/{code}/viewed")
def viewed(code: str, auth: dict = Depends(teacher)):
    """หน้าครูเปิดดูนักเรียนคนนี้ ใช้วัดว่าครูเข้ามาดูหลังแจ้งเตือนกี่นาที"""
    services.log_teacher(code, "viewed")
    return {"ok": True}


@router.get("/inbox")
def inbox(auth: dict = Depends(teacher)):
    names = roster_map()
    return [{**row, "name": names.get(row["code"])} for row in services.inbox()]


@router.get("/students/{code}/answers")
def student_answers(code: str, auth: dict = Depends(teacher)):
    """โจทย์ที่กำลังทำและคำตอบแต่ละครั้ง ใช้ตรวจกิจกรรมข้างกล่องแชต"""
    return services.answer_sheet(code)


@router.post("/students/{code}/messages")
async def send_message(code: str, body: TeacherMessage, auth: dict = Depends(teacher)):
    text = body.text.strip()[:1000]
    if not text:
        raise HTTPException(400, "พิมพ์ข้อความก่อนส่ง")
    if not db.query_one("SELECT code FROM students WHERE code = ?", (code,)):
        raise HTTPException(404, "ไม่พบนักเรียนรหัสนี้")
    states = db.states_for(code)
    set_id = max(states, key=lambda s: s["last_activity"])["set_id"] if states else None
    services.log_teacher(code, "message", {"text": text})
    return await services.post_message(code, set_id, "teacher", text)


@router.post("/students/{code}/override")
async def override(code: str, body: Override, auth: dict = Depends(teacher)):
    return await services.override(code, body.set_id, body.action, body.params, body.reason, "teacher")


@router.get("/alerts")
def alerts(auth: dict = Depends(teacher)):
    return db.query(CLASS_ALERTS + " LIMIT 200")


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: int, auth: dict = Depends(teacher)):
    db.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    alert = db.query_one("SELECT code, kind, message FROM alerts WHERE id = ?", (alert_id,))
    if alert:
        services.log_teacher(alert["code"], "ack", {"alert_id": alert_id, "kind": alert["kind"], "message": alert["message"]})
    return {"ok": True}


# ---------------------------------------------------------------- Roster

@router.get("/roster")
def roster(auth: dict = Depends(teacher)):
    rows = db.query(
        "SELECT s.code, r.name, s.created_at FROM students s LEFT JOIN roster r ON r.code = s.code "
        "WHERE s.kind = 'real' ORDER BY s.code"
    )
    return rows


@router.post("/roster")
def add_roster(body: RosterEntry, auth: dict = Depends(teacher)):
    code = (body.code or "").strip().upper()
    if not code:
        existing = [r["code"] for r in db.query("SELECT code FROM students WHERE code LIKE 'S-%'")]
        numbers = [int(c[2:]) for c in existing if c[2:].isdigit()]
        code = f"S-{(max(numbers) + 1) if numbers else 1:02d}"
    db.execute("INSERT OR IGNORE INTO students (code, kind, persona, created_at) VALUES (?,?,?,?)",
               (code, "real", None, time.time()))
    db.execute("INSERT OR REPLACE INTO roster (code, name) VALUES (?, ?)", (code, body.name.strip()))
    return {"code": code, "name": body.name.strip()}


@router.delete("/roster/{code}")
def remove_roster(code: str, auth: dict = Depends(teacher)):
    db.execute("DELETE FROM roster WHERE code = ?", (code,))
    return {"ok": True}


# ---------------------------------------------------------------- เนื้อหา

def summary(subject: dict) -> dict:
    sets = []
    for qs in subject.get("question_sets", []):
        sets.append({**qs, "readiness": check_set(subject, qs["id"])})
    return {
        "id": subject["id"], "name": subject["name"], "grade": subject.get("grade", ""),
        "description": subject.get("description", ""), "concepts": len(subject.get("concepts", [])),
        "items": len(subject.get("items", [])), "bug_tags": len(subject.get("bug_tags", [])), "sets": sets,
    }


@router.get("/subjects")
def subjects(auth: dict = Depends(content_editor)):
    return [summary(s) for s in db.list_subjects()]


@router.get("/subjects/{subject_id}")
def get_subject(subject_id: str, auth: dict = Depends(content_editor)):
    subject = db.get_subject(subject_id)
    if not subject:
        raise HTTPException(404, "ไม่พบวิชานี้")
    return subject


def validate(subject: dict):
    for key in ("id", "name"):
        if not str(subject.get(key, "")).strip():
            raise HTTPException(400, "วิชาต้องมีรหัสและชื่อ")
    for key in ("concepts", "items", "bug_tags", "walkthroughs", "question_sets"):
        subject.setdefault(key, [])
    ids = [it["id"] for it in subject["items"]]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "มีรหัสโจทย์ซ้ำกัน")
    others = {qs["id"] for s in db.list_subjects() if s["id"] != subject["id"] for qs in s.get("question_sets", [])}
    clash = [qs["id"] for qs in subject["question_sets"] if qs["id"] in others]
    if clash:
        raise HTTPException(400, f"รหัสชุดคำถามซ้ำกับวิชาอื่น: {', '.join(clash)}")


@router.put("/subjects/{subject_id}")
def save_subject(subject_id: str, subject: dict, auth: dict = Depends(content_editor)):
    subject["id"] = subject_id
    validate(subject)
    db.save_subject(subject)
    services.invalidate_content()
    return summary(subject)


@router.post("/subjects")
def create_subject(subject: dict, auth: dict = Depends(content_editor)):
    validate(subject)
    if db.get_subject(subject["id"]):
        raise HTTPException(400, "มีวิชารหัสนี้อยู่แล้ว")
    db.save_subject(subject)
    services.invalidate_content()
    seed.rebuild_index(subject["id"])
    return summary(subject)


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: str, auth: dict = Depends(content_editor)):
    db.delete_subject(subject_id)
    db.execute("DELETE FROM documents WHERE subject_id = ?", (subject_id,))
    services.invalidate_content()
    return {"ok": True}


@router.get("/subjects/{subject_id}/readiness/{set_id}")
def readiness(subject_id: str, set_id: str, auth: dict = Depends(content_editor)):
    subject = db.get_subject(subject_id)
    if not subject:
        raise HTTPException(404, "ไม่พบวิชานี้")
    return check_set(subject, set_id)


@router.get("/subjects/{subject_id}/documents")
def documents(subject_id: str, auth: dict = Depends(content_editor)):
    rows = db.query(
        "SELECT id, filename, kind, chars, warning, uploaded_at, chunks FROM documents WHERE subject_id = ? ORDER BY uploaded_at DESC",
        (subject_id,),
    )
    for row in rows:
        chunks = db.loads(row.pop("chunks"), [])
        row["chunks"] = len(chunks)
        row["preview"] = chunks[0][:240] if chunks else ""
    return rows


@router.post("/subjects/{subject_id}/documents")
async def upload(subject_id: str, file: UploadFile = File(...), auth: dict = Depends(content_editor)):
    if not db.get_subject(subject_id):
        raise HTTPException(404, "ไม่พบวิชานี้")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 15 MB")
    text, warning = rag.extract_text(file.filename or "file.txt", data)
    if not text:
        raise HTTPException(400, warning or "อ่านข้อความจากไฟล์นี้ไม่ได้")
    doc_id = seed.add_document(subject_id, file.filename or "เอกสาร", text, warning)
    return {"id": doc_id, "warning": warning, "chars": len(text)}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, auth: dict = Depends(content_editor)):
    row = db.query_one("SELECT subject_id FROM documents WHERE id = ?", (doc_id,))
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    if row:
        seed.rebuild_index(row["subject_id"])
    return {"ok": True}


# ---------------------------------------------------------------- แท็กที่ AI เดา (รอครูยืนยัน)

@router.get("/tags")
def tags(auth: dict = Depends(teacher)):
    rows = db.query("SELECT * FROM suggested_tags ORDER BY ts DESC LIMIT 100")
    tag_names = {}
    item_info = {}
    for subject in db.list_subjects():
        tag_names.update({t["id"]: t["name"] for t in subject.get("bug_tags", [])})
        item_info.update({it["id"]: f"{it['prompt']} {it.get('math') or ''}".strip() for it in subject.get("items", [])})
    for row in rows:
        row["tag_name"] = tag_names.get(row["tag"], row["tag"])
        row["item_text"] = item_info.get(row["item_id"], row["item_id"])
    return rows


@router.post("/tags/{tag_id}")
def decide_tag(tag_id: int, body: TagDecision, auth: dict = Depends(teacher)):
    row = db.query_one("SELECT * FROM suggested_tags WHERE id = ?", (tag_id,))
    if not row:
        raise HTTPException(404, "ไม่พบรายการนี้")
    if body.decision == "confirm":
        for subject in db.list_subjects():
            for item in subject.get("items", []):
                if item["id"] == row["item_id"]:
                    answer = row["answer"]
                    if item["format"] == "numeric":
                        try:
                            answer = float(answer) if "." in answer else int(answer)
                        except ValueError:
                            pass
                    if not any(str(b["answer"]) == str(answer) for b in item.setdefault("bugs", [])):
                        item["bugs"].append({"answer": answer, "tag": row["tag"]})
                    db.save_subject(subject)
                    services.invalidate_content()
    db.execute("UPDATE suggested_tags SET status = ? WHERE id = ?",
               ("confirmed" if body.decision == "confirm" else "rejected", tag_id))
    return {"ok": True}


@router.get("/ai-logs")
def ai_logs(code: str | None = None, auth: dict = Depends(teacher)):
    if code:
        rows = db.query("SELECT * FROM ai_logs WHERE code = ? ORDER BY ts DESC LIMIT 50", (code,))
    else:
        rows = db.query("SELECT * FROM ai_logs ORDER BY ts DESC LIMIT 50")
    for row in rows:
        for key in ("frames", "retrieved", "guard"):
            row[key] = db.loads(row[key])
    return rows
