"""Readiness Check: ตรวจ Question Set ก่อนเปิดใช้

ตรวจว่ามีองค์ประกอบครบตามที่ตรรกะของระบบต้องใช้
error = เปิดใช้ไม่ได้, warning = เปิดใช้ได้แต่บางกลไกจะทำงานไม่เต็มที่
"""

from ..tutor import guard


def check_set(subject: dict, set_id: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    qs = next((q for q in subject.get("question_sets", []) if q["id"] == set_id), None)
    if qs is None:
        return {"ok": False, "errors": ["ไม่พบชุดคำถามนี้"], "warnings": []}
    items = {it["id"]: it for it in subject.get("items", [])}
    concepts = {c["id"]: c for c in subject.get("concepts", [])}
    target = qs.get("target_concept")
    if target not in concepts:
        errors.append("ยังไม่ได้เลือก Target Concept หรือ Concept นั้นไม่มีอยู่")
    mains = [items[i] for i in qs.get("main_items", []) if i in items]
    missing = [i for i in qs.get("main_items", []) if i not in items]
    if missing:
        errors.append(f"มีโจทย์หลักที่ไม่พบในคลัง: {', '.join(missing)}")
    if not mains:
        errors.append("ต้องมีโจทย์หลักอย่างน้อย 1 ข้อ")

    formats = set()
    for it in mains:
        label = f"โจทย์ {it['id']}"
        formats.add(it.get("format"))
        hints = it.get("hints", {})
        for level in ("1", "2", "3"):
            if not (hints.get(level) or "").strip():
                errors.append(f"{label} ยังไม่มีคำใบ้ระดับ {level}")
            else:
                leaked = guard.check(hints[level], it)
                if leaked.blocked and not leaked.trigger:
                    warnings.append(f"{label} คำใบ้ระดับ {level} อาจบอกคำตอบ ({leaked.reason}: {leaked.matched})")
        if not _has_answer(it):
            errors.append(f"{label} ยังไม่ได้กำหนดคำตอบที่ถูก")
        isos = [items[i] for i in it.get("isomorphs", []) if i in items]
        if not isos:
            errors.append(f"{label} ยังไม่มี Isomorphic Item")
        elif len(isos) < 2:
            warnings.append(f"{label} มี Isomorphic Item 1 ข้อ ควรมีอย่างน้อย 2 ข้อ (สอบคู่ขนานได้ 2 รอบ)")
        for iso in isos:
            formats.add(iso.get("format"))
    if mains and len(formats) < 2:
        warnings.append("โจทย์ของ Target Concept มีรูปแบบคำตอบเดียว Cross-Format Check จะยังทำงานไม่ได้")

    if target in concepts:
        prereqs = concepts[target].get("prerequisites", [])
        for prereq in prereqs:
            remedial = [it for it in items.values() if it["concept"] == prereq and it["kind"] == "remedial"]
            name = concepts.get(prereq, {}).get("name", prereq)
            if not remedial:
                warnings.append(f"Prerequisite \"{name}\" ยังไม่มี Remedial Item ระบบจะเลือก Prerequisite อื่นแทน")
            elif len(remedial) < 3:
                warnings.append(f"Prerequisite \"{name}\" มี Remedial Item {len(remedial)} ข้อ ควรมีอย่างน้อย 3 ข้อสำหรับ 2 รอบ")
        walks = {w["concept"] for w in subject.get("walkthroughs", [])}
        for concept_id in [target] + prereqs:
            if concept_id not in walks:
                warnings.append(f"\"{concepts.get(concept_id, {}).get('name', concept_id)}\" ยังไม่มี Walkthrough Example")
    if not qs.get("challenge_items"):
        warnings.append("ยังไม่มี Challenge Item เส้นทาง Fast-Track จะใช้โจทย์หลักแทน")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _has_answer(item: dict) -> bool:
    answer = item.get("answer") or {}
    if item.get("format") == "numeric":
        return "value" in answer and answer["value"] is not None
    if item.get("format") == "mcq":
        return bool(answer.get("option")) and any(o["id"] == answer["option"] for o in item.get("options", []))
    return bool(answer.get("accepted"))
