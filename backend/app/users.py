"""ผู้ใช้ฝั่งครูและ Admin: หลายคนใช้เว็บเดียวกัน แต่ละคนมีรหัสผ่าน ข้อมูล และ API key ของตัวเอง

แต่ละคนเห็นเฉพาะ Gem นักเรียน และข้อมูลการเรียนของตัวเอง (scope.py) ตั้งค่า AI และ API key ได้เฉพาะของตัวเอง
AI ของ Gem คิดกับ API key ของเจ้าของ Gem เสมอ (settings_store.use_keys_of) จึงไม่มีใครใช้ key ของคนอื่น
ยังไม่มีผู้ใช้ในตาราง staff = โหมดเดิม: เข้าหน้าครูและ Admin ได้ทันที (หรือใช้รหัสจาก .env) เห็นทุกอย่าง และใช้ API key กลาง

ใช้จาก command line บนเซิร์ฟเวอร์:
  python -m app.users add <ชื่อผู้ใช้> "<ชื่อที่แสดง>"   สร้างผู้ใช้และสุ่มรหัสผ่าน
  python -m app.users passwd <ชื่อผู้ใช้>                สุ่มรหัสผ่านใหม่
  python -m app.users claim <ชื่อผู้ใช้>                 ให้ Gem นักเรียนที่ยังไม่มีเจ้าของ และ API key กลางเดิม เป็นของผู้ใช้นี้
  python -m app.users list
"""

import hashlib
import re
import secrets
import sys
import time

from . import db, settings_store

ITERATIONS = 200_000


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()


def exist() -> bool:
    return db.query_one("SELECT 1 AS x FROM staff LIMIT 1") is not None


def listing() -> list[dict]:
    return db.query("SELECT username, name, created_at FROM staff ORDER BY created_at")


def first() -> str | None:
    """ผู้ใช้คนแรก: เจ้าของข้อมูลที่เกิดก่อนมีผู้ใช้หลายคน"""
    row = db.query_one("SELECT username FROM staff ORDER BY created_at LIMIT 1")
    return row["username"] if row else None


def get(username: str | None) -> dict | None:
    return db.query_one("SELECT username, name FROM staff WHERE username = ?", (username,)) if username else None


def verify(username: str, password: str) -> dict | None:
    row = db.query_one("SELECT * FROM staff WHERE username = ?", ((username or "").strip().lower(),))
    if not row:
        return None
    salt, digest = row["password_hash"].split("$", 1)
    if not secrets.compare_digest(_hash(password or "", salt), digest):
        return None
    return {"username": row["username"], "name": row["name"]}


def set_password(username: str, password: str | None = None) -> str:
    password = password or secrets.token_urlsafe(9)
    salt = secrets.token_hex(8)
    db.execute("UPDATE staff SET password_hash = ? WHERE username = ?", (f"{salt}${_hash(password, salt)}", username))
    return password


def add(username: str, name: str, password: str | None = None) -> str:
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,31}", username):
        raise ValueError("ชื่อผู้ใช้ใช้ได้แค่ a-z 0-9 . _ - ยาว 2–32 ตัว")
    if get(username):
        raise ValueError(f"มีผู้ใช้ {username} แล้ว")
    db.execute("INSERT INTO staff (username, name, password_hash, created_at) VALUES (?, ?, '', ?)",
               (username, name.strip() or username, time.time()))
    return set_password(username, password)


def claim(username: str) -> tuple[int, list[str]]:
    """Gem นักเรียน และบันทึก AI ที่เกิดก่อนมีผู้ใช้ และ API key กลางเดิม เป็นของผู้ใช้คนนี้"""
    count = db.adopt_orphans(username)
    moved = settings_store.claim_shared_keys(username)
    return count, moved


def owner_name(username: str | None) -> str | None:
    user = get(username)
    return user["name"] if user else None


def main(argv: list[str]) -> int:
    command, *args = argv or ["list"]
    if command == "add" and args:
        password = add(args[0], args[1] if len(args) > 1 else args[0])
        print(f"{args[0].lower()}\t{password}")
    elif command == "passwd" and args:
        if not get(args[0].lower()):
            print("ไม่พบผู้ใช้นี้")
            return 1
        print(f"{args[0].lower()}\t{set_password(args[0].lower())}")
    elif command == "claim" and args:
        count, moved = claim(args[0].lower())
        print(f"ติวเตอร์ที่ยังไม่มีเจ้าของ {count} ตัว และ API key กลาง {', '.join(moved) or '-'} เป็นของ {args[0].lower()} แล้ว")
    elif command == "list":
        for row in listing():
            print(f"{row['username']}\t{row['name']}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    db.connect()
    sys.exit(main(sys.argv[1:]))
