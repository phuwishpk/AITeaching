"""Alert Rule ของ Gem: สถานการณ์ไหนแจ้งครู ระดับไหน และ "แจ้งอย่างเดียว" หรือ "หยุดรอครู" (Q3, Q13)

engine และ services ยังสร้างแจ้งเตือนตามกฎเดิม (core.alert) ไฟล์นี้แค่ตัดสินตอนบันทึกว่า Gem นี้
เปิดสถานการณ์นั้นไหม ใช้ระดับอะไร และต้องสลับแชตเป็นโหมดครู (AI ร่าง ครูอนุมัติก่อนส่ง) หรือไม่
ข้อความทำร้ายตนเองปิดไม่ได้และหยุดรอครูเสมอ
"""

LEVELS = ("urgent", "normal", "silent")
MODES = ("notify", "pause")

SITUATIONS = [
    {"key": "self_harm", "label": "ข้อความสื่อถึงการทำร้ายตนเอง", "kinds": ["self_harm"],
     "default": {"enabled": True, "level": "urgent", "mode": "pause"}, "locked": True},
    {"key": "ask_teacher", "label": "นักเรียนขอคุยกับครู", "kinds": ["ask_teacher"],
     "default": {"enabled": True, "level": "normal", "mode": "pause"}},
    {"key": "deadlock", "label": "ซ่อมเสริมครบรอบแล้วยังติด (Stagnation Deadlock)", "kinds": ["deadlock"],
     "default": {"enabled": True, "level": "normal", "mode": "notify"}},
    {"key": "stress", "label": "เครียดหรือท้อ (Circuit Breaker)", "kinds": ["stress"],
     "default": {"enabled": True, "level": "normal", "mode": "notify"}},
    {"key": "quit", "label": "บอกว่าไม่อยากเรียนต่อ", "kinds": ["quit"],
     "default": {"enabled": True, "level": "normal", "mode": "notify"}},
    {"key": "ai_outage", "label": "AI ขัดข้อง", "kinds": ["ai_outage"],
     "default": {"enabled": True, "level": "normal", "mode": "notify"}},
    {"key": "off_topic", "label": "ถามนอกบทเรียน AI ตอบให้ไม่ได้", "kinds": ["off_topic"],
     "default": {"enabled": True, "level": "silent", "mode": "notify"}},
    {"key": "new_misconception", "label": "คำตอบผิดแบบใหม่ที่ไม่อยู่ใน Bug Library", "kinds": ["new_misconception"],
     "default": {"enabled": True, "level": "silent", "mode": "notify"}},
    {"key": "guard_blocked", "label": "Answer-Leak Guard บล็อกคำตอบของ AI", "kinds": ["guard_blocked"],
     "default": {"enabled": True, "level": "silent", "mode": "notify"}},
    {"key": "burnout", "label": "สัญญาณหมดไฟ (พักบ่อย เดารัว Risk Score สูง)",
     "kinds": ["burnout_idle", "burnout_rapid", "burnout_risk"],
     "default": {"enabled": True, "level": "silent", "mode": "notify"}},
    {"key": "hint_abuse", "label": "กดขอคำใบ้รัว ๆ", "kinds": ["hint_abuse"],
     "default": {"enabled": True, "level": "silent", "mode": "notify"}},
    {"key": "cap", "label": "ครบเพดานข้อแล้วยังไม่ผ่านเกณฑ์", "kinds": ["cap"],
     "default": {"enabled": True, "level": "silent", "mode": "notify"}},
    # ขั้นใน Flow ที่ AI ออกแบบจากคำสั่งของครู (ADR-0004) ระดับของขั้นแจ้งครูมาจาก Flow เอง
    {"key": "flow_notify", "label": "ขั้น \"แจ้งครู\" ใน Flow ของ Gem", "kinds": ["flow_notify"],
     "default": {"enabled": True, "level": "normal", "mode": "notify"}},
    {"key": "flow_teacher", "label": "ขั้น \"หยุดรอครู\" ใน Flow ของ Gem", "kinds": ["flow_teacher"],
     "default": {"enabled": True, "level": "normal", "mode": "pause"}},
]

_BY_KIND = {kind: s for s in SITUATIONS for kind in s["kinds"]}
_BY_KEY = {s["key"]: s for s in SITUATIONS}


def defaults() -> dict:
    return {s["key"]: dict(s["default"]) for s in SITUATIONS}


def normalize(rules: dict | None) -> dict:
    """ค่าที่ครูตั้ง เติมค่าเริ่มต้นให้ครบ และบังคับสถานการณ์ที่ล็อกไว้"""
    out = defaults()
    for key, rule in (rules or {}).items():
        situation = _BY_KEY.get(key)
        if situation is None or situation.get("locked") or not isinstance(rule, dict):
            continue
        out[key] = {
            "enabled": bool(rule.get("enabled", out[key]["enabled"])),
            "level": rule.get("level") if rule.get("level") in LEVELS else out[key]["level"],
            "mode": rule.get("mode") if rule.get("mode") in MODES else out[key]["mode"],
        }
    return out


def resolve(gem: dict | None, kind: str) -> dict | None:
    """กฎที่ใช้กับแจ้งเตือนชนิดนี้ คืน None ถ้าครูปิดไว้ ชุดคำถามที่ไม่ใช่ Gem ใช้ค่าเริ่มต้นของระบบ"""
    situation = _BY_KIND.get(kind)
    if situation is None:
        return None
    rule = normalize((gem or {}).get("alert_rules"))[situation["key"]]
    return rule if rule["enabled"] else None


def catalog() -> list[dict]:
    """รายการสถานการณ์สำหรับหน้าตั้งค่า Gem"""
    return [{"key": s["key"], "label": s["label"], "locked": bool(s.get("locked"))} for s in SITUATIONS]
