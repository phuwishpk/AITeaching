"""จำลองเส้นทางของ Flow: ลองทุกกรณีของตัวแปรที่เส้นออกจากแต่ละขั้นใช้ แล้วดูว่า engine จะไปขั้นไหน (ADR-0004)

ใช้สามที่: หาเส้นที่ไม่มีวันถูกใช้ (มีเส้นก่อนหน้าดักไว้หมด) ทำตารางให้ AI ตรวจกับแนวทางของครูอีกรอบตอนออกแบบ
และแสดงตารางให้ครูอ่านในแท็บ Flow ว่า "ถ้านักเรียนเป็นแบบนี้ จะไปขั้นไหน"
ไม่เรียก AI และไม่แตะ Student Model จริง ใช้ตัวตรวจเงื่อนไขชุดเดียวกับ engine
"""

import ast
import itertools

from ..engine import conditions

BASE = {"correct": False, "wrong": False, "misconception": False, "slip": False, "first_try": False,
        "rt": 20.0, "rt_ratio": 1.0, "slow": False, "judge_pass": None, "judge_score": None, "error_count": 0,
        "hint_level": 0, "impasse": 0.0, "mastery": 0.6, "concept_mastery": 0.6, "items_done": 1, "items_count": 2,
        "streak": 0, "solved_here": 0, "rounds": 0, "mains_left": 3, "challenge_done": False, "visits": 1,
        "has_prerequisite": True, "target_visits": 0, "widget_pass": False, "widget_tries": 1, "bug": "", "bug_type": ""}

# ค่าที่ลองต่อตัวแปร (ค่าแรก = กรณีทั่วไป) ตัวเลขในเงื่อนไขของครูถูกเพิ่มเข้าไปเองด้วย
DOMAINS = {
    "error_count": [1, 2, 3, 4], "hint_level": [0, 1], "items_done": [1, 2, 3, 4], "items_count": [2, 20],
    "streak": [0, 3], "solved_here": [0, 2], "rounds": [0, 2], "mains_left": [3, 0], "visits": [1, 2],
    "widget_tries": [1, 2], "target_visits": [0, 1], "mastery": [0.6, 0.9], "concept_mastery": [0.6, 0.9],
    "impasse": [0.0, 80.0], "rt": [20.0, 60.0], "rt_ratio": [1.0, 2.0], "judge_score": [90, 30],
    "bug_type": ["", "slip", "misconception"],
}
MAX_CASES = 4096
DEAD = "เส้นที่ไม่มีวันถูกใช้: "


def _constants(edges: list[dict]) -> dict[str, set]:
    """ตัวเลขที่เงื่อนไขเทียบกับตัวแปร เช่น items_done == 5 → ลอง 4 5 6 ด้วย"""
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
    for value in sorted(v for v in extra if not isinstance(v, str)):
        if value not in values and value >= low:
            values.append(value)
    return values


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
        names = sorted(set().union(*[u for u in used if other not in u]) - {"correct", "wrong"} if used else set())
        if outcome == "wrong" and "error_count" not in names:
            names.append("error_count")
        groups.append(({"correct": outcome == "correct", "wrong": outcome == "wrong"}, names))
    return groups


def cases(flow_spec: dict, step: dict):
    """ทุกกรณีของขั้นนี้: (ค่าตัวแปรที่ลอง, เส้นที่ engine เลือก)"""
    edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
    try:
        parsed = [(e, conditions.parse(e.get("when"))) for e in edges]
    except conditions.ConditionError:
        return
    extra = _constants(edges)
    for fixed, names in _groups(step, edges):
        domains = [_domain(n, extra.get(n, set())) for n in names]
        while len(names) and _product(domains) > MAX_CASES:
            longest = max(range(len(domains)), key=lambda i: len(domains[i]))
            domains[longest] = domains[longest][:-1]
        for combo in itertools.product(*domains) if names else [()]:
            values = _consistent({**BASE, **fixed, **dict(zip(names, combo))})
            yield {**fixed, **dict(zip(names, combo))}, _winner(parsed, values, {})


def _product(domains: list[list]) -> int:
    total = 1
    for d in domains:
        total *= max(len(d), 1)
    return total


def dead_edges(flow_spec: dict) -> list[str]:
    """เส้นที่ไม่มีกรณีไหนไปถึง เพราะเส้นก่อนหน้าดักไว้หมด (แนวทางของครูบนเส้นนั้นจะไม่เกิดเลย)"""
    notes = []
    for step in flow_spec["steps"]:
        edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
        if len(edges) < 2:
            continue
        used = {id(edge) for _, edge in cases(flow_spec, step) if edge is not None}
        for edge in edges:
            if id(edge) not in used:
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


def table(flow_spec: dict, limit: int = 40) -> list[dict]:
    """ตารางอ่านง่ายของขั้นทำโจทย์ (และขั้นที่มีหลายเส้น): กรณีทั่วไป แล้วเปลี่ยนทีละตัวแปร"""
    steps = {s["id"]: s for s in flow_spec["steps"]}
    out = []
    for step in flow_spec["steps"]:
        edges = [e for e in flow_spec["edges"] if e["from"] == step["id"]]
        if len(edges) < 2:
            continue
        key_vars = ("correct", "wrong", "error_count", "bug_type", "hint_level")
        baseline, variants = {}, []
        for values, edge in cases(flow_spec, step):
            # กรณีทั่วไป = ทุกตัวแปรเป็นค่าแรก นอกจากผลการตอบ ครั้งที่ผิด ชนิดข้อผิดพลาด และการใช้คำใบ้
            changed = [n for n, v in values.items() if n not in key_vars and v != _domain(n, set())[0]]
            key = tuple(values.get(n) for n in key_vars)
            target = "ไม่มีเส้น ระบบใช้ทางเริ่มต้น" if edge is None else (
                "กลับไปทำข้อเดิม" if edge["to"] == "back" else steps.get(edge["to"], {}).get("label", edge["to"]))
            if not changed:
                baseline[key] = target
            elif len(changed) == 1:
                variants.append((key, values, changed[0], target))
        rows, seen = [], set()

        def row(values: dict, extra: str | None, target: str):
            words = ["ตอบถูก" if values.get("correct") else "ตอบผิด" if values.get("wrong") else ""]
            words += [w for n in ("error_count", "bug_type", "hint_level") if n in values for w in [_say(n, values[n])] if w]
            rows.append({"case": " · ".join(w for w in words + [extra or ""] if w), "to": target})

        for values, _ in cases(flow_spec, step):
            key = tuple(values.get(n) for n in key_vars)
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
            if target != baseline.get(key) and (key, name, target) not in shown:
                shown.add((key, name, target))
                row(values, _say(name, values[name]), target)
        out.append({"step": step["id"], "label": step["label"], "rows": rows[:limit]})
    return out


def table_text(flow_spec: dict) -> str:
    return "\n".join(f"ขั้น {t['label']} ({t['step']}):\n" + "\n".join(f"- {r['case']} → {r['to']}" for r in t["rows"])
                     for t in table(flow_spec))
