"""วิชาตัวอย่างที่ติดมากับระบบ: คณิตศาสตร์ ม.2 หน่วยสมการเชิงเส้นตัวแปรเดียว

สร้างโจทย์ด้วยสูตร เพื่อให้คำตอบผิดของแต่ละ Misconception คำนวณได้จริงและไม่ซ้ำกัน
เช่น สมการ ax + b = c ที่ถูกคือ x = (c − b) / a
ส่วนคนที่ "ย้ายข้างไม่เปลี่ยนเครื่องหมาย" จะได้ x = (c + b) / a
"""

import random
from fractions import Fraction

MINUS = "−"
LETTERS = ["a", "b", "c", "d"]


def fmt(value) -> str:
    """แสดงตัวเลขแบบที่นักเรียนเห็นในหนังสือ (ใช้เครื่องหมายลบตัวยาว)"""
    v = Fraction(value)
    body = str(abs(v.numerator)) if v.denominator == 1 else f"{abs(v.numerator)}/{v.denominator}"
    return f"{MINUS}{body}" if v < 0 else body


def out(value):
    """ค่าที่เก็บใน JSON: จำนวนเต็มหรือทศนิยม 4 ตำแหน่ง"""
    v = Fraction(value)
    return int(v) if v.denominator == 1 else round(float(v), 4)


def lin(a: int, b: int) -> str:
    coef = "" if a == 1 else (MINUS if a == -1 else fmt(a))
    text = f"{coef}x"
    if b > 0:
        text += f" + {b}"
    elif b < 0:
        text += f" {MINUS} {abs(b)}"
    return text


def term(b: int) -> str:
    return f"+ {b}" if b > 0 else f"{MINUS} {abs(b)}"


def _mcq(item_id: str, correct, distractors: list[tuple[str, object]], label) -> tuple[list, dict, list]:
    values = [("__correct__", correct)] + distractors[:3]
    random.Random(item_id).shuffle(values)
    options, bugs, answer = [], [], {}
    for letter, (tag, value) in zip(LETTERS, values):
        options.append({"id": letter, "text": label(value)})
        if tag == "__correct__":
            answer = {"option": letter}
        else:
            bugs.append({"answer": letter, "tag": tag})
    return options, answer, bugs


SOCRATIC_BALANCE = "ถ้าสมการเป็นตาชั่งที่สมดุล ถ้าหยิบของออกจากจานเดียว ตาชั่งจะยังสมดุลไหม"
SOCRATIC_CHECK = "ลองแทนคำตอบของตัวเองกลับลงไปในสมการ ทั้งสองข้างได้ค่าเท่ากันไหม"
RULE_EQUALITY = (
    "ใช้สมบัติการเท่ากัน: ถ้าบวก ลบ คูณ หรือหารทั้งสองข้างด้วยจำนวนเดียวกัน สมการยังเป็นจริง "
    "สมการสองขั้นจึงแก้ทีละขั้น ขั้นแรกกำจัดค่าคงที่ออกจากข้างที่มี x "
    "ขั้นที่สองหารทั้งสองข้างด้วยตัวเลขที่คูณ x อยู่"
)


def two_step(item_id, a, b, c, kind, answer_format, difficulty, iso_of=None):
    """โจทย์ ax + b = c ของมโนทัศน์เป้าหมาย (สมการสองขั้น)"""
    x = Fraction(c - b, a)
    assert x.denominator == 1, item_id
    candidates = [
        ("M-SIGN", Fraction(c + b, a)),
        ("M-ORDER", Fraction(c, a) - b),
        ("M-SUBCOEF", Fraction(c - b) - a),
        ("S-SIGNFLIP", -x),
    ]
    seen, bugs = {x}, []
    for tag, value in candidates:
        if value not in seen:
            seen.add(value)
            bugs.append((tag, value))
    op = f"ลบ {b}" if b > 0 else f"บวก {abs(b)}"
    item = {
        "id": item_id,
        "concept": "C-TWO",
        "kind": kind,
        "iso_of": iso_of,
        "isomorphs": [],
        "format": answer_format,
        "prompt": "จงหาค่าของ x จากสมการ",
        "math": f"{lin(a, b)} = {fmt(c)}",
        "difficulty": difficulty,
        "min_read_time": 3,
        "expected_time": 45,
        "hints": {
            "1": (
                f"ลองดูฝั่งซ้ายของสมการ ตอนนี้ {lin(a, 0)} ยังมี {term(b)} ติดอยู่ "
                f"ถ้าอยากให้ฝั่งซ้ายเหลือแค่ {lin(a, 0)} ต้องทำอะไรกับทั้งสองข้างของสมการ"
            ),
            "2": RULE_EQUALITY,
            "3": (
                f"ขั้นแรก {op} ทั้งสองข้าง จะได้ {lin(a, 0)} = {fmt(c - b)} "
                f"ขั้นต่อไปลองคิดเองว่าต้องทำอะไรกับ {fmt(a)} เพื่อให้เหลือ x ตัวเดียว"
            ),
        },
        "socratic": [
            SOCRATIC_BALANCE,
            f"ตอนนี้ x ถูกคูณด้วย {fmt(a)} อยู่ การกระทำที่ตรงข้ามกับการคูณคืออะไร",
            SOCRATIC_CHECK,
        ],
    }
    if answer_format == "mcq":
        options, answer, mcq_bugs = _mcq(item_id, x, bugs, lambda v: f"x = {fmt(v)}")
        item.update(options=options, answer=answer, bugs=mcq_bugs)
    else:
        item.update(answer={"value": out(x)}, bugs=[{"answer": out(v), "tag": t} for t, v in bugs])
    return item


def one_step_add(item_id, b, c, answer_format="numeric"):
    """โจทย์ x + b = c ของ Prerequisite (สมการขั้นเดียว)"""
    x = Fraction(c - b)
    bugs = [("M-SIGN", Fraction(c + b)), ("S-SIGNFLIP", -x)]
    op = f"ลบ {b}" if b > 0 else f"บวก {abs(b)}"
    item = {
        "id": item_id,
        "concept": "C-ONE",
        "kind": "remedial",
        "iso_of": None,
        "isomorphs": [],
        "format": answer_format,
        "prompt": "จงหาค่าของ x จากสมการ",
        "math": f"{lin(1, b)} = {fmt(c)}",
        "difficulty": 0.2,
        "min_read_time": 2,
        "expected_time": 25,
        "hints": {
            "1": f"ฝั่งซ้ายมี x {term(b)} อยู่ ถ้าอยากให้เหลือ x ตัวเดียว ต้องทำอะไรกับทั้งสองข้าง",
            "2": "การบวกและการลบเป็นการกระทำตรงข้ามกัน ถ้ามีจำนวนบวกอยู่กับ x ให้ลบจำนวนนั้นออกทั้งสองข้าง ถ้ามีจำนวนลบอยู่ ให้บวกจำนวนนั้นทั้งสองข้าง",
            "3": f"{op} ทั้งสองข้าง ฝั่งซ้ายจะเหลือ x แล้วลองคำนวณฝั่งขวา {fmt(c)} {'−' if b > 0 else '+'} {abs(b)} เอง",
        },
        "socratic": [SOCRATIC_BALANCE, SOCRATIC_CHECK],
        "answer": {"value": out(x)},
        "bugs": [{"answer": out(v), "tag": t} for t, v in bugs],
    }
    return item


def one_step_mul(item_id, a, c, answer_format="numeric"):
    """โจทย์ ax = c ของ Prerequisite (สมการขั้นเดียว)"""
    x = Fraction(c, a)
    bugs = [("M-SUBCOEF", Fraction(c - a)), ("M-MULT", Fraction(c * a)), ("S-SIGNFLIP", -x)]
    item = {
        "id": item_id,
        "concept": "C-ONE",
        "kind": "remedial",
        "iso_of": None,
        "isomorphs": [],
        "format": answer_format,
        "prompt": "จงหาค่าของ x จากสมการ",
        "math": f"{lin(a, 0)} = {fmt(c)}",
        "difficulty": 0.25,
        "min_read_time": 2,
        "expected_time": 25,
        "hints": {
            "1": f"{lin(a, 0)} หมายถึง {fmt(a)} คูณกับ x ถ้าอยากให้เหลือ x ตัวเดียว ควรใช้การกระทำใด",
            "2": "การคูณและการหารเป็นการกระทำตรงข้ามกัน ถ้า x ถูกคูณด้วยจำนวนใด ให้หารทั้งสองข้างด้วยจำนวนนั้น",
            "3": f"หารทั้งสองข้างด้วย {fmt(a)} จะได้ x = {fmt(c)} ÷ {fmt(a)} ลองคำนวณผลหารนี้เอง",
        },
        "socratic": [f"{fmt(a)} คูณกับจำนวนใดแล้วได้ {fmt(c)}", SOCRATIC_CHECK],
    }
    if answer_format == "mcq":
        options, answer, mcq_bugs = _mcq(item_id, x, bugs, lambda v: f"x = {fmt(v)}")
        item.update(options=options, answer=answer, bugs=mcq_bugs)
    else:
        item.update(answer={"value": out(x)}, bugs=[{"answer": out(v), "tag": t} for t, v in bugs])
    return item


def integer_item(item_id, math, value, bugs, hints, answer_format="numeric", options_label=None):
    item = {
        "id": item_id,
        "concept": "C-INT",
        "kind": "remedial",
        "iso_of": None,
        "isomorphs": [],
        "format": answer_format,
        "prompt": "จงหาผลลัพธ์",
        "math": math,
        "difficulty": 0.15,
        "min_read_time": 2,
        "expected_time": 20,
        "hints": hints,
        "socratic": ["ลองนึกถึงเส้นจำนวน จำนวนบวกพาไปทางขวา จำนวนลบพาไปทางซ้าย", "ผลลัพธ์ควรเป็นจำนวนบวกหรือจำนวนลบ เพราะอะไร"],
    }
    if answer_format == "mcq":
        options, answer, mcq_bugs = _mcq(item_id, Fraction(value), [(t, Fraction(v)) for t, v in bugs], options_label or fmt)
        item.update(options=options, answer=answer, bugs=mcq_bugs)
    else:
        item.update(answer={"value": value}, bugs=[{"answer": v, "tag": t} for t, v in bugs])
    return item


def challenge(item_id, a1, b1, a2, b2, difficulty):
    """โจทย์ a1·x + b1 = a2·x + b2 (ตัวแปรสองข้าง) ใช้ในเส้นทาง Fast-Track"""
    x = Fraction(b2 - b1, a1 - a2)
    assert x.denominator == 1, item_id
    bugs = []
    for value in (Fraction(b2 - b1, a1 + a2), Fraction(b2 + b1, a1 - a2)):
        if value != x and value not in [v for _, v in bugs]:
            bugs.append(("M-SIGN", value))
    return {
        "id": item_id,
        "concept": "C-BOTH",
        "kind": "challenge",
        "iso_of": None,
        "isomorphs": [],
        "format": "numeric",
        "prompt": "จงหาค่าของ x จากสมการ",
        "math": f"{lin(a1, b1)} = {lin(a2, b2)}",
        "difficulty": difficulty,
        "min_read_time": 4,
        "expected_time": 70,
        "hints": {
            "1": "สมการนี้มี x อยู่ทั้งสองข้าง ลองคิดว่าจะรวมพจน์ที่มี x ไว้ข้างเดียวกันได้อย่างไร",
            "2": "ใช้สมบัติการเท่ากันย้ายพจน์ทีละอย่าง: ลบพจน์ที่มี x ออกจากข้างหนึ่งทั้งสองข้าง แล้วจัดการค่าคงที่ จากนั้นหารด้วยสัมประสิทธิ์ของ x",
            "3": f"ขั้นแรก ลบ {lin(a2, 0)} ทั้งสองข้าง จะได้ {lin(a1 - a2, b1)} = {fmt(b2)} แล้วแก้ต่อเหมือนสมการสองขั้น",
        },
        "socratic": ["พจน์ที่มี x อยู่ข้างไหนบ้าง ถ้าจะให้เหลือข้างเดียวต้องทำอะไร", SOCRATIC_CHECK],
        "answer": {"value": out(x)},
        "bugs": [{"answer": out(v), "tag": t} for t, v in bugs],
    }


def build_subject() -> dict:
    items: list[dict] = []

    # ---------- มโนทัศน์เป้าหมาย: สมการสองขั้น (Main Item + Isomorphic Item) ----------
    mains = [
        ("T-01", (2, 3, 11), "numeric", 0.30, [(3, 4, 19), (2, 7, 15)]),
        ("T-02", (3, 5, 20), "numeric", 0.35, [(4, 3, 23), (3, 8, 26)]),
        ("T-03", (5, -4, 21), "mcq", 0.45, [(4, -3, 25), (6, -5, 31)]),
        ("T-04", (4, -7, 17), "numeric", 0.50, [(3, -5, 16), (5, -8, 22)]),
        ("T-05", (-2, 9, 1), "numeric", 0.65, [(-3, 10, 1), (-4, 5, -7)]),
        ("T-06", (6, 8, -10), "mcq", 0.70, [(5, 9, -6), (4, 7, -13)]),
    ]
    for item_id, (a, b, c), answer_format, difficulty, isos in mains:
        main = two_step(item_id, a, b, c, "main", answer_format, difficulty)
        for index, (ia, ib, ic) in enumerate(isos):
            iso_id = f"{item_id}-I{index + 1}"
            items.append(two_step(iso_id, ia, ib, ic, "isomorphic", answer_format, difficulty, iso_of=item_id))
            main["isomorphs"].append(iso_id)
        items.insert(len(items) - len(isos), main)

    # ---------- Fast-Track: ตัวแปรสองข้าง (Challenge Item) ----------
    items += [
        challenge("H-01", 3, 2, 1, 10, 0.85),
        challenge("H-02", 5, -3, 2, 12, 0.90),
        challenge("H-03", 7, 4, 3, 24, 0.95),
    ]

    # ---------- Prerequisite: สมการขั้นเดียว ----------
    items += [
        one_step_add("O-01", 7, 12),
        one_step_add("O-02", -4, 9),
        one_step_mul("O-03", 3, 18),
        one_step_mul("O-04", 5, -20, answer_format="mcq"),
    ]

    # ---------- Prerequisite: บวกลบจำนวนเต็ม ----------
    items += [
        integer_item(
            "I-01", f"({MINUS}3) + 7", 4, [("S-SIGNFLIP", -4), ("M-NEG", -10)],
            {
                "1": "ลองนึกถึงเส้นจำนวน เริ่มที่ −3 แล้วเดินไปทางขวา 7 ช่อง จะไปหยุดที่ไหน",
                "2": "บวกจำนวนลบกับจำนวนบวก ให้นำค่าสัมบูรณ์มาลบกัน แล้วใช้เครื่องหมายของจำนวนที่มีค่าสัมบูรณ์มากกว่า",
                "3": "ค่าสัมบูรณ์คือ 3 กับ 7 ลองหา 7 − 3 แล้วคิดว่าผลลัพธ์ควรเป็นบวกหรือลบ",
            },
        ),
        integer_item(
            "I-02", f"5 {MINUS} 9", -4, [("S-SIGNFLIP", 4)],
            {
                "1": "ถ้ามีเงิน 5 บาทแต่ต้องจ่าย 9 บาท จะขาดหรือเหลือ",
                "2": "ถ้าตัวลบมากกว่าตัวตั้ง ผลลัพธ์จะเป็นจำนวนลบ",
                "3": "หาว่า 9 มากกว่า 5 อยู่เท่าไร แล้วใส่เครื่องหมายให้ถูก",
            },
        ),
        integer_item(
            "I-03", f"({MINUS}4) {MINUS} ({MINUS}6)", 2, [("M-NEG", -10), ("S-SIGNFLIP", -2)],
            {
                "1": "การลบด้วยจำนวนลบ เหมือนกับการบวกด้วยจำนวนใด",
                "2": "a − (−b) = a + b การลบด้วยจำนวนลบเท่ากับการบวกด้วยจำนวนบวกที่มีค่าเท่ากัน",
                "3": "เขียนใหม่เป็น (−4) + 6 แล้วลองคำนวณต่อเอง",
            },
        ),
        integer_item(
            "I-04", f"6 {MINUS} ({MINUS}2)", 8, [("M-NEG", 4), ("S-SIGNFLIP", -8), ("M-NEG", -4)],
            {
                "1": "ลบด้วยจำนวนลบ ทำให้ผลลัพธ์มากขึ้นหรือน้อยลง",
                "2": "a − (−b) = a + b",
                "3": "เขียนใหม่เป็น 6 + 2 แล้วคำนวณ",
            },
            answer_format="mcq",
        ),
    ]

    # ---------- Prerequisite: สมบัติการเท่ากัน ----------
    items += [
        {
            "id": "E-01", "concept": "C-EQP", "kind": "remedial", "iso_of": None, "isomorphs": [],
            "format": "mcq", "prompt": "ขั้นแรกที่ถูกต้องในการแก้สมการนี้คือข้อใด", "math": "2x + 5 = 13",
            "difficulty": 0.2, "min_read_time": 3, "expected_time": 25,
            "options": [
                {"id": "a", "text": "ลบ 5 ทั้งสองข้างของสมการ"},
                {"id": "b", "text": "บวก 5 ทั้งสองข้างของสมการ"},
                {"id": "c", "text": "ลบ 5 เฉพาะฝั่งซ้าย"},
                {"id": "d", "text": "หาร 2 เฉพาะพจน์ 2x"},
            ],
            "answer": {"option": "a"},
            "bugs": [{"answer": "b", "tag": "M-SIGN"}, {"answer": "c", "tag": "M-ONESIDE"}, {"answer": "d", "tag": "M-ORDER"}],
            "hints": {
                "1": "สิ่งที่ทำกับข้างหนึ่งของสมการ ต้องทำกับอีกข้างด้วยหรือไม่",
                "2": "สมบัติการเท่ากัน: ทำการกระทำเดียวกันกับทั้งสองข้างเสมอ และเริ่มจากกำจัดค่าคงที่ที่อยู่กับพจน์ x",
                "3": "ตอนนี้มี + 5 อยู่กับ 2x การกระทำตรงข้ามของการบวก 5 คืออะไร และต้องทำกับกี่ข้าง",
            },
            "socratic": [SOCRATIC_BALANCE],
        },
        {
            "id": "E-02", "concept": "C-EQP", "kind": "remedial", "iso_of": None, "isomorphs": [],
            "format": "mcq", "prompt": "ถ้า a = b แล้วข้อใดเป็นจริงเสมอ", "math": "a = b",
            "difficulty": 0.2, "min_read_time": 3, "expected_time": 25,
            "options": [
                {"id": "a", "text": "a + 4 = b"},
                {"id": "b", "text": "a + 4 = b + 4"},
                {"id": "c", "text": "a − 4 = b + 4"},
                {"id": "d", "text": "4a = b"},
            ],
            "answer": {"option": "b"},
            "bugs": [{"answer": "a", "tag": "M-ONESIDE"}, {"answer": "c", "tag": "M-SIGN"}, {"answer": "d", "tag": "M-ONESIDE"}],
            "hints": {
                "1": "ถ้าเพิ่มของในจานเดียวของตาชั่ง ตาชั่งยังสมดุลไหม",
                "2": "สมบัติการเท่ากัน: บวกจำนวนเดียวกันทั้งสองข้าง สมการยังเป็นจริง",
                "3": "หาตัวเลือกที่ทำการกระทำเดียวกันกับทั้ง a และ b",
            },
            "socratic": [SOCRATIC_BALANCE],
        },
        {
            "id": "E-03", "concept": "C-EQP", "kind": "remedial", "iso_of": None, "isomorphs": [],
            "format": "numeric", "prompt": "ต้องนำจำนวนใดมาลบออกจากทั้งสองข้าง จึงจะเหลือ x ตัวเดียว", "math": "x + 6 = 10",
            "difficulty": 0.15, "min_read_time": 3, "expected_time": 20,
            "answer": {"value": 6},
            "bugs": [{"answer": -6, "tag": "M-SIGN"}, {"answer": 10, "tag": "M-ONESIDE"}],
            "hints": {
                "1": "ดูว่ามีจำนวนใดบวกอยู่กับ x",
                "2": "การกระทำตรงข้ามของการบวกคือการลบ ต้องลบจำนวนเดียวกันทั้งสองข้าง",
                "3": "จำนวนที่บวกอยู่กับ x ในสมการนี้คือจำนวนที่ต้องนำมาลบ",
            },
            "socratic": [SOCRATIC_BALANCE],
        },
        {
            "id": "E-04", "concept": "C-EQP", "kind": "remedial", "iso_of": None, "isomorphs": [],
            "format": "short", "prompt": "สมบัติที่บอกว่า \"ลบจำนวนเดียวกันออกจากทั้งสองข้างของสมการ สมการยังเป็นจริง\" เรียกว่าสมบัติอะไร",
            "math": None, "difficulty": 0.25, "min_read_time": 4, "expected_time": 30,
            "answer": {"accepted": ["สมบัติการเท่ากัน", "สมบัติของการเท่ากัน", "การเท่ากัน", "สมบัติการเท่ากันเกี่ยวกับการลบ"]},
            "bugs": [],
            "hints": {
                "1": "สมบัตินี้เกี่ยวกับการทำให้สองข้างของสมการยังสมดุลกันเหมือนตาชั่ง",
                "2": "นึกถึงเครื่องหมาย = ที่บอกว่าสองข้างมีค่าเท่ากัน ชื่อสมบัตินี้ตั้งตามความหมายนั้น",
                "3": "ลองตอบในรูป \"สมบัติ...\" โดยเติมคำที่บอกความสัมพันธ์ของเครื่องหมาย =",
            },
            "socratic": ["เครื่องหมาย = ในสมการบอกความสัมพันธ์แบบใดระหว่างสองข้าง"],
        },
    ]

    concepts = [
        {"id": "C-INT", "name": "บวกลบจำนวนเต็ม", "grade": "ม.1", "prerequisites": [],
         "description": "การบวกและลบจำนวนเต็มบวกและจำนวนเต็มลบ รวมถึงการลบด้วยจำนวนลบ"},
        {"id": "C-EQP", "name": "สมบัติการเท่ากัน", "grade": "ม.1", "prerequisites": ["C-INT"],
         "description": "ทำการกระทำเดียวกันกับทั้งสองข้างของสมการ แล้วสมการยังเป็นจริง"},
        {"id": "C-ONE", "name": "สมการขั้นเดียว", "grade": "ม.1", "prerequisites": ["C-EQP", "C-INT"],
         "description": "สมการที่แก้ได้ด้วยการกระทำครั้งเดียว เช่น x + 7 = 12 หรือ 3x = 18"},
        {"id": "C-TWO", "name": "สมการสองขั้น", "grade": "ม.2", "prerequisites": ["C-ONE", "C-EQP", "C-INT"],
         "description": "สมการรูป ax + b = c ต้องกำจัดค่าคงที่ก่อน แล้วจึงหารด้วยสัมประสิทธิ์"},
        {"id": "C-BOTH", "name": "ตัวแปรสองข้าง", "grade": "ม.2", "prerequisites": ["C-TWO"],
         "description": "สมการที่มี x อยู่ทั้งสองข้าง ต้องรวมพจน์ที่มี x ไว้ข้างเดียวกันก่อน"},
    ]

    bug_tags = [
        {"id": "M-SIGN", "type": "misconception", "name": "ย้ายข้างโดยไม่เปลี่ยนเครื่องหมาย", "prerequisite": "C-EQP",
         "description": "ย้ายจำนวนข้ามเครื่องหมายเท่ากับโดยคงเครื่องหมายเดิม เช่น 2x + 3 = 11 กลายเป็น 2x = 11 + 3",
         "response": "ชี้ให้เห็นว่าการย้ายข้างที่แท้จริงคือการลบหรือบวกจำนวนเดียวกันทั้งสองข้าง แล้วถามว่าถ้าเอา 3 ออกจากฝั่งซ้าย ฝั่งขวาต้องทำอย่างไร",
         "socratic": "ถ้าเอาจำนวนนี้ออกจากฝั่งซ้าย ฝั่งขวาต้องทำอะไรถึงจะยังเท่ากัน"},
        {"id": "M-ORDER", "type": "misconception", "name": "หารก่อนกำจัดค่าคงที่", "prerequisite": "C-EQP",
         "description": "หารด้วยสัมประสิทธิ์เฉพาะบางพจน์ก่อนจัดการค่าคงที่ จึงได้ x = c ÷ a − b",
         "response": "ชวนให้เห็นว่าการหารต้องหารทุกพจน์ของแต่ละข้าง และการกำจัดค่าคงที่ก่อนจะง่ายกว่า",
         "socratic": "ถ้าหารด้วย a ต้องหารพจน์ไหนบ้าง แล้วค่าคงที่ที่บวกอยู่ล่ะ"},
        {"id": "M-SUBCOEF", "type": "misconception", "name": "ลบสัมประสิทธิ์แทนการหาร", "prerequisite": "C-ONE",
         "description": "มอง 2x เหมือน 2 + x จึงลบ 2 ออกแทนการหารด้วย 2",
         "response": "ถามว่า 2x หมายถึงอะไร (2 คูณ x) แล้วการกระทำตรงข้ามของการคูณคืออะไร",
         "socratic": "2x หมายถึง 2 บวก x หรือ 2 คูณ x"},
        {"id": "M-MULT", "type": "misconception", "name": "คูณแทนการหาร", "prerequisite": "C-ONE",
         "description": "เมื่อเห็น 3x = 18 ก็นำ 18 คูณ 3 แทนการหาร",
         "response": "ชวนลองแทนค่ากลับ ถ้า x มีค่าเท่านั้นจริง 3x จะได้เท่าไร",
         "socratic": "ถ้า x เท่ากับคำตอบนี้ 3 คูณ x จะได้ 18 ไหม"},
        {"id": "M-ONESIDE", "type": "misconception", "name": "ทำการกระทำกับสมการเพียงข้างเดียว", "prerequisite": "C-EQP",
         "description": "ลบหรือบวกจำนวนกับข้างเดียวของสมการ ทำให้สมการไม่สมดุล",
         "response": "ใช้ภาพตาชั่งให้เห็นว่าต้องทำกับทั้งสองข้างเสมอ",
         "socratic": "ถ้าหยิบของออกจากจานเดียว ตาชั่งจะเอียงไหม"},
        {"id": "M-NEG", "type": "misconception", "name": "ลบด้วยจำนวนลบผิด", "prerequisite": "C-INT",
         "description": "คิดว่า (−4) − (−6) = −10 เพราะมองการลบด้วยจำนวนลบเป็นการลบตามปกติ",
         "response": "ทบทวนว่าการลบด้วยจำนวนลบเท่ากับการบวกด้วยจำนวนบวก",
         "socratic": "การเอาหนี้ออกไป ทำให้เรามีเงินมากขึ้นหรือน้อยลง"},
        {"id": "S-ARITH", "type": "slip", "name": "คำนวณคลาดเคลื่อน", "prerequisite": None,
         "description": "ขั้นตอนถูกต้องแต่คำนวณตัวเลขคลาดไปเล็กน้อย",
         "response": "สะกิดให้ตรวจการคำนวณอีกรอบ ไม่ต้องอธิบายหลักการใหม่",
         "socratic": "ลองตรวจการคำนวณทีละขั้นอีกรอบ มีขั้นไหนที่คิดเร็วไปไหม"},
        {"id": "S-SIGNFLIP", "type": "slip", "name": "เผลอใส่เครื่องหมายผิด", "prerequisite": None,
         "description": "ได้ตัวเลขถูกแต่เครื่องหมายบวกลบกลับกัน",
         "response": "ชวนให้ตรวจเครื่องหมายของคำตอบ",
         "socratic": "ลองดูเครื่องหมายของคำตอบอีกครั้ง ควรเป็นบวกหรือลบ"},
    ]

    walkthroughs = [
        {"concept": "C-TWO", "title": "แก้สมการสองขั้นทีละขั้น", "problem": "7x + 3 = 59",
         "steps": [
             "กำจัดค่าคงที่: ลบ 3 ทั้งสองข้าง  7x + 3 − 3 = 59 − 3  จึงได้ 7x = 56",
             "หารด้วยสัมประสิทธิ์: หาร 7 ทั้งสองข้าง  7x ÷ 7 = 56 ÷ 7  จึงได้ x = 8",
             "ตรวจคำตอบ: 7(8) + 3 = 56 + 3 = 59 ตรงกับฝั่งขวา",
         ]},
        {"concept": "C-ONE", "title": "แก้สมการขั้นเดียว", "problem": "x − 5 = 12",
         "steps": [
             "ฝั่งซ้ายมี − 5 อยู่กับ x การกระทำตรงข้ามคือบวก 5",
             "บวก 5 ทั้งสองข้าง  x − 5 + 5 = 12 + 5  จึงได้ x = 17",
             "ตรวจคำตอบ: 17 − 5 = 12 ถูกต้อง",
         ]},
        {"concept": "C-EQP", "title": "สมบัติการเท่ากันกับตาชั่ง", "problem": "3 + 5 = 8",
         "steps": [
             "สมการเหมือนตาชั่งที่สองจานหนักเท่ากัน",
             "ถ้าหยิบ 2 ออกจากทั้งสองจาน  3 + 5 − 2 = 8 − 2  ตาชั่งยังสมดุล (6 = 6)",
             "ถ้าหยิบออกจากจานเดียว ตาชั่งจะเอียง สมการจึงไม่เป็นจริงอีกต่อไป",
         ]},
        {"concept": "C-INT", "title": "ลบด้วยจำนวนลบ", "problem": "(−7) − (−3)",
         "steps": [
             "การลบด้วยจำนวนลบเท่ากับการบวกด้วยจำนวนบวก: (−7) − (−3) = (−7) + 3",
             "บนเส้นจำนวน เริ่มที่ −7 แล้วเดินไปทางขวา 3 ช่อง",
             "จึงหยุดที่ −4",
         ]},
        {"concept": "C-BOTH", "title": "สมการที่มี x สองข้าง", "problem": "6x + 1 = 2x + 25",
         "steps": [
             "ลบ 2x ทั้งสองข้าง  จะได้ 4x + 1 = 25",
             "ลบ 1 ทั้งสองข้าง  จะได้ 4x = 24",
             "หาร 4 ทั้งสองข้าง  จะได้ x = 6",
         ]},
    ]

    question_sets = [
        {
            "id": "QS-1",
            "name": "ชุดที่ 1 แก้สมการสองขั้น",
            "description": "ฝึกแก้สมการรูป ax + b = c มีโจทย์ปูพื้นฐานจำนวนเต็ม สมบัติการเท่ากัน และสมการขั้นเดียว",
            "target_concept": "C-TWO",
            "main_items": [m[0] for m in mains],
            "challenge_items": ["H-01", "H-02", "H-03"],
            "max_items": 20,
            "published": True,
        }
    ]

    return {
        "id": "math-m2",
        "name": "คณิตศาสตร์ ม.2",
        "grade": "ม.2",
        "description": "หน่วยสมการเชิงเส้นตัวแปรเดียว วิชาตัวอย่างที่ติดมากับระบบ",
        "concepts": concepts,
        "bug_tags": bug_tags,
        "items": items,
        "walkthroughs": walkthroughs,
        "question_sets": question_sets,
    }


SAMPLE_DOCUMENT_NAME = "สรุปการแก้สมการเชิงเส้นตัวแปรเดียว.md"

SAMPLE_DOCUMENT = """# สรุปการแก้สมการเชิงเส้นตัวแปรเดียว

## สมบัติการเท่ากัน
สมการเปรียบเหมือนตาชั่งที่สองจานหนักเท่ากัน ถ้านำจำนวนเดียวกันมาบวก ลบ คูณ หรือหาร (ที่ไม่ใช่ศูนย์) กับทั้งสองข้างของสมการ สมการยังเป็นจริงเสมอ การกระทำกับข้างเดียวทำให้ตาชั่งเอียงและสมการไม่เป็นจริง

## การกระทำตรงข้าม
การบวกกับการลบเป็นการกระทำตรงข้ามกัน การคูณกับการหารก็เป็นการกระทำตรงข้ามกัน เมื่อต้องการให้ x อยู่ตัวเดียว ให้ใช้การกระทำตรงข้ามกับสิ่งที่ติดอยู่กับ x

## ขั้นตอนแก้สมการสองขั้น ax + b = c
ขั้นที่หนึ่ง กำจัดค่าคงที่ b ออกจากข้างที่มี x ด้วยการลบ b (หรือบวกถ้า b เป็นจำนวนลบ) ทั้งสองข้าง
ขั้นที่สอง หารทั้งสองข้างด้วยสัมประสิทธิ์ a เพื่อให้เหลือ x ตัวเดียว
ขั้นที่สาม ตรวจคำตอบโดยแทนค่า x กลับลงในสมการเดิม ถ้าสองข้างเท่ากัน คำตอบถูกต้อง

## ข้อผิดพลาดที่พบบ่อย
ย้ายข้างโดยไม่เปลี่ยนเครื่องหมาย: คิดว่า 2x + 3 = 11 กลายเป็น 2x = 11 + 3 ที่ถูกคือลบ 3 ทั้งสองข้าง
หารก่อนกำจัดค่าคงที่: หารเฉพาะ 2x แต่ไม่หารค่าคงที่ ทำให้สมการไม่สมดุล
ลบสัมประสิทธิ์แทนการหาร: มอง 2x เป็น 2 + x ทั้งที่ 2x หมายถึง 2 คูณ x
ลบด้วยจำนวนลบผิด: a − (−b) เท่ากับ a + b ไม่ใช่ a − b

## จำนวนเต็มลบบนเส้นจำนวน
บวกจำนวนบวกคือเดินไปทางขวาของเส้นจำนวน บวกจำนวนลบคือเดินไปทางซ้าย การลบด้วยจำนวนลบจึงเท่ากับเดินไปทางขวา

## ภาษาไทยกับการตัดคำ
ภาษาไทยเขียนติดกันไม่มีช่องว่างระหว่างคำ คำอย่าง "ตากลม" อาจตัดได้เป็น "ตาก ลม" หรือ "ตา กลม" ระบบค้นเอกสารจึงต้องตัดคำภาษาไทยก่อนเทียบคำค้น
"""
