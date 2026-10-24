"""Gem: สร้าง Item Bank ด้วย LLM ปลอม (ไม่เรียก Provider จริง) แล้วตรวจว่า engine และหน้านักเรียนใช้ได้"""

import asyncio
import json

from fastapi.testclient import TestClient

from app import db, services
from app.api.deps import issue_token
from app.gems import builder, manage, verify
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
        if "ออกแบบโครงของบทเรียน" in user:
            payload = PLAN
        elif "ชุดที่ 1" in user:
            payload = ITEMS_A
        elif "ชุดที่ 2" in user:
            payload = ITEMS_B
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
    fake_llm(monkeypatch, resolve_wrong={0})
    gem = manage.create({"name": "ติวสมการ"}, "teacher")
    asyncio.run(builder.build(gem["id"]))
    first = manage.get(gem["id"])
    subject = db.get_subject(first["subject_id"])
    assert "LLM แก้ซ้ำ" in subject["items"][0]["flag"]["reasons"][0]

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
    assert build["steps"][0]["status"] == "error"
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
        if "โจทย์ทบทวนพื้นฐาน" in user and failing["extras"]:
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
