"""ค่าตั้งค่าระบบ: API key, Provider, พารามิเตอร์ของกลไก, Demo Mode และ PIN

API key เก็บในไฟล์ runtime/secrets.json (ไม่ขึ้น git) ถ้ามีตัวแปร environment
ANTHROPIC_API_KEY หรือ GEMINI_API_KEY จะใช้ค่านั้นแทน และหน้าเว็บเห็นแค่ 4 ตัวท้าย
"""

import hashlib
import json
import os
import secrets as pysecrets

from . import db
from .config import (
    CLAUDE_DEFAULT_MODEL,
    DEFAULT_PARAMS,
    DEFAULT_PINS,
    GEMINI_DEFAULT_MODEL,
    SECRETS_PATH,
)

ENV_KEYS = {"claude": ("ANTHROPIC_API_KEY",), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}


def _read_file() -> dict:
    if SECRETS_PATH.exists():
        try:
            return json.loads(SECRETS_PATH.read_text("utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def api_key(provider: str) -> tuple[str | None, str]:
    """คืนค่า (key, ที่มา) โดย environment มีสิทธิ์เหนือไฟล์"""
    for name in ENV_KEYS.get(provider, ()):
        if os.environ.get(name):
            return os.environ[name], "env"
    value = _read_file().get(provider)
    return (value, "file") if value else (None, "none")


def save_api_key(provider: str, value: str | None) -> None:
    data = _read_file()
    if value:
        data[provider] = value.strip()
    else:
        data.pop(provider, None)
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(data, indent=2), "utf-8")
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def masked(provider: str) -> dict:
    key, source = api_key(provider)
    return {"configured": bool(key), "source": source, "last4": key[-4:] if key else None}


def ai_settings() -> dict:
    stored = db.get_setting("ai", {}) or {}
    return {
        "active": stored.get("active", "claude"),
        "order": stored.get("order", ["claude", "gemini"]),
        "claude_model": stored.get("claude_model", CLAUDE_DEFAULT_MODEL),
        "gemini_model": stored.get("gemini_model", GEMINI_DEFAULT_MODEL),
    }


def save_ai_settings(updates: dict) -> dict:
    current = ai_settings()
    for key in ("active", "order", "claude_model", "gemini_model"):
        if key in updates and updates[key] is not None:
            current[key] = updates[key]
    db.set_setting("ai", current)
    return current


def params() -> dict:
    stored = db.get_setting("params", {}) or {}
    return {**DEFAULT_PARAMS, **{k: v for k, v in stored.items() if k in DEFAULT_PARAMS}}


def save_params(updates: dict) -> dict:
    stored = db.get_setting("params", {}) or {}
    for key, value in updates.items():
        if key in DEFAULT_PARAMS and value is not None:
            stored[key] = float(value)
    db.set_setting("params", stored)
    return params()


def demo() -> dict:
    stored = db.get_setting("demo", {}) or {}
    return {"enabled": stored.get("enabled", False), "time_scale": stored.get("time_scale", 0.2)}


def time_scale() -> float:
    d = demo()
    return float(d["time_scale"]) if d["enabled"] else 1.0


def save_demo(updates: dict) -> dict:
    current = demo()
    current.update({k: v for k, v in updates.items() if k in ("enabled", "time_scale") and v is not None})
    db.set_setting("demo", current)
    return current


def _hash(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()


def check_pin(role: str, pin: str) -> bool:
    stored = db.get_setting(f"pin_{role}")
    if not stored:
        return pin == DEFAULT_PINS.get(role)
    return pysecrets.compare_digest(stored["hash"], _hash(pin, stored["salt"]))


def set_pin(role: str, pin: str) -> None:
    salt = pysecrets.token_hex(8)
    db.set_setting(f"pin_{role}", {"salt": salt, "hash": _hash(pin, salt)})


def pin_is_default(role: str) -> bool:
    return db.get_setting(f"pin_{role}") is None
