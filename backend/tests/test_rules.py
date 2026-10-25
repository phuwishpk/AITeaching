"""ทดสอบหน้า "กฎทั้งหมด": ข้อความเติมค่าได้ครบ อ้างถึงสิ่งที่มีอยู่จริง และครอบคลุมพารามิเตอร์ทุกตัว"""

import re

from fastapi.testclient import TestClient

from app import demo, rules, settings_store
from app.api.deps import issue_token
from app.config import DEFAULT_PARAMS
from app.engine import flow as F
from app.main import app


def test_rules_render_and_reference_real_things():
    data = rules.build()
    node_ids = {n["id"] for n in F.NODES}
    ids = [r["id"] for g in data["groups"] for r in g["rules"]]
    assert len(ids) == len(set(ids)) == data["total"]
    for group in data["groups"]:
        for rule in group["rules"]:
            assert "{" not in rule["when"] + rule["then"], rule["id"]
            if rule.get("node"):
                assert rule["node"] in node_ids, rule["id"]
            if rule.get("test"):
                assert rule["test"] in demo.STRESS_TESTS, rule["id"]


def test_every_parameter_has_a_rule():
    used = {key for g in rules.GROUPS for r in g["rules"] for key in r.get("params", [])}
    written = {key for g in rules.GROUPS for r in g["rules"] for key in re.findall(r"\{(\w+)", r["when"] + r["then"])}
    assert set(DEFAULT_PARAMS) <= used
    assert written & set(DEFAULT_PARAMS) <= used


def test_rule_text_follows_current_settings():
    settings_store.save_params({"deliberate_delay": 20})
    rule = next(r for g in rules.build()["groups"] for r in g["rules"] if r["id"] == "R-22")
    assert "20 วินาที" in rule["then"]
    param = rule["params"][0]
    assert param["value"] == 20 and param["default"] == 15 and param["changed"]


def test_staff_enter_without_pin_but_roles_stay_separate():
    client = TestClient(app)
    teacher = client.post("/api/auth/staff", json={"role": "teacher"}).json()["token"]
    admin = client.post("/api/auth/staff", json={"role": "admin"}).json()["token"]
    assert client.post("/api/auth/staff", json={"role": "student"}).status_code == 400
    assert client.get("/api/admin/flow", headers={"Authorization": f"Bearer {admin}"}).status_code == 200
    assert client.get("/api/admin/flow", headers={"Authorization": f"Bearer {teacher}"}).status_code in (401, 403)


def test_rules_endpoint_is_staff_only():
    client = TestClient(app)
    student = issue_token("student", "S-01")
    teacher = issue_token("teacher")
    assert client.get("/api/rules", headers={"Authorization": f"Bearer {student}"}).status_code == 403
    response = client.get("/api/rules", headers={"Authorization": f"Bearer {teacher}"})
    assert response.status_code == 200 and response.json()["total"] >= 40


def test_activity_links_input_to_flow_path(content):
    from app import activity, db, services
    from app.engine import core as engine
    from app.engine.core import Ctx

    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-09', 'real', NULL, 0)")
    state = engine.new_state("S-09", content.subject["id"], "QS-1", 1, 1000.0)
    ctx = Ctx(content, settings_store.params(), 1.0, 1000.0)
    services.persist(state, engine.begin(state, ctx), 1000.0)
    ctx.now = 1020.0
    services.persist(state, engine.submit(state, ctx, "7"), 1020.0)

    latest = activity.events("S-09")[0]
    assert latest["source"] == "student"
    assert latest["inputs"][0]["action"] == "answer"
    path = latest["decisions"][0]["path"]
    assert path[:4] == ["ANSWERING", "E_SUBMIT", "G_CLEAN", "G1"] and path[-1] == "DELIBERATE_DELAY"
    assert [r["id"] for r in latest["rules"]] == ["R-08", "R-21", "R-22"]

    ctx.now = 1021.0
    services.persist(state, engine.submit(state, ctx, "abc"), 1021.0)
    rejected = activity.events("S-09")[0]
    assert rejected["steps"][-1].startswith("ตีกลับ") and rejected["rules"][0]["id"] == "R-02"


def test_journey_numbers_one_session_from_start(content):
    from app import activity, db, services
    from app.engine import core as engine
    from app.engine.core import Ctx

    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-10', 'real', NULL, 0)")
    first = services.new_session("S-10", "QS-1", 1000.0)
    state = engine.new_state("S-10", content.subject["id"], "QS-1", first, 1000.0)
    ctx = Ctx(content, settings_store.params(), 1.0, 1000.0)
    services.persist(state, engine.begin(state, ctx), 1000.0)
    ctx.now = 1020.0
    services.persist(state, engine.submit(state, ctx, "7"), 1020.0)

    trip = activity.journey("S-10")
    assert [s["n"] for s in trip["steps"]] == [1, 2]
    assert trip["steps"][0]["milestone"] == "start" and trip["steps"][0]["source"] == "student"
    assert trip["steps"][1]["position"] == "DELIBERATE_DELAY"
    assert trip["summary"]["answers"] == 1 and trip["summary"]["correct"] == 0
    assert not trip["summary"]["finished"]

    # เริ่มชุดใหม่: Session เดิมจบช่วงเวลาที่ Session ใหม่เริ่ม และเลือกดูย้อนหลังได้
    second = services.new_session("S-10", "QS-1", 2000.0)
    state = engine.new_state("S-10", content.subject["id"], "QS-1", second, 2000.0)
    ctx.now = 2000.0
    services.persist(state, engine.begin(state, ctx), 2000.0)
    assert [r["id"] for r in activity.journey("S-10")["runs"]] == [second, first]
    assert len(activity.journey("S-10")["steps"]) == 1
    assert len(activity.journey("S-10", first)["steps"]) == 2

    client = TestClient(app)
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    assert client.get("/api/admin/students/S-10/journey", headers=admin).json()["run"]["id"] == second
    assert activity.journey("NOBODY")["steps"] == []


def test_rule_edges_exist():
    edge_ids = {e["id"] for e in F.EDGES}
    for rule_id, edges in rules.RULE_EDGES.items():
        assert rule_id in {r["id"] for g in rules.GROUPS for r in g["rules"]}
        assert set(edges) <= edge_ids, rule_id


def test_every_flow_box_explains_itself():
    from app import node_info

    for node in F.NODES:
        info = node_info.describe(node["id"], [])
        assert info["card"] and info["uses"], node["id"]
    on_boxes = {key for info in node_info.NODE_INFO.values() for key in info["params"]}
    assert set(DEFAULT_PARAMS) <= on_boxes  # ทุกค่าปรับได้จากกล่องใดกล่องหนึ่ง
    assert set(node_info.PARAM_GUIDE) == set(DEFAULT_PARAMS)
    for key, value in DEFAULT_PARAMS.items():
        low, high, _ = node_info.PARAM_GUIDE[key]["range"]
        assert low <= value <= high, key


def test_param_validation():
    from app import node_info

    assert node_info.validate_params({"deliberate_delay": 20}) == []
    assert node_info.validate_params({"deliberate_delay": 999})
    assert node_info.validate_params({"standard_mastery": 0.9, "fast_track_mastery": 0.8})


def test_only_teachers_author_content(subject):
    """ครูสร้างและแก้เนื้อหา Admin ดู Gem ได้อย่างเดียว (ADR-0003) และไม่เห็น Roster"""
    from app import db

    db.save_subject(subject)
    client = TestClient(app)
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    new = {**subject, "id": "math-x", "name": "วิชาทดลอง", "question_sets": []}
    assert client.post("/api/teacher/subjects", json=new, headers=admin).status_code == 403
    assert client.post("/api/teacher/subjects", json=new, headers=teacher).status_code == 200
    assert client.get("/api/teacher/subjects/math-x", headers=teacher).json()["name"] == "วิชาทดลอง"
    assert client.get("/api/teacher/roster", headers=admin).status_code == 403


def test_answer_sheet_shows_question_and_answer(content):
    from app import db, services
    from app.engine import core as engine
    from app.engine.core import Ctx

    db.save_subject(content.subject)
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-08', 'real', NULL, 0)")
    state = engine.new_state("S-08", content.subject["id"], "QS-1", 1, 1000.0)
    ctx = Ctx(content, settings_store.params(), 1.0, 1000.0)
    services.persist(state, engine.begin(state, ctx), 1000.0)
    ctx.now = 1020.0
    services.persist(state, engine.submit(state, ctx, "7"), 1020.0)

    sheet = services.answer_sheet("S-08")
    assert sheet["current"]["math"] == "2x + 3 = 11" and sheet["current"]["correct"] == "4"
    first = sheet["answers"][0]
    assert first["raw"] == "7" and first["correct"] is False and first["item"]["id"] == "T-01"
    assert first["diagnosis"]["class"] == "misconception"


def test_every_box_and_lane_has_a_walkthrough():
    from app import flow_guide, node_info

    for node in F.NODES:
        info = node_info.describe(node["id"], [])
        assert len(info["steps"]) >= 3 and info["example"], node["id"]
        assert all("{" not in text for text in [*info["steps"], info["example"]]), node["id"]
        assert info["outgoing"] or node["id"] in ("COMPLETED", "SESSION_ENDED"), node["id"]
    # ทุกกล่องอยู่ในลำดับของกลุ่มตัวเองพอดีหนึ่งครั้ง
    listed = [node_id for lane in flow_guide.LANES.values() for node_id in lane["order"]]
    assert sorted(listed) == sorted(n["id"] for n in F.NODES)
    for node in F.NODES:
        assert node["id"] in flow_guide.LANES[node["lane"]]["order"], node["id"]
    for lane_id in flow_guide.LANES:
        lane = node_info.describe_lane(lane_id, [])
        assert lane["entries"] or lane_id == "main", lane_id
        assert "{" not in lane["summary"] + lane["example"] + "".join(lane["enter"] + lane["exit"])
    assert node_info.describe_lane("nope", []) is None


def test_lane_endpoint_is_admin_only():
    client = TestClient(app)
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    assert client.get("/api/admin/flow/lanes/wrong", headers=admin).json()["nodes"][0]["id"] == "G_ISOCHK"
    assert client.get("/api/admin/flow/lanes/nope", headers=admin).status_code == 404
    assert client.get("/api/admin/flow/lanes/wrong", headers=teacher).status_code in (401, 403)


def test_end_boxes_explain_the_difference():
    from app import node_info

    for node_id in ("COMPLETED", "SESSION_ENDED"):
        compare = node_info.describe(node_id, [])["compare"]
        assert compare["columns"] == ["จบชุด", "จบ Session"]
        assert all("{" not in cell for row in compare["rows"] for cell in row)
    assert node_info.describe("G1", [])["compare"] is None


def test_teacher_and_student_exchange_messages(content):
    from app import db, services
    from app.engine import core as engine
    from app.engine import flow as Flow
    from app.engine.core import Ctx

    db.save_subject(content.subject)
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-07', 'real', NULL, 0)")
    state = engine.new_state("S-07", content.subject["id"], "QS-1", 1, 1000.0)
    state["position"] = Flow.SAFETY  # ระบบหยุดรอครู
    db.save_state(state)
    client = TestClient(app)
    student = {"Authorization": f"Bearer {issue_token('student', 'S-07')}"}
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}

    reply = client.post("/api/student/sets/QS-1/chat", json={"message": "ครูครับ ผมโอเคแล้ว"}, headers=student).json()
    assert reply["to_teacher"] and reply["reply"] is None  # ตอนหยุดรอครู AI ไม่ตอบ ข้อความไปถึงครูโดยตรง

    sent = client.post("/api/teacher/students/S-07/messages", json={"text": "ครูกำลังไปหานะ"}, headers=teacher)
    assert sent.status_code == 200 and sent.json()["sender"] == "teacher"

    thread = client.get("/api/student/sets/QS-1/messages", headers=student).json()["messages"]
    assert [m["sender"] for m in thread] == ["student", "teacher"]
    assert client.get("/api/teacher/students/S-07/messages", headers=student).status_code == 403



def test_teacher_joins_chat_and_reviews_ai_draft(content):
    from app import db, services
    from app.engine import core as engine
    from app.engine.core import Ctx

    db.save_subject(content.subject)
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-10', 'real', NULL, 0)")
    state = engine.new_state("S-10", content.subject["id"], "QS-1", 1, 1000.0)
    services.persist(state, engine.begin(state, Ctx(content, settings_store.params(), 1.0, 1000.0)), 1000.0)
    client = TestClient(app)
    student = {"Authorization": f"Bearer {issue_token('student', 'S-10')}"}
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}

    assert client.post("/api/teacher/students/S-10/chat-mode", json={"mode": "teacher"}, headers=teacher).json()["mode"] == "teacher"
    reply = client.post("/api/student/sets/QS-1/chat", json={"message": "ทำไมต้องลบ 3"}, headers=student).json()
    assert reply["reply"] is None and reply["to_teacher"]  # AI ไม่ตอบเอง

    seen_by_teacher = client.get("/api/teacher/students/S-10/messages", headers=teacher).json()
    draft = next(m for m in seen_by_teacher["messages"] if m["sender"] == "draft")
    student_view = client.get("/api/student/sets/QS-1/messages", headers=student).json()
    assert all(m["sender"] != "draft" for m in student_view["messages"]) and student_view["mode"] == "teacher"

    sent = client.post(f"/api/teacher/drafts/{draft['draft_id']}/send", json={"text": "ลองนึกถึงตาชั่งดูนะ"}, headers=teacher).json()
    assert sent["sender"] == "teacher" and sent["text"] == "ลองนึกถึงตาชั่งดูนะ"
    senders = [m["sender"] for m in client.get("/api/student/sets/QS-1/messages", headers=student).json()["messages"]]
    assert senders[-2:] == ["student", "teacher"] and "draft" not in senders
    assert client.get("/api/teacher/inbox", headers=teacher).json()[0]["code"] == "S-10"


def test_teacher_sees_full_ai_chat_history_with_hints(content):
    """ครูเห็นประวัติที่นักเรียนคุยกับ AI ย้อนหลังได้ทีละหน้า พร้อมคำใบ้ที่ AI ให้ และชื่อชุดคำถาม"""
    from app import db, services

    db.save_subject(content.subject)
    db.execute("INSERT INTO students (code, kind, persona, created_at) VALUES ('S-11', 'real', NULL, 0)")
    for i in range(70):
        sender = "student" if i % 2 == 0 else "tutor"
        db.execute("INSERT INTO messages (ts, code, set_id, sender, text) VALUES (?, 'S-11', 'QS-1', ?, ?)",
                   (1000 + i, sender, f"ข้อความ {i}"))
    db.execute("INSERT INTO ai_logs (ts, code, purpose, provider, final_text) VALUES (1010.5, 'S-11', 'hint_l2', 'gemini', 'ลองใช้สมบัติการเท่ากัน')")
    teacher = {"Authorization": f"Bearer {issue_token('teacher')}"}
    client = TestClient(app)
    latest = client.get("/api/teacher/students/S-11/messages", headers=teacher).json()
    assert latest["has_more"] and len(latest["messages"]) == 60 and latest["messages"][-1]["text"] == "ข้อความ 69"
    assert latest["messages"][-1]["sender"] == "tutor" and latest["messages"][-1]["set_name"] == "ชุดที่ 1 แก้สมการสองขั้น"
    older = client.get(f"/api/teacher/students/S-11/messages?before={latest['messages'][0]['ts']}", headers=teacher).json()
    assert not older["has_more"]
    hint = next(m for m in older["messages"] + latest["messages"] if m["sender"] == "hint")
    assert hint["level"] == 2 and hint["text"] == "ลองใช้สมบัติการเท่ากัน"
    texts = [m["text"] for m in older["messages"] + latest["messages"] if m["sender"] != "hint"]
    assert texts == [f"ข้อความ {i}" for i in range(70)]  # ไม่ซ้ำ ไม่หาย เรียงตามเวลา
    plain = client.get("/api/teacher/students/S-11/messages?hints=false", headers=teacher).json()
    assert all(m["sender"] != "hint" for m in plain["messages"])
