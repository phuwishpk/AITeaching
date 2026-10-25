"""กิจกรรมของนักเรียนแบบเป็นเหตุการณ์: สิ่งที่นักเรียนป้อนเข้ามา → เส้นทางที่ผ่านในผัง → กฎที่ทำงาน → ตำแหน่งใหม่

ร่องรอย (traces) กับการตัดสินใจ (decisions) ที่เกิดจากการกระทำเดียวกันบันทึกด้วยเวลาเดียวกัน
จึงรวมเป็นเหตุการณ์เดียวด้วย (รหัสนักเรียน, เวลา) ถ้ามีแต่การตัดสินใจโดยไม่มีร่องรอย แปลว่าเกิดจากตัวจับเวลาของระบบ
หรือจากครูสั่ง Manual Override
"""

from . import db, rules
from .gems import versions
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


def _assemble(traces: list[dict], decisions: list[dict]) -> list[dict]:
    """รวมร่องรอยและการตัดสินใจที่เกิดพร้อมกันเป็นเหตุการณ์เดียว เรียงจากเก่าไปใหม่"""
    grouped: dict[tuple[str, float], dict] = {}

    def slot(row: dict) -> dict:
        key = (row["code"], round(row["ts"], 3))
        return grouped.setdefault(key, {"code": row["code"], "ts": row["ts"], "inputs": [], "decisions": []})

    for row in sorted(traces, key=lambda r: (r["ts"], r["id"])):
        slot(row)["inputs"].append({"action": row["action"], "target": row["target"], "data": db.loads(row["data"], {})})
    for row in decisions:
        edges = db.loads(row["edges"], [])
        path = node_path(edges)
        slot(row)["decisions"].append({
            "from": row["from_pos"], "to": row["to_pos"], "rule": row["rule"], "edges": edges,
            "path": path, "path_labels": [NODE_LABELS.get(n, n) for n in path],
            "detail": db.loads(row["detail"], {}), "id": row["id"], "set_id": row["set_id"],
        })

    from .services import item_brief, item_lookup  # import ภายในฟังก์ชันกันการ import วนกับ services

    items = item_lookup()
    out = []
    for event in sorted(grouped.values(), key=lambda e: e["ts"]):
        for item in event["inputs"]:
            if item["action"] in ("answer", "invalid_answer", "duplicate_ignored"):
                item["item"] = item_brief(items.get(item["target"]))
        event["decisions"].sort(key=lambda d: d["id"])
        edges = [e for d in event["decisions"] for e in d["edges"]]
        steps, rule_ids, route_edges = ([], [], []) if event["decisions"] else _input_route(event["inputs"])
        event["edges"] = edges or route_edges
        event["steps"] = steps
        event["rules"] = _related_rules(edges, rule_ids)
        event["source"] = "student" if event["inputs"] or "e_start" in edges else ("teacher" if any(
            "e_override" in d["edges"] or "e_teacher_release" in d["edges"] or "e_teacher_safety" in d["edges"]
            or "g_teacher" in d["edges"]
            or d["rule"].startswith("ครู") for d in event["decisions"]) else "system")
        event["position"] = event["decisions"][-1]["to"] if event["decisions"] else None
        # Flow ที่ครูออกแบบใน Gem: ขั้นของ Flow ที่นักเรียนไปอยู่ต่อ (ผังของ Gem วาดตามขั้น ไม่ใช่ตำแหน่งมาตรฐาน)
        last_detail = event["decisions"][-1]["detail"] if event["decisions"] else {}
        event["step"] = last_detail.get("step")
        event["step_label"] = last_detail.get("step_label")
        out.append(event)
    return out


def events(code: str | None = None, include_sim: bool = False, limit: int = 40) -> list[dict]:
    where, params = [], []
    if code:
        where.append("x.code = ?")
        params.append(code)
    elif not include_sim:
        where.append("s.kind NOT IN ('sim', 'test')")
    else:
        where.append("s.kind != 'test'")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    join = "JOIN students s ON s.code = x.code"
    fetch = limit * 4
    traces = db.query(f"SELECT x.id, x.ts, x.code, x.action, x.target, x.data FROM traces x {join} {clause} "
                      f"ORDER BY x.ts DESC LIMIT ?", (*params, fetch))
    decisions = db.query(f"SELECT x.id, x.ts, x.code, x.set_id, x.from_pos, x.to_pos, x.edges, x.rule, x.detail "
                         f"FROM decisions x {join} {clause} ORDER BY x.ts DESC, x.id DESC LIMIT ?", (*params, fetch))
    return list(reversed(_assemble(traces, decisions)))[:limit]


# ---------------------------------------------------------------- เส้นทางตั้งแต่ต้นจนจบของหนึ่ง Session

END_LABELS = {"completed": "จบชุด", None: "กำลังทำอยู่"}


def _runs(code: str) -> list[dict]:
    """Session ทั้งหมดของนักเรียน เรียงจากเก่าไปใหม่ พร้อมช่วงเวลาที่เป็นของ Session นั้น

    Session ที่ยังไม่จบกินเวลาไปถึง Session ถัดไปของนักเรียนคนเดียวกัน (เช่น กดเริ่มชุดใหม่)
    """
    from .services import NotFound, find_set

    rows = db.query("SELECT id, set_id, started_at, ended_at, end_reason FROM sessions WHERE code = ? ORDER BY started_at, id",
                    (code,))
    runs, last_of_set = [], {}
    for i, row in enumerate(rows):
        following = rows[i + 1]["started_at"] if i + 1 < len(rows) else None
        # จบแล้วนับถึงเหตุการณ์สุดท้ายที่จบ ยังไม่จบนับถึงก่อน Session ถัดไปเริ่ม
        until = (row["ended_at"] + 0.001 if row["ended_at"] is not None else
                 following - 0.001 if following is not None else None)
        prev = last_of_set.get(row["set_id"])
        # ต่อจาก Session ที่จบเพราะครบเพดานหรือหยุดเอง = ทำต่อจากความคืบหน้าเดิม ไม่ใช่เริ่มชุดใหม่
        resumed = bool(prev and prev["ended_at"] is not None and prev["end_reason"] != "completed")
        try:
            subject, qs = find_set(row["set_id"])
            set_name = qs["name"]
            gem = subject.get("gem")
        except NotFound:
            set_name, gem = row["set_id"], None
        # เรียนกับ Gem ตัวไหน คลังรุ่นไหน และ Gem Version ไหน (เวอร์ชันล่าสุดก่อนเริ่ม Session)
        gem_info = {"id": gem["id"], "name": gem.get("name"), "bank_version": gem.get("bank_version"),
                    "version": versions.at(gem["id"], row["started_at"])} if gem else None
        runs.append({
            "id": row["id"], "set_id": row["set_id"], "set_name": set_name,
            "started": row["started_at"], "ended": row["ended_at"], "until": until,
            "end_reason": row["end_reason"], "resumed": resumed, "gem": gem_info,
            "outcome": END_LABELS.get(row["end_reason"], "จบ Session"),
        })
        last_of_set[row["set_id"]] = row
    return runs


def journey(code: str, session_id: int | None = None) -> dict:
    """ทุกการกระทำใน Session เดียว เรียงเป็นขั้นที่ 1 ถึงขั้นสุดท้าย พร้อมสรุปผล"""
    runs = _runs(code)
    if not runs:
        return {"runs": [], "run": None, "steps": [], "summary": None}
    run = next((r for r in runs if r["id"] == session_id), runs[-1])
    window = "code = ? AND ts >= ?" + (" AND ts <= ?" if run["until"] is not None else "")
    params = (code, run["started"] - 0.001) + ((run["until"],) if run["until"] is not None else ())
    traces = db.query(f"SELECT id, ts, code, action, target, data FROM traces WHERE {window} ORDER BY ts", params)
    decisions = db.query(f"SELECT id, ts, code, set_id, from_pos, to_pos, edges, rule, detail FROM decisions "
                         f"WHERE {window} ORDER BY ts, id", params)
    # ช่วงที่ซ้อนกับชุดอื่น: ตัดเหตุการณ์ที่ระบบตัดสินในชุดอื่นออก
    steps = [e for e in _assemble(traces, decisions)
             if not e["decisions"] or any(d["set_id"] == run["set_id"] for d in e["decisions"])]
    for n, step in enumerate(steps, 1):
        step["n"] = n
        edges = step["edges"]
        step["milestone"] = ("start" if "e_start" in edges else
                             "completed" if step["position"] == F.DONE else
                             "ended" if step["position"] == F.ENDED else None)

    teacher = teacher_timeline(code, run["started"] - 0.001, run["until"])
    answers = [i for s in steps for i in s["inputs"] if i["action"] == "answer"]
    hints = sorted({d["to"] for s in steps for d in s["decisions"] if d["to"] in F.HINT_POSITIONS.values()})
    last = next((s["position"] for s in reversed(steps) if s["position"]), None)
    return {
        "runs": [{k: r[k] for k in ("id", "set_name", "started", "ended", "outcome", "resumed", "gem")} for r in reversed(runs)],
        "run": run,
        "steps": steps,
        "teacher": teacher,
        "summary": {
            "steps": len(steps),
            "answers": len(answers),
            "correct": sum(1 for a in answers if a["data"].get("correct")),
            "items": len({a["target"] for a in answers}),
            "hints": len([d for s in steps for d in s["decisions"] if d["to"] in F.HINT_POSITIONS.values()]),
            "hint_levels": [NODE_LABELS[h] for h in hints],
            "duration": ((run["ended"] or (steps[-1]["ts"] if steps else run["started"])) - run["started"]),
            "position": last,
            "position_label": NODE_LABELS.get(last, last) if last else None,
            "finished": run["ended"] is not None,
            "alerts": sum(1 for t in teacher if t["kind"] == "alert"),
            "responses": sum(1 for t in teacher if t.get("after_alert") is not None),
        },
    }


# ---------------------------------------------------------------- การทำงานของครูต่อนักเรียนหนึ่งคน (Q4)

TEACHER_TEXT = {
    "viewed": "ครูเปิดดูนักเรียนคนนี้",
    "ack": "ครูรับทราบแจ้งเตือน",
    "message": "ครูพิมพ์ตอบในแชต",
    "draft_sent": "ครูอนุมัติร่างคำตอบของ AI",
    "draft_discarded": "ครูทิ้งร่างคำตอบของ AI",
    "chat_mode": "ครูเปลี่ยนโหมดแชต",
}
RESPONSES = {"viewed", "ack", "message", "draft_sent", "override"}


def teacher_timeline(code: str, start: float, until: float | None) -> list[dict]:
    """แจ้งเตือนที่ส่งถึงครู และสิ่งที่ครูทำหลังจากนั้น เรียงตามเวลา พร้อมเวลาที่ครูใช้ตอบสนองต่อแจ้งเตือน"""
    window = "code = ? AND ts >= ?" + (" AND ts <= ?" if until is not None else "")
    params = (code, start) + ((until,) if until is not None else ())
    rows = [{"ts": r["ts"], "kind": "alert", "level": r["level"], "alert_kind": r["kind"], "text": r["message"]}
            for r in db.query(f"SELECT ts, level, kind, message FROM alerts WHERE {window}", params)]
    for r in db.query(f"SELECT ts, kind, detail FROM teacher_actions WHERE {window}", params):
        detail = db.loads(r["detail"], {})
        text = TEACHER_TEXT.get(r["kind"], r["kind"])
        if r["kind"] == "message":
            text += f": \"{detail.get('text', '')}\""
        elif r["kind"] == "draft_sent":
            text = ("ครูแก้ร่างของ AI แล้วส่ง" if detail.get("edited") else "ครูอนุมัติร่างของ AI ตามเดิม") + f": \"{detail.get('sent', '')}\""
        elif r["kind"] == "chat_mode":
            text = "ครูเข้าร่วมแชต (AI ร่างให้ครูตรวจ)" if detail.get("mode") == "teacher" else "ครูออกจากแชต ให้ AI ตอบต่อ"
        elif r["kind"] == "ack":
            text += f": {detail.get('message', '')}"
        rows.append({"ts": r["ts"], "kind": r["kind"], "text": text, "detail": detail})
    for r in db.query(f"SELECT ts, action, reason FROM overrides WHERE {window}", params):
        rows.append({"ts": r["ts"], "kind": "override", "text": f"ครูสั่ง Manual Override: {r['action']}"
                     + (f" · เหตุผล: {r['reason']}" if r["reason"] else "")})
    rows.sort(key=lambda r: r["ts"])
    pending = None  # แจ้งเตือนที่ครูยังไม่ได้ตอบสนอง
    for row in rows:
        if row["kind"] == "alert" and row["level"] != "silent":
            pending = pending if pending is not None else row["ts"]
        elif row["kind"] in RESPONSES and pending is not None:
            row["after_alert"] = round(row["ts"] - pending, 1)
            pending = None
    return rows
