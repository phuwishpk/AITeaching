"""กิจกรรมของนักเรียนแบบเป็นเหตุการณ์: สิ่งที่นักเรียนป้อนเข้ามา → เส้นทางที่ผ่านในผัง → กฎที่ทำงาน → ตำแหน่งใหม่

ร่องรอย (traces) กับการตัดสินใจ (decisions) ที่เกิดจากการกระทำเดียวกันบันทึกด้วยเวลาเดียวกัน
จึงรวมเป็นเหตุการณ์เดียวด้วย (รหัสนักเรียน, เวลา) ถ้ามีแต่การตัดสินใจโดยไม่มีร่องรอย แปลว่าเกิดจากตัวจับเวลาของระบบ
หรือจากครูสั่ง Manual Override
"""

from . import db, rules
from .engine import flow as F

EDGES = {e["id"]: e for e in F.EDGES}
NODE_LABELS = {n["id"]: n["label"].replace("\n", " ") for n in F.NODES}
RULE_TITLES = {r["id"]: r["title"] for g in rules.GROUPS for r in g["rules"]}
RULES_BY_EDGE: dict[str, list[str]] = {}
for _rule_id, _edges in rules.RULE_EDGES.items():
    for _edge in _edges:
        RULES_BY_EDGE.setdefault(_edge, []).append(_rule_id)

SUBMIT = ["e_submit", "e_clean_ok", "e_clean_reject"]

# การกระทำที่ไม่ได้ย้ายตำแหน่งในผัง: บอกว่าไปจบที่ขั้นไหนและกฎข้อไหน (ขั้น, กฎ, เส้นในผัง)
HINT_ROUTES = {
    "wait": (["ปุ่มคำใบ้", "ยังคิดไม่ครบเวลา ชวนให้คิดต่อ"], ["R-18"]),
    "delay": (["ปุ่มคำใบ้", "อยู่ระหว่าง Deliberate Delay คำใบ้จะขึ้นเองเมื่อครบเวลา"], ["R-22"]),
    "socratic": (["ปุ่มคำใบ้", "ไม่ข้ามระดับ ให้คำถามนำแทน"], ["R-20"]),
    "abuse": (["ปุ่มคำใบ้", "กดรัวเกินกำหนด พักปุ่มและให้คำถามนำ"], ["R-19"]),
    "cooldown": (["ปุ่มคำใบ้", "ปุ่มยังพักอยู่ ให้คำถามนำ"], ["R-19"]),
}
INPUT_ROUTES = {
    "invalid_answer": (["ส่งคำตอบ", "กรองสัญญาณรบกวน ตรวจรูปแบบคำตอบ", "ตีกลับ: ผิดรูปแบบ ไม่นับ Attempt"], ["R-02"], SUBMIT),
    "duplicate_ignored": (["ส่งคำตอบ", "กรองสัญญาณรบกวน ตรวจรูปแบบคำตอบ", "ตีกลับ: ส่งซ้ำ นับครั้งเดียว"], ["R-01"], SUBMIT),
    "chat": (["ตรวจข้อความทุกข์ใจในเครื่อง: ไม่พบ", "ลบข้อมูลส่วนตัว", "AI Tutor ตอบแบบ Socratic ผ่าน Guard"],
             ["R-44", "R-40", "R-36", "R-38"], []),
    "undo": (["ปุ่มยกเลิกคำตอบ", "คืนสถานะก่อนตอบ ไม่นับ Error Count"], ["R-06"], []),
    "restart_item": (["ปุ่มเริ่มข้อใหม่", "เริ่มนับเวลาใหม่ ประวัติยังอยู่"], ["R-07"], []),
    "content_revisit": (["ปุ่มทบทวนเนื้อหา", "บันทึกเป็นตัวแปร Content Revisit"], [], []),
    "resume_session": (["กลับเข้าชุดคำถาม", "ทำต่อจากตำแหน่งเดิม"], ["R-05"], []),
}


def node_path(edges: list[str]) -> list[str]:
    """แปลงลำดับเส้นเป็นลำดับขั้นในผัง เช่น e_submit, e_clean_ok → กำลังคิด, ส่งคำตอบ, กรองสัญญาณรบกวน"""
    path: list[str] = []
    for edge_id in edges:
        edge = EDGES.get(edge_id)
        if not edge:
            continue
        for node in (edge["source"], edge["target"]):
            if not path or path[-1] != node:
                path.append(node)
    return path


def _related_rules(edges: list[str], extra: list[str] = ()) -> list[dict]:
    seen, out = set(), []
    for rule_id in [r for e in edges for r in RULES_BY_EDGE.get(e, [])] + list(extra):
        if rule_id not in seen:
            seen.add(rule_id)
            out.append({"id": rule_id, "title": RULE_TITLES[rule_id]})
    return out


def _input_route(inputs: list[dict]) -> tuple[list[str], list[str], list[str]]:
    for item in inputs:
        if item["action"] == "hint_request":
            steps, rule_ids = HINT_ROUTES.get(item["data"].get("result"), (["ปุ่มคำใบ้"], []))
            return steps, rule_ids, []
        if item["action"] in INPUT_ROUTES:
            return INPUT_ROUTES[item["action"]]
    return [], [], []


def events(code: str | None = None, include_sim: bool = False, limit: int = 40) -> list[dict]:
    where, params = [], []
    if code:
        where.append("x.code = ?")
        params.append(code)
    elif not include_sim:
        where.append("s.kind != 'sim'")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    join = "JOIN students s ON s.code = x.code"
    fetch = limit * 4
    traces = db.query(f"SELECT x.ts, x.code, x.action, x.target, x.data FROM traces x {join} {clause} "
                      f"ORDER BY x.ts DESC LIMIT ?", (*params, fetch))
    decisions = db.query(f"SELECT x.id, x.ts, x.code, x.set_id, x.from_pos, x.to_pos, x.edges, x.rule, x.detail "
                         f"FROM decisions x {join} {clause} ORDER BY x.ts DESC, x.id DESC LIMIT ?", (*params, fetch))

    grouped: dict[tuple[str, float], dict] = {}

    def slot(row: dict) -> dict:
        key = (row["code"], round(row["ts"], 3))
        return grouped.setdefault(key, {"code": row["code"], "ts": row["ts"], "inputs": [], "decisions": []})

    for row in traces:
        slot(row)["inputs"].append({"action": row["action"], "target": row["target"], "data": db.loads(row["data"], {})})
    for row in decisions:
        edges = db.loads(row["edges"], [])
        path = node_path(edges)
        slot(row)["decisions"].append({
            "from": row["from_pos"], "to": row["to_pos"], "rule": row["rule"], "edges": edges,
            "path": path, "path_labels": [NODE_LABELS.get(n, n) for n in path],
            "detail": db.loads(row["detail"], {}), "id": row["id"],
        })

    out = []
    for event in sorted(grouped.values(), key=lambda e: e["ts"], reverse=True)[:limit]:
        event["decisions"].sort(key=lambda d: d["id"])
        event["inputs"].reverse()
        edges = [e for d in event["decisions"] for e in d["edges"]]
        steps, rule_ids, route_edges = ([], [], []) if event["decisions"] else _input_route(event["inputs"])
        event["edges"] = edges or route_edges
        event["steps"] = steps
        event["rules"] = _related_rules(edges, rule_ids)
        event["source"] = "student" if event["inputs"] else ("teacher" if any(
            "e_override" in d["edges"] or "e_teacher_release" in d["edges"] or "e_teacher_safety" in d["edges"]
            or d["rule"].startswith("ครู") for d in event["decisions"]) else "system")
        event["position"] = event["decisions"][-1]["to"] if event["decisions"] else None
        out.append(event)
    return out
