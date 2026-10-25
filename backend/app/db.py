"""ฐานข้อมูล SQLite ของระบบ

เก็บทุกอย่างไว้ในไฟล์เดียวใต้ runtime/ (ไม่ขึ้น git) ใช้ sqlite3 ของ Python ตรง ๆ
เพื่อให้อ่านโค้ดแล้วเห็นว่าข้อมูลแต่ละอย่างอยู่ตรงไหน
ชื่อจริงของนักเรียนอยู่ในตาราง roster เท่านั้น ตารางอื่นใช้ Student Code
"""

import json
import sqlite3
import threading
import time
from typing import Any

from .config import DB_PATH, RUNTIME

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id TEXT, filename TEXT, kind TEXT,
    chars INTEGER, chunks TEXT, warning TEXT, uploaded_at REAL, reader TEXT
);
CREATE TABLE IF NOT EXISTS students (
    code TEXT PRIMARY KEY, kind TEXT DEFAULT 'real', persona TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS roster (
    code TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS states (
    code TEXT, set_id TEXT, data TEXT, updated_at REAL, PRIMARY KEY (code, set_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, set_id TEXT,
    started_at REAL, ended_at REAL, end_reason TEXT, items INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, action TEXT, target TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, set_id TEXT,
    from_pos TEXT, to_pos TEXT, edges TEXT, rule TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, level TEXT, kind TEXT,
    message TEXT, acknowledged INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor TEXT, code TEXT, action TEXT,
    reason TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS ai_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, purpose TEXT, provider TEXT,
    model TEXT, frames TEXT, retrieved TEXT, output TEXT, final_text TEXT, guard TEXT,
    tokens_in INTEGER, tokens_out INTEGER, latency_ms INTEGER, error TEXT
);
CREATE TABLE IF NOT EXISTS suggested_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, item_id TEXT, answer TEXT,
    tag TEXT, rationale TEXT, status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY, role TEXT, code TEXT, created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_traces_code ON traces (code, ts);
CREATE INDEX IF NOT EXISTS idx_decisions_code ON decisions (code, ts);
CREATE INDEX IF NOT EXISTS idx_ai_logs_ts ON ai_logs (ts);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, set_id TEXT, sender TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_code ON messages (code, ts);
CREATE TABLE IF NOT EXISTS chat_modes (
    code TEXT PRIMARY KEY, mode TEXT, since REAL
);
CREATE TABLE IF NOT EXISTS gems (
    id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS gem_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, gem_id TEXT, n INTEGER, ts REAL, actor TEXT, note TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS idx_gem_versions ON gem_versions (gem_id, n);
CREATE TABLE IF NOT EXISTS teacher_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, code TEXT, kind TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_teacher_actions ON teacher_actions (code, ts);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        _migrate(_conn)
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """คอลัมน์ที่เพิ่มทีหลังในฐานข้อมูลเดิม"""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
    if "reader" not in columns:
        conn.execute("ALTER TABLE documents ADD COLUMN reader TEXT")


def use_memory_db() -> None:
    """ใช้ฐานข้อมูลในหน่วยความจำ (สำหรับ test)"""
    global _conn
    _conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)


def execute(sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
    with _lock:
        return connect().execute(sql, params)


def executemany(sql: str, rows: list[tuple]) -> None:
    with _lock:
        conn = connect()
        conn.execute("BEGIN")
        conn.executemany(sql, rows)
        conn.execute("COMMIT")


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in connect().execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    with _lock:
        row = connect().execute(sql, params).fetchone()
        return dict(row) if row else None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    return json.loads(text)


# ---------- settings ----------

def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return loads(row["value"]) if row else default


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, dumps(value)),
    )


# ---------- subjects ----------

def get_subject(subject_id: str) -> dict | None:
    row = query_one("SELECT data FROM subjects WHERE id = ?", (subject_id,))
    return loads(row["data"]) if row else None


def list_subjects() -> list[dict]:
    return [loads(r["data"]) for r in query("SELECT data FROM subjects ORDER BY id")]


def save_subject(subject: dict) -> None:
    execute(
        "INSERT INTO subjects (id, data, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (subject["id"], dumps(subject), time.time()),
    )


def delete_subject(subject_id: str) -> None:
    execute("DELETE FROM subjects WHERE id = ?", (subject_id,))


# ---------- gems ----------

def get_gem(gem_id: str) -> dict | None:
    row = query_one("SELECT data FROM gems WHERE id = ?", (gem_id,))
    return loads(row["data"]) if row else None


def list_gems() -> list[dict]:
    return [loads(r["data"]) for r in query("SELECT data FROM gems ORDER BY updated_at DESC")]


def save_gem(gem: dict) -> None:
    execute(
        "INSERT INTO gems (id, data, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (gem["id"], dumps(gem), time.time()),
    )


def delete_gem(gem_id: str) -> None:
    execute("DELETE FROM gems WHERE id = ?", (gem_id,))
    execute("DELETE FROM gem_versions WHERE gem_id = ?", (gem_id,))


# ---------- student states ----------

def load_state(code: str, set_id: str) -> dict | None:
    row = query_one("SELECT data FROM states WHERE code = ? AND set_id = ?", (code, set_id))
    return loads(row["data"]) if row else None


def save_state(state: dict) -> None:
    execute(
        "INSERT INTO states (code, set_id, data, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(code, set_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (state["code"], state["set_id"], dumps(state), time.time()),
    )


def all_states() -> list[dict]:
    return [loads(r["data"]) for r in query("SELECT data FROM states")]


def states_for(code: str) -> list[dict]:
    return [loads(r["data"]) for r in query("SELECT data FROM states WHERE code = ?", (code,))]
