"""เงื่อนไขบนเส้นของ Flow ที่ AI ออกแบบใน Gem (ADR-0004)

เงื่อนไขเขียนเป็นนิพจน์สั้น ๆ แบบ Python เช่น "wrong and error_count >= 2" อ่านออกได้ทั้งครูและ AI
ตัวแปรมาจาก Student Model เท่านั้น (VARS) ไม่มีการเรียกฟังก์ชันหรือ eval
ตรวจด้วย ast ว่าใช้แค่ and / or / not / การเปรียบเทียบ / ตัวเลข / ตัวแปรที่รู้จัก
และเศษจากการหาร (ตัวแปร % ตัวเลข) สำหรับแนวทางแบบ "ทุก 2 ข้อ" เช่น items_done % 2 == 0
"""

import ast

# ตัวแปรที่เงื่อนไขใช้ได้: (คำอธิบายภาษาคน, ชนิด) ชนิด bool ใช้ตรง ๆ ได้ เช่น "correct and first_try"
VARS: dict[str, tuple[str, str]] = {
    "correct": ("ตอบถูก", "bool"),
    "wrong": ("ตอบผิด", "bool"),
    "error_count": ("จำนวนครั้งที่ผิดในข้อนี้ นับรวมครั้งล่าสุดแล้ว (ผิดครั้งแรก = 1)", "int"),
    "chat_help": ("จำนวนครั้งที่ถามครูผู้ช่วยในแชตเรื่องข้อนี้ (นับรวมเป็นการขอคำใบ้ด้วย)", "int"),
    "hint_level": ("ระดับคำใบ้สูงสุดที่นักเรียนเห็นแล้วในข้อนี้ (ถามในแชตนับเป็นระดับ 1) ก่อนไปขั้นถัดไป (ยังไม่เคยเห็น = 0) ใช้ error_count เลือกระดับคำใบ้ตามครั้งที่ผิด", "int"),
    "misconception": ("คำตอบผิดตรงกับความเข้าใจผิด (Misconception) ใน Bug Library", "bool"),
    "slip": ("คำตอบผิดแบบสะเพร่า (Slip)", "bool"),
    "first_try": ("ถูกตั้งแต่ครั้งแรกโดยไม่ใช้คำใบ้", "bool"),
    "rt": ("เวลาคิดของคำตอบล่าสุด (วินาที หลังตัดค่าเกิน)", "num"),
    "rt_ratio": ("เวลาคิดเทียบกับเวลาที่คาดไว้ของข้อ (1 = พอดี)", "num"),
    "slow": ("คิดนานกว่าเวลาที่คาดไว้ของข้อ", "bool"),
    "impasse": ("คะแนน Fuzzy ว่าติดหล่ม จากเวลาคิดที่ยาวขึ้นต่อเนื่อง (0–100)", "num"),
    "mastery": ("Mastery ของมโนทัศน์เป้าหมาย (0–1) ใช้กับเกณฑ์จบชุดและความเข้าใจรวม", "num"),
    "concept_mastery": ("Mastery ของมโนทัศน์ของข้อนี้ (0–1) ใช้ตัดสินรายข้อ ไม่ใช่เกณฑ์จบชุด", "num"),
    "items_done": ("จำนวนข้อที่ทำถูกแล้วใน Session นี้", "int"),
    "items_count": ("จำนวนข้อที่ได้รับแล้วใน Session นี้", "int"),
    "streak": ("ถูกตั้งแต่ครั้งแรกติดกันกี่ข้อ", "int"),
    "solved_here": ("ทำถูกกี่ข้อแล้วในขั้นนี้ (นับใหม่ทุกครั้งที่เข้าขั้นนี้จากขั้นอื่น)", "int"),
    "has_prerequisite": ("เรื่องของข้อนี้มีโจทย์ความรู้พื้นฐานให้ทบทวน (ไม่มี = ใช้ตัวอย่างทีละขั้นแทนได้)", "bool"),
    "rounds": ("ส่งไปทบทวนพื้นฐานจากข้อนี้มาแล้วกี่รอบ", "int"),
    "mains_left": ("โจทย์หลักที่ยังไม่ผ่าน", "int"),
    "challenge_done": ("ทำโจทย์ท้าทายถูกแล้ว", "bool"),
    "visits": ("เข้าขั้นนี้มาแล้วกี่ครั้งใน Session นี้", "int"),
    "judge_pass": ("AI ประเมินว่าคำอธิบายผ่านเกณฑ์ของครู", "bool"),
    "judge_score": ("คะแนนคำอธิบายที่ AI ประเมิน (0–100)", "num"),
    "target_visits": ("นักเรียนเคยเข้าขั้นปลายทางของเส้นนี้มาแล้วกี่ครั้ง ใช้กับแนวทางที่ทำครั้งเดียว "
                      "เช่น items_done >= 3 and target_visits == 0 = ครั้งแรกที่ครบ 3 ข้อ", "int"),
    "widget_pass": ("นักเรียนทำ Widget ล่าสุดถูก (Widget ที่ AI เขียนเองเป็นจริงเสมอ)", "bool"),
    "widget_tries": ("จำนวนครั้งที่ส่งคำตอบใน Widget นี้ นับรวมครั้งล่าสุดแล้ว", "int"),
    "bug": ("รหัสข้อผิดพลาดของคำตอบผิดล่าสุด", "text"),
    "bug_type": ("ชนิดข้อผิดพลาดล่าสุด (misconception หรือ slip)", "text"),
}

OPS = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
OP_TEXT = {"==": "เท่ากับ", "!=": "ไม่เท่ากับ", "<": "น้อยกว่า", "<=": "ไม่เกิน", ">": "มากกว่า", ">=": "อย่างน้อย"}
ALWAYS = {"", "always", "else", "otherwise", "true", "True"}


class ConditionError(ValueError):
    pass


def parse(text: str | None) -> ast.AST | None:
    """คืน None ถ้าเป็นเส้นที่ผ่านเสมอ ไม่อย่างนั้นคืน ast ที่ตรวจแล้ว"""
    text = (text or "").strip()
    if text in ALWAYS:
        return None
    try:
        tree = ast.parse(text, mode="eval").body
    except SyntaxError as error:
        raise ConditionError(f"อ่านเงื่อนไข \"{text}\" ไม่ได้") from error
    _check(tree, text)
    return tree


def _check(node: ast.AST, text: str):
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _check(value, text)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        _check(node.operand, text)
    elif isinstance(node, ast.Compare):
        if not all(type(op) in OPS for op in node.ops):
            raise ConditionError(f"เงื่อนไข \"{text}\" ใช้ตัวเปรียบเทียบที่ไม่รองรับ")
        for part in [node.left, *node.comparators]:
            _check(part, text)
    elif isinstance(node, ast.Name):
        if node.id not in VARS and node.id not in ("True", "False"):
            raise ConditionError(f"ไม่รู้จักตัวแปร \"{node.id}\" ในเงื่อนไข \"{text}\"")
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, bool, str)) or (isinstance(node.value, str) and len(node.value) > 40):
            raise ConditionError(f"เงื่อนไข \"{text}\" ใช้ได้แค่ตัวเลข true/false และข้อความสั้น ๆ ในเครื่องหมายคำพูด")
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        pass
    elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Name)
          and isinstance(node.right, ast.Constant) and type(node.right.value) is int and 1 < node.right.value <= 100):
        _check(node.left, text)
        if VARS.get(node.left.id, ("", ""))[1] not in ("int", "num"):
            raise ConditionError(f"เงื่อนไข \"{text}\" หาเศษได้เฉพาะตัวแปรที่เป็นตัวเลข")
    else:
        raise ConditionError(f"เงื่อนไข \"{text}\" ใช้ได้แค่ and, or, not และการเปรียบเทียบ")


def evaluate(text: str | None, values: dict) -> bool:
    tree = parse(text)
    return True if tree is None else bool(_value(tree, values))


def _value(node: ast.AST, values: dict):
    if isinstance(node, ast.BoolOp):
        results = (_value(v, values) for v in node.values)
        return all(results) if isinstance(node.op, ast.And) else any(results)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _value(node.operand, values)
    if isinstance(node, ast.UnaryOp):
        return -_value(node.operand, values)
    if isinstance(node, ast.BinOp):
        left = _value(node.left, values)
        return None if left is None else left % node.right.value
    if isinstance(node, ast.Compare):
        left = _value(node.left, values)
        for op, right_node in zip(node.ops, node.comparators):
            right = _value(right_node, values)
            # ตัวแปรที่ยังไม่มีค่า (เช่น judge_score ก่อนประเมิน) ทำให้การเปรียบเทียบเป็นเท็จ
            if left is None or right is None or not _compare(OPS[type(op)], left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        if node.id in ("True", "False"):
            return node.id == "True"
        return values.get(node.id)
    return node.value


def _compare(op: str, left, right) -> bool:
    if isinstance(left, str) != isinstance(right, str):
        # ข้อความเทียบกับตัวเลขไม่ได้ (เช่น bug > 2) ถือว่าเป็นเท็จ ไม่ใช่ error ตอนนักเรียนเรียน
        return op == "!="
    if isinstance(left, str) and op not in ("==", "!="):
        return False
    return {"==": left == right, "!=": left != right, "<": left < right, "<=": left <= right,
            ">": left > right, ">=": left >= right}[op]


def names(text: str | None) -> set[str]:
    tree = parse(text)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - {"True", "False"} if tree is not None else set()


def describe(text: str | None) -> str:
    """แปลเงื่อนไขเป็นภาษาคนสำหรับหน้าครูและผังของ Admin"""
    tree = parse(text)
    return "ทุกกรณีที่เหลือ" if tree is None else _say(tree)


def _say(node: ast.AST) -> str:
    if isinstance(node, ast.BoolOp):
        joiner = " และ " if isinstance(node.op, ast.And) else " หรือ "
        return joiner.join(_say(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return f"ไม่ใช่ ({_say(node.operand)})" if not isinstance(node.operand, ast.Name) else f"ไม่{VARS[node.operand.id][0]}"
    if (isinstance(node, ast.Compare) and isinstance(node.left, ast.BinOp) and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq) and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == 0):
        return f"{_say(node.left.left)} ครบทุก {node.left.right.value}"
    if isinstance(node, ast.BinOp):
        return f"เศษของ {_say(node.left)} หารด้วย {node.right.value}"
    if isinstance(node, ast.Compare):
        parts = [_say(node.left)]
        for op, right in zip(node.ops, node.comparators):
            parts += [OP_TEXT[OPS[type(op)]], _say(right)]
        return " ".join(parts)
    if isinstance(node, ast.Name):
        return VARS[node.id][0] if node.id in VARS else node.id
    if isinstance(node, ast.UnaryOp):
        return f"-{_say(node.operand)}"
    if isinstance(node.value, str):
        return f"\"{node.value}\""
    return "จริง" if node.value is True else "เท็จ" if node.value is False else f"{node.value:g}"
