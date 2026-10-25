"""Answer-Leak Guard: ตรวจทุกข้อความจาก LLM ก่อนถึงนักเรียน (ADR-0001)

prompt อย่างเดียวรับประกันไม่ได้ว่า LLM จะไม่เฉลย ด่านนี้จึงตรวจด้วยกฎที่อธิบายได้
ถ้าพบคำตอบสุดท้าย ระบบจะใช้คำใบ้ต้นฉบับ (Authored Hint) แทน
ตรวจได้เฉพาะรูปแบบที่รู้จัก ไม่ได้เข้าใจความหมายทั้งหมด (เป็นข้อจำกัดที่ต้องบอกในสไลด์)
"""

import re
from dataclasses import dataclass
from fractions import Fraction

from ..engine.answers import NUMBER_RE, normalize, normalize_short, parse_number, same_number

TRIGGER = "TRIGGER_CIRCUIT_BREAKER"


def has_trigger(text: str) -> bool:
    """รหัสตัดวงจรจาก LLM แม้ขีดล่างถูกตัดหรือเว้นวรรค (ข้อความผ่าน _clean ที่ลบ markdown มาก่อน)"""
    return "TRIGGERCIRCUITBREAKER" in re.sub(r"[^A-Za-z]", "", text or "").upper()
THAI_LETTERS = {"a": "ก", "b": "ข", "c": "ค", "d": "ง"}


@dataclass
class GuardResult:
    blocked: bool
    reason: str = ""
    matched: str = ""
    trigger: bool = False

    def to_dict(self) -> dict:
        return {"blocked": self.blocked, "reason": self.reason, "matched": self.matched, "trigger": self.trigger}


def _numbers(text: str) -> list[tuple[str, Fraction]]:
    found = []
    for match in NUMBER_RE.finditer(text):
        value = parse_number(match.group(0))
        if value is not None:
            found.append((match.group(0), value))
    return found


def check(text: str, item: dict) -> GuardResult:
    if not text:
        return GuardResult(False)
    if has_trigger(text):
        return GuardResult(True, "LLM ส่งรหัสตัดวงจร", TRIGGER, trigger=True)
    norm = normalize(text)
    answer_format = item.get("format", "numeric")

    if answer_format == "numeric":
        answer = Fraction(item["answer"]["value"])
        # รูปแบบ 1: x = คำตอบ, x เท่ากับ คำตอบ
        for match in re.finditer(r"x\s*(?:=|เท่ากับ|คือ|มีค่า(?:เท่ากับ)?)\s*(" + NUMBER_RE.pattern + ")", norm, re.I):
            value = parse_number(match.group(1))
            if value is not None and same_number(value, answer):
                return GuardResult(True, "บอกค่าของ x ตรง ๆ", match.group(0))
        # รูปแบบ 2: คำตอบคือ ..., เฉลย ..., ผลลัพธ์ ...
        for match in re.finditer(r"(?:คำตอบ|เฉลย|ผลลัพธ์|ตอบ)\s*(?:สุดท้าย)?\s*(?:คือ|=|เท่ากับ|ได้|ว่า)?\s*(" + NUMBER_RE.pattern + ")", norm):
            value = parse_number(match.group(1))
            if value is not None and same_number(value, answer):
                return GuardResult(True, "บอกคำตอบสุดท้าย", match.group(0))
        # รูปแบบ 3: มีตัวเลขเท่ากับคำตอบ ทั้งที่ตัวเลขนี้ไม่อยู่ในโจทย์
        problem = normalize(" ".join([item.get("prompt", ""), item.get("math") or ""]))
        problem_values = [v for _, v in _numbers(problem)]
        for raw, value in _numbers(norm):
            if same_number(value, answer) and not any(same_number(value, p) for p in problem_values):
                return GuardResult(True, "มีตัวเลขเท่ากับคำตอบที่ไม่อยู่ในโจทย์", raw)
        return GuardResult(False)

    if answer_format == "mcq":
        option = next((o for o in item.get("options", []) if o["id"] == item["answer"]["option"]), None)
        letter = item["answer"]["option"]
        thai = THAI_LETTERS.get(letter, letter)
        if re.search(rf"(?:ข้อ|ตัวเลือก|ตอบ)\s*(?:\(?\s*)({re.escape(letter)}|{re.escape(thai)})(?![ก-๙a-z])", norm, re.I):
            return GuardResult(True, "บอกตัวเลือกที่ถูก", thai)
        if option and normalize_short(option["text"]) in normalize_short(norm):
            return GuardResult(True, "ยกข้อความตัวเลือกที่ถูกมาตรง ๆ", option["text"])
        return GuardResult(False)

    for accepted in item["answer"].get("accepted", []):
        if normalize_short(accepted) and normalize_short(accepted) in normalize_short(norm):
            return GuardResult(True, "มีคำตอบที่ยอมรับอยู่ในข้อความ", accepted)
    return GuardResult(False)
