"""จำลองเส้นทางของ Flow: ลองทุกกรณีของตัวแปรที่เส้นออกจากแต่ละขั้นใช้ แล้วดูว่า engine จะไปขั้นไหน (ADR-0004)

ใช้สามที่: หาเส้นที่ไม่มีวันถูกใช้ (มีเส้นก่อนหน้าดักไว้หมด) ทำตารางให้ AI ตรวจกับแนวทางของครูอีกรอบตอนออกแบบ
และแสดงตารางให้ครูอ่านในแท็บ Flow ว่า "ถ้านักเรียนเป็นแบบนี้ จะไปขั้นไหน"
ไม่เรียก AI และไม่แตะ Student Model จริง ใช้ตัวตรวจเงื่อนไขชุดเดียวกับ engine
"""

import ast
import itertools
import json
from collections.abc import Iterator
from functools import lru_cache

from ..engine import conditions

BASE = {"correct": False, "wrong": False, "misconception": False, "slip": False, "first_try": False,
        "rt": 20.0, "rt_ratio": 1.0, "slow": False, "judge_pass": None, "judge_score": None, "error_count": 0,
        "hint_level": 0, "impasse": 0.0, "mastery": 0.6, "concept_mastery": 0.6, "items_done": 1, "items_count": 2,
        "streak": 0, "solved_here": 0, "rounds": 0, "mains_left": 3, "challenge_done": False, "visits": 1,
        "has_prerequisite": True, "target_visits": 0, "chat_help": 0, "widget_pass": False, "widget_tries": 1, "bug": "", "bug_type": ""}

# ค่าที่ลองต่อตัวแปร (ค่าแรก = กรณีทั่วไป) ตัวเลขในเงื่อนไขของครูถูกเพิ่มเข้าไปเองด้วย
DOMAINS = {
    "error_count": [1, 2, 3, 4], "hint_level": [0, 1], "items_done": [1, 2, 3, 4], "items_count": [2, 20],
    "streak": [0, 3], "solved_here": [0, 2], "rounds": [0, 2], "mains_left": [3, 0], "visits": [1, 2],
    "widget_tries": [1, 2], "target_visits": [0, 1], "chat_help": [0, 4], "mastery": [0.6, 0.9], "concept_mastery": [0.6, 0.9],
    "impasse": [0.0, 80.0], "rt": [20.0, 60.0], "rt_ratio": [1.0, 2.0], "judge_score": [90, 30],
    "bug_type": ["", "slip", "misconception"],
}
# เพดานกรณีต่อกลุ่มหลังตัดค่าที่ให้ผลเหมือนกันแล้ว (Flow จริงที่ใช้ตัวแปรมากสุดเหลือราว 83,000 กรณี ใช้ไม่ถึง 2 วินาที)
MAX_CASES = 200_000
# ตัวแปรที่ _consistent คิดจากตัวแปรอื่น เงื่อนไขที่ใช้ตัวเหล่านี้ทำให้ตัวแปรต้นทางต้องลองทุกค่า
SOURCES = {"wrong": {"correct"}, "slip": {"bug_type", "correct"}, "misconception": {"bug_type", "correct"},
           "first_try": {"correct", "hint_level", "error_count"}, "judge_pass": {"judge_score"}}
# กรณีทดสอบมาตรฐานของขั้นทำโจทย์ ลองเสมอแม้ Flow ไม่ได้ใช้ตัวแปรนั้น ตารางจึงเห็นแนวทางที่ AI ลืมใส่
# เช่น ผิดครั้งที่ 3 แล้วติดหล่ม แต่ยังได้คำใบ้ระดับ 3 (ตัวแปรที่ไม่ได้ใช้ไม่ทำให้ engine เลือกต่างกัน แค่โผล่ในตาราง)
PROBES = {"wrong": ["bug_type", "impasse", "has_prerequisite", "rounds", "chat_help"],
          "correct": ["hint_level", "mastery", "mains_left", "challenge_done"]}
SHOW_ALWAYS = {"impasse", "has_prerequisite", "rounds", "mastery", "mains_left", "challenge_done", "chat_help"}
# แสดงทุกครั้งที่ผิด ไม่ใช่แค่ตั้งแต่ครั้งที่ 3 (เจอจาก Gemini จริง: ถามแชต 4 ครั้งแล้วผิดครั้งแรก ยังได้คำใบ้แทนตัวอย่าง)
EVERY_ERROR = {"chat_help"}
# กรณีที่ต้องเปลี่ยนหลายตัวแปรพร้อมกันถึงจะเห็นผล (ตารางปกติเปลี่ยนทีละตัว) เช่น เข้าเกณฑ์จบชุด
COMBOS = [("ตอบถูก · ไม่ใช้คำใบ้ · โจทย์หลักครบ · Mastery 0.9", {"correct": True, "mains_left": 0, "mastery": 0.9}),
          ("ตอบถูก · หลังใช้คำใบ้ · โจทย์หลักครบ · Mastery 0.9", {"correct": True, "hint_level": 1, "mains_left": 0, "mastery": 0.9}),
          ("ตอบผิด · ผิดครั้งที่ 2 · โจทย์หลักครบ · Mastery 0.9 · ทำโจทย์ท้าทายได้",
           {"wrong": True, "error_count": 2, "mains_left": 0, "mastery": 0.9, "challenge_done": True})]
FLOOR = {"": 0, "slip": 1, "misconception": 2}
DEAD = "เส้นที่ไม่มีวันถูกใช้: "


def _constants(edges: list[dict]) -> dict[str, set]:
    """ตัวเลขที่เงื่อนไขเทียบกับตัวแปร เช่น items_done == 5 → ลอง 4 5 6 ด้วย (ค่าตรงตัวมาก่อน ค่า ±1 ไว้ท้าย ถูกตัดก่อน)"""
    found: dict[str, set] = {}
    for edge in edges:
        tree = conditions.parse(edge.get("when"))
        for node in ast.walk(tree) if tree is not None else []:
            if isinstance(node, ast.Compare):
                names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
                numbers = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant)
                           and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)]
                strings = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                for name in names:
                    for number in numbers:
                        found.setdefault(name, set()).update({number - 1, number, number + 1} if isinstance(number, int)
                                                             else {number - 0.05, number, number + 0.05})
                    found.setdefault(name, set()).update(strings)
    return found


def _domain(name: str, extra: set) -> list:
    kind = conditions.VARS.get(name, ("", "bool"))[1]
    if kind == "bool":
        usual = bool(BASE.get(name, False))
        return [usual, not usual]
    if name == "bug":
        return [""] + sorted(v for v in extra if isinstance(v, str))
    values = list(DOMAINS.get(name, [BASE.get(name, 0)]))
    low = 1 if name in ("error_count", "visits", "widget_tries") else 0
    numbers = sorted(v for v in extra if not isinstance(v, str))
    exact = [v for v in numbers if not any(abs(v - w) in (1, 0.05) and w in numbers and v != w and _is_exact(w, numbers)
                                           for w in numbers)]
    for value in exact + [v for v in numbers if v not in exact]:
        if value not in values and value >= low:
            values.append(value)
    return values


def _is_exact(value, numbers: list) -> bool:
    """ค่าตรงตัวจากเงื่อนไข = ค่าที่มีทั้ง ค่า-1 และ ค่า+1 อยู่ในชุด (ชุดถูกสร้างเป็นสามค่าเสมอ)"""
    step = 1 if isinstance(value, int) else 0.05
    return any(abs((value - step) - n) < 1e-9 for n in numbers) and any(abs((value + step) - n) < 1e-9 for n in numbers)


def _consistent(values: dict) -> dict:
    """ค่าที่ผูกกัน: ตอบถูกกับตอบผิดตรงข้ามกัน ชนิดข้อผิดพลาดกับ slip/misconception ตรงกัน"""
    out = dict(values)
    if out["correct"]:
        out["wrong"] = False
        out["bug"], out["bug_type"] = "", ""
    out["slip"] = out["bug_type"] == "slip"
    out["misconception"] = out["bug_type"] == "misconception"
    out["first_try"] = out["correct"] and out["hint_level"] == 0 and out["error_count"] <= 1
    if out.get("judge_score") is not None and out.get("judge_pass") is None:
        out["judge_pass"] = out["judge_score"] >= 60
    return out


def _winner(edges: list[tuple[dict, ast.AST | None]], values: dict, visits: dict) -> dict | None:
    for edge, tree in edges:
        current = {**values, "target_visits": visits.get(edge["to"], values["target_visits"])}
        if tree is None or conditions._value(tree, current):
            return edge
    return None


def _groups(step: dict, edges: list[dict]) -> list[tuple[dict, list[str]]]:
    """(ค่าคงที่ของกลุ่ม, ตัวแปรที่ลอง) ขั้นทำโจทย์แยกกรณีตอบถูกกับตอบผิด เพราะตัวแปรคนละชุดมีผล"""
    used = [conditions.names(e.get("when")) for e in edges]
    if step["kind"] != "item":
        names = sorted(set().union(*used) if used else set())
        return [({}, names)]
    groups = []
    for outcome, other in (("correct", "wrong"), ("wrong", "correct")):
        # ทุกตัวแปรที่เส้นใช้ (เส้นที่มี correct ก็อาจเป็นจริงตอนตอบผิดได้ เช่น "(correct and ...) or challenge_done")
        names = sorted(set().union(*used) - {"correct", "wrong"} if used else set())
        if outcome == "wrong" and "error_count" not in names:
            names.append("error_count")
        names += [p for p in PROBES[outcome] if p not in names]
        groups.append(({"correct": outcome == "correct", "wrong": outcome == "wrong"}, names))
    return groups


def reached(flow_spec: dict, step: dict) -> list[tuple[dict, list[dict | None]]]:
    """ต่อกลุ่มกรณี (ค่าคงที่ของกลุ่ม เช่น ตอบผิด): เส้นที่ engine เลือกได้ เรียงตามกรณีแรกที่ไปเส้นนั้น (None = ไม่มีเส้นไหนเป็นจริง)"""
    edges, key = _key(flow_spec, step)
    return [(fixed, [edges[i] if i >= 0 else None for i in firsts]) for fixed, firsts in _cases(key)]


def _key(flow_spec: dict, step: dict) -> tuple[list[dict], str]:
    edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
    return edges, json.dumps([step["id"], step["kind"], [[e["to"], e.get("when") or ""] for e in edges]], ensure_ascii=False)


def _unused(flow_spec: dict, step: dict) -> list[dict]:
    """เส้นของขั้นนี้ที่ไม่มีกรณีไหนไปถึง"""
    edges, key = _key(flow_spec, step)
    used = {i for _, firsts in _cases(key) for i in firsts}
    return [e for i, e in enumerate(edges) if i not in used]


@lru_cache(maxsize=256)
def _cases(key: str) -> tuple:
    """จำแค่เลขเส้นที่ชนะ (-1 = ไม่มีเส้น) ตามลำดับกรณีแรกที่ไปถึง ไม่เก็บค่าตัวแปรของทุกกรณี
    (เดิมเก็บทุกกรณี ราว 17 MB ต่อขั้น แคช 256 ขั้นเคยทำ RAM ของเซิร์ฟเวอร์เต็มจนเว็บค้าง)"""
    step_id, kind, pairs = json.loads(key)
    edges = [{"to": to, "when": when, "index": i} for i, (to, when) in enumerate(pairs)]
    return tuple(_enumerate({"id": step_id, "kind": kind}, edges))


def _enumerate(step: dict, edges: list[dict]):
    try:
        parsed = [(e, conditions.parse(e.get("when"))) for e in edges]
    except conditions.ConditionError:
        return
    extra = _constants(edges)
    used = set().union(*(conditions.names(e.get("when")) for e in edges))
    sources = set().union(*(SOURCES.get(n, set()) for n in used))
    tests, tangled = _tests(parsed)
    for fixed, names in _groups(step, edges):
        # ตัวแปรที่เงื่อนไขไม่ได้ใช้ (ใส่ไว้ให้ตารางแสดง) ไม่เปลี่ยนเส้นที่ engine เลือก จึงไม่ต้องลอง
        names = [n for n in names if n in used or n in sources]
        domains = [_distinct(n, _domain(n, extra.get(n, set())), None if n in tangled or n in sources else tests.get(n, []))
                   for n in names]
        while names and _product(domains) > MAX_CASES:
            # ตัดจากโดเมนที่ยาวที่สุดทีละค่าท้าย (ค่า ±1 ของตัวเลขในเงื่อนไข) ครั้งที่ผิด 1–4 ไม่ตัด
            longest = max(range(len(domains)), key=lambda i: len(domains[i]) - (10 if names[i] == "error_count" else 0))
            domains[longest] = domains[longest][:-1]
        firsts, seen = [], set()
        for combo in itertools.product(*domains):
            edge = _winner(parsed, _consistent({**BASE, **fixed, **dict(zip(names, combo))}), {})
            index = edge["index"] if edge is not None else -1
            if index not in seen:
                seen.add(index)
                firsts.append(index)
                if len(seen - {-1}) == len(edges):
                    break  # ทุกเส้นมีกรณีไปถึงแล้ว ลองต่อไม่ได้อะไรเพิ่ม
        yield fixed, tuple(firsts)


def _atoms(node: ast.AST):
    """ส่วนย่อยที่เงื่อนไขเอาค่าจริงเท็จไปใช้ (ทุกอย่างใต้ and, or, not) เช่น mastery >= 0.8, streak, items_done % 2"""
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _atoms(value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        yield from _atoms(node.operand)
    else:
        yield node


def _tests(parsed: list[tuple[dict, ast.AST | None]]) -> tuple[dict[str, list], set[str]]:
    """ส่วนย่อยของเงื่อนไขที่ถามตัวแปรตัวเดียว และตัวแปรที่ถูกเทียบกับตัวแปรอื่น (ต้องลองทุกค่า)"""
    tests: dict[str, list] = {}
    tangled: set[str] = set()
    for _, tree in parsed:
        for atom in _atoms(tree) if tree is not None else []:
            inside = {n.id for n in ast.walk(atom) if isinstance(n, ast.Name)} - {"True", "False"}
            if len(inside) == 1 and not inside & SOURCES.keys():
                tests.setdefault(next(iter(inside)), []).append(atom)
            else:
                tangled |= inside
    return tests, tangled


def _distinct(name: str, values: list, tests: list | None) -> list:
    """ค่าที่ทุกส่วนของเงื่อนไขที่ถามตัวแปรนี้ได้ผลเท่ากันใช้แทนกันได้ ลองแค่ค่าแรก (ค่าแรกของโดเมน = กรณีทั่วไป อยู่เสมอ)
    เช่น เงื่อนไขถามแค่ mastery >= 0.8 ค่า 0.6 กับ 0.75 ให้ผลเหมือนกัน · tests = None คือต้องลองทุกค่า"""
    if tests is None:
        return values
    kept, seen = [], set()
    for value in values:
        mark = tuple(bool(conditions._value(test, {name: value})) for test in tests)
        if mark not in seen:
            seen.add(mark)
            kept.append(value)
    return kept


def _product(domains: list[list]) -> int:
    total = 1
    for d in domains:
        total *= max(len(d), 1)
    return total


def dead_in(flow_spec: dict, step: dict) -> list[dict]:
    edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
    if len(edges) < 2:
        return []
    return _unused(flow_spec, step)


def reorder_dead(flow_spec: dict) -> list[str]:
    """ย้ายเส้นที่ไม่มีวันถูกใช้ขึ้นไปก่อนเส้นที่ดักมันไว้ (ตำแหน่งต่ำสุดที่เส้นนั้นถูกใช้ได้และไม่ทำให้เส้นอื่นเสีย)
    แก้ลำดับเส้นด้วยกฎ ไม่ต้องให้ AI แก้ซ้ำ (เจอจาก Gemini จริง: เส้นถามแชตเกิน 3 ครั้งอยู่ใต้เส้นคำใบ้ที่ดักทุกกรณี)"""
    notes = []
    for step in flow_spec["steps"]:
        for edge in dead_in(flow_spec, step):
            own = [i for i, e in enumerate(flow_spec["edges"]) if e["from"] == step["id"]]
            at = own.index(next(i for i in own if flow_spec["edges"][i] is edge))
            before = len(dead_in(flow_spec, step))
            for slot in range(at - 1, -1, -1):
                trial = list(flow_spec["edges"])
                trial.remove(edge)
                trial.insert(trial.index(flow_spec["edges"][own[slot]]), edge)
                candidate = {**flow_spec, "edges": trial}
                dead = dead_in(candidate, step)
                if edge not in dead and len(dead) < before:
                    above = flow_spec["edges"][own[slot]]
                    flow_spec["edges"] = trial
                    notes.append(f"ระบบย้ายเส้น \"{edge.get('label') or edge['when']}\" ของขั้น \"{step['label']}\" "
                                 f"ขึ้นไปก่อน \"{above.get('label') or above['when'] or 'ทุกกรณี'}\" เพราะเส้นนั้นดักไว้ทุกกรณี")
                    break
    return notes


def dead_edges(flow_spec: dict) -> list[str]:
    """เส้นที่ไม่มีกรณีไหนไปถึง เพราะเส้นก่อนหน้าดักไว้หมด (แนวทางของครูบนเส้นนั้นจะไม่เกิดเลย)"""
    notes = []
    for step in flow_spec["steps"]:
        edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
        if len(edges) < 2:
            continue
        for edge in _unused(flow_spec, step):
            notes.append(f"{DEAD}จาก \"{step['label']}\" เส้น \"{edge.get('label') or edge.get('when') or 'ทุกกรณี'}\" "
                         f"({edge.get('when') or 'ทุกกรณี'}) เพราะเส้นก่อนหน้าดักทุกกรณีไว้แล้ว ย้ายเส้นนี้ขึ้นไปหรือแก้เงื่อนไข")
    return notes


SAY = {
    "hint_level": {0: "ไม่ใช้คำใบ้", 1: "หลังใช้คำใบ้"},
    "bug_type": {"": "ไม่ตรง Bug Library", "slip": "สะเพร่า", "misconception": "เข้าใจผิด"},
}


def _say(name: str, value) -> str | None:
    if name in SAY and value in SAY[name]:
        return SAY[name][value]
    label = conditions.VARS.get(name, (name, ""))[0].split(" (")[0]
    if name == "has_prerequisite":
        return "มีพื้นฐานให้ทบทวน" if value else "ไม่มีพื้นฐานให้ทบทวน"
    if isinstance(value, bool):
        return label if value else f"ไม่{label}"
    if name == "error_count":
        return f"ผิดครั้งที่ {value}"
    if name == "bug":
        return f"รหัส {value}" if value else None
    return f"{label} = {value:g}" if isinstance(value, (int, float)) else f"{label} = {value}"


KEY_VARS = ("correct", "wrong", "error_count", "bug_type", "hint_level")


def _table_cases(step: dict, edges: list[dict]) -> Iterator[tuple[dict, dict | None]]:
    """กรณีที่ตารางใช้: ตัวแปรหลัก (ผลการตอบ ครั้งที่ผิด ชนิดข้อผิดพลาด คำใบ้) ทุกค่า ตัวแปรอื่นเป็นค่าแรกหรือเปลี่ยนทีละตัว
    เรียงตามลำดับเดียวกับการไล่ทุกกรณี (itertools.product) โดยไม่ต้องไล่ทุกกรณีจริง ขั้นหนึ่งมีได้เป็นล้านกรณี"""
    try:
        parsed = [(e, conditions.parse(e.get("when"))) for e in edges]
    except conditions.ConditionError:
        return
    extra = _constants(edges)
    for fixed, names in _groups(step, edges):
        domains = [_domain(n, extra.get(n, set())) for n in names]
        keys = [i for i, n in enumerate(names) if n in KEY_VARS]
        others = [i for i, n in enumerate(names) if n not in KEY_VARS]
        picks = set()
        for combo in itertools.product(*(range(len(domains[i])) for i in keys)):
            base = [0] * len(names)
            for i, at in zip(keys, combo):
                base[i] = at
            picks.add(tuple(base))
            for i in others:
                picks.update(tuple(base[:i] + [at] + base[i + 1:]) for at in range(1, len(domains[i])))
        for pick in sorted(picks):
            values = {**fixed, **{n: domains[i][at] for i, (n, at) in enumerate(zip(names, pick))}}
            yield values, _winner(parsed, _consistent({**BASE, **values}), {})


def table(flow_spec: dict, limit: int = 40) -> list[dict]:
    """ตารางอ่านง่ายของขั้นทำโจทย์ (และขั้นที่มีหลายเส้น): กรณีทั่วไป แล้วเปลี่ยนทีละตัวแปร"""
    steps = {s["id"]: s for s in flow_spec["steps"]}
    out = []
    for step in flow_spec["steps"]:
        edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
        if len(edges) < 2:
            continue
        baseline, variants = {}, []
        tried = list(_shown(_table_cases(step, edges)))
        for values, edge in tried:
            # กรณีทั่วไป = ทุกตัวแปรเป็นค่าแรก นอกจากผลการตอบ ครั้งที่ผิด ชนิดข้อผิดพลาด และการใช้คำใบ้
            changed = [n for n, v in values.items() if n not in KEY_VARS and v != _domain(n, set())[0]]
            key = tuple(values.get(n) for n in KEY_VARS)
            target = _target(steps, edge, values)
            if not changed:
                baseline[key] = target
            elif len(changed) == 1:
                variants.append((key, values, changed[0], target))
        rows, seen = [], set()

        def row(values: dict, extra: str | None, target: str):
            words = ["ตอบถูก" if values.get("correct") else "ตอบผิด" if values.get("wrong") else ""]
            words += [w for n in ("error_count", "bug_type", "hint_level") if n in values for w in [_say(n, values[n])] if w]
            rows.append({"case": " · ".join(w for w in words + [extra or ""] if w), "to": target})

        for values, _ in tried:
            key = tuple(values.get(n) for n in KEY_VARS)
            # ครั้งที่ผิดเกิน 4 ผลเหมือน "ตั้งแต่ครั้งที่ 4" ไม่ต้องแสดงซ้ำ
            if (values.get("error_count") or 0) > 4:
                continue
            if key in baseline and key not in seen:
                seen.add(key)
                row(values, None, baseline[key])
        # กรณีพิเศษ: แสดงเฉพาะค่าที่ทำให้ไปขั้นต่างจากกรณีทั่วไป (ค่าแรกที่เปลี่ยนผล)
        shown = set()
        for key, values, name, target in variants:
            if (values.get("error_count") or 0) > 4:
                continue
            # ตัวแปรของกรณีทดสอบมาตรฐานแสดงเสมอ (ผิดตั้งแต่ครั้งที่ 3 หรือตอบถูกโดยไม่ใช้คำใบ้) แม้ผลไม่ต่าง
            probe = (name in PROBES["wrong"] and values.get("wrong")
                     and (values.get("error_count", 0) >= 3 or name in EVERY_ERROR)
                     and values.get("bug_type", "") == "") or (name in PROBES["correct"] and values.get("correct")
                                                                and values.get("hint_level") == 0)
            probe = probe and name in SHOW_ALWAYS
            if (target != baseline.get(key) or probe) and (key, name, target) not in shown:
                shown.add((key, name, target))
                row(values, _say(name, values[name]), target)
        combos = []
        if step["kind"] == "item":
            parsed = [(e, conditions.parse(e.get("when"))) for e in edges]
            for text, combo in COMBOS:
                values = _consistent({**BASE, **combo})
                combos.append({"case": text, "to": _target(steps, _winner(parsed, values, {}), values)})
        # แถวเข้าเกณฑ์จบชุดอยู่ในตารางเสมอแม้แถวอื่นเกินเพดาน AI ใช้ตารางนี้ตรวจเกณฑ์จบของครู
        out.append({"step": step["id"], "label": step["label"], "rows": rows[:limit - len(combos)] + combos})
    return out


BASELINE = ("กรณีทั่วไปในตาราง: Mastery 0.6 โจทย์หลักยังเหลือ 3 ข้อ มีพื้นฐานให้ทบทวน ยังไม่เคยส่งไปทบทวน "
            "ไม่ติดหล่ม ถูกแล้ว 1 ข้อ แต่ละแถวเปลี่ยนจากกรณีทั่วไปเฉพาะที่เขียนไว้ ตัวเลขในแถวคือค่าที่ระบบลองใส่ "
            "ไม่ใช่เกณฑ์ (เช่น Mastery 0.9 = นักเรียนที่ Mastery สูงกว่าเกณฑ์ 0.8 ของครู)\n")


def _shown(rows):
    """กรณีที่แสดงในตาราง: ตอบถูกไม่สนครั้งที่ผิดและชนิดข้อผิดพลาด ตอบผิดไม่สนการใช้คำใบ้ (ไม่ต้องแสดงซ้ำ)"""
    for values, edge in rows:
        if values.get("correct") and (values.get("error_count", 1) != 1 or values.get("bug_type", "")):
            continue
        if values.get("wrong") and values.get("hint_level", 0):
            continue
        shown = dict(values)
        if shown.get("correct"):
            shown.pop("error_count", None)
            shown.pop("bug_type", None)
        if shown.get("wrong"):
            shown.pop("hint_level", None)
        yield shown, edge


def _target(steps: dict, edge: dict | None, values: dict) -> str:
    """ปลายทางที่อ่านแล้วตรงกับที่ engine ทำ: ขั้นคำใบ้บอกระดับที่นักเรียนได้จริง (auto คิดจากครั้งที่ผิดและชนิดข้อผิดพลาด)"""
    if edge is None:
        return "ไม่มีเส้น ระบบใช้ทางเริ่มต้น"
    if edge["to"] == "back":
        return "กลับไปทำข้อเดิม"
    step = steps.get(edge["to"], {})
    if step.get("kind") == "hint":
        level = step.get("level", "auto")
        if level == "auto":
            level = max(1, min(3, max(values.get("error_count") or 1, FLOOR.get(values.get("bug_type") or "", 0))))
        name = step.get("label", edge["to"])
        # บอกชื่อขั้นเมื่อชื่อไม่ได้บอกระดับที่นักเรียนได้จริง (เช่น ขั้นชื่อ "คำใบ้ระดับ 1" แต่ตั้ง auto)
        return f"คำใบ้ระดับ {level}" if f"ระดับ {level}" in name else f"คำใบ้ระดับ {level} (ขั้น \"{name}\")"
    return step.get("label", edge["to"])


def table_text(flow_spec: dict) -> str:
    return BASELINE + "\n".join(f"ขั้น {t['label']} ({t['step']}):\n" + "\n".join(f"- {r['case']} → {r['to']}" for r in t["rows"])
                     for t in table(flow_spec))
