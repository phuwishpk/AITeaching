"""นิยาม Flow Position และผังตรรกะ (ADR-0002)

ไฟล์นี้เป็นแหล่งเดียวของผังที่หน้า Admin วาด ทั้งตำแหน่งที่นักเรียนอยู่ได้ (position)
ด่านตัดสินใจ (gate) และเส้นทางระหว่างกัน (edge)
ทุกครั้งที่ engine ย้ายตำแหน่ง จะบันทึกรหัส edge ที่วิ่งผ่านลงใน Decision Trace
"""

ANSWERING = "ANSWERING"
DELAY = "DELIBERATE_DELAY"
LOCK = "RAPID_GUESS_LOCK"
HINT_L1 = "HINT_L1"
HINT_L2 = "HINT_L2"
HINT_L3 = "HINT_L3"
ISO = "ISOMORPHIC_TEST"
IMPASSE = "IMPASSE"
REMEDIAL = "REMEDIAL"
CB = "CIRCUIT_BREAKER"
WALK = "WALKTHROUGH"
IDLE = "IDLE_PAUSE"
CHOOSE = "CHOOSING_PATH"
SAFETY = "SAFETY_STOP"
DEADLOCK = "STAGNATION_DEADLOCK"
DONE = "COMPLETED"
ENDED = "SESSION_ENDED"

HINT_POSITIONS = {1: HINT_L1, 2: HINT_L2, 3: HINT_L3}
ANSWER_POSITIONS = {ANSWERING, HINT_L1, HINT_L2, HINT_L3, ISO, REMEDIAL}
# ระหว่าง Deliberate Delay นักเรียนลองตอบใหม่เองได้ (Productive Struggle)
CAN_ANSWER = ANSWER_POSITIONS | {DELAY}

POSITION_LABELS = {
    ANSWERING: "กำลังคิด",
    DELAY: "Deliberate Delay",
    LOCK: "ล็อก Rapid Guess",
    HINT_L1: "คำใบ้ L1",
    HINT_L2: "คำใบ้ L2",
    HINT_L3: "คำใบ้ L3",
    ISO: "Isomorphic Test",
    IMPASSE: "Impasse",
    REMEDIAL: "Remedial Loop",
    CB: "Circuit Breaker",
    WALK: "Walkthrough",
    IDLE: "Idle Pause",
    CHOOSE: "รอเลือกทางต่อ",
    SAFETY: "หยุดเพื่อความปลอดภัย",
    DEADLOCK: "Stagnation Deadlock",
    DONE: "จบชุด",
    ENDED: "จบ Session",
}

# สถานะเป็นภาษาคนสำหรับหน้าครู (ไม่มีศัพท์เทคนิค)
TEACHER_TEXT = {
    ANSWERING: "กำลังทำโจทย์",
    DELAY: "กำลังลองคิดเองหลังตอบผิดครั้งแรก",
    LOCK: "พักปุ่มตอบเพราะตอบเร็วเกินไป",
    HINT_L1: "ได้คำใบ้ระดับ 1 แล้ว",
    HINT_L2: "ได้คำใบ้ระดับ 2 แล้ว",
    HINT_L3: "ได้คำใบ้ระดับ 3 แล้ว",
    ISO: "ทำข้อทดสอบความเข้าใจ (ไม่มีคำใบ้)",
    IMPASSE: "คิดต่อเองไม่ได้",
    REMEDIAL: "กำลังทบทวนความรู้พื้นฐาน",
    CB: "กำลังพักสายตา",
    WALK: "กำลังอ่านตัวอย่างทีละขั้น",
    IDLE: "พักการเรียนอยู่",
    CHOOSE: "บอกว่าไม่อยากเรียนต่อ",
    SAFETY: "หยุดเพื่อความปลอดภัย ต้องการครูด่วน",
    DEADLOCK: "ติดหล่มหลังซ่อมเสริม 2 รอบ รอครูช่วย",
    DONE: "จบชุดแล้ว",
    ENDED: "จบการเรียนรอบนี้",
}

# kind: position = ที่นักเรียนอยู่ได้, gate = ด่านตัดสินใจ, step = ขั้นประมวลผล, event = เหตุการณ์
NODES = [
    {"id": ANSWERING, "label": "กำลังคิด", "kind": "position", "lane": "main"},
    {"id": "E_SUBMIT", "label": "ส่งคำตอบ", "kind": "event", "lane": "main"},
    {"id": "G_CLEAN", "label": "กรองสัญญาณรบกวน\nตรวจรูปแบบคำตอบ", "kind": "step", "lane": "main"},
    {"id": "G1", "label": "ด่าน 1\nตอบถูกไหม", "kind": "gate", "lane": "main"},
    {"id": "G_MASTERY", "label": "อัปเดต Mastery\nCross-Format Check", "kind": "step", "lane": "correct"},
    {"id": "G_FINISH", "label": "ถึงเกณฑ์จบชุด?", "kind": "gate", "lane": "correct"},
    {"id": "G_PATH", "label": "เลือก Learning Path\nFuzzy เลือกความยาก", "kind": "step", "lane": "correct"},
    {"id": DONE, "label": "จบชุด", "kind": "position", "lane": "correct"},
    {"id": ENDED, "label": "จบ Session", "kind": "position", "lane": "correct"},
    {"id": ISO, "label": "Isomorphic Test", "kind": "position", "lane": "correct"},
    {"id": "G_ISOCHK", "label": "อยู่ใน\nIsomorphic Test?", "kind": "gate", "lane": "wrong"},
    {"id": "G2", "label": "ด่าน 2\nตอบเร็วเกินไหม", "kind": "gate", "lane": "wrong"},
    {"id": LOCK, "label": "ล็อก Rapid Guess", "kind": "position", "lane": "wrong"},
    {"id": "G_DIAG", "label": "วินิจฉัย Bug Library\nตั้ง Hint Floor", "kind": "step", "lane": "wrong"},
    {"id": "G3", "label": "ด่าน 3\nผิดครั้งที่เท่าไร", "kind": "gate", "lane": "wrong"},
    {"id": DELAY, "label": "Deliberate Delay", "kind": "position", "lane": "wrong"},
    {"id": HINT_L1, "label": "คำใบ้ L1", "kind": "position", "lane": "wrong"},
    {"id": HINT_L2, "label": "คำใบ้ L2", "kind": "position", "lane": "wrong"},
    {"id": "G_TREND", "label": "Fuzzy\nเวลาคิดยาวขึ้น?", "kind": "gate", "lane": "wrong"},
    {"id": HINT_L3, "label": "คำใบ้ L3", "kind": "position", "lane": "wrong"},
    {"id": IMPASSE, "label": "Impasse", "kind": "position", "lane": "help"},
    {"id": "G_ROUNDS", "label": "ส่งซ่อมเสริม\nครบ 2 รอบ?", "kind": "gate", "lane": "help"},
    {"id": REMEDIAL, "label": "Remedial Loop", "kind": "position", "lane": "help"},
    {"id": CB, "label": "Circuit Breaker", "kind": "position", "lane": "care"},
    {"id": WALK, "label": "Walkthrough", "kind": "position", "lane": "care"},
    {"id": DEADLOCK, "label": "Stagnation\nDeadlock", "kind": "position", "lane": "human"},
    {"id": IDLE, "label": "Idle Pause", "kind": "position", "lane": "care"},
    {"id": CHOOSE, "label": "รอเลือกทางต่อ", "kind": "position", "lane": "care"},
    {"id": SAFETY, "label": "หยุดเพื่อ\nความปลอดภัย", "kind": "position", "lane": "human"},
]

EDGES = [
    {"id": "e_start", "source": ANSWERING, "target": ANSWERING, "label": "เริ่มชุด", "hidden": True},
    {"id": "e_submit", "source": ANSWERING, "target": "E_SUBMIT", "label": ""},
    {"id": "e_submit_l1", "source": HINT_L1, "target": "E_SUBMIT", "label": ""},
    {"id": "e_submit_l2", "source": HINT_L2, "target": "E_SUBMIT", "label": ""},
    {"id": "e_submit_l3", "source": HINT_L3, "target": "E_SUBMIT", "label": ""},
    {"id": "e_submit_iso", "source": ISO, "target": "E_SUBMIT", "label": ""},
    {"id": "e_submit_rem", "source": REMEDIAL, "target": "E_SUBMIT", "label": ""},
    {"id": "e_submit_delay", "source": DELAY, "target": "E_SUBMIT", "label": "แก้เองระหว่างรอ"},
    {"id": "e_clean_ok", "source": "E_SUBMIT", "target": "G_CLEAN", "label": ""},
    {"id": "e_clean_reject", "source": "G_CLEAN", "target": ANSWERING, "label": "ส่งซ้ำ หรือผิดรูปแบบ"},
    {"id": "e_g1_pass", "source": "G_CLEAN", "target": "G1", "label": ""},
    {"id": "e_g1_correct", "source": "G1", "target": "G_MASTERY", "label": "ถูก"},
    {"id": "e_mastery_iso", "source": "G_MASTERY", "target": ISO, "label": "ผ่านด้วยคำใบ้"},
    {"id": "e_mastery_finish", "source": "G_MASTERY", "target": "G_FINISH", "label": "ไม่ใช้คำใบ้"},
    {"id": "e_remedial_pass", "source": "G_MASTERY", "target": ANSWERING, "label": "ซ่อมเสริมผ่าน กลับข้อเดิม"},
    {"id": "e_remedial_next", "source": "G_MASTERY", "target": REMEDIAL, "label": "ซ่อมเสริมข้อถัดไป"},
    {"id": "e_finish_yes", "source": "G_FINISH", "target": DONE, "label": "ถึง"},
    {"id": "e_finish_cap", "source": "G_FINISH", "target": ENDED, "label": "ครบ 20 ข้อ"},
    {"id": "e_finish_no", "source": "G_FINISH", "target": "G_PATH", "label": "ยัง"},
    {"id": "e_path_next", "source": "G_PATH", "target": ANSWERING, "label": "ข้อถัดไป"},
    {"id": "e_g1_wrong", "source": "G1", "target": "G_ISOCHK", "label": "ผิด"},
    {"id": "e_iso_retry", "source": "G_ISOCHK", "target": ISO, "label": "ผิดครั้งแรก ลองอีกครั้ง"},
    {"id": "e_iso_fail", "source": "G_ISOCHK", "target": ANSWERING, "label": "ไม่ผ่าน กลับ Standard"},
    {"id": "e_iso_impasse", "source": "G_ISOCHK", "target": IMPASSE, "label": "ไม่ผ่าน 2 รอบติด"},
    {"id": "e_iso_no", "source": "G_ISOCHK", "target": "G2", "label": "ไม่ใช่"},
    {"id": "e_g2_fast", "source": "G2", "target": LOCK, "label": "เร็วกว่าเวลาอ่าน"},
    {"id": "e_lock_done", "source": LOCK, "target": ANSWERING, "label": "ครบ 15 วินาที"},
    {"id": "e_g2_normal", "source": "G2", "target": "G_DIAG", "label": "ปกติ"},
    {"id": "e_diag", "source": "G_DIAG", "target": "G3", "label": ""},
    {"id": "e_g3_1", "source": "G3", "target": DELAY, "label": "ครั้งที่ 1"},
    {"id": "e_hint_button", "source": ANSWERING, "target": HINT_L1, "label": "คิดครบ 30 วินาทีแล้วขอคำใบ้"},
    {"id": "e_delay_l1", "source": DELAY, "target": HINT_L1, "label": "ครบเวลา"},
    {"id": "e_delay_l2", "source": DELAY, "target": HINT_L2, "label": "Floor = L2"},
    {"id": "e_g3_2", "source": "G3", "target": HINT_L2, "label": "ครั้งที่ 2"},
    {"id": "e_g3_3", "source": "G3", "target": "G_TREND", "label": "ครั้งที่ 3"},
    {"id": "e_trend_no", "source": "G_TREND", "target": HINT_L3, "label": "ไม่"},
    {"id": "e_trend_yes", "source": "G_TREND", "target": IMPASSE, "label": "ใช่"},
    {"id": "e_g3_4", "source": "G3", "target": IMPASSE, "label": "4 ขึ้นไป"},
    {"id": "e_impasse", "source": IMPASSE, "target": "G_ROUNDS", "label": ""},
    {"id": "e_rounds_ok", "source": "G_ROUNDS", "target": REMEDIAL, "label": "ยัง"},
    {"id": "e_rounds_full", "source": "G_ROUNDS", "target": DEADLOCK, "label": "ครบ 2 รอบ"},
    {"id": "e_rounds_root", "source": "G_ROUNDS", "target": WALK, "label": "ไม่มี Prerequisite"},
    {"id": "e_remedial_impasse", "source": REMEDIAL, "target": CB, "label": "Impasse ซ้ำ"},
    {"id": "e_cb_done", "source": CB, "target": WALK, "label": "ครบ 1 นาที"},
    {"id": "e_walk_round", "source": WALK, "target": "G_ROUNDS", "label": "ปิดรอบซ่อมเสริม"},
    {"id": "e_walk_easier", "source": WALK, "target": ANSWERING, "label": "โจทย์ง่ายลง"},
    {"id": "e_idle", "source": ANSWERING, "target": IDLE, "label": "นิ่ง 5 นาที"},
    {"id": "e_idle_back", "source": IDLE, "target": ANSWERING, "label": "ทำต่อ"},
    {"id": "e_distress", "source": ANSWERING, "target": CB, "label": "ข้อความเครียดหรือท้อ"},
    {"id": "e_quit", "source": ANSWERING, "target": CHOOSE, "label": "ไม่อยากเรียนแล้ว"},
    {"id": "e_choose_on", "source": CHOOSE, "target": ANSWERING, "label": "ทำต่อแบบง่ายลง"},
    {"id": "e_choose_stop", "source": CHOOSE, "target": ENDED, "label": "หยุดวันนี้"},
    {"id": "e_safety", "source": ANSWERING, "target": SAFETY, "label": "สื่อถึงการทำร้ายตนเอง"},
    {"id": "e_teacher_release", "source": DEADLOCK, "target": ANSWERING, "label": "ครูปลด"},
    {"id": "e_teacher_safety", "source": SAFETY, "target": ANSWERING, "label": "ครูปลด"},
    {"id": "e_override", "source": ANSWERING, "target": ANSWERING, "label": "Manual Override", "hidden": True},
]

EDGE_IDS = {edge["id"] for edge in EDGES}
