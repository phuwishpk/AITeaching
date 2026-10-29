"""ค่าตั้งค่าระบบ: API key, Provider, พารามิเตอร์ของกลไก และ Demo Mode

API key เก็บในไฟล์ runtime/secrets.json (ไม่ขึ้น git) ถ้ามีตัวแปร environment
ANTHROPIC_API_KEY หรือ GEMINI_API_KEY จะใช้ค่านั้นแทน และหน้าเว็บเห็นแค่ 4 ตัวท้าย
มีผู้ใช้หลายคน: API key Provider โมเดล พารามิเตอร์ และ Demo Mode เป็นของแต่ละคน ตั้งแล้วไม่กระทบคนอื่น
"""

import json
import os
from contextvars import ContextVar

from . import db
from .config import (
    CLAUDE_DEFAULT_MODEL,
    DEFAULT_PARAMS,
    GEMINI_DEFAULT_MODEL,
    SECRETS_PATH,
)

ENV_KEYS = {"claude": ("ANTHROPIC_API_KEY",), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}

# เมื่อมีผู้ใช้ฝั่งครูหลายคน (users.py) API key เป็นของแต่ละคน: คำขอที่กำลังทำงานคิดกับ key ของผู้ใช้ในตัวแปรนี้
# ตั้งที่ deps.require (ผู้ใช้ที่ล็อกอิน) gems API (เจ้าของ Gem) และ services (เจ้าของ Gem ที่นักเรียนกำลังเรียน)
# งานเบื้องหลังที่สร้างด้วย asyncio.create_task ได้ค่าเดียวกันไปด้วย
_key_owner: ContextVar[str | None] = ContextVar("key_owner", default=None)


def use_keys_of(username: str | None) -> None:
    _key_owner.set(username)


def key_owner() -> str | None:
    return _key_owner.get()


def _per_user() -> bool:
    return db.query_one("SELECT 1 AS x FROM staff LIMIT 1") is not None


def _read_file() -> dict:
    if SECRETS_PATH.exists():
        try:
            return json.loads(SECRETS_PATH.read_text("utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def api_key(provider: str) -> tuple[str | None, str]:
    """คืนค่า (key, ที่มา) โดย environment มีสิทธิ์เหนือไฟล์ เมื่อมีผู้ใช้หลายคน ใช้เฉพาะ key ของเจ้าของงานนี้"""
    if _per_user():
        owner = _key_owner.get()
        value = ((_read_file().get("users") or {}).get(owner) or {}).get(provider) if owner else None
        return (value, "user") if value else (None, "none")
    for name in ENV_KEYS.get(provider, ()):
        if os.environ.get(name):
            return os.environ[name], "env"
    value = _read_file().get(provider)
    return (value, "file") if value else (None, "none")


def save_api_key(provider: str, value: str | None) -> None:
    data = _read_file()
    target = data
    if _per_user():
        owner = _key_owner.get()
        if not owner:
            raise PermissionError("ต้องล็อกอินเป็นผู้ใช้ก่อนใส่ API key")
        target = data.setdefault("users", {}).setdefault(owner, {})
    if value:
        target[provider] = value.strip()
    else:
        target.pop(provider, None)
    _write_file(data)


def claim_shared_keys(username: str) -> list[str]:
    """ย้าย API key กลาง (ก่อนมีผู้ใช้หลายคน) ไปเป็นของผู้ใช้คนนี้"""
    data = _read_file()
    moved = [p for p in ENV_KEYS if data.get(p)]
    mine = data.setdefault("users", {}).setdefault(username, {})
    for provider in moved:
        mine.setdefault(provider, data.pop(provider))
    _write_file(data)
    return moved


def _write_file(data: dict) -> None:
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(data, indent=2), "utf-8")
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def masked(provider: str) -> dict:
    key, source = api_key(provider)
    return {"configured": bool(key), "source": source, "last4": key[-4:] if key else None}


def _setting_key(name: str, owner: str | None = None) -> str:
    """ค่าตั้งของผู้ใช้แต่ละคนเก็บชื่อ name:ผู้ใช้ (ผู้ใช้ = เจ้าของงานนี้ เหมือน API key)"""
    owner = owner or _key_owner.get()
    return f"{name}:{owner}" if owner and _per_user() else name


def _stored(name: str, owner: str | None = None) -> dict:
    """ค่าที่ผู้ใช้ตั้งไว้ ยังไม่เคยตั้งใช้ค่ากลางเดิม (ก่อนมีผู้ใช้หลายคน)"""
    key = _setting_key(name, owner)
    value = db.get_setting(key)
    if value is None and key != name:
        value = db.get_setting(name)
    return value or {}


def ai_settings(owner: str | None = None) -> dict:
    stored = _stored("ai", owner)
    return {
        "active": stored.get("active", "claude"),
        "order": stored.get("order", ["claude", "gemini"]),
        "claude_model": stored.get("claude_model", CLAUDE_DEFAULT_MODEL),
        "gemini_model": stored.get("gemini_model", GEMINI_DEFAULT_MODEL),
        # งานสร้างบทเรียน (อ่านเอกสาร สร้างคลัง ออกแบบและตรวจ Flow) เรียกไม่กี่ครั้ง ใช้โมเดลที่ฉลาดกว่าแชตได้
        "gemini_design_model": stored.get("gemini_design_model") or stored.get("gemini_model", GEMINI_DEFAULT_MODEL),
    }


def save_ai_settings(updates: dict) -> dict:
    current = ai_settings()
    for key in ("active", "order", "claude_model", "gemini_model", "gemini_design_model"):
        if key in updates and updates[key] is not None:
            current[key] = updates[key]
    db.set_setting(_setting_key("ai"), current)
    return current


def params(owner: str | None = None) -> dict:
    stored = _stored("params", owner)
    return {**DEFAULT_PARAMS, **{k: v for k, v in stored.items() if k in DEFAULT_PARAMS}}


def save_params(updates: dict) -> dict:
    stored = dict(_stored("params"))
    for key, value in updates.items():
        if key in DEFAULT_PARAMS and value is not None:
            stored[key] = float(value)
    db.set_setting(_setting_key("params"), stored)
    return params()


def demo(owner: str | None = None) -> dict:
    stored = _stored("demo", owner)
    return {"enabled": stored.get("enabled", False), "time_scale": stored.get("time_scale", 0.2)}


def cohort(owner: str | None = None) -> dict:
    """นักเรียนจำลอง (Simulated Cohort) ของผู้ใช้: ปิดแล้วระบบไม่สร้างให้อีก ทั้งตอนเริ่มเซิร์ฟเวอร์และตอนสร้างคลังโจทย์"""
    return {"enabled": _stored("cohort", owner).get("enabled", True)}


def save_cohort(enabled: bool) -> dict:
    db.set_setting(_setting_key("cohort"), {"enabled": bool(enabled)})
    return cohort()


def time_scale() -> float:
    d = demo()
    return float(d["time_scale"]) if d["enabled"] else 1.0


def save_demo(updates: dict) -> dict:
    current = demo()
    current.update({k: v for k, v in updates.items() if k in ("enabled", "time_scale") and v is not None})
    db.set_setting(_setting_key("demo"), current)
    return current

