"""กฎทั้งหมดของระบบ สำหรับหน้า "กฎทั้งหมด" ของครูและ Admin

กฎแต่ละข้อบอกว่าเกิดเมื่อไร (when) ระบบทำอะไร (then) ใช้พารามิเตอร์ตัวไหน และโค้ดที่บังคับใช้อยู่ตรงไหน
ตัวเลขในข้อความเขียนเป็น {ชื่อพารามิเตอร์} แล้วเติมจากค่าที่ตั้งไว้ตอนเรียกดู หน้าเว็บจึงตรงกับที่ engine ใช้จริงเสมอ
ถ้าแก้กฎใน engine ให้แก้ข้อความที่นี่ด้วย (tests/test_rules.py ตรวจว่าพารามิเตอร์ทุกตัวมีกฎอธิบาย)
"""

import re

from . import settings_store
from .config import DEFAULT_PARAMS, PARAM_LABELS, SCALED_PARAMS, WEIGHTS
from .engine import flow as F

ENGINE = "engine/core.py"

GROUPS = [
    {
        "id": "clean",
        "title": "รับคำตอบและคัดกรองข้อมูล",
        "summary": "กรองสัญญาณรบกวนก่อนนำร่องรอยไปคำนวณ ไม่ให้ตัวแปรของ Student Model เพี้ยน",
        "rules": [
            {
                "id": "R-01", "title": "ส่งคำตอบซ้ำจากเว็บกระตุก",
                "when": "ส่งคำตอบเดิมซ้ำภายใน {duplicate_window:g} วินาที",
                "then": "นับเป็นการส่งครั้งเดียว ไม่บันทึก Attempt ซ้ำ",
                "params": ["duplicate_window"], "principle": "Noise Filtering", "source": "สเปก 6.2",
                "code": f"{ENGINE} › _submit()", "node": "G_CLEAN", "test": "double_submit",
            },
            {
                "id": "R-02", "title": "คำตอบผิดรูปแบบ",
                "when": "คำตอบอ่านไม่ได้ตาม Answer Format เช่น ตัวอักษรในข้อตัวเลข ช่องว่าง หรือตัวเลือกที่ไม่มีอยู่",
                "then": "บอกรูปแบบที่ถูกต้อง ไม่นับเป็น Attempt และไม่เพิ่ม Error Count",
                "principle": "Data Cleaning", "source": "decisions.md",
                "code": "engine/answers.py › check_answer()", "node": "G_CLEAN", "test": "malformed",
            },
            {
                "id": "R-03", "title": "ตัดเวลาคิดส่วนเกิน",
                "when": "เวลาคิดของการตอบครั้งหนึ่งยาวเกิน {rt_cap:g} วินาที",
                "then": "บันทึกเวลาคิดแค่ {rt_cap:g} วินาที ส่วนที่เกินถือเป็น Outlier ไม่ให้ค่าเฉลี่ยเวลาคิดเพี้ยน",
                "params": ["rt_cap"], "principle": "Outlier Cleaning", "source": "สเปก 6.1",
                "code": f"{ENGINE} › _submit()", "node": "G_CLEAN", "test": "idle",
            },
            {
                "id": "R-04", "title": "หน้าจอนิ่ง (Idle Pause)",
                "when": "ไม่มีการกระทำบนหน้าจอนาน {idle_timeout:g} วินาที",
                "then": "พักบทเรียนพร้อมข้อความปลอบใจ เวลาที่พักไม่นับเป็นเวลาคิด และ Deliberate Delay ที่ค้างอยู่เลื่อนออกไปเท่าเวลาที่พัก",
                "params": ["idle_timeout"], "principle": "Cognitive Impasse", "source": "สเปก 6.1",
                "code": f"{ENGINE} › idle(), resume()", "node": "IDLE_PAUSE", "test": "idle",
            },
            {
                "id": "R-05", "title": "เน็ตหลุดหรือปิดหน้ากลางคัน",
                "when": "กลับเข้ามาใหม่ระหว่างทำชุดคำถาม",
                "then": "กลับไปตำแหน่งเดิมในข้อเดิม ไม่บันทึกคะแนนเป็นศูนย์ ถ้าจบ Session ไปแล้วจะเริ่ม Session ใหม่ต่อจากความคืบหน้าเดิม",
                "principle": "Session Dropout", "source": "สเปก 6.2",
                "code": "services.py › start()", "test": "disconnect",
            },
            {
                "id": "R-06", "title": "ยกเลิกคำตอบล่าสุด",
                "when": "กดยกเลิกคำตอบภายใน {undo_window:g} วินาที เช่น จอสัมผัสรวนแล้วกดพลาด",
                "then": "คืนสถานะก่อนตอบ ไม่นับใน Error Count ใช้ได้ข้อละ 1 ครั้ง",
                "params": ["undo_window"], "principle": "ปัจจัยที่เซนเซอร์ตรวจไม่พบ", "source": "สเปก 6.2",
                "code": f"{ENGINE} › undo()", "test": "undo",
            },
            {
                "id": "R-07", "title": "เริ่มข้อนี้ใหม่",
                "when": "กดเริ่มข้อนี้ใหม่",
                "then": "เริ่มนับเวลาคิดใหม่ แต่ประวัติการตอบและ Error Count ยังอยู่ครบ ปุ่มนี้จึงใช้ล้างความผิดไม่ได้",
                "principle": "ปัจจัยที่เซนเซอร์ตรวจไม่พบ", "source": "สเปก 6.2",
                "code": f"{ENGINE} › restart_item()",
            },
        ],
    },
    {
        "id": "gate1",
        "title": "ด่าน 1: ตรวจความถูกต้องและอัปเดต Mastery",
        "summary": "ตรวจถูกผิดด้วยกฎที่อธิบายได้ แล้วคิด Mastery แบบถ่วงน้ำหนักตามความช่วยเหลือที่ใช้ไป",
        "rules": [
            {
                "id": "R-08", "title": "ตรวจคำตอบด้วยกฎ ไม่ใช้ LLM",
                "when": "ส่งคำตอบที่อ่านได้",
                "then": "ตรวจตาม Answer Format: ตัวเลขรับเลขไทย เศษส่วน และทศนิยมที่ปัดแล้ว · ปรนัยเทียบรหัสตัวเลือก · ข้อความสั้นเทียบคำตอบที่ยอมรับหลังตัดช่องว่าง",
                "principle": "Rule-based Decision", "source": "สเปก 3.1 · ADR-0001",
                "code": "engine/answers.py › check_answer()", "node": "G1",
            },
            {
                "id": "R-09", "title": "น้ำหนัก Mastery ต่อข้อ",
                "when": "ตอบถูก",
                "then": "ถูกครั้งแรกได้ {w_first:g} · แก้เองได้โดยไม่ใช้คำใบ้ได้ {w_self:g} · ผ่านหลังคำใบ้ระดับ 1, 2, 3 ได้ {w1:g}, {w2:g}, {w3:g} แล้วเฉลี่ยจาก {mastery_window:g} ข้อล่าสุดของมโนทัศน์นั้น",
                "params": ["mastery_window"], "principle": "Student Model", "source": "decisions.md หัวข้อ 2",
                "code": f"{ENGINE} › item_weight(), mastery_value()", "node": "G_MASTERY",
            },
            {
                "id": "R-10", "title": "Cross-Format Check",
                "when": "ข้อปรนัยของมโนทัศน์เดียวกันถูกตั้งแต่ครั้งแรก ≥ 80% (อย่างน้อย 2 ข้อ) แต่ข้อเติมตัวเลขหรือข้อความถูก ≤ 34% (อย่างน้อย 2 ข้อ)",
                "then": "ถือว่าที่ผ่านมาอาจเป็นการเดา ลดน้ำหนักข้อปรนัยลงครึ่งหนึ่งตอนคิด Mastery",
                "principle": "Cross-Validation", "source": "สเปก 6.1",
                "code": f"{ENGINE} › cross_format_flag()", "node": "G_MASTERY", "test": "cross_format",
            },
            {
                "id": "R-11", "title": "Isomorphic Test หลังผ่านด้วยคำใบ้",
                "when": "ผ่านข้อหลักโดยใช้คำใบ้",
                "then": "ข้อถัดไปเป็นข้อคู่ขนาน โครงสร้างเดิม ตัวเลขใหม่ และปิดปุ่มคำใบ้ ถูกครั้งแรกได้น้ำหนัก {w_first:g} แก้ได้ในครั้งที่ 2 ได้ {w_self:g}",
                "principle": "Generalization vs Overfitting", "source": "สเปก 3.2 · บทที่ 6 สไลด์ 19",
                "code": f"{ENGINE} › on_correct()", "node": "ISOMORPHIC_TEST",
            },
            {
                "id": "R-12", "title": "ไม่ผ่าน Isomorphic Test",
                "when": "ตอบข้อคู่ขนานผิดครบ {iso_attempts:g} ครั้ง",
                "then": "ข้อที่ผ่านมาด้วยคำใบ้ได้น้ำหนัก 0 แล้วฝึกโจทย์แบบเดียวกันต่อโดยเปิดคำใบ้คืน ถ้าไม่ผ่าน 2 รอบติดกันในมโนทัศน์เดียวกันถือเป็น Impasse",
                "params": ["iso_attempts"], "principle": "Isomorphic Test", "source": "decisions.md หัวข้อ 3",
                "code": f"{ENGINE} › on_iso_wrong()", "node": "G_ISOCHK",
            },
            {
                "id": "R-13", "title": "เกณฑ์จบชุด",
                "when": "Mastery ของ Target Concept ≥ {finish_mastery:g} จากอย่างน้อย {finish_min_items:g} ข้อ และทำโจทย์หลักครบหรือทำโจทย์ท้าทายถูก 1 ข้อ",
                "then": "จบชุดพร้อมข้อความชื่นชม ไม่มีตัวเลขเปรียบเทียบกับคนอื่น",
                "params": ["finish_mastery", "finish_min_items"], "principle": "Mastery Learning", "source": "decisions.md หัวข้อ 3",
                "code": f"{ENGINE} › finished()", "node": "G_FINISH",
            },
            {
                "id": "R-14", "title": "เพดานจำนวนข้อต่อ Session",
                "when": "ทำครบ {max_items:g} ข้อแล้วยังไม่ถึงเกณฑ์จบ (ชุดคำถามกำหนดเพดานของตัวเองได้)",
                "then": "จบ Session นี้ บันทึกความคืบหน้าไว้ทำต่อครั้งหน้า และแจ้งครูแบบเงียบ",
                "params": ["max_items"], "principle": "Drop-off Tracking", "source": "decisions.md หัวข้อ 3",
                "code": f"{ENGINE} › advance()", "node": "G_FINISH",
            },
            {
                "id": "R-15", "title": "เลือก Learning Path",
                "when": "ตอบถูกแล้วยังไม่จบชุด",
                "then": "Mastery ≥ {fast_track_mastery:g} (อย่างน้อย 2 ข้อ) และตอบเร็วกว่าเวลาที่คาด → Fast-Track ไปโจทย์ท้าทาย · Mastery ≥ {standard_mastery:g} → Standard · ต่ำกว่านั้น → Supported เลือกจากโจทย์ที่ง่ายที่สุด",
                "params": ["fast_track_mastery", "standard_mastery"], "principle": "Adaptive Branching · ZPD",
                "source": "สเปก 3.1", "code": f"{ENGINE} › choose_path()", "node": "G_PATH",
            },
            {
                "id": "R-16", "title": "ความยากของข้อถัดไป",
                "when": "เลือกข้อถัดไปในเส้นทางที่ได้",
                "then": "Fuzzy Logic รวม Mastery กับความช้า (เวลาคิดเทียบเวลาที่คาด) เป็นความยากเป้าหมาย 0–100 แล้วเลือกโจทย์ที่ความยากใกล้ที่สุด",
                "principle": "Fuzzy Logic · Dynamic Difficulty", "source": "ใบงานที่ 5",
                "code": "ml/fuzzy.py › DIFFICULTY_SYSTEM", "node": "G_PATH",
            },
        ],
    },
    {
        "id": "gate2",
        "title": "ด่าน 2: ตรวจเวลาที่ใช้ (Anti-Gaming)",
        "summary": "กันการเดารัวและการปั๊มคำใบ้ เพื่อรักษาความพยายามของผู้เรียน (Productive Struggle)",
        "rules": [
            {
                "id": "R-17", "title": "เดาสุ่ม (Rapid Guess)",
                "when": "ตอบผิดเร็วกว่าเวลาอ่านขั้นต่ำของข้อ (ค่าเริ่มต้น {rapid_guess_threshold:g} วินาที ถ้าโจทย์ไม่ได้กำหนดเอง)",
                "then": "ข้อนี้เป็นโมฆะ ไม่นับเข้า Mastery ไม่เพิ่ม Error Count และล็อกปุ่มตอบ {rapid_guess_lock:g} วินาที พร้อมชวนอ่านโจทย์ให้ครบ",
                "params": ["rapid_guess_threshold", "rapid_guess_lock"], "principle": "Anti-Gaming",
                "source": "สเปก 3.1 ด่าน 2, 6.1", "code": f"{ENGINE} › on_rapid_guess()", "node": "G2",
                "test": "rapid_guess",
            },
            {
                "id": "R-18", "title": "ขอคำใบ้ก่อนลองตอบ",
                "when": "ยังไม่เคยตอบผิดในข้อนี้แล้วกดขอคำใบ้",
                "then": "ปุ่มคำใบ้ปลดเมื่อคิดครบ {hint_unlock_wait:g} วินาที ก่อนหน้านั้นชวนให้คิดต่ออีกนิด",
                "params": ["hint_unlock_wait"], "principle": "Productive Struggle", "source": "สเปก 2.3",
                "code": f"{ENGINE} › request_hint()", "node": "ANSWERING",
            },
            {
                "id": "R-19", "title": "กดขอคำใบ้รัว ๆ (Hint Abuse)",
                "when": "กดขอคำใบ้ {hint_abuse_presses:g} ครั้งภายใน {hint_abuse_window:g} วินาที",
                "then": "พักปุ่มคำใบ้ {hint_abuse_cooldown:g} วินาที ไม่เปิดคำใบ้เพิ่ม ให้คำถามนำแบบ Socratic แทน ถ้าเกิดซ้ำครบ 3 ครั้งแจ้งครูแบบเงียบ",
                "params": ["hint_abuse_presses", "hint_abuse_window", "hint_abuse_cooldown"],
                "principle": "Gaming the System", "source": "สเปก 6.1",
                "code": f"{ENGINE} › request_hint()", "test": "hint_spam",
            },
            {
                "id": "R-20", "title": "ขอคำใบ้เพิ่มหลังตอบผิด",
                "when": "ได้คำใบ้แล้วกดขอคำใบ้อีก",
                "then": "ไม่ข้ามระดับ คำใบ้ระดับถัดไปปลดเมื่อลองตอบใหม่ ระหว่างนี้ได้คำถามนำแบบ Socratic",
                "principle": "Scaffolding", "source": "สเปก 3.2", "code": f"{ENGINE} › request_hint()",
            },
        ],
    },
    {
        "id": "gate3",
        "title": "ด่าน 3: นับครั้งที่ผิดและบันไดคำใบ้",
        "summary": "เวลาคิดปกติแต่ตอบผิด ระบบช่วยทีละขั้นตามจำนวนครั้งที่ผิด โดยไม่มีขั้นไหนเฉลยคำตอบ",
        "rules": [
            {
                "id": "R-21", "title": "วินิจฉัยกับ Bug Library (Hint Floor)",
                "when": "ตอบผิดด้วยเวลาคิดปกติ",
                "then": "ตรงกับ Misconception → คำใบ้เริ่มที่ระดับ 2 และบันทึกให้ครูเห็น · ไม่ใช่ Misconception แต่ Mastery ของมโนทัศน์นั้น ≥ {slip_mastery:g} → Slip เริ่มที่ระดับ 1 · นอกจากนั้นยังจัดประเภทไม่ได้ ให้ AI เสนอแท็กรอครูยืนยัน (เมื่อเปิดใช้ AI)",
                "params": ["slip_mastery"], "principle": "Slip vs Misconception", "source": "สเปก 3.3",
                "code": f"{ENGINE} › diagnose()", "node": "G_DIAG",
            },
            {
                "id": "R-22", "title": "ผิดครั้งที่ 1: Deliberate Delay",
                "when": "ตอบผิดครั้งแรกในข้อนี้",
                "then": "ยังไม่ให้คำใบ้ หน่วงเวลา {deliberate_delay:g} วินาทีให้ลองแก้เอง ถ้าแก้ถูกระหว่างนั้นได้น้ำหนัก {w_self:g} ครบเวลาแล้วเปิดคำใบ้ระดับ 1 (หรือระดับ 2 ถ้าเป็น Misconception)",
                "params": ["deliberate_delay"], "principle": "Productive Struggle · Self-Regulation", "source": "สเปก 2.3",
                "code": f"{ENGINE} › _submit(), resolve_timers()", "node": "DELIBERATE_DELAY",
            },
            {
                "id": "R-23", "title": "ผิดครั้งที่ 2",
                "when": "ตอบผิดครั้งที่ 2 ในข้อนี้",
                "then": "เปิดคำใบ้ระดับ 2 อธิบายกฎหรือหลักการที่เกี่ยวข้องสั้น ๆ ทันที",
                "principle": "Scaffolding", "source": "สเปก 3.2", "code": f"{ENGINE} › _submit()", "node": "HINT_L2",
            },
            {
                "id": "R-24", "title": "ผิดครั้งที่ 3: Fuzzy ตัดสิน Impasse",
                "when": "ตอบผิดครั้งที่ 3 ในข้อนี้",
                "then": "Fuzzy Logic ดูว่าเวลาคิดยาวขึ้นต่อเนื่องหรือไม่ ถ้าค่าที่ได้ ≥ {impasse_threshold:g} เป็น Impasse ถ้าไม่ถึงเปิดคำใบ้ระดับ 3 ที่แสดงแค่ขั้นแรก",
                "params": ["impasse_threshold"], "principle": "Fuzzy Logic (min/max · COG)", "source": "ใบงานที่ 5 · สเปก 3.2",
                "code": "ml/fuzzy.py › IMPASSE_SYSTEM", "node": "G_TREND",
            },
            {
                "id": "R-25", "title": "ผิดครั้งที่ 4 ขึ้นไป",
                "when": "ยังตอบผิดหลังได้คำใบ้ระดับ 3",
                "then": "เป็น Impasse พักข้อนี้แล้วพาไปทบทวนพื้นฐาน",
                "principle": "Cognitive Impasse", "source": "สเปก 3.2", "code": f"{ENGINE} › _submit()", "node": "G3",
            },
            {
                "id": "R-26", "title": "กฎเหล็ก: ไม่เฉลยคำตอบ",
                "when": "ทุกระดับคำใบ้และทุกข้อความจาก AI",
                "then": "ห้ามบอกคำตอบสุดท้ายหรือวิธีทำทั้งหมด คำใบ้ระดับ 3 แสดงได้แค่ขั้นแรกแล้วให้นักเรียนคิดต่อเอง",
                "principle": "Cognitive Short-circuiting", "source": "สเปก 3.2 · ADR-0001",
                "code": "tutor/guard.py › check()", "node": "HINT_L3", "test": "prompt_injection",
            },
        ],
    },
    {
        "id": "remedial",
        "title": "Impasse และการซ่อมเสริม (Remedial Loop)",
        "summary": "เมื่อคิดต่อเองไม่ได้ ระบบพาย้อนไปซ่อมความรู้พื้นฐานตามแผนผังความรู้ และมีจุดจบที่ครูเสมอ",
        "rules": [
            {
                "id": "R-27", "title": "เข้า Remedial Loop",
                "when": "เกิด Impasse ในข้อหลัก",
                "then": "พักข้อนี้ไว้ แล้วทบทวน Prerequisite ที่ผูกกับ Misconception ที่พบ ถ้าไม่มีใช้ Prerequisite ที่ Mastery ต่ำที่สุด",
                "principle": "Knowledge Map · Prerequisite", "source": "สเปก 2.1, 3.2",
                "code": f"{ENGINE} › start_round(), choose_prerequisite()", "node": "REMEDIAL",
            },
            {
                "id": "R-28", "title": "ผ่าน Remedial Loop",
                "when": "ตอบโจทย์ทบทวนถูก {remedial_pass_streak:g} ข้อติดกัน",
                "then": "กลับไปข้อเดิม Error Count เริ่มนับใหม่",
                "params": ["remedial_pass_streak"], "principle": "Content Sequencing", "source": "decisions.md หัวข้อ 3",
                "code": f"{ENGINE} › on_correct()", "node": "REMEDIAL",
            },
            {
                "id": "R-29", "title": "มโนทัศน์ที่ไม่มี Prerequisite",
                "when": "มโนทัศน์ที่ติดไม่มี Prerequisite ที่มีโจทย์ทบทวน",
                "then": "อ่านตัวอย่างทีละขั้น (Walkthrough) แล้วฝึกโจทย์ที่ง่ายกว่าข้อที่ติด",
                "principle": "Worked Example", "source": "decisions.md หัวข้อ 3",
                "code": f"{ENGINE} › start_round()", "node": "WALKTHROUGH",
            },
            {
                "id": "R-30", "title": "Impasse ซ้ำระหว่างซ่อมเสริม",
                "when": "เกิด Impasse ระหว่างทำโจทย์ทบทวน",
                "then": "Circuit Breaker พักสายตา {circuit_breaker_break:g} วินาที อ่านตัวอย่างทีละขั้น แล้วปิดรอบนี้ไปเริ่มรอบถัดไป (ถ้ายังไม่ครบจำนวนรอบ)",
                "params": ["circuit_breaker_break"], "principle": "Circuit Breaker", "source": "สเปก 7.1",
                "code": f"{ENGINE} › enter_impasse()", "node": "CIRCUIT_BREAKER",
            },
            {
                "id": "R-31", "title": "Stagnation Deadlock",
                "when": "ข้อเดียวกันถูกส่งซ่อมเสริมครบ {remedial_max_rounds:g} รอบแล้วยังติด",
                "then": "หยุดลูป แจ้งครูแบบปกติ และรอครูปลดล็อกด้วย Manual Override",
                "params": ["remedial_max_rounds"], "principle": "Bounded Loop · Human Escalation", "source": "สเปก 7.1",
                "code": f"{ENGINE} › start_round()", "node": "STAGNATION_DEADLOCK", "test": "deadlock",
            },
        ],
    },
    {
        "id": "care",
        "title": "การดูแลจิตใจและการส่งต่อครู",
        "summary": "ตรวจข้อความแชตด้วยรายการคำในเครื่องก่อนเสมอ จึงทำงานได้แม้ไม่มีอินเทอร์เน็ต",
        "rules": [
            {
                "id": "R-32", "title": "ข้อความสื่อถึงการทำร้ายตนเอง",
                "when": "แชตมีข้อความเช่น \"อยากตาย\" หรือ \"ทำร้ายตัวเอง\"",
                "then": "หยุดกิจกรรมทันที แสดงสายด่วนสุขภาพจิต 1323 แจ้งครูแบบด่วน AI ไม่คุยเรื่องนั้นต่อ และรอครูปลด",
                "principle": "Human-in-the-Loop", "source": "outline 7.1",
                "code": "tutor/distress.py › detect()", "node": "SAFETY_STOP", "test": "distress",
            },
            {
                "id": "R-33", "title": "บอกว่าไม่อยากเรียนต่อ",
                "when": "แชตมีข้อความเช่น \"ไม่อยากเรียนแล้ว\" หรือ \"ยอมแพ้\"",
                "then": "ไม่บังคับให้เรียนต่อ ให้เลือกเอง: พัก · ทำต่อแบบง่ายลง · หยุดวันนี้ แล้วแจ้งครูแบบปกติ",
                "principle": "Learner Agency", "source": "outline 7.1",
                "code": f"{ENGINE} › on_distress(), choose()", "node": "CHOOSING_PATH", "test": "distress",
            },
            {
                "id": "R-34", "title": "เครียดหรือท้อ (Circuit Breaker)",
                "when": "แชตมีข้อความเช่น \"เครียดมาก\" หรือ \"ทำไม่ได้สักที\" หรือ LLM ส่งรหัส TRIGGER_CIRCUIT_BREAKER",
                "then": "พักสายตา {circuit_breaker_break:g} วินาที แล้วเริ่มใหม่ด้วยตัวอย่างทีละขั้นและโจทย์ที่ง่ายลง แจ้งครูแบบปกติ",
                "params": ["circuit_breaker_break"], "principle": "Human-centered Safety", "source": "สเปก 7.1",
                "code": f"{ENGINE} › on_distress()", "node": "CIRCUIT_BREAKER", "test": "distress",
            },
            {
                "id": "R-35", "title": "Burnout Signal",
                "when": "Idle Pause ครบ {burnout_idle:g} ครั้งใน Session · Rapid Guess ติดกัน {burnout_rapid_streak:g} ครั้ง · หรือ Risk Score ≥ {burnout_risk:g} หลังตอบแล้วอย่างน้อย 5 ครั้ง",
                "then": "แจ้งครูแบบเงียบเท่านั้น ไม่หยุดกิจกรรมของนักเรียน เพราะตัวเลขอย่างเดียวไม่ควรตัดสินแทนครู",
                "params": ["burnout_idle", "burnout_rapid_streak", "burnout_risk"], "principle": "Algorithmic Determinism",
                "source": "decisions.md หัวข้อ 7", "code": f"{ENGINE} › idle(), on_rapid_guess(), check_burnout_risk()",
            },
        ],
    },
    {
        "id": "ai",
        "title": "AI Tutor และข้อจำกัดของ LLM",
        "summary": "LLM ช่วยปรับถ้อยคำภายใต้กรอบที่ควบคุมไว้ ไม่ได้ตัดสินเส้นทางหรือถูกผิด",
        "rules": [
            {
                "id": "R-36", "title": "คำใบ้ต้นฉบับของครูเป็นหลัก",
                "when": "ระบบต้องแสดงคำใบ้",
                "then": "ใช้คำใบ้ที่ครูเขียนเป็นข้อมูลหลัก LLM แค่ปรับถ้อยคำ ถ้าเป็น Offline Mode, Provider ล่ม หรือเป็นนักเรียนจำลองและนักเรียนสาธิต ใช้คำใบ้ต้นฉบับทันที",
                "principle": "Authored Hint", "source": "ADR-0001", "code": "tutor/service.py › generate_hint()",
            },
            {
                "id": "R-37", "title": "prompt 4 กรอบ (Context Framing)",
                "when": "เรียก LLM ทุกครั้ง",
                "then": "ประกอบ prompt จาก Role & Persona · Context & Environment (ตัวแปรจาก Student Model และ RAG) · Task & Intent (ระดับคำใบ้) · Constraints & Fallback",
                "principle": "Context Framing", "source": "สเปก 4.2", "code": "tutor/prompt.py",
            },
            {
                "id": "R-38", "title": "Answer-Leak Guard",
                "when": "LLM ตอบกลับ",
                "then": "ตรวจทุกข้อความก่อนถึงนักเรียน ถ้าพบค่า x ที่ถูก ตัวเลือกที่ถูก หรือคำตอบที่ยอมรับ บล็อกแล้วใช้คำใบ้ต้นฉบับแทน และบันทึกให้ครูตรวจย้อนหลัง",
                "principle": "Constraints & Fallback", "source": "ADR-0001 · สเปก 6.2",
                "code": "tutor/guard.py › check()", "test": "prompt_injection",
            },
            {
                "id": "R-39", "title": "RAG ค้นในเครื่อง",
                "when": "ก่อนเรียก LLM",
                "then": "ค้นเอกสารวิชาด้วย BM25 และตัดคำไทยด้วย PyThaiNLP ใส่แค่ 2 ย่อหน้าที่เกี่ยวข้องที่สุด พร้อมรายการ Bug Library ที่พบ กัน Hallucination และ Lost in the Middle",
                "principle": "Retrieval-Augmented Generation", "source": "สเปก 4.1", "code": "tutor/rag.py",
            },
            {
                "id": "R-40", "title": "ข้อความของนักเรียนไม่ใช่คำสั่ง",
                "when": "นักเรียนพิมพ์แชต รวมถึงพยายามสั่งให้ AI เฉลย",
                "then": "ส่งข้อความในแท็ก <student_message> ที่ prompt ระบุว่าเป็นข้อมูล ไม่ใช่คำสั่ง ถ้าอยู่นอกบทเรียนให้ชวนกลับเข้าโจทย์ ตอบไม่เกิน 3 ประโยคและจบด้วยคำถาม",
                "principle": "Prompt Injection", "source": "สเปก 4.2, 6.2",
                "code": "tutor/prompt.py › constraints_frame()", "test": "prompt_injection",
            },
            {
                "id": "R-41", "title": "Provider สำรอง",
                "when": "Provider ที่เลือกเรียกไม่สำเร็จ",
                "then": "ลองตัวถัดไปตามลำดับในหน้าตั้งค่า ถ้าไม่สำเร็จทั้งหมดใช้คำใบ้ต้นฉบับ และบันทึกข้อผิดพลาดไว้",
                "principle": "Fallback", "source": "decisions.md หัวข้อ 4", "code": "tutor/service.py › _call()",
            },
            {
                "id": "R-42", "title": "แท็กที่ AI เสนอ",
                "when": "คำตอบผิดไม่ตรงกับรายการใดใน Bug Library",
                "then": "AI เลือกแท็กจากรายการที่มีอยู่เท่านั้น และยังไม่ใช้กับนักเรียนจนกว่าครูจะยืนยัน",
                "principle": "Human-in-the-Loop", "source": "decisions.md หัวข้อ 4", "code": "api/teacher.py › decide_tag()",
            },
        ],
    },
    {
        "id": "privacy",
        "title": "ความเป็นส่วนตัวและ Anti-Labeling",
        "summary": "เก็บข้อมูลเท่าที่ต้องใช้ และไม่ให้ตัวเลขของระบบกลายเป็นป้ายที่ตัดสินตัวนักเรียน",
        "rules": [
            {
                "id": "R-43", "title": "รหัสแทนชื่อจริง",
                "when": "บันทึกร่องรอยดิจิทัลทุกชนิด",
                "then": "ใช้ Student Code แทนชื่อจริง ชื่อจริงอยู่ใน Roster ที่เปิดได้เฉพาะครู หน้า Admin เห็นแค่รหัส",
                "principle": "PDPA", "source": "สเปก 7.2", "code": "api/teacher.py › roster()",
            },
            {
                "id": "R-44", "title": "ลบข้อมูลส่วนตัวก่อนส่งออกนอกเครื่อง",
                "when": "ส่งข้อความแชตให้ LLM",
                "then": "แทนที่อีเมล เบอร์โทร เลขบัตรประชาชน และชื่อใน Roster ด้วยป้ายกลาง ๆ ก่อนส่ง ข้อความที่ออกนอกเครื่องจึงไม่มีข้อมูลระบุตัวตน",
                "principle": "PDPA", "source": "สเปก 7.2", "code": "tutor/pii.py › scrub()",
            },
            {
                "id": "R-45", "title": "Anti-Labeling",
                "when": "แสดงผลหน้านักเรียน",
                "then": "ไม่แสดง Risk Score ชื่อกลุ่ม หรือสีแดงเตือน แสดงแถบความก้าวหน้ากับข้อความเชิงบวกแทน ตัวเลขทั้งหมดอยู่ฝั่งครู",
                "principle": "Self-fulfilling Prophecy", "source": "สเปก 2.4, 7.2", "code": f"{ENGINE} › student_view()",
            },
            {
                "id": "R-46", "title": "API key อยู่ในเครื่องเท่านั้น",
                "when": "ใส่ API key ในหน้าตั้งค่า",
                "then": "เก็บในไฟล์ runtime/secrets.json บนเครื่องนี้ซึ่งไม่ขึ้น git หน้าเว็บเห็นแค่ 4 ตัวท้าย",
                "principle": "Security", "source": "decisions.md หัวข้อ 4", "code": "settings_store.py",
            },
        ],
    },
    {
        "id": "human",
        "title": "ครูเป็นผู้ตัดสินใจขั้นสุดท้าย (Human-in-the-Loop)",
        "summary": "ระบบช่วยคัดกรอง แต่ทุกเรื่องที่ต้องใช้ดุลยพินิจส่งต่อให้ครู และครูแทรกแซงได้เสมอ",
        "rules": [
            {
                "id": "R-47", "title": "Manual Override",
                "when": "ครูเห็นว่าควรแทรกแซง",
                "then": "ปลดล็อก เริ่มข้อใหม่ เปลี่ยนโจทย์ ตั้งเส้นทาง แก้ Mastery หรือจบ Session ได้ทุกเมื่อ ทุกคำสั่งบันทึกพร้อมผู้สั่งและเหตุผล",
                "principle": "Human-in-the-Loop", "source": "สเปก 7.1", "code": f"{ENGINE} › override()",
            },
            {
                "id": "R-48", "title": "ระดับการแจ้งเตือน",
                "when": "ระบบต้องส่งเรื่องถึงครู",
                "then": "ด่วน: ความปลอดภัยของนักเรียน · ปกติ: ระบบช่วยต่อเองไม่ได้ (Deadlock เครียด ไม่อยากเรียน) · เงียบ: สัญญาณให้ครูสังเกต (Burnout, Hint Abuse, ครบเพดานข้อ) การแจ้งเตือนของนักเรียนจำลองไม่ขึ้นหน้าครู",
                "principle": "Escalation", "source": "decisions.md หัวข้อ 7", "code": f"{ENGINE} › alert()",
            },
            {
                "id": "R-50", "title": "ครูเข้าร่วมแชต",
                "when": "ครูกด \"เข้าร่วมแชต\" กับนักเรียนคนหนึ่ง หรือระบบหยุดรอครู (หยุดเพื่อความปลอดภัย, Stagnation Deadlock)",
                "then": "AI ไม่ตอบนักเรียนเอง ข้อความของนักเรียนส่งถึงครู AI ร่างคำตอบให้ครูส่งตามนั้น แก้แล้วส่ง หรือทิ้ง นักเรียนเห็นป้าย \"ครูอยู่ในแชต\" และทุกข้อความมีป้ายบทบาท (ครู · ครูผู้ช่วย (AI) · ระบบ)",
                "principle": "Human-in-the-Loop", "source": "สเปก 7.1 · กฎของครูข้อ 1 และ 4",
                "code": "services.py › chat(), send_draft()",
            },
            {
                "id": "R-49", "title": "ตรวจความพร้อมก่อนเปิดชุดคำถาม",
                "when": "ครูเปิดชุดคำถามให้นักเรียน",
                "then": "นักเรียนเห็นชุดนั้นเมื่อเปิดใช้และผ่านการตรวจความพร้อมแล้ว: โจทย์หลักทุกข้อมีคำตอบ มีคำใบ้ครบ 3 ระดับ และมีข้อคู่ขนาน",
                "principle": "Readiness Check", "source": "decisions.md หัวข้อ 1", "code": "content/readiness.py › check_set()",
            },
        ],
    },
]

# เส้นในผังที่หมายถึงกฎแต่ละข้อทำงาน (ใช้บอกว่าการกระทำหนึ่งครั้งไปเจอกฎข้อไหน)
# นับเฉพาะเส้นของทางแยกที่เลือกจริง ไม่ใช่ทุกกล่องที่เดินผ่าน
RULE_EDGES = {
    "R-01": ["e_clean_reject"], "R-02": ["e_clean_reject"],
    "R-04": ["e_idle", "e_idle_back"],
    "R-08": ["e_g1_correct", "e_g1_wrong"],
    "R-09": ["e_mastery_finish"],
    "R-11": ["e_mastery_iso"],
    "R-12": ["e_iso_retry", "e_iso_fail", "e_iso_impasse"],
    "R-13": ["e_finish_yes"], "R-14": ["e_finish_cap"],
    "R-15": ["e_path_next"], "R-16": ["e_path_next"],
    "R-17": ["e_g2_fast", "e_lock_done"],
    "R-18": ["e_hint_button"],
    "R-21": ["e_diag"],
    "R-22": ["e_g3_1", "e_delay_l1", "e_delay_l2"],
    "R-23": ["e_g3_2"],
    "R-24": ["e_g3_3", "e_trend_yes", "e_trend_no"],
    "R-25": ["e_g3_4"],
    "R-27": ["e_impasse", "e_rounds_ok"],
    "R-28": ["e_remedial_pass", "e_remedial_next"],
    "R-29": ["e_rounds_root"],
    "R-30": ["e_remedial_impasse", "e_walk_round"],
    "R-31": ["e_rounds_full"],
    "R-32": ["e_safety"],
    "R-33": ["e_quit", "e_choose_on", "e_choose_stop"],
    "R-34": ["e_distress", "e_cb_done"],
    "R-47": ["e_override", "e_teacher_release", "e_teacher_safety"],
}

LABEL_RE = re.compile(r"^(.*?)\s*\(([^)]*)\)\s*$")


def param_info(key: str, values: dict, scale: float) -> dict:
    """ชื่อ หน่วย ค่าที่ใช้อยู่ และค่าเริ่มต้นของพารามิเตอร์ (หน่วยแยกจากวงเล็บท้ายชื่อใน PARAM_LABELS)"""
    label = PARAM_LABELS.get(key, key)
    match = LABEL_RE.match(label)
    name, unit = (match.group(1), match.group(2)) if match else (label, "")
    value = float(values[key])
    scaled = key in SCALED_PARAMS
    return {
        "key": key,
        "label": name,
        "unit": unit,
        "value": value,
        "default": float(DEFAULT_PARAMS[key]),
        "changed": value != float(DEFAULT_PARAMS[key]),
        "scaled": scaled,
        "effective": round(value * scale, 2) if scaled and scale != 1 else None,
    }


def build() -> dict:
    values = {k: float(v) for k, v in settings_store.params().items()}
    weights = {"w_first": WEIGHTS["first"], "w_self": WEIGHTS["self"], "w1": WEIGHTS[1], "w2": WEIGHTS[2], "w3": WEIGHTS[3]}
    scale = settings_store.time_scale()
    nodes = {n["id"]: n["label"].replace("\n", " ") for n in F.NODES}
    groups = []
    for group in GROUPS:
        rules = []
        for rule in group["rules"]:
            rules.append({
                **rule,
                "when": rule["when"].format(**values, **weights),
                "then": rule["then"].format(**values, **weights),
                "params": [param_info(k, values, scale) for k in rule.get("params", [])],
                "node_label": nodes.get(rule.get("node", "")),
            })
        groups.append({**group, "rules": rules})
    return {
        "groups": groups,
        "total": sum(len(g["rules"]) for g in groups),
        "demo": settings_store.demo(),
        "time_scale": scale,
    }
