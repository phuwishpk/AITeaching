"""Widget ในขั้น "widget" ของ Flow ที่ AI ออกแบบจากคำสั่งของครู (ADR-0004)

คลัง Widget: AI เลือกชนิดและใส่ข้อมูลตอนออกแบบ Flow ตรวจคำตอบด้วยกฎที่นี่ (ไม่ใช้ AI ตัดสิน) จึงนับเข้า Mastery ได้
หน้านักเรียนได้แค่ public() ที่ไม่มีเฉลย ถูกผิดตัดสินที่เซิร์ฟเวอร์เสมอ
custom: Widget ที่คลังไม่มี AI เขียนเป็น HTML รันในกรอบแยก (iframe sandbox ไม่มีเน็ต) ตรวจคำตอบด้วยกฎไม่ได้ จึงไม่นับคะแนน
"""

import random
import re
from fractions import Fraction

from .answers import normalize, normalize_short, parse_number

WIDGETS = {
    "order": {"label": "ลากเรียงลำดับ", "graded": True,
              "about": "นักเรียนลากเรียงข้อความให้ถูกลำดับ เช่น ขั้นของ PEMDAS หรือขั้นตอนแก้สมการ",
              "config": '{"items": ["ข้อความตามลำดับที่ถูก", ...]} 3–8 ข้อ ระบบสลับให้นักเรียนเอง'},
    "match": {"label": "จับคู่", "graded": True,
              "about": "นักเรียนจับคู่ข้อความฝั่งซ้ายกับฝั่งขวา เช่น คำศัพท์กับความหมาย สมการกับคำตอบ",
              "config": '{"pairs": [["ซ้าย", "ขวาที่คู่กัน"], ...]} 2–6 คู่ ข้อความไม่ซ้ำกัน'},
    "balance": {"label": "ตาชั่งสมการ", "graded": True,
                "about": "สมการ ax+b=c บนตาชั่ง นักเรียนบวก ลบ หรือหารทีละขั้น ทำข้างเดียวตาชั่งจะเอียง "
                         "ต้องเหลือ x ข้างเดียวโดยตาชั่งยังสมดุล",
                "config": '{"equation": "2x+3=7"} a เป็นจำนวนเต็ม 1–9 คำตอบเป็นจำนวนเต็ม ตัวเลขไม่เกิน 30'},
    "fraction": {"label": "แบบจำลองเศษส่วน", "graded": True,
                 "about": "รูปวงกลม (พิซซ่า) หรือแถบแบ่งเท่า ๆ กัน นักเรียนระบายให้ได้เศษส่วนที่กำหนด",
                 "config": '{"shape": "circle" หรือ "bar", "parts": 2–12, "target": "3/4"} target × parts ต้องเป็นจำนวนเต็ม'},
    "numberline": {"label": "เส้นจำนวน", "graded": True,
                   "about": "นักเรียนวางจุดบนเส้นจำนวนให้ตรงค่าที่กำหนด (จำนวนเต็ม ติดลบ หรือเศษส่วน)",
                   "config": '{"min": -10, "max": 10, "step": "1" หรือ "1/4", "target": "-3"} target ต้องอยู่บนขีด ไม่เกิน 40 ขีด'},
    "blank": {"label": "เติมคำในช่องว่าง", "graded": True,
              "about": "ข้อความที่มีช่องว่าง ___ ให้นักเรียนเติม",
              "config": '{"text": "ทำในวงเล็บ ___ แล้วคูณหรือหาร", "answers": [["ก่อน", "เป็นอันดับแรก"]]} '
                        "หนึ่งรายการต่อหนึ่งช่อง ใส่คำตอบที่ยอมรับได้หลายแบบ"},
    "custom": {"label": "Widget ที่ AI เขียนเอง", "graded": False,
               "about": "ใช้เมื่อคำสั่งของครูขอ Widget ที่คลังไม่มี บรรยายใน goal ให้ละเอียด AI เขียนเป็นหน้าเว็บเล็ก ๆ "
                        "นักเรียนลองเล่นแล้วกดไปต่อ ตรวจคำตอบด้วยกฎไม่ได้ จึงไม่นับเข้า Mastery และเงื่อนไข widget_pass เป็นจริงเสมอ",
               "config": "{} (ใส่คำบรรยายใน goal ของขั้นแทน)"},
}

HTML_LIMIT = 40000


class WidgetError(ValueError):
    pass


def _text(value, limit: int = 80) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _number(value, what: str) -> Fraction:
    number = parse_number(str(value)) if value is not None else None
    if number is None:
        raise WidgetError(f"{what} \"{value}\" ไม่ใช่ตัวเลข")
    return number


def _show(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def parse_equation(text: str) -> tuple[int, int, int]:
    """ax+b=c → (a, b, c)"""
    s = normalize(text).replace(" ", "").lower().replace("*", "")
    match = re.fullmatch(r"(\d*)x([+-]\d+)?=([+-]?\d+)", s)
    if not match:
        raise WidgetError(f"สมการ \"{text}\" ต้องอยู่ในรูป ax+b=c เช่น 2x+3=7")
    a = int(match.group(1) or 1)
    return a, int(match.group(2) or 0), int(match.group(3))


def normalize_config(kind: str, config) -> dict:
    """ตรวจและจัดข้อมูลของ Widget ตอนออกแบบหรือครูแก้ ข้อมูลผิดรูป raise WidgetError ให้ AI แก้"""
    config = config if isinstance(config, dict) else {}
    if kind == "order":
        items = [_text(i) for i in config.get("items") or [] if _text(i)][:8]
        if len(items) < 3 or len(set(items)) != len(items):
            raise WidgetError("Widget เรียงลำดับต้องมีข้อความ 3–8 ข้อที่ไม่ซ้ำกัน")
        return {"items": items}
    if kind == "match":
        pairs = [[_text(p[0]), _text(p[1])] for p in config.get("pairs") or []
                 if isinstance(p, (list, tuple)) and len(p) == 2 and _text(p[0]) and _text(p[1])][:6]
        lefts, rights = [p[0] for p in pairs], [p[1] for p in pairs]
        if len(pairs) < 2 or len(set(lefts)) != len(lefts) or len(set(rights)) != len(rights):
            raise WidgetError("Widget จับคู่ต้องมี 2–6 คู่ และข้อความแต่ละฝั่งไม่ซ้ำกัน")
        return {"pairs": pairs}
    if kind == "balance":
        a, b, c = parse_equation(str(config.get("equation") or ""))
        if not 1 <= a <= 9 or max(abs(b), abs(c)) > 30 or (c - b) % a:
            raise WidgetError(f"สมการบนตาชั่ง \"{config.get('equation')}\" ต้องมี a 1–9 ตัวเลขไม่เกิน 30 และคำตอบเป็นจำนวนเต็ม")
        return {"equation": equation_text(a, b, c)}
    if kind == "fraction":
        parts = int(_number(config.get("parts"), "จำนวนส่วน"))
        target = _number(config.get("target"), "เศษส่วนเป้าหมาย")
        if not 2 <= parts <= 12 or not 0 < target <= 1 or (target * parts).denominator != 1:
            raise WidgetError(f"แบบจำลองเศษส่วนต้องแบ่ง 2–12 ส่วน และ {config.get('target')} ระบายได้พอดีกับ {parts} ส่วน")
        return {"shape": "bar" if config.get("shape") == "bar" else "circle", "parts": parts, "target": _show(target)}
    if kind == "numberline":
        low, high = _number(config.get("min", 0), "ค่าต่ำสุด"), _number(config.get("max", 10), "ค่าสูงสุด")
        step = _number(config.get("step", 1), "ระยะขีด")
        target = _number(config.get("target"), "ค่าที่ต้องวาง")
        ticks = (high - low) / step if step > 0 else 0
        if step <= 0 or high <= low or ticks.denominator != 1 or ticks > 40:
            raise WidgetError("เส้นจำนวนต้องมี min < max และแบ่งขีดได้พอดีไม่เกิน 40 ขีด")
        if not low <= target <= high or ((target - low) / step).denominator != 1:
            raise WidgetError(f"ค่า {config.get('target')} ต้องอยู่บนขีดของเส้นจำนวน")
        return {"min": _show(low), "max": _show(high), "step": _show(step), "target": _show(target)}
    if kind == "blank":
        text = _text(config.get("text"), 400)
        answers = [[_text(a, 60) for a in (group if isinstance(group, list) else [group]) if _text(a, 60)]
                   for group in config.get("answers") or []]
        blanks = text.count("___")
        if not blanks or blanks > 6 or len(answers) != blanks or not all(answers):
            raise WidgetError("เติมคำต้องมีช่องว่าง ___ 1–6 ช่อง และคำตอบหนึ่งรายการต่อหนึ่งช่อง")
        return {"text": text, "answers": answers}
    if kind == "custom":
        html = str(config.get("html") or "")[:HTML_LIMIT]
        return {"html": html} if html else {}
    raise WidgetError(f"ไม่มี Widget ชนิด \"{kind}\" ในคลัง (ใช้ custom ถ้าคลังไม่มี)")


def equation_text(a, b, c) -> str:
    a, b, c = Fraction(a), Fraction(b), Fraction(c)
    left = ("" if a == 1 else _show(a)) + "x" + (f"+{_show(b)}" if b > 0 else f"{_show(b)}" if b < 0 else "")
    return f"{left}={_show(c)}"


def public(kind: str, config: dict, seed: str) -> dict:
    """สิ่งที่หน้านักเรียนได้: ไม่มีเฉลย (ลำดับที่ถูก คู่ที่ถูก คำตอบของช่องว่าง)"""
    rng = random.Random(seed)
    if kind == "order":
        items = list(config["items"])
        shuffled = items[:]
        while shuffled == items:
            rng.shuffle(shuffled)
        return {"items": shuffled}
    if kind == "match":
        rights = [p[1] for p in config["pairs"]]
        rng.shuffle(rights)
        return {"lefts": [p[0] for p in config["pairs"]], "rights": rights}
    if kind == "blank":
        return {"parts": config["text"].split("___")}
    return dict(config)


def check(kind: str, config: dict, response) -> dict:
    """ตรวจคำตอบด้วยกฎ คืน correct, marks (ถูกผิดรายส่วน ถ้ามี), value (สรุปสิ่งที่นักเรียนตอบให้ครูอ่าน)"""
    response = response if isinstance(response, dict) else {}
    if kind == "custom":
        return {"correct": True, "marks": None, "value": _text(response.get("result"), 300) or "ลองเล่นแล้ว", "graded": False}
    if kind == "order":
        answer = [str(x) for x in response.get("order") or []]
        marks = [i < len(answer) and answer[i] == item for i, item in enumerate(config["items"])]
        return {"correct": all(marks) and len(answer) == len(marks), "marks": marks, "value": " → ".join(answer)}
    if kind == "match":
        chosen = response.get("pairs") or {}
        marks = [str(chosen.get(left, "")) == right for left, right in config["pairs"]]
        return {"correct": all(marks), "marks": marks,
                "value": ", ".join(f"{left} ↔ {chosen.get(left, '-')}" for left, _ in config["pairs"])}
    if kind == "balance":
        return _check_balance(config, response)
    if kind == "fraction":
        shaded = int(response.get("shaded") or 0)
        correct = Fraction(shaded, config["parts"]) == _number(config["target"], "")
        return {"correct": correct, "marks": None, "value": f"ระบาย {shaded} จาก {config['parts']} ส่วน"}
    if kind == "numberline":
        value = parse_number(str(response.get("value", "")))
        correct = value is not None and value == _number(config["target"], "")
        return {"correct": correct, "marks": None, "value": f"วางที่ {_show(value) if value is not None else '-'}"}
    if kind == "blank":
        filled = [str(x) for x in response.get("blanks") or []]
        marks = [i < len(filled) and _same(filled[i], accepted) for i, accepted in enumerate(config["answers"])]
        return {"correct": all(marks), "marks": marks, "value": " | ".join(filled)}
    return {"correct": False, "marks": None, "value": ""}


def _same(answer: str, accepted: list[str]) -> bool:
    number = parse_number(answer)
    for option in accepted:
        expected = parse_number(option)
        if number is not None and expected is not None and number == expected:
            return True
        if normalize_short(answer) == normalize_short(option):
            return True
    return False


def _check_balance(config: dict, response: dict) -> dict:
    """เล่นซ้ำทุกขั้นที่นักเรียนทำ: ทำข้างเดียวตาชั่งเอียง สุดท้ายต้องเหลือ x ข้างเดียวและยังสมดุล"""
    a, b, c = parse_equation(config["equation"])
    solution = Fraction(c - b, a)
    # ข้างซ้าย a·x + b ข้างขวา c (ข้างขวาเป็นตัวเลขอย่างเดียว ข้างซ้ายเก็บเป็นสัมประสิทธิ์และค่าคงที่)
    left_a, left_b, right = Fraction(a), Fraction(b), Fraction(c)
    lopsided = 0
    steps = response.get("steps") or []
    for move in steps[:20]:
        if not isinstance(move, dict):
            continue
        op, side = move.get("op"), move.get("side", "both")
        n = parse_number(str(move.get("n", "")))
        if n is None or op not in ("+", "-", "/") or (op == "/" and n == 0):
            continue
        if side in ("both", "left"):
            if op == "+":
                left_b += n
            elif op == "-":
                left_b -= n
            else:
                left_a, left_b = left_a / n, left_b / n
        if side in ("both", "right"):
            right = right + n if op == "+" else right - n if op == "-" else right / n
        if side != "both":
            lopsided += 1
    balanced = left_a * solution + left_b == right
    isolated = left_a == 1 and left_b == 0
    shown = equation_text(left_a, left_b, right)
    return {"correct": balanced and isolated, "marks": None,
            "value": f"{len(steps)} ขั้น จบที่ {shown}" + (f" (ทำข้างเดียว {lopsided} ครั้ง)" if lopsided else ""),
            "lopsided": lopsided}


def solution(kind: str, config: dict) -> dict:
    """คำตอบที่ถูกของ Widget (ใช้ในการจำลองนักเรียนและการทดสอบ ไม่ส่งถึงหน้านักเรียน)"""
    if kind == "order":
        return {"order": list(config["items"])}
    if kind == "match":
        return {"pairs": {left: right for left, right in config["pairs"]}}
    if kind == "balance":
        a, b, c = parse_equation(config["equation"])
        steps = ([{"op": "-" if b > 0 else "+", "n": abs(b)}] if b else []) + ([{"op": "/", "n": a}] if a != 1 else [])
        return {"steps": steps}
    if kind == "fraction":
        return {"shaded": int(_number(config["target"], "") * config["parts"])}
    if kind == "numberline":
        return {"value": config["target"]}
    if kind == "blank":
        return {"blanks": [group[0] for group in config["answers"]]}
    return {"done": True}


def text_of(kind: str, config: dict) -> str:
    """ข้อความทั้งหมดของ Widget รวมเฉลย ใช้ตรวจ Answer-Leak Guard กับโจทย์ในคลัง"""
    if kind == "order":
        return " ".join(config.get("items", []))
    if kind == "match":
        return " ".join(f"{l} {r}" for l, r in config.get("pairs", []))
    if kind == "balance":
        a, b, c = parse_equation(config["equation"])
        return f"{config['equation']} x={_show(Fraction(c - b, a))}"
    if kind == "blank":
        text = config.get("text", "")
        for group in config.get("answers", []):
            text = text.replace("___", group[0], 1)
        return text
    if kind == "custom":
        # รวมข้อความในสคริปต์ด้วย คำตอบอาจซ่อนอยู่ในโค้ด
        return re.sub(r"<[^>]+>", " ", config.get("html", ""))
    return " ".join(str(v) for v in config.values())
