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


def test_admin_can_author_content_but_not_see_roster(subject):
    from app import db

    db.save_subject(subject)
    client = TestClient(app)
    admin = {"Authorization": f"Bearer {issue_token('admin')}"}
    new = {**subject, "id": "math-x", "name": "วิชาทดลอง", "question_sets": []}
    assert client.post("/api/teacher/subjects", json=new, headers=admin).status_code == 200
    assert client.get("/api/teacher/subjects/math-x", headers=admin).json()["name"] == "วิชาทดลอง"
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


def test_end_boxes_explain_the_difference():
    from app import node_info

    for node_id in ("COMPLETED", "SESSION_ENDED"):
        compare = node_info.describe(node_id, [])["compare"]
        assert compare["columns"] == ["จบชุด", "จบ Session"]
        assert all("{" not in cell for row in compare["rows"] for cell in row)
    assert node_info.describe("G1", [])["compare"] is None
