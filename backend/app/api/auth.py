from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db, settings_store
from .deps import current, issue_token, revoke_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class StudentLogin(BaseModel):
    code: str


class StaffLogin(BaseModel):
    role: str
    pin: str


@router.post("/student")
def login_student(body: StudentLogin):
    code = body.code.strip().upper()
    row = db.query_one("SELECT code, kind FROM students WHERE code = ?", (code,))
    if not row or row["kind"] not in ("real", "demo"):
        raise HTTPException(404, "ไม่พบรหัสนี้ ขอรหัสจากครูประจำวิชาได้เลย")
    return {"token": issue_token("student", code), "role": "student", "code": code}


@router.post("/staff")
def login_staff(body: StaffLogin):
    if body.role not in ("teacher", "admin"):
        raise HTTPException(400, "บทบาทไม่ถูกต้อง")
    if not settings_store.check_pin(body.role, body.pin.strip()):
        raise HTTPException(401, "PIN ไม่ถูกต้อง")
    return {"token": issue_token(body.role), "role": body.role}


@router.get("/me")
def me(auth: dict = Depends(current)):
    return {"role": auth["role"], "code": auth.get("code")}


@router.post("/logout")
def logout(auth: dict = Depends(current)):
    revoke_token(auth["token"])
    return {"ok": True}


@router.get("/pin-hints")
def pin_hints():
    """บอกหน้าเข้าสู่ระบบว่ายังใช้ PIN เริ่มต้นอยู่หรือไม่ (เพื่อแสดงคำแนะนำตอนสาธิต)"""
    return {role: settings_store.pin_is_default(role) for role in ("teacher", "admin")}
