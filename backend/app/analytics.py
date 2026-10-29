"""ตัวชี้วัดฝั่งครูและ Admin: ฟีเจอร์ของนักเรียน, Student Cluster, Risk Score และ Platform Telemetry
owner = ผู้ใช้ที่ดูอยู่ (มีผู้ใช้หลายคน) ตัวชี้วัดคิดจากนักเรียนของผู้ใช้คนนั้นเท่านั้น None = ทุกคน (โหมดเดิม)"""

import time

from . import db, scope
from .engine import core as engine
from .ml import kmeans

# ผลจัดกลุ่มล่าสุดของแต่ละผู้ใช้ (owner → {ts, model})
_cluster_cache: dict[str | None, dict] = {}


def forget_clusters(owner: str | None) -> None:
    """นักเรียนของบัญชีนี้เปลี่ยน (เช่น ลบนักเรียน) จัดกลุ่มใหม่ครั้งหน้าที่ขอ"""
    _cluster_cache.pop(owner, None)


def student_rows(owner: str | None = None) -> list[dict]:
    clause, params = scope.where(owner)
    return db.query(f"SELECT code, kind, persona FROM students WHERE {clause} ORDER BY code", params)


def latest_states(owner: str | None = None) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    clause, params = scope.where(owner)
    for row in db.query(f"SELECT data, updated_at FROM states WHERE {clause} ORDER BY updated_at", params):
        state = db.loads(row["data"])
        latest[state["code"]] = state
    return latest


def session_minutes(code: str, now: float | None = None) -> float | None:
    """ความยาว Session เฉลี่ย ใช้ Session ที่จบแล้วก่อน ถ้ายังไม่มีจึงใช้ Session ที่กำลังทำอยู่"""
    now = now or time.time()
    rows = db.query("SELECT started_at, ended_at FROM sessions WHERE code = ?", (code,))
    ended = [(r["ended_at"] - r["started_at"]) / 60 for r in rows if r["ended_at"] and r["ended_at"] > r["started_at"]]
    if ended:
        return sum(ended) / len(ended)
    ongoing = [(min(now, r["started_at"] + 3600) - r["started_at"]) / 60 for r in rows if not r["ended_at"]]
    return sum(ongoing) / len(ongoing) if ongoing else None


def features(code: str) -> dict | None:
    states = db.states_for(code)
    attempts = sum(s["attempts_total"] for s in states)
    if attempts < 3:
        return None
    rt_count = sum(s["rt_count"] for s in states)
    return {
        "code": code,
        "avg_rt": sum(s["rt_sum"] for s in states) / rt_count if rt_count else 0.0,
        "accuracy": sum(s["correct_total"] for s in states) / attempts,
        "session_min": session_minutes(code) or 10.0,
    }


def clusters(force: bool = False, owner: str | None = None) -> dict:
    """K-Means ทั้งห้อง (นักเรียนของผู้ใช้คนนี้) คำนวณใหม่ทุก 20 วินาทีหรือเมื่อขอ"""
    now = time.time()
    cached = _cluster_cache.get(owner)
    if not force and cached and now - cached["ts"] < 20:
        return cached["model"]
    rows = []
    for student in student_rows(owner):
        if student["kind"] == "test":
            continue
        f = features(student["code"])
        if f:
            f["simulated"] = student["kind"] != "real"
            rows.append(f)
    model = kmeans.cluster_students(rows)
    _cluster_cache[owner] = {"ts": now, "model": model}
    return model


def cluster_of(code: str, owner: str | None = None) -> dict | None:
    model = clusters(owner=owner)
    point = next((p for p in model.get("points", []) if p["code"] == code), None)
    return {"key": point["cluster"], "name": point["cluster_name"]} if point else None


def telemetry(owner: str | None = None) -> dict:
    """Platform Telemetry: Drop-off Rate ต่อชุดคำถาม, Average Remediation Success, Hint Utility Rate"""
    now = time.time()
    states = list(latest_states(owner).values())
    per_set: dict[str, dict] = {}
    clause, params = scope.where(owner)
    for row in db.query(f"SELECT code, set_id, ended_at, end_reason, started_at FROM sessions WHERE {clause}", params):
        entry = per_set.setdefault(row["set_id"], {"sessions": 0, "dropped": 0, "completed": 0})
        entry["sessions"] += 1
        if row["end_reason"] == "completed":
            entry["completed"] += 1
        elif row["end_reason"] in ("student_stop", "cap") or (row["ended_at"] is None and now - row["started_at"] > 6 * 3600):
            entry["dropped"] += 1
    for entry in per_set.values():
        entry["drop_off_rate"] = round(entry["dropped"] / entry["sessions"], 3) if entry["sessions"] else 0.0
    started = sum(s.get("remedial_started", 0) for s in states)
    passed = sum(s.get("remedial_passed", 0) for s in states)
    shown = sum(s.get("hints_shown", 0) for s in states)
    useful = sum(s.get("hints_useful", 0) for s in states)
    return {
        "drop_off": per_set,
        "remediation_success": round(passed / started, 3) if started else None,
        "remediation_counts": {"started": started, "passed": passed},
        "hint_utility": round(useful / shown, 3) if shown else None,
        "hint_counts": {"shown": shown, "useful": useful},
    }


def bug_hits(subject: dict, owner: str | None = None) -> list[dict]:
    """จำนวนครั้งที่เจอแต่ละรายการใน Bug Library (นับจากร่องรอยการตอบ)"""
    counts: dict[str, dict] = {}
    clause, params = scope.where(owner)
    for row in db.query(f"SELECT data FROM traces WHERE action = 'answer' AND {clause}", params):
        data = db.loads(row["data"], {})
        diagnosis = data.get("diagnosis") or {}
        tag = diagnosis.get("tag")
        if not tag:
            continue
        entry = counts.setdefault(tag, {"total": 0, "misconception": 0, "slip": 0, "unclassified": 0})
        entry["total"] += 1
        entry[diagnosis.get("class", "unclassified")] = entry.get(diagnosis.get("class", "unclassified"), 0) + 1
    result = []
    for tag in subject.get("bug_tags", []):
        entry = counts.get(tag["id"], {"total": 0, "misconception": 0, "slip": 0, "unclassified": 0})
        result.append({**tag, "hits": entry})
    return result


def risk_for(state: dict) -> dict:
    result = engine.risk_score(state)
    return {"score": result["output"], "inputs": result["inputs"]}
