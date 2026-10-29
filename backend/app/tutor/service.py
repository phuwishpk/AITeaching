"""AI Tutor: ปรับถ้อยคำคำใบ้ ตอบแชตแบบ Socratic และเสนอแท็กข้อผิดพลาด

ลำดับการทำงาน: ดึงบริบท (RAG) → ประกอบ prompt 4 กรอบ → เรียก Provider ตามลำดับสำรอง
→ ตรวจด้วย Answer-Leak Guard → ถ้าไม่ผ่านหรือเรียกไม่ได้ ใช้คำใบ้ต้นฉบับ
ทุกครั้งบันทึกลง ai_logs ให้ครูและ Admin เปิดดูย้อนหลังได้ (กฎครูข้อ 1)
"""

import json
import re
import time

from .. import db, scope, settings_store
from . import distress, guard, prompt, providers, rag

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
    # task="design" = งานสร้างบทเรียนตอนครูกดสร้าง (ใช้โมเดลที่ตั้งไว้สำหรับงานนี้) ไม่ระบุ = งานตอนนักเรียนเรียน
    task = options.pop("task", "chat")
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
                claude_options = {k: v for k, v in options.items() if k not in ("backup_models", "thinking", "attachments")}
                return await providers.call_claude(key, ai["claude_model"], system, user, **claude_options), errors
            if provider == "gemini":
                gemini_options = {"backup_models": providers.GEMINI_BACKUPS, **options}
                model = ai["gemini_design_model"] if task == "design" else ai["gemini_model"]
                result = await providers.call_gemini(key, model, system, user, **gemini_options)
                if result.fallback:
                    errors.append(f"gemini: ใช้ {result.model} แทน ({result.fallback})")
                return result, errors
        except providers.ProviderError as error:
            errors.append(f"{provider}: {error}")
    return None, errors


def _log(code: str | None, purpose: str, frames: dict | None, retrieved: list | None, result, final_text: str,
         guard_result: dict | None, errors: list[str]) -> int:
    # เจ้าของบันทึก = คนที่ API key ถูกใช้ (เจ้าของ Gem หรือผู้ใช้ที่กด) ให้แต่ละคนเห็นเฉพาะการเรียก AI ของตัวเอง
    owner = settings_store.key_owner() or scope.student_owner(code)
    cursor = db.execute(
        "INSERT INTO ai_logs (ts, code, purpose, provider, model, frames, retrieved, output, final_text, guard, "
        "tokens_in, tokens_out, latency_ms, error, owner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            time.time(), code, purpose,
            result.provider if result else "offline",
            result.model if result else None,
            db.dumps(frames), db.dumps(retrieved or []),
            result.text if result else None,
            final_text, db.dumps(guard_result), result.tokens_in if result else 0,
            result.tokens_out if result else 0, result.latency_ms if result else 0,
            "; ".join(errors) if errors else None, owner,
        ),
    )
    return cursor.lastrowid


# ความจำเอกสารของ Gem: ส่งเอกสารทั้งหมดให้ AI ทุกครั้งที่เขียนคำใบ้ ตอบแชต หรือประเมินคำอธิบาย
# ไม่เกิน MEMORY_LIMIT ตัวอักษรส่งต้นฉบับเต็ม ยาวกว่านั้นใช้บันทึกที่ AI สรุปไว้ตอนสร้างคลังโจทย์ (ครอบคลุมทุกส่วน)
# วางไว้ใน system prompt ส่วนที่เหมือนเดิมทุกครั้ง Gemini จึงแคชส่วนนี้ให้เองและคิดค่าโทเคนถูกลง
MEMORY_LIMIT = 100_000
_memory: dict[str, str] = {}


def forget_memory(gem_id: str) -> None:
    _memory.pop(gem_id, None)


def knowledge_memory(subject: dict) -> str:
    from ..gems import builder  # builder import ไฟล์นี้ จึง import ตอนใช้

    gem_id = (subject.get("gem") or {}).get("id") or subject["id"]
    if gem_id not in _memory:
        total = sum(len(text) for _, text in builder.documents_text(gem_id))
        stored = (db.get_gem(gem_id) or {}).get("knowledge") or {}
        if total > MEMORY_LIMIT and stored.get("mode") == "digest" and stored.get("text"):
            _memory[gem_id] = stored["text"][:MEMORY_LIMIT]
        else:
            _memory[gem_id] = builder.knowledge_text(gem_id, MEMORY_LIMIT) if total else ""
    return _memory[gem_id]


def _with_memory(built: dict, memory: str) -> dict:
    if not memory:
        return built
    frames = built["frames"]
    built["system"] = (
        f"{frames['role']}\n\n<knowledge>\nเอกสารประกอบการสอนทั้งหมดที่ครูแนบไว้ในติวเตอร์นี้ ใช้อ้างอิงเนื้อหา คำอธิบาย ตัวอย่าง "
        f"และแนวทางการสอนของครู\n{memory}\n</knowledge>\n\n{frames['constraints']}"
    )
    # บันทึกใน ai_logs แค่ขนาด ไม่เก็บเอกสารเต็มซ้ำทุกครั้ง
    frames["knowledge"] = f"ส่งเอกสารของติวเตอร์ทั้งหมด {len(memory):,} ตัวอักษรไปใน system prompt"
    return built


# ไฟล์ความรู้สั้น (รวมไม่เกิน WHOLE_DOC ตัวอักษร) ส่งทั้งหมดทุกครั้ง ไม่ต้องเดาว่าย่อหน้าไหนเกี่ยว
# ยาวกว่านั้นค้นด้วย BM25 แล้วส่ง RETRIEVE_K ย่อหน้าที่ตรงที่สุด
WHOLE_DOC = 8000
RETRIEVE_K = 5


def _retrieve(subject: dict, query: str, k: int = RETRIEVE_K) -> tuple[list[str], list[dict]]:
    # Knowledge File ของ Gem ผูกกับตัว Gem ใช้ร่วมกันทุกรุ่นของคลังโจทย์
    index = rag.get_index((subject.get("gem") or {}).get("id") or subject["id"])
    if not index or not index.docs:
        return [], []
    if sum(len(d["text"]) for d in index.docs) <= WHOLE_DOC:
        return rag.tokenize(query), [{"filename": d["filename"], "text": d["text"], "score": None} for d in index.docs]
    return index.search(query, k)


LATEX = {r"\div": "÷", r"\times": "×", r"\cdot": "×", r"\pm": "±", r"\le": "≤", r"\ge": "≥", r"\neq": "≠",
         r"\left": "", r"\right": ""}


def _clean(text: str) -> str:
    # markdown และ LaTeX ที่ LLM ชอบใส่ หน้าจอนักเรียนแสดงข้อความธรรมดา: \div → ÷ \frac{a}{b} → a/b ^{2} → ^2
    for command, plain in LATEX.items():
        text = re.sub(re.escape(command) + r"(?![a-zA-Z])", plain, text)
    text = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}",
                  lambda m: "/".join(p if re.fullmatch(r"[\w.]+", p) else f"({p})" for p in m.groups()), text)
    text = re.sub(r"\^\{([^{}]*)\}", r"^\1", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
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
    memory = knowledge_memory(subject)
    terms, docs = _retrieve(subject, query) if not memory else (rag.tokenize(query), [])
    built = _with_memory(prompt.hint_prompt(subject, item, concept_name, level, student, tag, docs, authored), memory)
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
                     tag: dict | None, hints_shown: list[str], fallback: str, code: str | None,
                     history: list[dict] | None = None, chat: dict | None = None, intent: dict | None = None) -> dict:
    query = " ".join(filter(None, [message, item.get("prompt") if item else None, concept_name]))
    memory = knowledge_memory(subject)
    terms, docs = _retrieve(subject, query) if not memory else (rag.tokenize(query), [])
    built = _with_memory(prompt.chat_prompt(subject, item, concept_name, student, message, tag, docs, hints_shown, history,
                                            chat, intent), memory)
    result, errors = await _call(built["system"], built["user"])
    retrieved = {"query_terms": terms[:30], "documents": docs, "tag": tag["id"] if tag else None}
    if result is not None and guard.has_trigger(result.text) and not distress.detect(message)["level"]:
        # LLM ส่งรหัสตัดวงจรกับข้อความที่รายการคำไม่พบความเครียด (เคยเกิดกับคำถามธรรมดา): ถามซ้ำหนึ่งครั้งเพื่อยืนยัน
        _log(code, "chat", built["frames"], retrieved, result, "", {"blocked": True, "reason": "รหัสตัดวงจรที่ต้องยืนยัน",
                                                                     "matched": guard.TRIGGER, "trigger": True}, errors)
        result, errors = await _call(built["system"], built["user"] + "\n(ตรวจอีกครั้ง: ส่งรหัสตัดวงจรเฉพาะเมื่อข้อความนี้"
                                     "แสดงความเครียดหรือท้อแท้จริง ถ้าเป็นคำถามเรื่องบทเรียนให้ตอบตามปกติ)")
    if result is None:
        log_id = _log(code, "chat", built["frames"], retrieved, None, fallback, None, errors)
        return {"text": fallback, "source": "authored", "log_id": log_id, "errors": errors}
    off_topic = prompt.OFF_TOPIC in result.text
    text = _clean(result.text.replace(prompt.OFF_TOPIC, ""))
    trigger = guard.has_trigger(result.text)
    checked = guard.check(text, item) if item and not trigger else guard.GuardResult(trigger, trigger=trigger)
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


async def make_activity(subject: dict, step: dict, item: dict | None, concept_name: str, student: dict,
                        tag: dict | None, code: str | None) -> dict | None:
    """ขั้น "กิจกรรม" ใน Flow ของ Gem: AI สร้างเนื้อหาตามเป้าหมายที่บรรยายไว้ อิงเอกสารของครู ห้ามเฉลยข้อที่กำลังทำ
    คืน None ถ้าเรียก AI ไม่สำเร็จหรือ Answer-Leak Guard บล็อก (services ใช้ข้อความสำรองแทน)"""
    asks = step.get("response") == "text"
    context = (
        f"นักเรียนระดับ {subject.get('grade', '')} เรื่อง{concept_name}\n"
        + (f"โจทย์ที่เพิ่งทำ: {item['prompt']} {item.get('math') or ''}\n" if item else "")
        + f"ตอบผิดในข้อนี้ {student.get('error_count', 0)} ครั้ง"
        + (f" ข้อผิดพลาดที่พบ: {tag['name']} ({tag.get('description', '')})" if tag else "")
    )
    task = (
        f"สร้างกิจกรรมสั้น ๆ ให้นักเรียนคนนี้ตามเป้าหมายของครู: {step.get('goal', '')}\n"
        "ใช้เนื้อหาและวิธีคิดจากเอกสารของครู ภาษาเข้าใจง่าย ไม่เกิน 8 บรรทัด ห้ามบอกคำตอบของโจทย์ที่นักเรียนกำลังทำ "
        "ถ้ายกตัวอย่างให้ใช้ตัวเลขอื่น\n"
        + ("ปิดท้ายด้วยคำถามหนึ่งข้อให้นักเรียนพิมพ์ตอบ\n" if asks else "ไม่ต้องให้นักเรียนตอบ ให้อ่านแล้วไปต่อ\n")
        + "ตอบเป็น JSON: {\"text\": \"เนื้อหากิจกรรม\", \"question\": \"คำถามให้นักเรียนตอบ หรือ \\\"\\\" ถ้าไม่ต้องตอบ\"}"
    )
    built = {"frames": {"role": prompt.role_frame(subject), "context": context, "task": task,
                        "constraints": prompt.constraints_frame()}}
    built["system"] = f"{built['frames']['role']}\n\n{built['frames']['constraints']}"
    built["user"] = f"{context}\n\n{task}"
    built = _with_memory(built, knowledge_memory(subject))
    user = built["user"]
    for attempt in range(2):
        result, errors = await _call(built["system"], user, max_tokens=1500, json_mode=True)
        if result is None:
            _log(code, "activity", built["frames"], None, None, "", None, errors)
            return None
        match = re.search(r"\{.*\}", result.text, re.S)
        try:
            data = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            data = {}
        text, question = _clean(str(data.get("text") or "")), _clean(str(data.get("question") or ""))
        checked = guard.check(f"{text}\n{question}", item) if item else guard.GuardResult(False)
        log_id = _log(code, "activity", built["frames"], None, result, text if not checked.blocked else "", checked.to_dict(), errors)
        if text and not checked.blocked:
            return {"text": text, "question": question if asks else "", "log_id": log_id}
        if not checked.blocked or attempt:
            return None
        # Answer-Leak Guard บล็อก (ตัวอย่างบังเอิญได้ผลเท่ากับคำตอบของข้อนี้): ให้สร้างใหม่หนึ่งครั้งโดยห้ามตัวเลขนั้น
        user = (f"{built['user']}\nข้อความรอบก่อนใช้ไม่ได้เพราะมีตัวเลข {checked.matched} ซึ่งเป็นคำตอบของข้อที่นักเรียนกำลังทำ "
                f"สร้างใหม่โดยห้ามมีตัวเลข {checked.matched} ทั้งในตัวอย่างและผลลัพธ์")
    return None


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
    memory = knowledge_memory(subject)
    frames = {"role": system, "task": user}
    if memory:
        # ประเมินโดยเห็นเอกสารของครูทั้งหมด เช่น นิยามและลำดับขั้นที่ครูใช้สอน
        system = f"{system}\n\n<knowledge>\n{memory}\n</knowledge>"
        frames["knowledge"] = f"ส่งเอกสารของติวเตอร์ทั้งหมด {len(memory):,} ตัวอักษรไปใน system prompt"
    result, errors = await _call(system, user, max_tokens=400, json_mode=True, timeout=40.0)
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
