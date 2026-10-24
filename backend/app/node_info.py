"""ข้อมูลของแต่ละกล่องในผังตรรกะ: ใช้ข้อมูลอะไรตัดสิน ปรับค่าอะไรได้ และเนื้อหาส่วนไหนแก้ได้ที่ไหน

ส่วน "คืออะไร ทำหน้าที่อะไร" ใช้การ์ดหลักการใน principles.py ไฟล์นี้เพิ่มเฉพาะส่วนที่ปรับแต่งได้
PARAM_GUIDE บอกผลของการปรับแต่ละค่าและช่วงที่ยอมให้ตั้ง หน้า Admin ใช้ช่วยตัดสินใจก่อนปรับ
"""

from . import flow_guide, principles, rules, settings_store
from .config import PARAM_LABELS
from .engine import flow as F

TEACHER_CONTENT = "หน้าครู → วิชาและชุดคำถาม"

NODE_INFO: dict[str, dict] = {
    "ANSWERING": {"uses": ["โจทย์ที่ระบบเลือกให้", "เวลาที่เริ่มเห็นโจทย์ (เริ่มนับ Response Time)"],
                  "params": ["hint_unlock_wait", "idle_timeout"],
                  "content": f"คำสั่งโจทย์และสมการ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "E_SUBMIT": {"uses": ["คำตอบที่พิมพ์หรือเลือก", "เวลาที่กดส่ง", "Risk Score ที่คำนวณใหม่หลังรับคำตอบทุกครั้ง"],
                 "params": ["undo_window", "burnout_risk"]},
    "G_CLEAN": {"uses": ["คำตอบดิบ", "คำตอบครั้งก่อนและเวลาที่ส่ง", "Response Time"],
                "params": ["duplicate_window", "rt_cap"]},
    "G1": {"uses": ["คำตอบหลังกรองแล้ว", "คำตอบที่ถูกของโจทย์ตาม Answer Format"], "params": [],
           "content": f"คำตอบที่ถูกและคำตอบที่ยอมรับ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "G_MASTERY": {"uses": ["ระดับคำใบ้ที่ใช้ในข้อนี้", "จำนวนครั้งที่ผิด", "ผลข้อปรนัยเทียบข้อเติมคำ"],
                  "params": ["mastery_window"]},
    "G_FINISH": {"uses": ["Mastery ของ Target Concept", "จำนวนข้อที่ทำใน Session", "โจทย์หลักที่ทำครบแล้ว"],
                 "params": ["finish_mastery", "finish_min_items", "max_items"],
                 "content": f"โจทย์หลักและโจทย์ท้าทายของชุด แก้ได้ที่{TEACHER_CONTENT} → แท็บชุดคำถาม"},
    "G_PATH": {"uses": ["Mastery", "เวลาคิดเทียบเวลาที่คาด", "ความยากของโจทย์ที่เหลือ"],
               "params": ["fast_track_mastery", "standard_mastery"],
               "content": f"ความยากและเวลาที่คาดของแต่ละโจทย์ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "COMPLETED": {"uses": ["ผลของเกณฑ์จบชุด"], "params": ["finish_mastery", "finish_min_items"]},
    "SESSION_ENDED": {"uses": ["จำนวนข้อใน Session", "การเลือกหยุดของนักเรียน"], "params": ["max_items"]},
    "ISOMORPHIC_TEST": {"uses": ["ข้อคู่ขนานของโจทย์ที่ผ่านด้วยคำใบ้"], "params": ["iso_attempts"],
                        "content": f"ข้อคู่ขนาน (Isomorphic Item) แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "G_ISOCHK": {"uses": ["โหมดของข้อที่กำลังทำ", "จำนวนครั้งที่ตอบข้อคู่ขนาน"], "params": ["iso_attempts"]},
    "G2": {"uses": ["Response Time", "เวลาอ่านขั้นต่ำของโจทย์"], "params": ["rapid_guess_threshold", "rapid_guess_lock"],
           "content": f"เวลาอ่านขั้นต่ำรายข้อ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "RAPID_GUESS_LOCK": {"uses": ["เวลาที่ล็อก", "จำนวน Rapid Guess ติดกัน"],
                         "params": ["rapid_guess_lock", "burnout_rapid_streak"]},
    "G_DIAG": {"uses": ["คำตอบผิด", "Bug Library ของโจทย์", "Mastery ของมโนทัศน์"], "params": ["slip_mastery"],
               "content": f"คำตอบผิดที่รู้จักและรายการ Bug Library แก้ได้ที่{TEACHER_CONTENT} → แท็บ Bug Library"},
    "G3": {"uses": ["Error Count ของข้อนี้", "Hint Floor จากการวินิจฉัย"], "params": []},
    "DELIBERATE_DELAY": {"uses": ["เวลาที่ตอบผิดครั้งแรก", "Hint Floor"], "params": ["deliberate_delay"]},
    "HINT_L1": {"uses": ["คำใบ้ต้นฉบับระดับ 1", "AI Tutor (ถ้าเปิดใช้)"],
                "params": ["hint_abuse_presses", "hint_abuse_window", "hint_abuse_cooldown"],
                "content": f"ข้อความคำใบ้ 3 ระดับ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "HINT_L2": {"uses": ["คำใบ้ต้นฉบับระดับ 2", "Misconception ที่พบ", "AI Tutor (ถ้าเปิดใช้)"],
                "params": ["hint_abuse_presses", "hint_abuse_window", "hint_abuse_cooldown"],
                "content": f"ข้อความคำใบ้ 3 ระดับ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "HINT_L3": {"uses": ["คำใบ้ต้นฉบับระดับ 3", "Answer-Leak Guard", "AI Tutor (ถ้าเปิดใช้)"],
                "params": ["hint_abuse_presses", "hint_abuse_window", "hint_abuse_cooldown"],
                "content": f"ข้อความคำใบ้ 3 ระดับ แก้ได้ที่{TEACHER_CONTENT} → แท็บโจทย์"},
    "G_TREND": {"uses": ["เวลาคิดของการตอบผิด 3 ครั้ง", "เวลาที่คาดของโจทย์"], "params": ["impasse_threshold"]},
    "IMPASSE": {"uses": ["ข้อที่ติด", "Misconception ล่าสุด"], "params": ["impasse_threshold"]},
    "G_ROUNDS": {"uses": ["จำนวนรอบซ่อมเสริมของข้อนี้"], "params": ["remedial_max_rounds"]},
    "REMEDIAL": {"uses": ["Prerequisite ในแผนผังความรู้", "Misconception ที่พบ", "Mastery ของแต่ละ Prerequisite"],
                 "params": ["remedial_pass_streak"],
                 "content": f"โจทย์ทบทวนและ Prerequisite แก้ได้ที่{TEACHER_CONTENT} → แท็บมโนทัศน์และโจทย์"},
    "CIRCUIT_BREAKER": {"uses": ["ข้อความแชตที่แสดงความเครียด", "Impasse ระหว่างซ่อมเสริม"],
                        "params": ["circuit_breaker_break"]},
    "WALKTHROUGH": {"uses": ["มโนทัศน์ที่ติด"], "params": [],
                    "content": f"ตัวอย่างทีละขั้น แก้ได้ที่{TEACHER_CONTENT} → แท็บตัวอย่างทีละขั้น"},
    "STAGNATION_DEADLOCK": {"uses": ["จำนวนรอบซ่อมเสริมที่ครบแล้ว"], "params": ["remedial_max_rounds"]},
    "IDLE_PAUSE": {"uses": ["เวลาที่หน้าจอนิ่ง", "จำนวนครั้งที่พักใน Session"], "params": ["idle_timeout", "burnout_idle"]},
    "CHOOSING_PATH": {"uses": ["ข้อความแชต", "รายการคำที่สื่อว่าไม่อยากเรียน"], "params": [],
                      "content": "รายการคำอยู่ในโค้ด backend/app/tutor/distress.py"},
    "SAFETY_STOP": {"uses": ["ข้อความแชต", "รายการคำที่สื่อถึงการทำร้ายตนเอง"], "params": [],
                    "content": "รายการคำอยู่ในโค้ด backend/app/tutor/distress.py ครูปลดได้ด้วย Manual Override"},
}

# กล่องที่มักถูกถามว่าต่างกันอย่างไร: แสดงตารางเทียบในแผงข้อมูลของทั้งสองกล่อง
END_COMPARE = {
    "columns": ["จบชุด", "จบ Session"],
    "rows": [
        ["ความหมาย", "เรียนรู้ครบตามเป้าหมายแล้ว", "หยุดเรียนรอบนี้ก่อนถึงเป้าหมาย กลับมาทำต่อได้"],
        ["เกิดเมื่อ", "Mastery ของ Target Concept ≥ {finish_mastery:g} จากอย่างน้อย {finish_min_items:g} ข้อ และทำโจทย์หลักครบหรือโจทย์ท้าทายถูก 1 ข้อ",
         "ครบ {max_items:g} ข้อใน Session · นักเรียนเลือกหยุดวันนี้ · ครูสั่งจบ Session · โจทย์ในชุดหมด"],
        ["นักเรียนเห็น", "ทำชุดนี้สำเร็จแล้ว พร้อมข้อความชื่นชม", "จบรอบนี้แล้ว ความคืบหน้าบันทึกไว้"],
        ["สถานะในหน้าเลือกชุด", "ทำจบแล้ว (ปุ่ม \"ทำอีกครั้ง\")", "พักไว้ (ปุ่ม \"ทำต่อจากเดิม\")"],
        ["เข้ามาใหม่", "เริ่มชุดใหม่ตั้งแต่ต้น Mastery นับใหม่", "เปิด Session ใหม่ Mastery และข้อที่ทำแล้วยังอยู่ จำนวนข้อใน Session นับใหม่"],
        ["Telemetry ของครู", "นับเป็นจบชุด", "หยุดเองหรือครบเพดานนับเป็น Drop-off"],
        ["เส้นในผัง", "ด่าน \"ถึงเกณฑ์จบชุด?\" → ถึง", "ด่าน \"ถึงเกณฑ์จบชุด?\" → ครบ 20 ข้อ · รอเลือกทางต่อ → หยุดวันนี้"],
    ],
}
COMPARE_NODES = {"COMPLETED", "SESSION_ENDED"}

# ผลของการปรับแต่ละค่า และช่วงที่ยอมให้ตั้ง (min, max, step)
PARAM_GUIDE: dict[str, dict] = {
    "deliberate_delay": {"range": (0, 60, 1), "effect": "มากขึ้น = ให้คิดเองนานขึ้นก่อนเห็นคำใบ้ · น้อยลง = ช่วยเร็วขึ้น สเปกแนะนำ 15–30 วินาที"},
    "rapid_guess_threshold": {"range": (1, 10, 0.5), "effect": "ใช้เมื่อโจทย์ไม่ได้กำหนดเวลาอ่านเอง มากขึ้น = จับการเดาได้มากขึ้น แต่อาจจับคนที่อ่านเร็วจริง สเปกแนะนำ 1–3 วินาที"},
    "rapid_guess_lock": {"range": (0, 60, 1), "effect": "นานขึ้น = เตือนแรงขึ้น แต่ถ้านานเกินนักเรียนอาจหงุดหงิด"},
    "hint_unlock_wait": {"range": (0, 120, 1), "effect": "เวลาที่ต้องคิดก่อนกดคำใบ้ได้ (ก่อนตอบผิดครั้งแรก) ตั้ง 0 = กดได้ทันที"},
    "hint_abuse_presses": {"range": (2, 10, 1), "effect": "น้อยลง = จับการปั๊มคำใบ้เข้มขึ้น"},
    "hint_abuse_window": {"range": (3, 60, 1), "effect": "ช่วงเวลาที่นับการกดติดกัน ยาวขึ้น = เข้มขึ้น"},
    "hint_abuse_cooldown": {"range": (0, 120, 1), "effect": "ปุ่มคำใบ้พักนานเท่านี้หลังพบการปั๊มคำใบ้"},
    "idle_timeout": {"range": (30, 1800, 10), "effect": "หน้าจอนิ่งนานเท่านี้จึงพักบทเรียน สเปกแนะนำ 5 นาที (300 วินาที)"},
    "rt_cap": {"range": (60, 1800, 10), "effect": "เวลาคิดที่ยาวกว่านี้ถือเป็น Outlier และถูกตัดเหลือค่านี้"},
    "duplicate_window": {"range": (0, 5, 0.1), "effect": "ส่งคำตอบเดิมซ้ำภายในเวลานี้นับเป็นครั้งเดียว ตั้ง 0 = ไม่กรอง"},
    "mastery_window": {"range": (1, 20, 1), "effect": "มากขึ้น = Mastery นิ่งขึ้นแต่ตอบสนองต่อพัฒนาการช้าลง"},
    "fast_track_mastery": {"range": (0.5, 1, 0.05), "effect": "ต่ำลง = เข้า Fast-Track ง่ายขึ้น ต้องสูงกว่าเกณฑ์ Standard"},
    "standard_mastery": {"range": (0, 0.95, 0.05), "effect": "ต่ำกว่านี้ไปเส้นทาง Supported (ง่ายลง) ต้องต่ำกว่าเกณฑ์ Fast-Track"},
    "slip_mastery": {"range": (0, 1, 0.05), "effect": "ต่ำลง = นับคำตอบผิดเป็น Slip ง่ายขึ้น (ได้คำใบ้ระดับ 1 แทนระดับที่สูงกว่า)"},
    "iso_attempts": {"range": (1, 5, 1), "effect": "จำนวนครั้งที่ตอบข้อคู่ขนานได้ก่อนถือว่าไม่ผ่าน"},
    "remedial_pass_streak": {"range": (1, 5, 1), "effect": "มากขึ้น = ต้องทบทวนนานขึ้นก่อนกลับข้อเดิม"},
    "remedial_max_rounds": {"range": (1, 5, 1), "effect": "มากขึ้น = ระบบพยายามเองนานขึ้นก่อนส่งต่อครู"},
    "circuit_breaker_break": {"range": (10, 300, 5), "effect": "เวลาพักสายตา สเปกแนะนำ 1 นาที"},
    "undo_window": {"range": (0, 60, 1), "effect": "เวลาที่ยกเลิกคำตอบได้ ตั้ง 0 = ปิดปุ่มยกเลิก"},
    "finish_mastery": {"range": (0.5, 1, 0.05), "effect": "สูงขึ้น = ต้องเก่งขึ้นก่อนจบชุด"},
    "finish_min_items": {"range": (1, 20, 1), "effect": "จำนวนข้ออย่างน้อยก่อนจบชุด กันการจบเพราะโชคดีไม่กี่ข้อ"},
    "max_items": {"range": (5, 60, 1), "effect": "เพดานจำนวนข้อต่อ Session กันนักเรียนล้า (ชุดคำถามกำหนดเองได้)"},
    "burnout_idle": {"range": (1, 10, 1), "effect": "น้อยลง = แจ้งครูแบบเงียบเร็วขึ้นเมื่อพักบ่อย"},
    "burnout_rapid_streak": {"range": (2, 10, 1), "effect": "น้อยลง = แจ้งครูแบบเงียบเร็วขึ้นเมื่อเดารัว"},
    "burnout_risk": {"range": (0, 100, 1), "effect": "Risk Score ที่ส่งแจ้งเตือนเงียบ ต่ำลง = แจ้งบ่อยขึ้น"},
    "impasse_threshold": {"range": (0, 100, 1), "effect": "สูงขึ้น = ให้คำใบ้ระดับ 3 บ่อยขึ้นก่อนส่งซ่อมเสริม · ต่ำลง = ส่งซ่อมเสริมเร็วขึ้น"},
}


def validate_params(updates: dict) -> list[str]:
    """ตรวจค่าก่อนบันทึก คืนรายการข้อผิดพลาดเป็นภาษาไทย"""
    errors = []
    for key, value in updates.items():
        guide = PARAM_GUIDE.get(key)
        if guide is None:
            continue
        low, high, _ = guide["range"]
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f"{key} ต้องเป็นตัวเลข")
            continue
        if not low <= number <= high:
            errors.append(f"{PARAM_LABELS.get(key, key)} ต้องอยู่ระหว่าง {low:g} ถึง {high:g}")
    merged = {**settings_store.params(), **{k: float(v) for k, v in updates.items() if _is_number(v)}}
    if merged["standard_mastery"] >= merged["fast_track_mastery"]:
        errors.append("เกณฑ์ Standard ต้องต่ำกว่าเกณฑ์ Fast-Track")
    return errors


def _is_number(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def describe(node_id: str, positions: list[dict]) -> dict | None:
    node = next((n for n in F.NODES if n["id"] == node_id), None)
    if node is None:
        return None
    info = NODE_INFO.get(node_id, {})
    values = {k: float(v) for k, v in settings_store.params().items()}
    scale = settings_store.time_scale()
    params = []
    for key in info.get("params", []):
        low, high, step = PARAM_GUIDE[key]["range"]
        params.append({**rules.param_info(key, values, scale), "effect": PARAM_GUIDE[key]["effect"],
                       "min": low, "max": high, "step": step})
    related = [{"id": r["id"], "title": r["title"]} for g in rules.GROUPS for r in g["rules"]
               if r.get("node") == node_id or set(r.get("params", [])) & set(info.get("params", []))]
    fill = flow_guide.fill_values(values)
    guide = flow_guide.NODE_GUIDE.get(node_id, {})
    lane = flow_guide.LANES[node["lane"]]
    return {
        "id": node_id,
        "label": node["label"].replace("\n", " "),
        "kind": node["kind"],
        "lane": node["lane"],
        "lane_info": {"id": node["lane"], "name": lane["name"], "color": lane["color"]},
        "card": principles.NODE_CARDS.get(node_id),
        "steps": [step.format(**fill) for step in guide.get("steps", [])],
        "example": guide["example"].format(**fill) if guide.get("example") else None,
        "incoming": _routes(node_id, "target", "source"),
        "outgoing": _routes(node_id, "source", "target"),
        "uses": info.get("uses", []),
        "params": params,
        "content": info.get("content"),
        "rules": related,
        "students": [p for p in positions if p["position"] == node_id],
        "compare": {
            "columns": END_COMPARE["columns"],
            "rows": [[cell.format(**values) for cell in row] for row in END_COMPARE["rows"]],
        } if node_id in COMPARE_NODES else None,
    }



_NODES = {n["id"]: n for n in F.NODES}


def _label(node_id: str) -> str:
    return _NODES[node_id]["label"].replace("\n", " ") if node_id in _NODES else node_id


def _routes(node_id: str, here: str, there: str) -> list[dict]:
    """เส้นที่เข้าหรือออกจากกล่องนี้ พร้อมเงื่อนไขบนเส้น (ไม่รวมเส้นที่ซ่อนและเส้นที่วนเข้าตัวเอง)"""
    return [{"edge": e["id"], "node": e[there], "label": _label(e[there]), "when": e["label"],
             "lane": _NODES[e[there]]["lane"] if e[there] in _NODES else None}
            for e in F.EDGES if e[here] == node_id and e[there] != node_id and not e.get("hidden")]


def _crossing(members: set[str], inward: bool) -> list[dict]:
    """เส้นที่ข้ามขอบกลุ่ม: inward = เข้ามาในกลุ่ม ไม่งั้นคือออกจากกลุ่ม"""
    return [{"edge": e["id"], "from": e["source"], "from_label": _label(e["source"]),
             "to": e["target"], "to_label": _label(e["target"]), "when": e["label"]}
            for e in F.EDGES if not e.get("hidden")
            and (e["target"] in members) == inward and (e["source"] in members) != inward]


def describe_lane(lane_id: str, positions: list[dict]) -> dict | None:
    """กลุ่มของกล่องในผัง: ดูแลเรื่องอะไร เข้าและออกทางไหน และมีกล่องอะไรตามลำดับ"""
    lane = flow_guide.LANES.get(lane_id)
    if lane is None:
        return None
    fill = flow_guide.fill_values({k: float(v) for k, v in settings_store.params().items()})
    nodes = [{"id": node_id, "label": _label(node_id), "kind": _NODES[node_id]["kind"],
              "text": (principles.NODE_CARDS.get(node_id) or {}).get("principle", ""),
              "students": sum(1 for p in positions if p["position"] == node_id)}
             for node_id in lane["order"]]
    members = set(lane["order"])
    return {
        "id": lane_id,
        "name": lane["name"],
        "color": lane["color"],
        "question": lane["question"],
        "summary": lane["summary"].format(**fill),
        "enter": [x.format(**fill) for x in lane["enter"]],
        "exit": [x.format(**fill) for x in lane["exit"]],
        "principles": lane["principles"],
        "example": lane["example"].format(**fill),
        "nodes": nodes,
        "entries": _crossing(members, inward=True),
        "exits": _crossing(members, inward=False),
        "students": sum(n["students"] for n in nodes),
    }


def lanes() -> list[dict]:
    """รายชื่อกลุ่มสำหรับแถบสัญลักษณ์บนผัง"""
    return [{"id": k, "name": v["name"], "color": v["color"], "count": len(v["order"])}
            for k, v in flow_guide.LANES.items()]
