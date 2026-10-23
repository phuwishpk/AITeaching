"""ตรวจคำตอบตาม Answer Format และจับคู่คำตอบผิดกับ Bug Library

ตรวจด้วยกฎล้วน ไม่ใช้ LLM ตัดสินถูกผิด (ADR-0001)
รองรับเลขไทย เศษส่วน และการพิมพ์ "x = 4"
"""

import re
from dataclasses import dataclass
from fractions import Fraction

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:/[-+]?\d+)?")


def normalize(text: str) -> str:
    """แปลงเลขไทย เครื่องหมายลบแบบต่าง ๆ และช่องว่าง ให้เป็นรูปแบบเดียวกัน"""
    text = (text or "").translate(THAI_DIGITS)
    for dash in ("−", "–", "—", "﹣", "－"):
        text = text.replace(dash, "-")
    return text.replace("＝", "=").replace("÷", "/").strip()


def parse_number(raw: str) -> Fraction | None:
    s = normalize(raw).replace(" ", "").replace(",", "").lower()
    s = re.sub(r"^x(=|เท่ากับ)", "", s)
    if not s:
        return None
    try:
        if re.fullmatch(r"[-+]?\d+(\.\d+)?", s):
            return Fraction(s)
        match = re.fullmatch(r"([-+]?\d+)/([-+]?\d+)", s)
        if match and int(match.group(2)) != 0:
            return Fraction(int(match.group(1)), int(match.group(2)))
    except (ValueError, ZeroDivisionError):
        return None
    return None


def same_number(a, b) -> bool:
    a, b = Fraction(a), Fraction(b)
    if a == b:
        return True
    # คำตอบที่ไม่ลงตัว (เช่น 17/5) ยอมรับทศนิยมที่ปัดแล้ว
    return abs(float(a) - float(b)) <= 0.01 and (a.denominator != 1 or b.denominator != 1)


def normalize_short(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text)).lower()


@dataclass
class Check:
    valid: bool
    correct: bool = False
    value: object = None
    message: str = ""


FORMAT_HELP = {
    "numeric": "กรุณาตอบเป็นตัวเลข เช่น 4, −2, 2.5 หรือ 7/2",
    "mcq": "กรุณาเลือกหนึ่งตัวเลือก",
    "short": "กรุณาพิมพ์คำตอบสั้น ๆ",
}


def check_answer(item: dict, raw) -> Check:
    answer_format = item.get("format", "numeric")
    raw = "" if raw is None else str(raw)
    if answer_format == "numeric":
        value = parse_number(raw)
        if value is None:
            return Check(False, message=FORMAT_HELP["numeric"])
        return Check(True, same_number(value, item["answer"]["value"]), value)
    if answer_format == "mcq":
        option_ids = {o["id"] for o in item.get("options", [])}
        choice = raw.strip().lower()
        if choice not in option_ids:
            return Check(False, message=FORMAT_HELP["mcq"])
        return Check(True, choice == item["answer"]["option"], choice)
    text = normalize_short(raw)
    if not text:
        return Check(False, message=FORMAT_HELP["short"])
    accepted = {normalize_short(a) for a in item["answer"].get("accepted", [])}
    return Check(True, text in accepted, raw.strip())


def match_bug(item: dict, value) -> str | None:
    """หาแท็ก Bug Library ของคำตอบผิด: ดูรายการเฉพาะข้อก่อน แล้วจึงดูรูปแบบ Slip ทั่วไป"""
    answer_format = item.get("format", "numeric")
    for bug in item.get("bugs", []):
        if answer_format == "numeric":
            if value is not None and same_number(value, bug["answer"]):
                return bug["tag"]
        elif str(bug["answer"]).strip().lower() == str(value).strip().lower():
            return bug["tag"]
    if answer_format == "numeric" and value is not None:
        correct = Fraction(item["answer"]["value"])
        if value == -correct and correct != 0:
            return "S-SIGNFLIP"
        if abs(value - correct) == 1:
            return "S-ARITH"
    return None


def answer_display(item: dict) -> str:
    """คำตอบที่ถูกในรูปที่คนอ่าน (ใช้เฉพาะฝั่งครูและ Admin)"""
    answer_format = item.get("format", "numeric")
    if answer_format == "numeric":
        return str(item["answer"]["value"])
    if answer_format == "mcq":
        option = next((o for o in item.get("options", []) if o["id"] == item["answer"]["option"]), None)
        return option["text"] if option else item["answer"]["option"]
    return " / ".join(item["answer"].get("accepted", []))
