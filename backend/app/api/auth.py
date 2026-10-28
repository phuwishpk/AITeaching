import asyncio
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db, users
from .deps import current, issue_token, revoke_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class StudentLogin(BaseModel):
    code: str


class StaffLogin(BaseModel):
    role: str
    username: str | None = None
    password: str | None = None


class AccountLogin(BaseModel):
    username: str
    password: str


# รหัสผ่านของครูและ Admin ตั้งในไฟล์ .env บนเซิร์ฟเวอร์ (run.sh โหลดให้) ไม่อยู่ใน repo
# ไม่ได้ตั้ง (เช่นรันในเครื่องตัวเองตอนสาธิต) เข้าได้ทันทีโดยไม่ใช้รหัสเหมือนเดิม
PASSWORD_ENV = {"teacher": "TUTOR_TEACHER_PASSWORD", "admin": "TUTOR_ADMIN_PASSWORD"}


def staff_password(role: str) -> str | None:
    return os.environ.get(PASSWORD_ENV.get(role, ""), "").strip() or None


@router.get("/staff-mode")
def staff_mode():
    """บทบาทไหนต้องใส่รหัสผ่าน และต้องใส่ชื่อผู้ใช้ไหม (มีผู้ใช้หลายคน) หน้าเว็บใช้ตัดสินว่าจะแสดงช่องอะไร"""
    if users.exist():
        return {"teacher": True, "admin": True, "users": True}
    return {**{role: staff_password(role) is not None for role in PASSWORD_ENV}, "users": False}


@router.post("/student")
def login_student(body: StudentLogin):
    code = body.code.strip().upper()
    row = db.query_one("SELECT code, kind FROM students WHERE code = ?", (code,))
    if not row or row["kind"] not in ("real", "demo"):
        raise HTTPException(404, "ไม่พบรหัสนี้ ขอรหัสจากครูประจำวิชาได้เลย")
    return {"token": issue_token("student", code), "role": "student", "code": code}


@router.post("/staff")
async def login_staff(body: StaffLogin):
    """ครูและ Admin: ใส่รหัสผ่านเมื่อเซิร์ฟเวอร์ตั้งไว้ แต่ละบทบาทได้ token ของตัวเอง สิทธิ์จึงแยกกันเหมือนเดิม"""
    if body.role not in PASSWORD_ENV:
        raise HTTPException(400, "บทบาทไม่ถูกต้อง")
    if users.exist():
        # หลายผู้ใช้: ทุกคนเข้าได้ทั้งหน้าครูและ Admin แต่เห็นเฉพาะข้อมูลและ API key ของตัวเอง (scope.py)
        user = await _verify(body.username or "", body.password or "")
        return {"token": issue_token(body.role, user["username"]), "role": body.role, "code": user["username"],
                "name": user["name"]}
    expected = staff_password(body.role)
    if expected and not secrets.compare_digest((body.password or "").encode(), expected.encode()):
        await asyncio.sleep(1.0)  # ชะลอการเดารหัส
        raise HTTPException(401, "รหัสผ่านไม่ถูกต้อง" if body.password else "ใส่รหัสผ่านก่อนเข้า")
    return {"token": issue_token(body.role), "role": body.role}


async def _verify(username: str, password: str) -> dict:
    user = users.verify(username, password)
    if user is None:
        await asyncio.sleep(1.0)  # ชะลอการเดารหัส
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return user


@router.post("/login")
async def login_account(body: AccountLogin):
    """หน้าแรกของเว็บ: บัญชีเดียวได้ token ทั้งหน้าครูและหน้า Admin ของผู้ใช้คนนี้"""
    if not users.exist():
        raise HTTPException(400, "เซิร์ฟเวอร์นี้ยังไม่มีบัญชีผู้ใช้ เข้าหน้าครูหรือ Admin ได้โดยตรง")
    user = await _verify(body.username, body.password)
    return {"username": user["username"], "name": user["name"],
            "tokens": {role: issue_token(role, user["username"]) for role in PASSWORD_ENV}}


@router.get("/me")
def me(auth: dict = Depends(current)):
    name = users.owner_name(auth.get("code")) if auth["role"] in ("teacher", "admin") else None
    return {"role": auth["role"], "code": auth.get("code"), "name": name}


@router.post("/logout")
def logout(auth: dict = Depends(current)):
    revoke_token(auth["token"])
    return {"ok": True}

