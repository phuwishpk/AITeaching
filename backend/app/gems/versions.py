"""Gem Version: สำเนาของ Gem ทุกครั้งที่ครูบันทึกหรือ AI สร้างคลังโจทย์เสร็จ

เก็บว่าใครแก้ แก้อะไร เมื่อไร และคลังโจทย์รุ่นไหน ย้อนกลับได้ (Q15)
Session หนึ่งเรียนกับคลังรุ่นเดียวจนจบ เพราะคลังแต่ละรุ่นเป็น Subject แยก (ดู builder.py)
"""

import time

from .. import db

FIELDS = ("name", "description", "instructions", "icon", "color", "tools", "starter_prompts", "alert_rules")
BANK = ("bank_version", "subject_id", "set_id")
LABELS = {
    "name": "ชื่อ", "description": "คำอธิบาย", "instructions": "คำสั่ง", "icon": "ไอคอน", "color": "สี",
    "tools": "เครื่องมือเริ่มต้น", "starter_prompts": "คำถามเริ่มต้น", "alert_rules": "การแจ้งเตือน",
}


def snapshot(gem: dict) -> dict:
    return {key: gem.get(key) for key in FIELDS + BANK}


def record(gem: dict, actor: str, note: str) -> int:
    latest = db.query_one("SELECT MAX(n) AS n FROM gem_versions WHERE gem_id = ?", (gem["id"],))
    n = (latest["n"] or 0) + 1
    db.execute("INSERT INTO gem_versions (gem_id, n, ts, actor, note, data) VALUES (?,?,?,?,?,?)",
               (gem["id"], n, time.time(), actor, note, db.dumps(snapshot(gem))))
    return n


def changes(before: dict, after: dict) -> list[str]:
    return [LABELS[key] for key in FIELDS if before.get(key) != after.get(key)]


def history(gem_id: str) -> list[dict]:
    rows = db.query("SELECT n, ts, actor, note, data FROM gem_versions WHERE gem_id = ? ORDER BY n DESC", (gem_id,))
    for row in rows:
        data = db.loads(row.pop("data"), {})
        row["bank_version"] = data.get("bank_version")
    return rows


def get(gem_id: str, n: int) -> dict | None:
    row = db.query_one("SELECT data FROM gem_versions WHERE gem_id = ? AND n = ?", (gem_id, n))
    return db.loads(row["data"]) if row else None


def at(gem_id: str, ts: float) -> int | None:
    """เวอร์ชันที่ใช้อยู่ ณ เวลาหนึ่ง เช่น ตอนนักเรียนเริ่ม Session"""
    row = db.query_one("SELECT MAX(n) AS n FROM gem_versions WHERE gem_id = ? AND ts <= ?", (gem_id, ts + 0.001))
    return row["n"] if row else None
