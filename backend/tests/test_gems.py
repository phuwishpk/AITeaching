"""Gem: สร้าง Item Bank ด้วย LLM ปลอม (ไม่เรียก Provider จริง) แล้วตรวจว่า engine และหน้านักเรียนใช้ได้"""

import asyncio
import json

from fastapi.testclient import TestClient

from app import db, services, settings_store
from app.api.deps import issue_token
from app.engine import flow as F
from app.gems import builder, flowspec, manage, verify
from app.gems import design as design_module
from app.main import app
from app.tutor import prompt, providers, service


def _item(math: str, answer, iso_answer=None, fmt="numeric"):
    base = {
        "prompt": "จงหาค่าของ x จากสมการ", "math": math, "format": fmt, "answer": answer,
        "difficulty": 0.4, "expected_time": 40,
        "hints": ["ดูฝั่งซ้ายก่อน", "ใช้สมบัติการเท่ากัน", "ขั้นแรกลบค่าคงที่ทั้งสองข้าง"],
        "socratic": ["ตาชั่งยังสมดุลไหม"], "wrong_answers": [{"answer": 7, "bug": "M-1"}],
    }
    if iso_answer is not None:
        base["isomorph"] = {**base, "math": "3x + 2 = 14", "answer": iso_answer}
    return base


PLAN = {
    "subject_name": "คณิตศาสตร์", "grade": "ม.2",
    "target": {"name": "สมการสองขั้น", "description": "ax + b = c"},
    "prerequisites": [{"name": "สมการขั้นเดียว", "description": "x + b = c", "grade": "ม.1"}],
    "bugs": [{"type": "misconception", "name": "ย้ายข้างไม่เปลี่ยนเครื่องหมาย", "description": "2x = 11 + 3",
              "response": "ชวนลบทั้งสองข้าง", "socratic": "ฝั่งขวาต้องทำอะไร", "prerequisite": 0}],
    "walkthroughs": [{"concept": "target", "title": "แก้ทีละขั้น", "problem": "2x + 1 = 7", "steps": ["ลบ 1", "หาร 2"]}],
}
ITEMS_A = {"items": [_item("2x + 3 = 11", 4, 4), _item("5x − 2 = 18", 4, 4)]}
# เฉลยข้อแรกผิด (คำตอบจริงคือ 5) sympy ต้องจับได้และติดธง
ITEMS_B = {"items": [_item("4x + 1 = 21", 6, 4), {
    "prompt": "ข้อใดคือค่าของ x เมื่อ x + 2 = 5", "format": "mcq", "options": ["1", "3", "5", "7"], "answer": 1,
    "hints": ["a", "b", "c"], "wrong_answers": [{"answer": 3, "bug": "M-1"}],
    "isomorph": {"prompt": "ข้อใดคือค่าของ x เมื่อ x + 4 = 9", "format": "mcq", "options": ["3", "5", "9", "13"],
                 "answer": "b", "hints": ["a", "b", "c"]},
}]}
EXTRAS = {
    "remedial": [{"prerequisite": 0, "items": [_item("x + 3 = 8", 5), _item("x − 2 = 4", 6), _item("x + 1 = 1", 0)]}],
    "challenge": [_item("6x + 1 = 2x + 25", 6)],
}


def fake_llm(monkeypatch, resolve_wrong: set[int] = frozenset()):
    calls = []

    async def fake_call(system, user, **options):
        calls.append(options)
        if "ออกแบบ Flow การสอน" in user:  # AI ออกแบบ Flow จากคำสั่ง (ในเทสต์ใช้โครงของแม่แบบอ้างอิง)
            payload = flowspec.standard_template()
        elif "ออกแบบโครงของบทเรียน" in user:
            payload = PLAN
        elif "ชุดที่ 1" in user:
            payload = ITEMS_A
        elif "ชุดที่ 2" in user:
            payload = ITEMS_B
        elif "ชุดที่ 9" in user:  # สร้างโจทย์สดระหว่างเรียน
            payload = {"items": [_item("7x + 2 = 30", 4, 4)]}
        elif "โจทย์ทบทวนพื้นฐาน" in user:
            payload = EXTRAS
        elif "แก้โจทย์ต่อไปนี้" in user:
            lines = [ln for ln in user.splitlines() if ln[:1].isdigit()]
            answers = []
            for i, line in enumerate(lines):
                truth = verify.sympy_answer(line.split("สมการ", 1)[-1].split("[")[0].strip())
                if "ตัวเลือก" in line:
                    answer = "b"
                else:
                    answer = int(truth) if truth is not None else 0
                answers.append({"i": i, "answer": 999 if i in resolve_wrong else answer})
            payload = {"answers": answers}
        else:
            return None, ["ไม่รู้จักคำขอ"]
        return providers.LLMResult(json.dumps(payload, ensure_ascii=False), "gemini", "fake", 1, 1, 1), []

    monkeypatch.setattr(service, "_call", fake_call)
    return calls


def test_sympy_answer_key_check():
    assert verify.sympy_answer("2x + 3 = 11") == 4
    assert verify.sympy_answer("(−7) − (−3)") == -4
    assert verify.sympy_answer("x/2 + 1 = 4") == 6
    assert verify.sympy_answer("x^2 = 4") is None  # สองคำตอบ ตรวจด้วย sympy ไม่ได้ ไม่ใช่ว่าผิด
    assert verify.sympy_answer('__import__("os")') is None  # ไม่ประเมินข้อความที่ไม่ใช่คณิตศาสตร์
    bad = {"format": "numeric", "math": "2x + 3 = 11", "answer": {"value": 5}}
    assert "sympy" in verify.check_with_sympy(bad)
    assert verify.check_resolved({"format": "mcq", "answer": {"option": "b"}}, "B") is None
    assert verify.check_resolved({"format": "short", "answer": {"accepted": ["สมบัติการเท่ากัน"]}}, "สมบัติ การเท่ากัน") is None


def test_llm_items_become_rule_checkable():
    bugs = {"M-1"}
    mcq = builder.to_item({"prompt": "เลือก", "options": ["1", "2"], "answer": 1,
                           "wrong_answers": [{"answer": 0, "bug": "M-1"}, {"answer": 1, "bug": "M-1"}]},
                          "X", "C-T", "main", bugs)
    assert mcq["format"] == "mcq" and mcq["answer"] == {"option": "b"}
    assert mcq["bugs"] == [{"answer": "a", "tag": "M-1"}]  # ตัวเลือกที่ถูกไม่ถูกนับเป็นคำตอบผิด
    assert len(mcq["hints"]) == 3  # คำใบ้ไม่ครบเติมด้วยคำใบ้กลาง
    assert builder.to_item({"prompt": "x", "format": "numeric", "answer": "ไม่ทราบ"}, "Y", "C-T", "main", bugs) is None
    short = builder.to_item({"prompt": "ชื่อสมบัติ", "answer": ["สมบัติการเท่ากัน"]}, "Z", "C-T", "main", bugs)
    assert short["format"] == "short"
    assert builder.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    # AI บางครั้งส่ง list มาตรง ๆ แทน object ที่สั่ง
    assert builder.parse_json('คำตอบ: [{"i": 0, "answer": 4}]') == [{"i": 0, "answer": 4}]
    assert builder.listing([{"i": 0}], "answers") == [{"i": 0}] and builder.listing({"answers": "x"}, "answers") == []


def test_build_flags_wrong_keys_and_students_can_learn(monkeypatch):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "ติวสมการ", "description": "ฝึกแก้สมการ", "instructions": "พูดแบบพี่สอนน้อง"}, "teacher")
    asyncio.run(builder.build(gem["id"]))

    gem = manage.get(gem["id"])
    assert gem["build"]["status"] == "ready", gem["build"]
    assert gem["bank_version"] == 1 and all(s["status"] == "done" for s in gem["build"]["steps"])
    subject = db.get_subject(gem["subject_id"])
    flagged = [it["id"] for it in subject["items"] if it.get("flag")]
    assert flagged == ["G-03"]  # 4x + 1 = 21 เฉลยเขียน 6 แต่ที่ถูกคือ 5
    assert gem["build"]["stats"]["main"] == 4 and gem["build"]["stats"]["flagged"] == 1

    # engine ไม่เห็นข้อที่ติดธง และ prompt ใช้คำสั่งของครูในกรอบ Role & Persona
    content = services.content_for(subject["id"], gem["set_id"])
    assert "G-03" not in content.items and "G-03" not in [m["id"] for m in content.main_items()]
    assert "พูดแบบพี่สอนน้อง" in prompt.role_frame(subject)
    assert "ห้ามบอกคำตอบสุดท้าย" in prompt.constraints_frame()

    # นักเรียนเห็น Gem เป็นการ์ดและเริ่มเรียนได้
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-20', 'real', NULL, 0)")
    client = TestClient(app)
    student = {"Authorization": f"Bearer {issue_token('student', 'S-20')}"}
    cards = client.get("/api/student/sets", headers=student).json()
    card = next(c for c in cards if c["id"] == gem["set_id"])
    assert card["name"] == "ติวสมการ" and card["gem"]["icon"] == "sparkles"
    view = client.post(f"/api/student/sets/{gem['set_id']}/start", headers=student, json={}).json()
    assert view["gem"]["tools"]["chat"] is True and view["item"]["id"] != "G-03"

    # ครูยืนยันเฉลยแล้วข้อนั้นกลับมาใช้ได้ หรือลบทิ้งพร้อมข้อคู่ขนาน
    detail = manage.resolve_flag(gem["id"], "G-03", keep=False)
    assert detail["bank"]["stats"]["flagged"] == 0
    assert "G-03-I1" not in {it["id"] for it in db.get_subject(gem["subject_id"])["items"]}


def test_second_layer_flags_disagreement_and_rebuild_retires_old_bank(monkeypatch):
    fake_llm(monkeypatch, resolve_wrong=set(range(60)))
    gem = manage.create({"name": "ติวสมการ"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    first = manage.get(gem["id"])
    subject = db.get_subject(first["subject_id"])
    # AI ที่แก้ซ้ำตอบผิดทุกข้อ: ข้อที่ sympy คำนวณได้และตรงเฉลยไม่ติดธง ข้อที่ sympy ตรวจไม่ได้ใช้ผลชั้นที่ 2
    assert not subject["items"][0].get("flag")
    no_math = next(it for it in subject["items"] if it["format"] == "mcq" and not it.get("math"))
    assert "LLM แก้ซ้ำ" in no_math["flag"]["reasons"][0]

    asyncio.run(builder.build(gem["id"]))
    second = manage.get(gem["id"])
    assert second["bank_version"] == 2 and second["subject_id"] != first["subject_id"]
    old = db.get_subject(first["subject_id"])
    assert old is not None and old["question_sets"][0]["published"] is False  # Session ที่ค้างยังทำต่อได้


def test_build_retries_then_reports_ai_failure(monkeypatch):
    attempts = []

    async def down(system, user, **options):
        attempts.append(1)
        return None, ["gemini: Gemini มีผู้ใช้มากชั่วคราว"]

    monkeypatch.setattr(service, "_call", down)
    monkeypatch.setattr(builder, "RETRY_DELAYS", (0, 0))
    gem = manage.create({"name": "ทดลอง"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    build = manage.get(gem["id"])["build"]
    assert build["status"] == "error" and "Gemini" in build["error"]
    assert next(s for s in build["steps"] if s["id"] == "plan")["status"] == "error"
    assert len(attempts) == 3  # ลองใหม่ 2 ครั้งก่อนยอมแพ้


def test_gem_api_roles_and_requirements():
    client = TestClient(app)
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    created = client.post("/api/gems", headers=teacher, json={"name": "Gem ครู", "icon": "nope"}).json()
    assert created["icon"] == "sparkles" and "ห้ามบอกคำตอบสุดท้าย" in created["locked_constraints"]
    assert client.post("/api/gems", headers=teacher, json={"name": "  "}).status_code == 400
    # Admin ดูได้อย่างเดียว
    assert client.get(f"/api/gems/{created['id']}", headers=admin).status_code == 200
    assert client.post("/api/gems", headers=admin, json={"name": "x"}).status_code == 403
    assert client.put(f"/api/gems/{created['id']}", headers=admin, json={"name": "x"}).status_code == 403
    # ยังไม่มี API key: สร้างคลังไม่ได้ และบอกให้ไปใส่ที่หน้า Admin
    response = client.post(f"/api/gems/{created['id']}/build", headers=teacher)
    assert response.status_code == 400 and "Admin" in response.json()["detail"]
    # ไฟล์ความรู้ผูกกับตัว Gem
    upload = client.post(f"/api/gems/{created['id']}/files", headers=teacher,
                         files={"file": ("note.md", "สมบัติการเท่ากัน: ทำเหมือนกันทั้งสองข้าง".encode(), "text/markdown")})
    assert upload.status_code == 200
    assert client.get(f"/api/gems/{created['id']}", headers=teacher).json()["files"][0]["filename"] == "note.md"
    assert client.delete(f"/api/gems/{created['id']}", headers=teacher).json()["ok"]
    assert client.get(f"/api/gems/{created['id']}", headers=teacher).status_code == 404


def test_rebuild_resumes_from_finished_steps(monkeypatch):
    monkeypatch.setattr(builder, "RETRY_DELAYS", (0, 0))
    calls = fake_llm(monkeypatch)
    real = service._call
    failing = {"extras": True}

    async def flaky(system, user, **options):
        if "โจทย์ทบทวนพื้นฐาน" in user and "ออกแบบ Flow" not in user and failing["extras"]:
            return None, ["gemini: Gemini มีผู้ใช้มากชั่วคราว"]
        return await real(system, user, **options)

    monkeypatch.setattr(service, "_call", flaky)
    gem = manage.create({"name": "ทำต่อ"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    assert manage.get(gem["id"])["build"]["status"] == "error"
    done_before = len(calls)

    failing["extras"] = False
    asyncio.run(builder.build(gem["id"]))
    assert manage.get(gem["id"])["build"]["status"] == "ready"
    # รอบสองเรียกแค่ extras กับการตรวจเฉลย ไม่วางแผนและไม่สร้างโจทย์หลักใหม่
    assert len(calls) - done_before == 2
    assert "draft" not in db.get_gem(gem["id"])
    assert calls[0]["backup_models"] == builder.GEMINI_BACKUPS


def test_gemini_switches_to_backup_model_when_busy(monkeypatch):
    tried = []

    async def once(api_key, model, *args):
        tried.append(model)
        if model == "main":
            raise providers.ProviderBusy("busy")
        return providers.LLMResult("{}", "gemini", model, 0, 0, 0)

    monkeypatch.setattr(providers, "_call_gemini_once", once)
    result = asyncio.run(providers.call_gemini("k", "main", "s", "u", backup_models=("lite", "old")))
    assert result.model == "lite" and tried == ["main", "lite"]


def test_latex_math_becomes_plain_and_checkable():
    assert builder.plain_math(r"\frac{1}{2} + \frac{1}{4} = \?") == "1/2 + 1/4"
    assert verify.sympy_answer(builder.plain_math(r"\frac{1}{2} - \frac{1}{3} =")) * 6 == 1
    assert builder.plain_math("   ") is None


def test_main_item_rests_when_all_its_isomorphs_are_flagged():
    subject = {
        "items": [{"id": "G-01", "isomorphs": ["G-01-I1"]}, {"id": "G-01-I1", "flag": {"reasons": ["x"]}},
                  {"id": "G-02", "isomorphs": ["G-02-I1"]}, {"id": "G-02-I1"}],
        "question_sets": [{"main_items": ["G-01", "G-02"], "challenge_items": []}],
    }
    view = builder.usable(subject)
    assert [it["id"] for it in view["items"]] == ["G-02", "G-02-I1"]
    assert view["question_sets"][0]["main_items"] == ["G-02"]


def test_unexpected_crash_still_ends_the_build(monkeypatch):
    fake_llm(monkeypatch)
    monkeypatch.setattr(builder, "apply_checks", lambda items, solved: 1 / 0)
    gem = manage.create({"name": "พัง"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    build = manage.get(gem["id"])["build"]
    assert build["status"] == "error" and "ZeroDivisionError" in build["error"]


def test_rounded_fraction_answers_read_as_fractions():
    from app.engine.answers import number_display

    assert [number_display(v) for v in (0.8333, 0.1667, 2.35, 0.125, 4, 3.0)] == ["5/6", "1/6", "2.35", "0.125", "4", "3"]


def test_versions_record_and_restore(monkeypatch):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "รุ่นแรก", "instructions": "สอนช้า ๆ"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    first_bank = manage.get(gem["id"])["subject_id"]
    manage.update(gem["id"], {"name": "รุ่นสอง", "instructions": "สอนเร็ว"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    notes = [v["note"] for v in manage.versions.history(gem["id"])]
    assert notes == ["สร้างคลังโจทย์รุ่นที่ 2", "แก้ชื่อ คำสั่ง", "สร้างคลังโจทย์รุ่นที่ 1", "สร้าง Gem"]

    restored = manage.restore(gem["id"], 2, "teacher")  # เวอร์ชัน 2 = หลังสร้างคลังรุ่นที่ 1
    assert restored["name"] == "รุ่นแรก" and restored["subject_id"] == first_bank
    assert db.get_subject(first_bank)["question_sets"][0]["published"] is True
    assert db.get_subject(first_bank)["gem"]["instructions"] == "สอนช้า ๆ"
    assert manage.versions.history(gem["id"])[0]["note"] == "ย้อนกลับไปเวอร์ชัน 2"


def test_legacy_question_set_becomes_a_gem(subject):
    from app import seed

    db.save_subject(subject)
    seed.add_document(subject["id"], "สรุป.md", "สมบัติการเท่ากัน")
    [gem_id] = manage.adopt_legacy()
    gem = manage.get(gem_id)
    assert gem["set_id"] == "QS-1" and gem["build"]["status"] == "ready" and gem["bank_version"] == 1
    assert db.get_subject(subject["id"])["gem"]["id"] == gem_id
    assert manage.files(gem_id)[0]["filename"] == "สรุป.md"
    assert manage.adopt_legacy() == []  # แปลงครั้งเดียว


def test_preview_uses_a_test_student_hidden_from_the_class(monkeypatch):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "พรีวิว"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    gem = manage.get(gem["id"])
    client = TestClient(app)
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    started = client.post(f"/api/gems/{gem['id']}/preview/start", headers=teacher).json()
    code = started["code"]
    assert code.startswith("TEST-") and started["view"]["item"]
    from app import demo
    item = services.content_for(gem["subject_id"], gem["set_id"]).item(started["view"]["item"]["id"])
    wrong = client.post(f"/api/gems/{gem['id']}/preview/answer", headers=teacher, json={"answer": demo.other_wrong(item)}).json()
    # ตอบทันทีหลังโจทย์ขึ้น engine จริงจับเป็น Rapid Guess เหมือนนักเรียนจริง
    assert wrong["view"]["position"] == "RAPID_GUESS_LOCK"
    assert client.get(f"/api/gems/{gem['id']}/preview", headers=teacher).json()["view"]["position"]
    # ไม่โผล่ในภาพรวม ตำแหน่งในผัง และกิจกรรมของห้อง
    assert code not in [s["code"] for s in services.staff_overview()]
    assert code not in [p["code"] for p in services.all_positions()]
    from app import activity
    assert all(e["code"] != code for e in activity.events(include_sim=True))
    assert client.post(f"/api/gems/{gem['id']}/preview/start",
                       headers={"Authorization": f"Bearer {issue_token('admin')}"}).status_code == 403


def _student_on_gem(monkeypatch, rules=None, code="S-30"):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "แจ้งเตือน", "alert_rules": rules or {}}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    gem = manage.get(gem["id"])
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES (?, 'real', NULL, 0)", (code,))
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {issue_token('student', code)}"}
    client.post(f"/api/student/sets/{gem['set_id']}/start", headers=headers, json={})
    return gem, client, headers


def test_alert_rules_normalize_and_lock_self_harm():
    from app.gems import alerts

    rules = alerts.normalize({"self_harm": {"enabled": False}, "stress": {"level": "urgent", "mode": "bogus"}, "x": {}})
    assert rules["self_harm"] == {"enabled": True, "level": "urgent", "mode": "pause"}
    assert rules["stress"] == {"enabled": True, "level": "urgent", "mode": "notify"}
    assert alerts.resolve({"alert_rules": {"deadlock": {"enabled": False}}}, "deadlock") is None
    assert alerts.resolve(None, "burnout_idle")["level"] == "silent"  # ชุดคำถามที่ไม่ใช่ Gem ใช้ค่าเดิมของระบบ


def test_ask_teacher_pauses_ai_into_drafts(monkeypatch):
    gem, client, headers = _student_on_gem(monkeypatch)
    services.mark_watching("S-30")  # ครูเปิดหน้าแชตของนักเรียนคนนี้อยู่
    reply = client.post(f"/api/student/sets/{gem['set_id']}/chat", headers=headers, json={"message": "ขอคุยกับครูหน่อย"}).json()
    assert reply["to_teacher"] and reply["reply"] is None
    alert = db.query_one("SELECT level, kind FROM alerts WHERE code = 'S-30'")
    assert alert == {"level": "normal", "kind": "ask_teacher"}
    assert services.chat_mode("S-30") == "teacher"
    assert db.query_one("SELECT sender FROM messages WHERE code = 'S-30' AND sender = 'draft'")


def test_teacher_rules_change_level_or_silence_alerts(monkeypatch):
    rules = {"stress": {"level": "urgent"}, "deadlock": {"enabled": False}}
    gem, client, headers = _student_on_gem(monkeypatch, rules, "S-31")
    client.post(f"/api/student/sets/{gem['set_id']}/chat", headers=headers, json={"message": "เครียดมากเลย"})
    assert db.query_one("SELECT level FROM alerts WHERE code = 'S-31' AND kind = 'stress'")["level"] == "urgent"

    from app.engine.core import Fx
    state = db.load_state("S-31", gem["set_id"])
    fx = Fx()
    fx.alerts.append({"level": "normal", "kind": "deadlock", "message": "ติด"})
    assert services.persist(state, fx) == []  # ครูปิดสถานการณ์นี้ไว้


def test_ai_outage_in_chat_tells_student_and_teacher(monkeypatch):
    gem, client, headers = _student_on_gem(monkeypatch, code="S-32")

    async def down(*args, **kwargs):
        return {"text": "fallback", "source": "authored", "errors": ["gemini: Gemini มีผู้ใช้มากชั่วคราว"], "log_id": 0}

    monkeypatch.setattr(services.tutor, "chat_reply", down)
    reply = client.post(f"/api/student/sets/{gem['set_id']}/chat", headers=headers, json={"message": "ทำไมต้องลบ"}).json()
    assert reply["source"] == "error" and "ตอบไม่ได้ชั่วคราว" in reply["reply"]
    assert db.query_one("SELECT kind FROM alerts WHERE code = 'S-32'")["kind"] == "ai_outage"


def test_off_topic_marker_is_stripped_and_reported(monkeypatch):
    gem, client, headers = _student_on_gem(monkeypatch, code="S-33")

    async def off(*args, **kwargs):
        return {"text": "กลับมาที่โจทย์กันนะ", "source": "gemini", "errors": [], "off_topic": True, "log_id": 0,
                "guard": {"blocked": False}}

    monkeypatch.setattr(services.tutor, "chat_reply", off)
    reply = client.post(f"/api/student/sets/{gem['set_id']}/chat", headers=headers, json={"message": "ฟุตบอลเมื่อคืน"}).json()
    assert reply["reply"] == "กลับมาที่โจทย์กันนะ"
    assert db.query_one("SELECT level, kind FROM alerts WHERE code = 'S-33'") == {"level": "silent", "kind": "off_topic"}
    assert "[OFF_TOPIC]" in prompt.constraints_frame()


def test_live_generation_adds_checked_items_to_the_bank(monkeypatch):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "สด"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    gem = manage.get(gem["id"])
    new_ids = asyncio.run(builder.generate_live(gem["subject_id"], {"difficulty": 50, "count": 1}))
    subject = db.get_subject(gem["subject_id"])
    assert new_ids == ["L-01"] and "L-01" in subject["question_sets"][0]["main_items"]
    live = next(it for it in subject["items"] if it["id"] == "L-01")
    assert live["live"] and live["isomorphs"] == ["L-01-I1"] and not live.get("flag")
    assert subject["gem"]["live_cap"] == 10
    again = asyncio.run(builder.generate_live(gem["subject_id"], {"difficulty": 50, "count": 1}))
    assert again == ["L-02"]  # รหัสต่อจากข้อเดิม ไม่นับรหัสของข้อคู่ขนาน


def test_admin_sees_the_flow_the_teacher_designed(monkeypatch):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "ออกแบบ", "instructions": "สอนแบบเกม",
                         "tools": {"hints": False, "walkthrough": False},
                         "alert_rules": {"stress": {"mode": "pause"}, "quit": {"enabled": False}}}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    client = TestClient(app)
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    design = client.get(f"/api/gems/{gem['id']}/design", headers=admin).json()
    # Admin เห็น Flow ที่ AI ออกแบบจาก prompt ของ Gem นี้ ไม่ใช่ผังตายตัว
    assert design["flow"]["custom"] and design["flow"]["nodes"]
    # แม่แบบอ้างอิง (Gem ที่ยังไม่มี Flow): ผังตัดกล่องของเครื่องมือที่ครูปิด และติดป้ายแจ้งเตือนตาม Alert Rule
    reference = design_module.flow_marks({**manage.get(gem["id"]), "flow": None})
    assert {"HINT_L1", "DELIBERATE_DELAY", "WALKTHROUGH"} <= set(reference["disabled"])
    assert "ISOMORPHIC_TEST" not in reference["disabled"]
    assert reference["alerts"]["CIRCUIT_BREAKER"][0]["mode"] == "pause"
    assert "CHOOSING_PATH" not in reference["alerts"]  # ครูปิดสถานการณ์นี้
    assert reference["alerts"]["SAFETY_STOP"][0]["mode"] == "pause"
    assert "สอนแบบเกม" in design["frames"]["role"] and "ห้ามบอกคำตอบสุดท้าย" in design["frames"]["constraints"]
    assert design["bank"]["stats"]["main"] == 4 and design["versions"]


def test_journey_shows_teacher_response_time(monkeypatch):
    from app import activity

    gem, client, headers = _student_on_gem(monkeypatch, code="S-40")
    services.mark_watching("S-40")
    client.post(f"/api/student/sets/{gem['set_id']}/chat", headers=headers, json={"message": "ขอคุยกับครูหน่อย"})
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    client.post("/api/teacher/students/S-40/viewed", headers=teacher)
    draft = db.query_one("SELECT id FROM messages WHERE code = 'S-40' AND sender = 'draft'")
    client.post(f"/api/teacher/drafts/{draft['id']}/send", headers=teacher, json={"text": "ครูมาแล้วจ้า"})

    trip = activity.journey("S-40")
    alerts = [t["alert_kind"] for t in trip["teacher"] if t["kind"] == "alert"]
    actions = [t for t in trip["teacher"] if t["kind"] != "alert"]
    # ในเทสต์ไม่มี API key แชตของ AI จึงล้มด้วย: แจ้งทั้งขอคุยกับครูและ AI ขัดข้อง
    assert alerts == ["ask_teacher", "ai_outage"]
    assert [a["kind"] for a in actions] == ["viewed", "draft_sent"]
    assert actions[0]["after_alert"] is not None and "after_alert" not in actions[1]
    assert "แก้ร่าง" in actions[1]["text"]
    assert trip["run"]["gem"]["id"] == gem["id"] and trip["run"]["gem"]["version"]
    assert trip["summary"]["alerts"] == 2 and trip["summary"]["responses"] == 1


def test_teacher_reviews_adds_edits_and_removes_items(monkeypatch):
    fake_llm(monkeypatch)
    gem = manage.create({"name": "คลัง"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    gem = manage.get(gem["id"])
    client = TestClient(app)
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    base = f"/api/gems/{gem['id']}"
    bank = client.get(f"{base}/items", headers=teacher).json()
    assert {i["status"] for i in bank["items"]} >= {"active", "flagged"}

    # AI สร้างเพิ่ม: รอครูอนุมัติ ยังไม่ถึงนักเรียน
    after = client.post(f"{base}/generate", headers=teacher, json={"count": 1})
    assert after.status_code == 400  # ยังไม่มี API key ในเทสต์
    asyncio.run(builder.generate_items(gem["subject_id"], {"difficulty": 50, "count": 1}, builder.REVIEW_PENDING))
    pending = [i for i in client.get(f"{base}/items", headers=teacher).json()["items"] if i["status"] == "pending"]
    assert pending and pending[0]["id"] not in services.content_for(gem["subject_id"], gem["set_id"]).items
    client.post(f"{base}/items/{pending[0]['id']}/approve", headers=teacher)
    services.invalidate_content()
    assert pending[0]["id"] in services.content_for(gem["subject_id"], gem["set_id"]).items

    # ครูแก้ข้อที่ติดธง: ธงหายเพราะครูเป็นผู้ตัดสินสุดท้าย และ sympy เตือนถ้ายังไม่ตรง
    fixed = client.put(f"{base}/items/G-03", headers=teacher, json={
        "prompt": "จงหาค่าของ x", "math": "4x + 1 = 21", "format": "numeric", "answer": {"value": "5"},
        "hints": {"1": "ดูฝั่งซ้าย", "2": "ใช้สมบัติการเท่ากัน", "3": "ลบ 1 ทั้งสองข้าง"}}).json()
    item = next(i for i in fixed["items"] if i["id"] == "G-03")
    assert item["status"] == "active" and fixed["warning"] is None
    wrong = client.put(f"{base}/items/G-03", headers=teacher, json={**item, "answer": {"value": "6"}}).json()
    assert "sympy" in wrong["warning"]

    # ครูเพิ่มโจทย์ปรนัยเอง แล้วลบ
    added = client.post(f"{base}/items", headers=teacher, json={
        "kind": "main", "prompt": "ข้อใดคือคำตอบของ x + 1 = 3", "format": "mcq",
        "options": [{"text": "1"}, {"text": "2"}], "answer": {"option": "b"}}).json()
    assert added["saved"] == "K-01"
    assert client.post(f"{base}/items", headers=teacher, json={"prompt": "x", "format": "mcq", "options": [{"text": "1"}],
                                                              "answer": {"option": "a"}}).status_code == 400
    removed = client.delete(f"{base}/items/K-01", headers=teacher).json()
    assert all(i["id"] != "K-01" for i in removed["items"])
    notes = [v["note"] for v in manage.versions.history(gem["id"])]
    assert "ครูเพิ่มโจทย์ K-01" in notes and "ครูลบโจทย์ K-01" in notes
    # Gem ยังเปิดให้นักเรียนได้ แม้โจทย์ที่ครูเพิ่มยังไม่มีข้อคู่ขนาน
    from app.content.readiness import check_set
    assert check_set(builder.usable(db.get_subject(gem["subject_id"])), gem["set_id"])["ok"]
    assert client.get(f"{base}/items", headers={"Authorization": f"Bearer {issue_token('admin')}"}).status_code == 403


def test_each_gem_draws_only_its_own_flow():
    """ผังของ Admin ไม่ตายตัว: กล่องของเครื่องมือที่ครูปิดไม่อยู่ในผัง และทุกเส้นต่อกับกล่องที่มีอยู่จริง"""
    from itertools import product

    from app.gems import design

    for combo in product([True, False], repeat=5):
        tools = dict(zip(("chat", "hints", "isomorphic", "walkthrough", "remedial"), combo))
        view = design.flow_view({"tools": tools})
        ids = {n["id"] for n in view["nodes"]}
        assert all(e["source"] in ids and e["target"] in ids for e in view["edges"]), tools
        assert not set(view["hidden"]) & ids
    everything = design.flow_view({})
    assert not everything["hidden"] and all(e["id"] != "e_g3_nohint" for e in everything["edges"])
    no_iso = design.flow_view({"tools": {"isomorphic": False}})
    assert next(e for e in no_iso["edges"] if e["id"] == "e_g1_wrong")["target"] == "G2"
    no_chat = {n["id"] for n in design.flow_view({"tools": {"chat": False}})["nodes"]}
    assert not {"TEACHER_REVIEW", "SAFETY_STOP", "CHOOSING_PATH"} & no_chat


# ---------------------------------------------------------------- Flow ที่ AI ออกแบบจากคำสั่งของครู (ADR-0004)

REFLECT_FLOW = {
    "summary": "ทุกข้อที่ถูกให้อธิบายวิธีคิด ครูให้ประเมินคำอธิบาย ผิดสองครั้งแจ้งครู",
    "start": "work", "params": {"max_items": 99},
    "steps": [
        {"id": "work", "kind": "item", "label": "ทำโจทย์", "pick": "main"},
        {"id": "why", "kind": "reflect", "label": "อธิบายวิธีคิด", "question": "ทำไมจึงได้คำตอบนี้",
         "judge": True, "rubric": "บอกว่าย้ายข้างอย่างไร"},
        {"id": "tell", "kind": "notify", "label": "แจ้งครู", "text": "ผิดสองครั้งแล้ว"},
        {"id": "end", "kind": "end", "label": "จบ"},
    ],
    "edges": [
        {"from": "work", "to": "why", "when": "correct"},
        {"from": "work", "to": "tell", "when": "wrong and error_count == 2"},
        {"from": "work", "to": "work", "when": ""},
        {"from": "tell", "to": "work", "when": ""},
        {"from": "why", "to": "end", "when": "judge_pass and items_done >= 2"},
        {"from": "why", "to": "work", "when": ""},
    ],
}


def _flow_gem(monkeypatch, flow=REFLECT_FLOW, judge=None):
    calls = fake_llm(monkeypatch)
    real = service._call

    async def with_flow(system, user, **options):
        if "ออกแบบ Flow การสอน" in user:
            calls.append(options)
            return providers.LLMResult(json.dumps(flow, ensure_ascii=False), "gemini", "fake", 1, 1, 1), []
        if "ประเมินคำอธิบาย" in system:
            return providers.LLMResult(json.dumps(judge or {"pass": True, "score": 90, "reason": "ดี"}), "gemini", "fake", 1, 1, 1), []
        return await real(system, user, **options)

    monkeypatch.setattr(service, "_call", with_flow)
    gem = manage.create({"name": "อธิบายเหตุผล", "instructions": "ทุกข้อที่ถูกให้นักเรียนอธิบายวิธีคิด"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    return manage.get(gem["id"])


def test_build_designs_the_flow_from_the_teacher_prompt(monkeypatch):
    gem = _flow_gem(monkeypatch)
    assert gem["flow"]["mode"] == "custom" and gem["flow"]["source"] == "ai" and not gem["flow"]["reviewed"]
    assert [s["kind"] for s in gem["flow"]["spec"]["steps"]] == ["item", "reflect", "notify", "end"]
    assert gem["flow"]["spec"]["params"]["max_items"] == 40, "ตัวเลขจาก prompt ถูกตัดให้อยู่ในช่วงที่ปลอดภัย"
    client = TestClient(app)
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    design = client.get(f"/api/gems/{gem['id']}/design", headers=admin).json()
    assert design["flow"]["custom"] and {n["id"] for n in design["flow"]["nodes"]} == {"work", "why", "tell", "end"}
    assert len(design["flow"]["locked"]) == 4 and design["flow"]["guards"]
    # คำสั่งเดิมสร้างคลังใหม่ ไม่ออกแบบ Flow ซ้ำ
    assert not builder.flow_needs_design(gem)


def test_student_runs_the_designed_flow_with_ai_judge(monkeypatch):
    gem = _flow_gem(monkeypatch)
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-40', 'real', NULL, 0)")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {issue_token('student', 'S-40')}"}
    set_id = gem["set_id"]
    view = client.post(f"/api/student/sets/{set_id}/start", headers=headers, json={}).json()
    from app import demo
    state = db.load_state("S-40", set_id)
    state["item"]["ready_at"] -= 30
    db.save_state(state)
    item = services.content_for(gem["subject_id"], set_id).item(view["item"]["id"])
    view = client.post(f"/api/student/sets/{set_id}/answer", headers=headers, json={"answer": demo.correct_raw(item)}).json()["view"]
    assert view["position"] == "FLOW_REFLECT" and view["reflect"]["question"] == "ทำไมจึงได้คำตอบนี้"
    reply = client.post(f"/api/student/sets/{set_id}/reflect", headers=headers, json={"message": "ย้าย 3 ไปลบ"}).json()
    assert reply["view"]["position"] == "ANSWERING"
    trace = db.query_one("SELECT data FROM traces WHERE code = 'S-40' AND action = 'reflect'")
    assert db.loads(trace["data"])["judge"]["pass"] is True
    staff = services.all_positions()
    assert next(p for p in staff if p["code"] == "S-40")["step"] == "work"


def test_teacher_reviews_and_edits_the_flow(monkeypatch):
    gem = _flow_gem(monkeypatch)
    client = TestClient(app)
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    flow = client.get(f"/api/gems/{gem['id']}/flow", headers=teacher).json()
    assert flow["mode"] == "custom" and not flow["reviewed"] and flow["map"]["nodes"]
    broken = {**flow["spec"], "edges": flow["spec"]["edges"][:-1] + [{"from": "why", "to": "nowhere", "when": "x > 1"}]}
    checked = client.post(f"/api/gems/{gem['id']}/flow/check", headers=teacher, json={"spec": broken}).json()
    assert checked["errors"]
    assert client.put(f"/api/gems/{gem['id']}/flow", headers=teacher, json={"spec": broken}).status_code == 400
    edited = {**flow["spec"], "params": {"rapid_guess_lock": 30}}
    saved = client.put(f"/api/gems/{gem['id']}/flow", headers=teacher, json={"spec": edited}).json()
    assert saved["source"] == "teacher" and saved["reviewed"] and saved["spec"]["params"] == {"rapid_guess_lock": 30}
    from app.gems import versions
    assert versions.history(gem["id"])[0]["note"] == "ครูแก้ Flow การสอน"
    # Flow ที่ครูแก้เองไม่ถูกออกแบบทับตอนสร้างคลังใหม่
    assert not builder.flow_needs_design(manage.get(gem["id"]))
    # ผังมาตรฐานเป็นแค่แม่แบบอ้างอิง เลือกใช้แทน Flow ของ Gem ไม่ได้
    assert client.post(f"/api/gems/{gem['id']}/flow/standard", headers=teacher).status_code in (404, 405)
    subject = db.get_subject(manage.get(gem["id"])["subject_id"])
    assert subject["gem"]["flow"]["mode"] == "custom"
    # Admin ดูได้ แก้ไม่ได้
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    assert client.put(f"/api/gems/{gem['id']}/flow", headers=admin, json={"spec": edited}).status_code == 403


def test_teacher_bug_table_is_kept_with_its_own_hint_ladder():
    """ตาราง Bug Library ของครู: รหัสตามครู คำตอบผิดหลายค่าต่อรหัส และคำใบ้ L1–L3 เฉพาะคำตอบผิดนั้น"""
    plan = builder.normalize_plan({
        "target": {"name": "ลำดับการดำเนินการ (PEMDAS)"}, "prerequisites": [{"name": "จำนวนเต็ม"}],
        "bugs": [{"id": "BUG-M01", "type": "misconception", "name": "ทำจากซ้ายไปขวาทั้งหมด"},
                 {"id": "bug-s02", "type": "slip", "name": "คิดเลขคลาด 1"}, {"id": "BUG-M01", "type": "misconception", "name": "ซ้ำ"}],
    })
    assert [b["id"] for b in plan["bug_tags"]] == ["BUG-M01", "BUG-S02", "M-2"]
    item = builder.to_item({
        "prompt": "จงหาค่าของ", "math": "20 - 12 ÷ 2 × 3 + 2^{2}", "format": "numeric", "answer": 6,
        "wrong_answers": [{"answer": 16, "bug": "BUG-M01", "hints": ["ลบ คูณ หาร ยกกำลัง สำคัญเท่ากันไหม", "ยกกำลังและคูณหารก่อน", "หา 2² กับ 12 ÷ 2 ก่อน"]},
                          {"answer": [5, 7], "bug": "BUG-S02", "hints": ["ทวน 2 + 4 อีกครั้ง"]},
                          {"answer": 6, "bug": "BUG-M01"}],
    }, "G-01", "C-T", "main", {"BUG-M01", "BUG-S02"})
    assert item["math"] == "20 - 12 ÷ 2 × 3 + 2^2" and verify.check_with_sympy(item) is None
    assert [(b["answer"], b["tag"]) for b in item["bugs"]] == [(16, "BUG-M01"), (5, "BUG-S02"), (7, "BUG-S02")]
    assert service.authored_hint(item, 3, "BUG-M01") == "หา 2² กับ 12 ÷ 2 ก่อน"
    assert service.authored_hint(item, 2, "BUG-S02") == item["hints"]["2"], "ครูไม่ได้ให้ L2 ของคำตอบนี้ ใช้คำใบ้ของข้อ"
    assert verify.sympy_answer("[20 - (4 + 2)] ÷ 7") == 2


def test_sympy_overrules_a_wrong_ai_resolve_and_checks_numeric_choices():
    good = builder.to_item({"prompt": "จงหาค่าของ", "math": "20 - 12 ÷ 2 × 3 + 2²", "format": "numeric", "answer": 6},
                           "G-01", "C-T", "main", set())
    mcq = builder.to_item({"prompt": "ข้อใดคือค่าของ", "math": "8 + 4² ÷ 2 - 5", "format": "mcq",
                           "options": ["7", "9", "11", "13"], "answer": 2}, "G-02", "C-T", "main", set())
    wrong_mcq = builder.to_item({"prompt": "ข้อใดคือค่าของ", "math": "8 + 4² ÷ 2 - 5", "format": "mcq",
                                 "options": ["7", "9", "11", "13"], "answer": 0}, "G-03", "C-T", "main", set())
    unknown = builder.to_item({"prompt": "สมบัติใด", "format": "short", "answer": ["สลับที่"]}, "G-04", "C-T", "main", set())
    builder.apply_checks([good, mcq, wrong_mcq, unknown], {0: 5, 1: "a", 2: "a", 3: "เปลี่ยนหมู่"})
    assert not good.get("flag") and not mcq.get("flag"), "sympy คำนวณได้ตรงเฉลย ไม่ติดธงแม้ AI แก้ซ้ำผิด"
    assert "ข้อ c" in wrong_mcq["flag"]["reasons"][0]
    assert unknown["flag"], "sympy ตรวจไม่ได้ ใช้ผลที่ AI แก้ซ้ำ"


def test_prerequisite_by_name_and_sympy_suggested_answer(monkeypatch):
    prereqs = [{"name": "การบวก ลบ คูณ หาร จำนวนเต็ม"}, {"name": "เลขยกกำลัง"}]
    assert builder.prereq_index("การบวก ลบ คูณ หาร จำนวนเต็ม", prereqs) == 0
    assert builder.prereq_index("1", prereqs) == 1 and builder.prereq_index(1, prereqs) == 1
    assert builder.prereq_index("เรื่องอื่น", prereqs) is None
    wrong = builder.to_item({"prompt": "จงหาค่าของ", "math": "30 - 16 ÷ 4 × 2 + 3²", "format": "numeric", "answer": 17,
                             "wrong_answers": [{"answer": 31, "bug": "M-1"}, {"answer": 21, "bug": "M-1"}]},
                            "G-05", "C-T", "main", {"M-1"})
    builder.apply_checks([wrong], {0: 31})
    assert wrong["flag"]["suggested"] == "31"


def test_long_knowledge_files_are_read_in_full_or_digested(monkeypatch):
    from app import seed

    gem = manage.create({"name": "อ่านเอกสาร"}, "teacher")
    seed.add_document(gem["id"], "short.md", "กฎ PEMDAS: คูณและหารทำจากซ้ายไปขวา")
    seen = []

    async def fake_ask(step, user, max_tokens=12000):
        seen.append(step)
        if step == "memory":
            return {"summary": "สอน PEMDAS", "concepts": [{"name": "คูณหารซ้ายไปขวา", "source": "[short.md]"}]}
        return {"notes": "ท้ายไฟล์บอกว่าวงเล็บเหลี่ยมทำก่อน" if "ความลับท้ายไฟล์" in user else "บันทึก"}

    monkeypatch.setattr(builder, "ask_json", fake_ask)
    reading = asyncio.run(builder.read_knowledge(gem["id"]))
    assert reading["mode"] == "full" and reading["read"] == reading["chars"]
    # ขั้น "จำ": AI จดสิ่งที่ต้องใช้จากเอกสารก่อนสร้างโจทย์ และส่งต่อเป็นรายการตรวจ
    assert reading["memory"]["summary"] == "สอน PEMDAS" and "<memory>" in builder.memory_block(reading["memory"])
    # ไฟล์สั้น: ตอนสอนส่งให้ AI ทั้งไฟล์ ไม่ต้องเดาว่าย่อหน้าไหนเกี่ยว
    terms, docs = service._retrieve({"id": "x", "gem": {"id": gem["id"]}}, "เรื่องอื่นเลย")
    assert docs and "ซ้ายไปขวา" in docs[0]["text"]

    # ไฟล์ยาวเกินที่ส่งได้ในครั้งเดียว: สรุปทีละส่วนจนครบ และส่วนท้ายสุดต้องถูกอ่านด้วย
    monkeypatch.setattr(builder, "READ_LIMIT", 3000)
    monkeypatch.setattr(builder, "DIGEST_SEGMENT", 2000)
    long_text = "\n\n".join(f"ย่อหน้าที่ {i} เนื้อหาบทเรียนเรื่องลำดับการดำเนินการ" for i in range(300)) + "\n\nความลับท้ายไฟล์: วงเล็บเหลี่ยมทำก่อน"
    seed.add_document(gem["id"], "long.md", long_text)
    seen.clear()
    reading = asyncio.run(builder.read_knowledge(gem["id"]))
    assert reading["mode"] == "digest" and reading["read"] == reading["chars"]
    assert "วงเล็บเหลี่ยมทำก่อน" in reading["text"] and seen.count("digest") == reading["segments"]
    assert seen[-1] == "memory" and reading["memory"]
    assert "100%" in builder.reading_note(reading)


def test_chat_prompt_remembers_the_conversation():
    built = prompt.chat_prompt({"name": "คณิต"}, None, "PEMDAS", {}, "แล้วต่อไปทำอะไร", None, [], [],
                               [{"sender": "student", "text": "หาร 12 ด้วย 2 ก่อนใช่ไหม"},
                                {"sender": "tutor", "text": "ใช่ แล้วได้เท่าไรนะ"}])
    assert "<history>" in built["user"] and "หาร 12 ด้วย 2 ก่อนใช่ไหม" in built["user"]


def test_chat_memory_stays_within_the_same_gem():
    db.execute("INSERT INTO messages (ts, code, set_id, sender, text) VALUES (1, 'S-50', 'gem-aaa-b1-set', 'student', 'คุยเรื่องเศษส่วน')")
    db.execute("INSERT INTO messages (ts, code, set_id, sender, text) VALUES (2, 'S-50', 'gem-bbb-b1-set', 'student', 'คุยเรื่องสมการ')")
    db.execute("INSERT INTO messages (ts, code, set_id, sender, text) VALUES (3, 'S-50', 'gem-bbb-b2-set', 'tutor', 'ตอบเรื่องสมการ')")
    db.execute("INSERT INTO messages (ts, code, set_id, sender, text) VALUES (4, 'S-50', 'gem-bbb-b2-set', 'student', 'ข้อความล่าสุด')")
    memory = services.chat_memory("S-50", "gem-bbb-b2-set")
    assert [m["text"] for m in memory] == ["คุยเรื่องสมการ", "ตอบเรื่องสมการ"]


def test_gemini_reads_pdfs_page_by_page_and_falls_back_locally(monkeypatch):
    import io

    from pypdf import PdfWriter

    from app import settings_store
    from app.tutor import reader

    writer = PdfWriter()
    for _ in range(13):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf = buffer.getvalue()
    # ไม่มี Gemini key: ใช้ตัวอ่านในเครื่อง (PDF เปล่าจึงอ่านไม่ได้และบอกเหตุผล)
    text, warning, how = asyncio.run(reader.read_file("blank.pdf", pdf))
    assert how == "local" and not text and warning

    monkeypatch.setattr(settings_store, "api_key", lambda provider: ("fake-key", "test"))
    monkeypatch.setattr(settings_store, "ai_settings", lambda: {"active": "gemini", "gemini_model": "gemini-test", "gemini_design_model": "gemini-test", "order": ["gemini"]})
    asked = []

    async def fake_gemini(key, model, system, user, **options):
        asked.append(user)
        if "หน้า 7–12" in user:
            raise providers.ProviderError("ล่ม")
        return providers.LLMResult(f"ข้อความที่ถอดจาก{user}", "gemini", model, 1, 1, 1)

    monkeypatch.setattr(providers, "call_gemini", fake_gemini)
    text, warning, how = asyncio.run(reader.read_file("book.pdf", pdf))
    assert len(asked) == 3 and "หน้า 1–6" in text and "หน้า 13–13" in text
    assert how == "gemini+local" and "7–12" in warning


def test_tutor_prompts_carry_the_whole_gem_document(monkeypatch):
    from app import seed

    gem = manage.create({"name": "จำเอกสาร"}, "teacher")
    seed.add_document(gem["id"], "notes.md", "ครูสอนว่า ÷ กับ × มีศักดิ์ศรีเท่ากัน ทำจากซ้ายไปขวา")
    seen = {}

    async def fake_call(system, user, **options):
        seen["system"] = system
        return providers.LLMResult("ลองดูเครื่องหมายทางซ้ายก่อนนะ", "gemini", "fake", 1, 1, 1), []

    monkeypatch.setattr(service, "_call", fake_call)
    subject = {"id": "s", "name": "คณิต", "grade": "ม.1", "gem": {"id": gem["id"], "instructions": ""}}
    item = {"id": "G-01", "prompt": "จงหาค่า", "math": "12 ÷ 2 × 3", "format": "numeric", "answer": {"value": 18}, "hints": {}}
    result = asyncio.run(service.chat_reply(subject, item, "PEMDAS", {}, "ทำอะไรก่อน", None, [], "ลองคิดดู", "S-1"))
    assert "ศักดิ์ศรีเท่ากัน" in seen["system"] and result["source"] == "gemini"
    log = db.query_one("SELECT frames FROM ai_logs ORDER BY id DESC LIMIT 1")
    assert "ส่งเอกสารของ Gem ทั้งหมด" in db.loads(log["frames"])["knowledge"]


def test_staff_password_when_the_server_sets_one(monkeypatch):
    client = TestClient(app)
    assert client.post("/api/auth/staff", json={"role": "teacher"}).status_code == 200
    monkeypatch.setenv("TUTOR_TEACHER_PASSWORD", "ครู-1234")
    assert client.get("/api/auth/staff-mode").json() == {"teacher": True, "admin": False, "users": False}
    assert client.post("/api/auth/staff", json={"role": "teacher"}).status_code == 401
    assert client.post("/api/auth/staff", json={"role": "teacher", "password": "ผิด"}).status_code == 401
    assert client.post("/api/auth/staff", json={"role": "teacher", "password": "ครู-1234"}).json()["token"]
    assert client.post("/api/auth/staff", json={"role": "admin"}).status_code == 200


def test_several_staff_share_one_system_but_not_api_keys(monkeypatch):
    from app import settings_store, users

    alice = users.add("alice", "ครูอลิซ")
    bob = users.add("bob", "ครูบ็อบ")
    client = TestClient(app)
    assert client.get("/api/auth/staff-mode").json()["users"] is True
    assert client.post("/api/auth/staff", json={"role": "teacher", "username": "alice", "password": "ผิด"}).status_code == 401
    login = lambda name, pw, role="teacher": {"Authorization": "Bearer " + client.post(
        "/api/auth/staff", json={"role": role, "username": name, "password": pw}).json()["token"]}
    a_admin, b_admin = login("alice", alice, "admin"), login("bob", bob, "admin")
    # แต่ละคนใส่ key ของตัวเอง เห็นแค่ของตัวเอง
    client.put("/api/admin/secrets", headers=a_admin, json={"provider": "gemini", "key": "AIza-alice-1111"})
    assert client.get("/api/admin/settings", headers=a_admin).json()["keys"]["gemini"]["last4"] == "1111"
    assert client.get("/api/admin/settings", headers=b_admin).json()["keys"]["gemini"]["configured"] is False
    # Gem ของใครคนนั้นเป็นเจ้าของ ทุกคนเห็น Gem ชุดเดียวกัน
    a_teacher, b_teacher = login("alice", alice), login("bob", bob)
    gem = client.post("/api/gems", headers=a_teacher, json={"name": "เศษส่วนของอลิซ"}).json()
    assert gem["owner"] == "alice" and gem["owner_name"] == "ครูอลิซ"
    assert [g["id"] for g in client.get("/api/gems", headers=b_teacher).json()] == [gem["id"]]
    # งาน AI ของ Gem คิดกับ key ของเจ้าของ แม้บ็อบเป็นคนกด และระหว่างนักเรียนเรียน
    seen = []

    async def fake_call(system, user, **options):
        seen.append(settings_store.api_key("gemini")[0])
        return providers.LLMResult("ลองคิดดูอีกที", "gemini", "fake", 1, 1, 1), []

    monkeypatch.setattr(service, "_call", fake_call)
    settings_store.use_keys_of("bob")
    services.bill_to_gem_owner({"gem": {"id": gem["id"]}})
    asyncio.run(service.chat_reply({"id": "x", "name": "คณิต", "gem": {"id": gem["id"]}}, None, "", {}, "ช่วยหน่อย", None, [], "", "S-1"))
    assert seen == ["AIza-alice-1111"]


def test_only_the_gem_owner_can_change_or_rebuild_it():
    from app import users

    alice, bob = users.add("alice", "ครูอลิซ"), users.add("bob", "ครูบ็อบ")
    client = TestClient(app)
    login = lambda name, pw: {"Authorization": "Bearer " + client.post(
        "/api/auth/staff", json={"role": "teacher", "username": name, "password": pw}).json()["token"]}
    a, b = login("alice", alice), login("bob", bob)
    gem = client.post("/api/gems", headers=a, json={"name": "ของอลิซ"}).json()
    assert client.put(f"/api/gems/{gem['id']}", headers=b, json={"name": "แก้"}).status_code == 403
    assert client.post(f"/api/gems/{gem['id']}/build", headers=b).status_code == 403
    assert client.delete(f"/api/gems/{gem['id']}", headers=b).status_code == 403
    assert client.get(f"/api/gems/{gem['id']}", headers=b).status_code == 200
    assert client.put(f"/api/gems/{gem['id']}", headers=a, json={"name": "แก้โดยเจ้าของ"}).status_code == 200


def test_gem_without_a_designed_flow_is_not_offered_to_students(monkeypatch):
    fake_llm(monkeypatch)
    real = service._call

    async def no_flow(system, user, **options):
        if "ออกแบบ Flow การสอน" in user:
            return providers.LLMResult("{}", "gemini", "fake", 1, 1, 1), []
        return await real(system, user, **options)

    monkeypatch.setattr(service, "_call", no_flow)
    gem = manage.create({"name": "ยังไม่มี Flow"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    gem = manage.get(gem["id"])
    assert gem["build"]["status"] == "ready" and (gem.get("flow") or {}).get("mode") != "custom"
    assert any("ออกแบบ Flow การสอนไม่สำเร็จ" in w for w in gem["build"]["warnings"])
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-60', 'real', NULL, 0)")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {issue_token('student', 'S-60')}"}
    assert gem["set_id"] not in [s["id"] for s in client.get("/api/student/sets", headers=headers).json()]
    assert client.post(f"/api/student/sets/{gem['set_id']}/start", headers=headers, json={}).status_code == 404


def test_ai_answers_in_scope_when_teacher_is_not_on_the_chat_page(monkeypatch):
    """ครูไม่ได้เปิดหน้าแชต: นักเรียนไม่ต้องรอ AI ตอบเรื่องบทเรียนเอง ทั้งตอนโหมดครูและตอนระบบหยุดรอครู
    ยกเว้นหยุดเพราะข้อความทำร้ายตนเอง ครูดูแลคนเดียวเสมอ"""
    gem, client, headers = _student_on_gem(monkeypatch, code="S-50")
    url = f"/api/student/sets/{gem['set_id']}/chat"
    reply = client.post(url, headers=headers, json={"message": "ขอคุยกับครูหน่อย"}).json()
    assert services.chat_mode("S-50") == "teacher" and not reply.get("to_teacher") and reply["reply"]
    assert not db.query_one("SELECT id FROM messages WHERE code = 'S-50' AND sender = 'draft'")

    state = db.load_state("S-50", gem["set_id"])
    state["position"] = F.DEADLOCK
    db.save_state(state)
    assert not client.post(url, headers=headers, json={"message": "ข้อนี้ต้องทำอะไรก่อน"}).json().get("to_teacher")
    services.mark_watching("S-50")
    assert client.post(url, headers=headers, json={"message": "ข้อนี้ต้องทำอะไรก่อน"}).json()["to_teacher"]

    services._watching.clear()
    state["position"] = F.SAFETY
    db.save_state(state)
    assert client.post(url, headers=headers, json={"message": "ข้อนี้ต้องทำอะไรก่อน"}).json()["to_teacher"]


def test_guard_block_is_not_an_ai_outage():
    """จาก Gemini จริง: AI ตอบได้แต่ Guard บล็อก นักเรียนเคยเห็น "ตอบไม่ได้ชั่วคราว (ยังไม่ได้ใส่ API key)" ของ Claude ที่ถูกข้าม"""
    blocked = {"text": "ลองคิดดูนะ", "source": "authored", "guard": {"blocked": True}, "errors": ["claude: ยังไม่ได้ใส่ API key"]}
    assert not services.ai_failed(blocked)
    failed = {"text": "x", "source": "authored", "errors": ["claude: ยังไม่ได้ใส่ API key", "gemini: เกินโควตา"]}
    assert services.ai_failed(failed) and services.failure_reason(failed["errors"]) == "เกินโควตา"


def test_design_and_chat_use_their_own_gemini_model(monkeypatch):
    """งานสร้างบทเรียนใช้โมเดลที่ฉลาดกว่าได้ งานแชตใช้ตัวเร็ว ตัวที่เลือกใช้ไม่ได้ (โควตาหมด) บันทึกเหตุผลที่ใช้ตัวสำรอง"""
    settings_store.save_ai_settings({"active": "gemini", "gemini_model": "gemini-fast", "gemini_design_model": "gemini-smart"})
    monkeypatch.setattr(settings_store, "api_key", lambda provider: ("key", "file"))
    asked = []

    async def fake_call_gemini(key, model, system, user, **options):
        asked.append(model)
        return providers.LLMResult("ok", "gemini", "gemini-lite", 1, 1, 1, fallback=f"{model}: โควตาหมด")

    monkeypatch.setattr(providers, "call_gemini", fake_call_gemini)
    result, errors = asyncio.run(service._call("s", "u", task="design"))
    asyncio.run(service._call("s", "u"))
    assert asked == ["gemini-smart", "gemini-fast"]
    assert result.text == "ok" and errors == ["gemini: ใช้ gemini-lite แทน (gemini-smart: โควตาหมด)"]
    assert not services.ai_failed({"text": "ok", "source": "gemini", "errors": errors})


def test_chat_history_marks_messages_from_earlier_items():
    """จาก AI จริง: ทำข้อใหม่แล้ว AI ยังพูดถึง "4x ลบ 2x" ของข้อก่อน ประวัติแชตต้องแยกว่าข้อความไหนเป็นของข้อก่อน"""
    block = prompt.history_block([{"sender": "student", "text": "4x - 2x ได้เท่าไหร่", "earlier": True},
                                  {"sender": "tutor", "text": "ลองนับดูนะ", "earlier": True},
                                  {"sender": "student", "text": "ข้อนี้เริ่มยังไง", "earlier": False}])
    assert block.index("ข้อก่อน") < block.index("4x") < block.index("(คุยกันในโจทย์ปัจจุบัน)") < block.index("ข้อนี้เริ่มยังไง")
    assert "ข้อก่อน" not in prompt.history_block([{"sender": "student", "text": "สวัสดี"}])
