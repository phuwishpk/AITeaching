"""ค่าตั้งต้นของระบบ: ที่อยู่ไฟล์ และพารามิเตอร์ของกลไกการสอน

ค่าทุกค่าใน DEFAULT_PARAMS ปรับได้จากหน้า Admin (บันทึกในตาราง settings)
ค่าที่อยู่ใน SCALED_PARAMS จะถูกคูณด้วย time_scale ตอนเปิด Demo Mode
ส่วนเกณฑ์ที่เกี่ยวกับความเร็วในการอ่านของคนจริง (เช่น Rapid Guess) ไม่ถูกย่อเวลา
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
DB_PATH = RUNTIME / "tutor.db"
SECRETS_PATH = RUNTIME / "secrets.json"
UPLOADS = RUNTIME / "uploads"
FRONTEND_DIST = ROOT / "frontend" / "dist"

DEFAULT_PARAMS: dict[str, float] = {
    # ด่าน 2 และการหน่วงเวลา (สเปก 2.3, 3.1)
    "deliberate_delay": 15,
    "rapid_guess_threshold": 3,
    "rapid_guess_lock": 15,
    # ปุ่มขอคำใบ้และการกันปั๊มคำใบ้ (สเปก 6.1)
    "hint_unlock_wait": 30,
    "hint_abuse_presses": 3,
    "hint_abuse_window": 10,
    "hint_abuse_cooldown": 10,
    # Data Cleaning และ Idle Pause
    "idle_timeout": 300,
    "rt_cap": 300,
    "duplicate_window": 1.0,
    # Mastery และ Learning Path
    "mastery_window": 5,
    "fast_track_mastery": 0.8,
    "standard_mastery": 0.5,
    "slip_mastery": 0.5,
    # Isomorphic Test และ Remedial Loop
    "iso_attempts": 2,
    "remedial_pass_streak": 2,
    "remedial_max_rounds": 2,
    "circuit_breaker_break": 60,
    "undo_window": 10,
    # เกณฑ์จบชุด
    "finish_mastery": 0.8,
    "finish_min_items": 3,
    "max_items": 20,
    # Burnout Signal และ Fuzzy Impasse
    "burnout_idle": 3,
    "burnout_rapid_streak": 3,
    "burnout_risk": 70,
    "impasse_threshold": 55,
}

SCALED_PARAMS = {
    "deliberate_delay",
    "rapid_guess_lock",
    "hint_unlock_wait",
    "hint_abuse_cooldown",
    "idle_timeout",
    "circuit_breaker_break",
}

PARAM_LABELS: dict[str, str] = {
    "deliberate_delay": "Deliberate Delay (วินาที)",
    "rapid_guess_threshold": "เวลาอ่านขั้นต่ำเริ่มต้น (วินาที)",
    "rapid_guess_lock": "ล็อกปุ่มตอบหลัง Rapid Guess (วินาที)",
    "hint_unlock_wait": "ปลดคำใบ้ก่อนลองตอบหลังคิด (วินาที)",
    "hint_abuse_presses": "จำนวนครั้งที่กดคำใบ้ติดกันจึงนับเป็น Hint Abuse",
    "hint_abuse_window": "ช่วงเวลาตรวจ Hint Abuse (วินาที)",
    "hint_abuse_cooldown": "ปุ่มคำใบ้พักหลัง Hint Abuse (วินาที)",
    "idle_timeout": "Idle Pause เมื่อไม่มีการกระทำ (วินาที)",
    "rt_cap": "ตัด Response Time ส่วนเกิน (วินาที)",
    "duplicate_window": "ส่งซ้ำภายในกี่วินาทีจึงนับเป็นครั้งเดียว",
    "mastery_window": "หน้าต่าง Mastery (ข้อล่าสุด)",
    "fast_track_mastery": "Mastery ขั้นต่ำของ Fast-Track",
    "standard_mastery": "Mastery ขั้นต่ำของ Standard Flow",
    "slip_mastery": "Mastery ขั้นต่ำที่นับเป็น Slip",
    "iso_attempts": "จำนวนครั้งที่ตอบได้ใน Isomorphic Test",
    "remedial_pass_streak": "ถูกติดกันกี่ข้อจึงผ่าน Remedial",
    "remedial_max_rounds": "Remedial สูงสุดต่อข้อ (รอบ)",
    "circuit_breaker_break": "Circuit Breaker พัก (วินาที)",
    "undo_window": "ยกเลิกคำตอบได้ภายใน (วินาที)",
    "finish_mastery": "Mastery ที่ถือว่าจบชุด",
    "finish_min_items": "จำนวนข้อขั้นต่ำก่อนจบชุด",
    "max_items": "เพดานจำนวนข้อต่อ Session",
    "burnout_idle": "Idle Pause กี่ครั้งต่อ Session จึงเป็น Burnout Signal",
    "burnout_rapid_streak": "Rapid Guess ติดกันกี่ครั้งจึงเป็น Burnout Signal",
    "burnout_risk": "Risk Score ที่ส่ง Burnout Signal",
    "impasse_threshold": "ค่า Fuzzy ที่ถือว่าเกิด Impasse",
}

# น้ำหนักต่อข้อของ Mastery: ถูกครั้งแรก / แก้เองถูก / หลังคำใบ้ระดับ 1-3
WEIGHTS = {"first": 1.0, "self": 0.8, 1: 0.7, 2: 0.4, 3: 0.2}

DEFAULT_PINS = {"teacher": "1234", "admin": "4321"}

CLAUDE_DEFAULT_MODEL = "claude-opus-5-5"
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
