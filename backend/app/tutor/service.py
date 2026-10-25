"""AI Tutor: ปรับถ้อยคำคำใบ้ ตอบแชตแบบ Socratic และเสนอแท็กข้อผิดพลาด

ลำดับการทำงาน: ดึงบริบท (RAG) → ประกอบ prompt 4 กรอบ → เรียก Provider ตามลำดับสำรอง
→ ตรวจด้วย Answer-Leak Guard → ถ้าไม่ผ่านหรือเรียกไม่ได้ ใช้คำใบ้ต้นฉบับ
ทุกครั้งบันทึกลง ai_logs ให้ครูและ Admin เปิดดูย้อนหลังได้ (กฎครูข้อ 1)
"""

import json
import re
import time

from .. import db, settings_store
from . import guard, prompt, providers, rag

LEVEL_FALLBACK = {
    1: "ลองดูโจทย์อีกครั้ง มีจุดไหนที่ควรตรวจทานไหม",
    2: "ลองนึกถึงกฎที่ใช้กับโจทย์แบบนี้ แล้วทำทีละขั้น",
    3: "ลองเริ่มจากขั้นแรกของวิธีทำ แล้วค่อยทำต่อเอง",
}


async def _call(system: str, user: str, **options) -> tuple[providers.LLMResult | None, list[str]]:
    """เรียก Provider ตามที่ตั้งไว้ ถ้าตัวแรกใช้ไม่ได้ลองตัวถัดไป คืน (ผล, รายการข้อผิดพลาด)

    options ส่งต่อให้ Provider เช่น max_tokens, json_mode, timeout (ใช้ตอนสร้าง Item Bank ของ Gem)
    """
    ai = settings_store.ai_settings()
    if ai["active"] == "offline":
        return None, ["Offline Mode"]
    chain = [ai["active"]] + [p for p in ai["order"] if p != ai["active"]]
    errors = []
    for provider in chain:
        key, _ = settings_store.api_key(provider)
        if not key:
            errors.append(f"{provider}: ยังไม่ได้ใส่ API key")
            continue
        try:
            if provider == "claude":
                claude_options = {k: v for k, v in options.items() if k != "backup_models"}
                return await providers.call_claude(key, ai["claude_model"], system, user, **claude_options), errors
            if provider == "gemini":
                gemini_options = {"backup_models": providers.GEMINI_BACKUPS, **options}
                return await providers.call_gemini(key, ai["gemini_model"], system, user, **gemini_options), errors
        except providers.ProviderError as error:
            errors.append(f"{provider}: {error}")
    return None, errors


def _log(code: str | None, purpose: str, frames: dict | None, retrieved: list | None, result, final_text: str,
         guard_result: dict | None, errors: list[str]) -> int:
    cursor = db.execute(
        "INSERT INTO ai_logs (ts, code, purpose, provider, model, frames, retrieved, output, final_text, guard, "
        "tokens_in, tokens_out, latency_ms, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            time.time(), code, purpose,
            result.provider if result else "offline",
            result.model if result else None,
            db.dumps(frames), db.dumps(retrieved or []),
            result.text if result else None,
            final_text, db.dumps(guard_result), result.tokens_in if result else 0,
            result.tokens_out if result else 0, result.latency_ms if result else 0,
            "; ".join(errors) if errors else None,
        ),
    )
    return cursor.lastrowid


def _retrieve(subject: dict, query: str, k: int = 2) -> tuple[list[str], list[dict]]:
    # Knowledge File ของ Gem ผูกกับตัว Gem ใช้ร่วมกันทุกรุ่นของคลังโจทย์
    index = rag.get_index((subject.get("gem") or {}).get("id") or subject["id"])
    if not index:
        return [], []
    return index.search(query, k)


def _clean(text: str) -> str:
    # markdown และเครื่องหมาย $ ของ LaTeX ที่ LLM ชอบใส่ หน้าจอนักเรียนแสดงข้อความธรรมดา
    text = re.sub(r"[*#`_>$]+", "", text).strip()
    return re.sub(r"\n{2,}", "\n", text)


def authored_hint(item: dict, level: int, tag_id: str | None) -> str:
    """คำใบ้ต้นฉบับ: คำใบ้ที่ครูเขียนไว้สำหรับคำตอบผิดแบบนี้ในข้อนี้ก่อน (ตาราง Bug Library ของครู) แล้วจึงคำใบ้ของข้อ"""
    for bug in item.get("bugs", []):
        if tag_id and bug.get("tag") == tag_id and (bug.get("hints") or {}).get(str(level)):
            return bug["hints"][str(level)]
    return item.get("hints", {}).get(str(level)) or LEVEL_FALLBACK[level]


async def generate_hint(subject: dict, item: dict, concept_name: str, level: int, student: dict,
                        tag: dict | None, code: str | None) -> dict:
    authored = authored_hint(item, level, tag["id"] if tag else None)
    query = " ".join(filter(None, [item.get("prompt"), item.get("math"), concept_name, tag["name"] if tag else None, authored]))
    terms, docs = _retrieve(subject, query)
    built = prompt.hint_prompt(subject, item, concept_name, level, student, tag, docs, authored)
    result, errors = await _call(built["system"], built["user"])
    retrieved = {"query_terms": terms[:30], "documents": docs, "tag": tag["id"] if tag else None}
    if result is None:
        log_id = _log(code, f"hint_l{level}", built["frames"], retrieved, None, authored, None, errors)
        return {"text": authored, "source": "authored", "guard": None, "log_id": log_id, "errors": errors}
    text = _clean(result.text)
    checked = guard.check(text, item)
    if checked.blocked:
        log_id = _log(code, f"hint_l{level}", built["frames"], retrieved, result, authored, checked.to_dict(), errors)
        return {"text": authored, "source": "authored", "guard": checked.to_dict(), "log_id": log_id,
                "trigger": checked.trigger, "errors": errors}
    log_id = _log(code, f"hint_l{level}", built["frames"], retrieved, result, text, checked.to_dict(), errors)
    return {"text": text, "source": result.provider, "model": result.model, "guard": checked.to_dict(),
            "log_id": log_id, "errors": errors}


async def chat_reply(subject: dict, item: dict | None, concept_name: str, student: dict, message: str,
                     tag: dict | None, hints_shown: list[str], fallback: str, code: str | None) -> dict:
    query = " ".join(filter(None, [message, item.get("prompt") if item else None, concept_name]))
    terms, docs = _retrieve(subject, query)
    built = prompt.chat_prompt(subject, item, concept_name, student, message, tag, docs, hints_shown)
    result, errors = await _call(built["system"], built["user"])
    retrieved = {"query_terms": terms[:30], "documents": docs, "tag": tag["id"] if tag else None}
    if result is None:
        log_id = _log(code, "chat", built["frames"], retrieved, None, fallback, None, errors)
        return {"text": fallback, "source": "authored", "log_id": log_id, "errors": errors}
    off_topic = prompt.OFF_TOPIC in result.text
    text = _clean(result.text.replace(prompt.OFF_TOPIC, ""))
    checked = guard.check(text, item) if item else guard.GuardResult(guard.TRIGGER in text, trigger=guard.TRIGGER in text)
    if checked.trigger:
        log_id = _log(code, "chat", built["frames"], retrieved, result, "", checked.to_dict(), errors)
        return {"text": "", "source": result.provider, "trigger": True, "log_id": log_id, "guard": checked.to_dict()}
    if checked.blocked:
        log_id = _log(code, "chat", built["frames"], retrieved, result, fallback, checked.to_dict(), errors)
        return {"text": fallback, "source": "authored", "guard": checked.to_dict(), "log_id": log_id, "errors": errors}
    log_id = _log(code, "chat", built["frames"], retrieved, result, text, checked.to_dict(), errors)
    return {"text": text, "source": result.provider, "guard": checked.to_dict(), "log_id": log_id, "errors": errors,
            "off_topic": off_topic}


async def suggest_tag(subject: dict, item: dict, answer: str, code: str | None) -> dict | None:
    tags = [t for t in subject.get("bug_tags", [])]
    if not tags:
        return None
    built = prompt.tag_prompt(subject, item, answer, tags)
    result, errors = await _call(built["system"], built["user"])
    if result is None:
        return None
    match_tag = re.search(r"TAG:\s*([A-Z0-9\-]+)", result.text)
    match_reason = re.search(r"REASON:\s*(.+)", result.text)
    tag_id = match_tag.group(1) if match_tag else "NONE"
    valid = {t["id"] for t in tags}
    _log(code, "suggest_tag", built["frames"], None, result, tag_id, None, errors)
    if tag_id not in valid:
        return None
    return {"tag": tag_id, "reason": match_reason.group(1).strip() if match_reason else ""}


async def judge_reflection(subject: dict, item: dict | None, step: dict, answer: str, code: str | None) -> dict:
    """LLM ประเมินคำอธิบายของนักเรียนตามเกณฑ์ของครู (เฉพาะขั้นที่ครูสั่งให้ประเมิน) ผลไม่แสดงให้นักเรียนเห็น
    ใช้แค่เลือกเส้นทางต่อและบันทึกให้ครูตรวจ ถูกผิดของโจทย์ยังตัดสินด้วยกฎเหมือนเดิม"""
    system = (
        "คุณเป็นผู้ช่วยครูที่ประเมินคำอธิบายวิธีคิดของนักเรียนตามเกณฑ์ของครู ประเมินความเข้าใจ ไม่ใช่ความสวยของภาษา "
        "ตอบเป็น JSON เท่านั้น: {\"pass\": true หรือ false, \"score\": 0-100, \"reason\": \"เหตุผลสั้น ๆ ให้ครูอ่าน\"}"
    )
    user = (
        f"วิชา: {subject.get('name', '')}\n"
        + (f"โจทย์ล่าสุด: {item.get('prompt', '')} {item.get('math') or ''}\n" if item else "")
        + f"คำถามที่ให้นักเรียนอธิบาย: {step.get('question', '')}\n"
        f"เกณฑ์ของครู: {step.get('rubric') or 'อธิบายขั้นตอนที่ใช้และเหตุผลได้ถูกต้อง'}\n"
        f"คำอธิบายของนักเรียน: \"\"\"{answer}\"\"\""
    )
    result, errors = await _call(system, user, max_tokens=400, json_mode=True, timeout=40.0)
    frames = {"role": system, "task": user}
    if result is None:
        _log(code, "judge_reflect", frames, None, None, "", None, errors)
        return {"pass": None, "score": None, "reason": "", "error": "; ".join(errors) or "เรียก AI ไม่สำเร็จ"}
    match = re.search(r"\{.*\}", result.text, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    verdict = {
        "pass": data.get("pass") if isinstance(data.get("pass"), bool) else None,
        "score": max(0, min(100, int(data["score"]))) if isinstance(data.get("score"), (int, float)) else None,
        "reason": str(data.get("reason", ""))[:300],
    }
    verdict["log_id"] = _log(code, "judge_reflect", frames, None, result, json.dumps(verdict, ensure_ascii=False), None, errors)
    return verdict


async def preview(subject: dict, item: dict, concept_name: str, level: int, tag: dict | None) -> dict:
    """ใช้ในแท็บ 4 ของ Admin: ประกอบ prompt และลองเรียกจริงโดยไม่ผูกกับนักเรียน"""
    student = {"error_count": level, "response_time": 40, "diagnosis": {"class": "misconception" if tag else None,
                                                                        "tag_name": tag["name"] if tag else None}}
    return await generate_hint(subject, item, concept_name, level, student, tag, "ADMIN-PREVIEW")
