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
