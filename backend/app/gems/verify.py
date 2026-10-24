"""Answer Key Check: ตรวจเฉลยที่ LLM สร้างก่อนถึงนักเรียน (ADR-0003)

ชั้นที่ 1 sympy คำนวณเฉลยจริงเมื่อโจทย์เป็นสมการตัวแปรเดียวหรือเลขคณิต
ชั้นที่ 2 เทียบกับคำตอบที่ LLM แก้ซ้ำโดยไม่เห็นเฉลย (builder เป็นคนเรียก LLM ไฟล์นี้แค่เทียบ)
ข้อที่ไม่ผ่านชั้นใดชั้นหนึ่งเป็น Flagged Item ซ่อนจากนักเรียนจนครูยืนยัน
"""

import re
from fractions import Fraction

from sympy import Eq, Rational, nsimplify, solve
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from ..engine.answers import normalize_short, parse_number, same_number

TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
# parse_expr ประเมินข้อความเป็นโค้ด จึงรับเฉพาะตัวเลข ตัวแปรตัวอักษรเดียว และเครื่องหมายคณิตศาสตร์
SAFE = re.compile(r"[0-9a-z\s+\-*/().=^]+")


def _clean(math: str) -> str | None:
    text = (math or "").strip().lower()
    for old, new in (("−", "-"), ("–", "-"), ("×", "*"), ("·", "*"), ("÷", "/"), ("²", "^2"), ("³", "^3")):
        text = text.replace(old, new)
    if not text or len(text) > 120 or not SAFE.fullmatch(text) or re.search(r"[a-z]{2}", text):
        return None
    return text


def sympy_answer(math: str) -> Fraction | None:
    """คำตอบที่คำนวณได้จริง: สมการตัวแปรเดียวที่มีคำตอบเดียว หรือนิพจน์เลขคณิต คืน None ถ้าคำนวณไม่ได้"""
    text = _clean(math)
    if text is None:
        return None
    try:
        if text.count("=") == 1:
            left, right = (parse_expr(side, transformations=TRANSFORMS) for side in text.split("="))
            symbols = (left - right).free_symbols
            if len(symbols) != 1:
                return None
            solutions = [s for s in solve(Eq(left, right), next(iter(symbols))) if s.is_real]
            if len(solutions) != 1:
                return None
            value = solutions[0]
        elif "=" not in text and not re.search(r"[a-z]", text):
            value = parse_expr(text, transformations=TRANSFORMS)
        else:
            return None
        value = nsimplify(value, rational=True)
        if not isinstance(value, Rational):
            return None
        return Fraction(int(value.p), int(value.q))
    except Exception:  # noqa: BLE001 ข้อความจาก LLM อ่านไม่ได้ ถือว่าตรวจด้วย sympy ไม่ได้ ไม่ใช่ว่าผิด
        return None


def check_with_sympy(item: dict) -> str | None:
    """คืนเหตุผลถ้าเฉลยตัวเลขไม่ตรงกับที่ sympy คำนวณ"""
    if item.get("format") != "numeric" or not item.get("math"):
        return None
    truth = sympy_answer(item["math"])
    if truth is None:
        return None
    if not same_number(truth, item["answer"]["value"]):
        return f"sympy คำนวณได้ {_show(truth)} แต่เฉลยเขียน {item['answer']['value']}"
    return None


def check_resolved(item: dict, solved) -> str | None:
    """เทียบคำตอบที่ LLM แก้ซ้ำโดยไม่เห็นเฉลย คืนเหตุผลถ้าไม่ตรง"""
    if solved is None or solved == "":
        return "LLM แก้ซ้ำแล้วไม่ได้คำตอบ"
    answer_format = item.get("format")
    if answer_format == "numeric":
        value = parse_number(str(solved))
        if value is None or not same_number(value, item["answer"]["value"]):
            return f"LLM แก้ซ้ำได้ {solved} แต่เฉลยเขียน {item['answer']['value']}"
        return None
    if answer_format == "mcq":
        if str(solved).strip().lower() != item["answer"]["option"]:
            return f"LLM แก้ซ้ำเลือกข้อ {solved} แต่เฉลยเป็นข้อ {item['answer']['option']}"
        return None
    accepted = {normalize_short(a) for a in item["answer"].get("accepted", [])}
    if normalize_short(str(solved)) not in accepted:
        return f"LLM แก้ซ้ำได้ \"{solved}\" ซึ่งไม่อยู่ในคำตอบที่ยอมรับ"
    return None


def _show(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"

