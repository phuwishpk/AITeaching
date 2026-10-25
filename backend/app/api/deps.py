"""การเข้าระบบ: Student ใช้ Student Code, Teacher และ Admin เข้าได้ทันที แต่ละบทบาทใช้ token ของตัวเอง"""

import secrets
import time

from fastapi import Depends, Header, HTTPException

from .. import db, settings_store


def issue_token(role: str, code: str | None = None) -> str:
    token = secrets.token_urlsafe(24)
    db.execute("INSERT INTO tokens (token, role, code, created_at) VALUES (?,?,?,?)", (token, role, code, time.time()))
    return token


def resolve_token(token: str | None) -> dict | None:
    if not token:
        return None
    row = db.query_one("SELECT role, code FROM tokens WHERE token = ?", (token,))
    return row


def revoke_token(token: str):
    db.execute("DELETE FROM tokens WHERE token = ?", (token,))


def current(authorization: str | None = Header(default=None)) -> dict:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    auth = resolve_token(token)
    if not auth:
        raise HTTPException(401, "กรุณาเข้าสู่ระบบใหม่")
    return {**auth, "token": token}


def require(*roles: str):
    async def dependency(auth: dict = Depends(current)) -> dict:
        if auth["role"] not in roles:
            raise HTTPException(403, "บทบาทนี้เข้าหน้านี้ไม่ได้")
        # ครูและ Admin: งาน AI ของคำขอนี้คิดกับ API key ของผู้ใช้ที่ล็อกอิน (gems API เปลี่ยนเป็นเจ้าของ Gem)
        # dependency เป็น async จึงตั้งค่าใน context เดียวกับ endpoint
        if auth["role"] in ("teacher", "admin"):
            settings_store.use_keys_of(auth.get("code"))
        return auth

    return dependency
