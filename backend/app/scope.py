"""ข้อมูลของใครของมัน: ผู้ใช้ฝั่งครูแต่ละคนเห็นเฉพาะ Gem นักเรียน และข้อมูลการเรียนของตัวเอง

นักเรียนแต่ละคนมีเจ้าของคนเดียว (students.owner): ครูที่เพิ่มรหัสใน Roster หรือเจ้าของ Gem สำหรับนักเรียนทดสอบ
นักเรียนสาธิต และนักเรียนจำลอง นักเรียนเรียนได้เฉพาะ Gem ของเจ้าของ ข้อมูลการเรียนทุกตาราง (states traces
decisions alerts messages ai_logs …) ผูกกับ Student Code การกรองจึงใช้เงื่อนไขเดียว: นักเรียนที่ผู้ใช้เป็นเจ้าของ

ยังไม่มีผู้ใช้ในตาราง staff (โหมดเดิม รันในเครื่องตัวเองและใน test) ผู้ใช้เป็น None = ไม่กรอง เห็นทุกอย่าง
"""

from fastapi import HTTPException

from . import db, users


def of(auth: dict) -> str | None:
    """ผู้ใช้ที่ต้องกรองข้อมูลให้ (None = เห็นทุกอย่าง)"""
    if auth.get("role") not in ("teacher", "admin") or not users.exist():
        return None
    return auth.get("code")


def student_owner(code: str | None) -> str | None:
    row = db.query_one("SELECT owner FROM students WHERE code = ?", (code,)) if code else None
    return row["owner"] if row else None


def sees(user: str | None, code: str | None) -> bool:
    return user is None or (code is not None and student_owner(code) == user)


def student(auth: dict, code: str) -> None:
    """นักเรียนของคนอื่นตอบเหมือนไม่มีรหัสนี้ ไม่บอกว่ามีอยู่"""
    if not sees(of(auth), code):
        raise HTTPException(404, "ไม่พบนักเรียนรหัสนี้")


def where(user: str | None, column: str = "code") -> tuple[str, tuple]:
    """เงื่อนไข SQL: แถวที่เป็นของนักเรียนของผู้ใช้"""
    if user is None:
        return "1 = 1", ()
    return f"{column} IN (SELECT code FROM students WHERE owner = ?)", (user,)


def codes(user: str | None) -> set[str] | None:
    """Student Code ของผู้ใช้ (None = ไม่กรอง)"""
    if user is None:
        return None
    return {r["code"] for r in db.query("SELECT code FROM students WHERE owner = ?", (user,))}


def owns(user: str | None, gem: dict | None) -> bool:
    return user is None or bool(gem and gem.get("owner") == user)


def gems(user: str | None) -> list[dict]:
    return [g for g in db.list_gems() if owns(user, g)]


def gem(auth: dict, gem_id: str) -> dict | None:
    """Gem ของคนอื่นตอบเหมือนไม่มี Gem นี้"""
    found = db.get_gem(gem_id)
    if found and not owns(of(auth), found):
        raise HTTPException(404, "ไม่พบ Gem นี้")
    return found


def subject_owner(subject: dict | None) -> str | None:
    """เจ้าของคลังโจทย์ = เจ้าของ Gem (วิชาที่ครูเขียนเองแบบเดิมเก็บเจ้าของไว้ในวิชา)"""
    gem_id = ((subject or {}).get("gem") or {}).get("id")
    found = db.get_gem(gem_id) if gem_id else None
    return found.get("owner") if found else (subject or {}).get("owner")


def owns_subject(user: str | None, subject: dict | None) -> bool:
    return user is None or (subject is not None and subject_owner(subject) == user)


def subjects(user: str | None) -> list[dict]:
    if user is None:
        return db.list_subjects()
    mine = {g["id"] for g in gems(user)}
    return [s for s in db.list_subjects()
            if ((s.get("gem") or {}).get("id")) in mine or (not s.get("gem") and s.get("owner") == user)]


def subject(auth: dict, subject_id: str) -> dict | None:
    """วิชาของคนอื่นตอบเหมือนไม่มีวิชานี้"""
    found = db.get_subject(subject_id)
    if found and not owns_subject(of(auth), found):
        raise HTTPException(404, "ไม่พบวิชานี้")
    return found


def may_learn(code: str, subject: dict) -> bool:
    """นักเรียนเรียนได้เฉพาะ Gem ของครูเจ้าของ (โหมดเดิมเรียนได้ทุก Gem)"""
    return not users.exist() or subject_owner(subject) == student_owner(code)


def code_for(base: str, owner: str | None) -> str:
    """รหัสนักเรียนสาธิตและนักเรียนจำลองแยกตามเจ้าของ เพราะ Student Code ใช้ร่วมกันทั้งระบบ
    ผู้ใช้คนแรกใช้รหัสเดิม (DEMO-1, SIM-01) ข้อมูลที่มีอยู่แล้วจึงไม่เปลี่ยนชื่อ"""
    if owner is None or owner == users.first():
        return base
    return f"{base}-{owner.upper()}"
