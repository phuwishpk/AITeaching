from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db, services
from ..content.readiness import check_set
from ..engine import core as engine
from .deps import require

router = APIRouter(prefix="/api/student", tags=["student"])
student = require("student")


class Answer(BaseModel):
    answer: str


class Choice(BaseModel):
    option: str


class Chat(BaseModel):
    message: str


class Start(BaseModel):
    restart: bool = False


class Revisit(BaseModel):
    concept: str | None = None


@router.get("/sets")
def list_sets(auth: dict = Depends(student)):
    result = []
    states = {s["set_id"]: s for s in db.states_for(auth["code"])}
    for subject in db.list_subjects():
        for qs in subject.get("question_sets", []):
            if not qs.get("published") or not check_set(subject, qs["id"])["ok"]:
                continue
            state = states.get(qs["id"])
            status = "new"
            if state:
                status = "completed" if state["end_reason"] == "completed" else ("paused" if state["ended"] else "in_progress")
            concept = next((c for c in subject["concepts"] if c["id"] == qs["target_concept"]), {})
            result.append({
                "id": qs["id"], "name": qs["name"], "description": qs.get("description", ""),
                "subject": subject["name"], "grade": subject.get("grade", ""), "target": concept.get("name", ""),
                "status": status,
            })
    return result


@router.post("/sets/{set_id}/start")
async def start(set_id: str, body: Start, auth: dict = Depends(student)):
    return await services.start(auth["code"], set_id, body.restart)


@router.get("/sets/{set_id}/state")
async def state(set_id: str, auth: dict = Depends(student)):
    return await services.get_state(auth["code"], set_id)


@router.post("/sets/{set_id}/answer")
async def answer(set_id: str, body: Answer, auth: dict = Depends(student)):
    return await services.submit(auth["code"], set_id, body.answer)


@router.post("/sets/{set_id}/hint")
async def hint(set_id: str, auth: dict = Depends(student)):
    return await services.hint(auth["code"], set_id)


@router.post("/sets/{set_id}/undo")
async def undo(set_id: str, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.undo)


@router.post("/sets/{set_id}/restart-item")
async def restart_item(set_id: str, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.restart_item)


@router.post("/sets/{set_id}/idle")
async def idle(set_id: str, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.idle)


@router.post("/sets/{set_id}/rest")
async def rest(set_id: str, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, lambda s, c: engine.idle(s, c, "manual"))


@router.post("/sets/{set_id}/resume")
async def resume(set_id: str, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.resume)


@router.post("/sets/{set_id}/walkthrough-done")
async def walkthrough_done(set_id: str, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.walkthrough_done)


@router.post("/sets/{set_id}/choose")
async def choose(set_id: str, body: Choice, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.choose, body.option)


@router.post("/sets/{set_id}/chat")
async def chat(set_id: str, body: Chat, auth: dict = Depends(student)):
    return await services.chat(auth["code"], set_id, body.message)


@router.get("/sets/{set_id}/messages")
def messages(set_id: str, auth: dict = Depends(student)):
    """บทสนทนาในกล่องแชต: ข้อความของเรา AI Tutor และครู พร้อมบอกว่าตอนนี้ครูอยู่ในแชตหรือไม่"""
    return {"messages": services.messages_for(auth["code"]), "mode": services.chat_mode(auth["code"])}


@router.get("/sets/{set_id}/notes")
async def notes(set_id: str, auth: dict = Depends(student)):
    """เนื้อหาสำหรับปุ่มทบทวนเนื้อหา: มโนทัศน์เป้าหมาย พื้นฐานที่ต้องรู้ก่อน และตัวอย่างทีละขั้น"""
    subject, qs = services.find_set(set_id)
    content = services.content_for(subject["id"], set_id)
    target = content.concepts[qs["target_concept"]]
    chain = [target] + [content.concepts[c] for c in target.get("prerequisites", []) if c in content.concepts]
    return [
        {"id": c["id"], "name": c["name"], "grade": c.get("grade", ""), "description": c.get("description", ""),
         "walkthrough": content.walkthrough(c["id"])}
        for c in chain
    ]


@router.post("/sets/{set_id}/revisit")
async def revisit(set_id: str, body: Revisit, auth: dict = Depends(student)):
    return await services.simple(auth["code"], set_id, engine.revisit, body.concept)
