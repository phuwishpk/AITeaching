from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from .deps import current, issue_token, revoke_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class StudentLogin(BaseModel):
    code: str


class StaffLogin(BaseModel):
    role: str


@router.post("/student")
def login_student(body: StudentLogin):
    code = body.code.strip().upper()
    row = db.query_one("SELECT code, kind FROM students WHERE code = ?", (code,))
    if not row or row["kind"] not in ("real", "demo"):
        raise HTTPException(404, "ไม่พบรหัสนี้ ขอรหัสจากครูประจำวิชาได้เลย")
    return {"token": issue_token("student", code), "role": "student", "code": code}


@router.post("/staff")
def login_staff(body: StaffLogin):
    """ครูและ Admin เข้าได้ทันทีโดยไม่ใช้ PIN แต่ละบทบาทยังได้ token ของตัวเอง สิทธิ์จึงแยกกันเหมือนเดิม"""
    if body.role not in ("teacher", "admin"):
        raise HTTPException(400, "บทบาทไม่ถูกต้อง")
    return {"token": issue_token(body.role), "role": body.role}


@router.get("/me")
def me(auth: dict = Depends(current)):
    return {"role": auth["role"], "code": auth.get("code")}


@router.post("/logout")
def logout(auth: dict = Depends(current)):
    revoke_token(auth["token"])
    return {"ok": True}

