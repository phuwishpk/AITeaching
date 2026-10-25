"""ทดสอบ Flow ที่ AI ออกแบบจากคำสั่งของครูใน Gem (ADR-0004) ด้วยนาฬิกาจำลอง"""

import copy

from app import demo, settings_store
from app.engine import core as engine
from app.engine import flow as F
from app.engine.core import Content, Ctx
from app.gems import flowspec


def gem_content(subject, raw_flow, tools=None):
    checked = flowspec.validate(raw_flow, tools or {})
    assert not checked["errors"], checked["errors"]
    subject = copy.deepcopy(subject)
    subject["gem"] = {"id": "gem-test", "name": "ทดสอบ", "tools": tools or {}, "live_cap": 0,
                      "flow": flowspec.record(checked["spec"], "ai", checked["warnings"], False)}
    return Content(subject, "QS-1")


def start(content, t=1000.0):
    state = engine.new_state("T", content.subject["id"], "QS-1", 1, t)
    ctx = Ctx(content, settings_store.params(), 1.0, t)
    engine.begin(state, ctx)
    return state, ctx


def at(ctx, t):
    ctx.now = t
    return ctx


def it_of(content, state):
    return content.item(state["item"]["id"])


def step(state):
    return state["flow"]["step"]


def test_template_runs_hint_ladder_then_isomorphic_test(subject):
    content = gem_content(subject, flowspec.standard_template())
    state, ctx = start(content)
    assert step(state) == "practice" and state["position"] == F.ANSWERING
    first = state["item"]["id"]
    fx = engine.submit(state, at(ctx, 1020), demo.other_wrong(it_of(content, state)))
    assert state["position"] == F.DELAY and step(state) == "hint1"
    assert fx.decisions[-1]["detail"]["step"] == "hint1"
    assert any(e.startswith("f") for e in fx.decisions[-1]["edges"])
    fx = engine.Fx()
    engine.resolve_timers(state, at(ctx, 1036), fx)
    # คำใบ้ "auto" ใช้ Hint Floor จาก Bug Library เหมือน Standard Flow (Misconception เริ่มที่ L2)
    floor = max(1, state["item"]["hint_floor"])
    assert state["position"] == F.HINT_POSITIONS[floor] and step(state) == "practice"
    assert state["item"]["id"] == first, "กลับขั้นเดิมขณะที่ยังไม่ถูก ต้องทำข้อเดิมต่อ"
    engine.submit(state, at(ctx, 1060), demo.other_wrong(it_of(content, state), 1))
    assert state["position"] == F.HINT_L2
    engine.submit(state, at(ctx, 1090), demo.correct_raw(it_of(content, state)))
    assert step(state) == "iso" and state["position"] == F.ISO
    assert state["item"]["iso_source"] == first
    view = engine.student_view(state, ctx)
    assert view["hint_button"]["visible"] is False
    engine.submit(state, at(ctx, 1120), demo.correct_raw(it_of(content, state)))
    assert step(state) == "practice" and state["item"]["id"] != first


def test_teacher_prompt_flow_with_new_steps(subject):
    """คำสั่งของครู: ทุกข้อที่ถูกให้อธิบายวิธีคิด ผิดสองครั้งให้อ่านบทเรียนย่อ ถูกครบ 2 ข้อจบ"""
    flow = {
        "start": "work",
        "params": {"rapid_guess_lock": 200, "max_items": 12},
        "steps": [
            {"id": "work", "kind": "item", "label": "ทำโจทย์", "pick": "main"},
            {"id": "why", "kind": "reflect", "label": "อธิบายวิธีคิด", "question": "ทำไมจึงได้คำตอบนี้",
             "judge": True, "rubric": "บอกขั้นตอนการย้ายข้าง"},
            {"id": "read", "kind": "lesson", "label": "ทบทวนหลัก", "text": "ย้ายข้างแล้วเปลี่ยนเครื่องหมาย"},
            {"id": "tell", "kind": "notify", "label": "บอกครู", "text": "อธิบายไม่ผ่าน", "level": "silent"},
            {"id": "end", "kind": "end", "label": "จบ", "result": "completed"},
        ],
        "edges": [
            {"from": "work", "to": "why", "when": "correct"},
            {"from": "work", "to": "read", "when": "wrong and error_count >= 2"},
            {"from": "work", "to": "work", "when": ""},
            {"from": "why", "to": "end", "when": "judge_pass and items_done >= 2"},
            {"from": "why", "to": "work", "when": "judge_pass"},
            {"from": "why", "to": "tell", "when": ""},
            {"from": "tell", "to": "work", "when": ""},
            {"from": "read", "to": "work", "when": ""},
        ],
    }
    content = gem_content(subject, flow)
    state, ctx = start(content)
    assert ctx.p("rapid_guess_lock") == 60, "ตัวเลขจาก prompt ถูกตัดให้อยู่ในช่วงที่ปลอดภัย"
    assert ctx.p("max_items") == 12
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it_of(content, state)))
    assert state["position"] == F.ANSWERING and state["item"]["error_count"] == 1
    engine.submit(state, at(ctx, 1040), demo.other_wrong(it_of(content, state), 1))
    assert state["position"] == F.LESSON
    assert engine.student_view(state, ctx)["lesson"]["text"].startswith("ย้ายข้าง")
    engine.walkthrough_done(state, at(ctx, 1060))
    assert state["position"] == F.ANSWERING and state["item"]["error_count"] == 2
    engine.submit(state, at(ctx, 1080), demo.correct_raw(it_of(content, state)))
    assert state["position"] == F.REFLECT
    fx = engine.reflect(state, at(ctx, 1100), "ไม่รู้", {"pass": False, "score": 20})
    assert step(state) == "work" and any(a["kind"] == "flow_notify" for a in fx.alerts)
    engine.submit(state, at(ctx, 1130), demo.correct_raw(it_of(content, state)))
    engine.reflect(state, at(ctx, 1150), "ย้าย 3 ไปลบ", {"pass": True, "score": 90})
    assert state["position"] == F.DONE and state["end_reason"] == "completed"


def test_locked_invariants_still_apply(subject):
    loose = {
        "start": "w",
        "steps": [{"id": "w", "kind": "item"}, {"id": "e", "kind": "end"}],
        "edges": [{"from": "w", "to": "e", "when": "correct and items_done >= 99"}, {"from": "w", "to": "w", "when": ""}],
    }
    content = gem_content(subject, loose)
    state, ctx = start(content)
    # Rapid Guess: ผิดเร็วเกินเวลาอ่าน ล็อกปุ่มตอบ คะแนนเป็นโมฆะ
    engine.submit(state, at(ctx, 1001), demo.other_wrong(it_of(content, state)))
    assert state["position"] == F.LOCK and state["item"]["voided"]
    fx = engine.Fx()
    engine.resolve_timers(state, at(ctx, 1030), fx)
    assert state["position"] == F.ANSWERING
    # ผิดข้อเดียวกันครบเพดาน ส่งต่อครู แม้ Flow ไม่มีทางออกให้
    t = 1030
    for k in range(6):
        t += 20
        fx = engine.submit(state, at(ctx, t), demo.other_wrong(it_of(content, state), k))
    assert state["position"] == F.DEADLOCK and any(a["kind"] == "deadlock" for a in fx.alerts)
    engine.override(state, at(ctx, t + 5), "release", {})
    assert state["position"] == F.ANSWERING and state["item"]["error_count"] == 0
    # เพดานจำนวนข้อ
    for _ in range(40):
        if state["ended"]:
            break
        t += 20
        engine.submit(state, at(ctx, t), demo.correct_raw(it_of(content, state)))
    assert state["end_reason"] in ("cap", "no_items")
    # ข้อความทำร้ายตนเองหยุดทันที
    state2, ctx2 = start(content)
    engine.on_distress(state2, at(ctx2, 1010), "self_harm")
    assert state2["position"] == F.SAFETY


def test_teacher_wait_step_resumes_on_release(subject):
    flow = {
        "start": "w",
        "steps": [{"id": "w", "kind": "item"}, {"id": "ask", "kind": "teacher", "text": "ผิดสองครั้งให้ครูดู"},
                  {"id": "e", "kind": "end"}],
        "edges": [{"from": "w", "to": "ask", "when": "wrong and error_count >= 2"},
                  {"from": "w", "to": "e", "when": "correct"}, {"from": "w", "to": "w", "when": ""},
                  {"from": "ask", "to": "w", "when": ""}],
    }
    content = gem_content(subject, flow)
    state, ctx = start(content)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it_of(content, state)))
    fx = engine.submit(state, at(ctx, 1040), demo.other_wrong(it_of(content, state), 1))
    assert state["position"] == F.DEADLOCK and any(a["kind"] == "flow_teacher" for a in fx.alerts)
    assert engine.staff_view(state, ctx)["map_node"] == "ask"
    engine.override(state, at(ctx, 1100), "release", {})
    assert state["position"] in F.ANSWER_POSITIONS and step(state) == "w"


def test_validator_rejects_unsafe_flows():
    stuck = {"start": "w", "steps": [{"id": "w", "kind": "item"}, {"id": "h", "kind": "hint"}],
             "edges": [{"from": "w", "to": "h", "when": "wrong"}]}
    errors = flowspec.validate(stuck)["errors"]
    assert any("ไม่มีเส้นออก" in e for e in errors)
    loop = {"start": "w", "steps": [{"id": "w", "kind": "item"}, {"id": "a", "kind": "check"}, {"id": "b", "kind": "notify"},
                                    {"id": "e", "kind": "end"}],
            "edges": [{"from": "w", "to": "a", "when": "wrong"}, {"from": "w", "to": "e", "when": ""},
                      {"from": "a", "to": "b", "when": ""}, {"from": "b", "to": "a", "when": ""}]}
    assert any("วนผ่าน" in e for e in flowspec.validate(loop)["errors"])
    sneaky = {"start": "w", "steps": [{"id": "w", "kind": "item"}, {"id": "e", "kind": "end"}],
              "edges": [{"from": "w", "to": "e", "when": "__import__('os')"}]}
    assert flowspec.validate(sneaky)["errors"]


def test_lesson_text_that_solves_a_bank_item_is_hidden(subject):
    item = next(it for it in subject["items"] if it["format"] == "numeric" and it.get("math"))
    text = f"ตัวอย่าง {item['math']} ทำทีละขั้นจะได้ x = {item['answer']['value']}"
    flow = {
        "start": "w",
        "steps": [{"id": "w", "kind": "item", "pick": "main"}, {"id": "read", "kind": "lesson", "text": text},
                  {"id": "e", "kind": "end"}],
        "edges": [{"from": "w", "to": "read", "when": "wrong"}, {"from": "w", "to": "e", "when": ""},
                  {"from": "read", "to": "w", "when": ""}],
    }
    spec = flowspec.validate(flow)["spec"]
    assert any(item["id"] in w for w in flowspec.leak_warnings(spec, subject["items"]))
    content = gem_content(subject, flow)
    state, ctx = start(content)
    fx = engine.submit(state, at(ctx, 1020), demo.other_wrong(it_of(content, state)))
    assert state["position"] == F.LESSON
    assert "Answer-Leak Guard" in fx.decisions[-1]["rule"]
    shown = engine.student_view(state, ctx)["lesson"]["text"]
    assert str(item["answer"]["value"]) not in shown or item["math"] not in shown


def test_hint_button_unlocks_one_level_per_attempt_in_gem_flows(subject):
    flow = {"start": "w", "steps": [{"id": "w", "kind": "item", "pick": "main", "hint_button": True}, {"id": "e", "kind": "end"}],
            "edges": [{"from": "w", "to": "e", "when": "correct"}, {"from": "w", "to": "w", "when": ""}]}
    content = gem_content(subject, flow)
    state, ctx = start(content)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it_of(content, state)))
    assert engine.request_hint(state, at(ctx, 1025)).result["kind"] == "hint"
    assert state["item"]["hint_level"] == 1
    assert engine.request_hint(state, at(ctx, 1040)).result["kind"] == "socratic", "ต้องลองตอบอีกครั้งก่อนปลดระดับถัดไป"
    engine.submit(state, at(ctx, 1060), demo.other_wrong(it_of(content, state), 1))
    engine.request_hint(state, at(ctx, 1065))
    assert state["item"]["hint_level"] == 2


def test_walkthrough_that_solves_an_unsolved_item_is_hidden(subject):
    subject = copy.deepcopy(subject)
    target = next(it for it in subject["items"] if it["kind"] == "main" and it["format"] == "numeric" and it.get("math"))
    concept = subject["question_sets"][0]["target_concept"]
    subject["walkthroughs"] = [{"concept": concept, "title": "ตัวอย่าง", "problem": target["math"],
                                "steps": [f"ทำทีละขั้นได้ x = {target['answer']['value']}"]}]
    flow = {"start": "w",
            "steps": [{"id": "w", "kind": "item", "pick": "main"}, {"id": "read", "kind": "lesson", "text": "ทบทวน", "walkthrough": True},
                      {"id": "e", "kind": "end"}],
            "edges": [{"from": "w", "to": "read", "when": "wrong"}, {"from": "w", "to": "e", "when": ""}, {"from": "read", "to": "w", "when": ""}]}
    content = gem_content(subject, flow)
    state, ctx = start(content)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it_of(content, state)))
    assert state["position"] == F.LESSON
    assert engine.student_view(state, ctx)["lesson"]["walkthrough"] is None
    state["done_items"].append(target["id"])
    assert engine.student_view(state, ctx)["lesson"]["walkthrough"] is not None, "ทำข้อนั้นถูกแล้ว แสดงตัวอย่างได้"


def test_flow_branches_on_bug_codes_and_runs_ai_activities(subject):
    from app.engine import gemflow

    item = next(it for it in subject["items"] if it["kind"] == "main" and it.get("bugs"))
    bug = item["bugs"][0]
    flow = {
        "start": "w",
        "steps": [{"id": "w", "kind": "item", "pick": "main"},
                  {"id": "trap", "kind": "hint", "level": 3},
                  {"id": "sort", "kind": "activity", "title": "เรียงขั้นตอน", "goal": "ให้นักเรียนเรียงขั้นตอนการแก้โจทย์แบบนี้",
                   "response": "text", "rubric": "เรียงขั้นถูก"},
                  {"id": "e", "kind": "end"}],
        "edges": [{"from": "w", "to": "trap", "when": f'wrong and bug == "{bug["tag"]}"'},
                  {"from": "w", "to": "sort", "when": "wrong"},
                  {"from": "w", "to": "e", "when": ""},
                  {"from": "trap", "to": "w", "when": ""},
                  {"from": "sort", "to": "e", "when": "judge_pass"},
                  {"from": "sort", "to": "w", "when": ""}],
    }
    content = gem_content(subject, flow)
    state, ctx = start(content)
    engine.serve(state, ctx, item, "main")
    state["flow"]["item_step"] = "w"
    engine.submit(state, at(ctx, 1030), str(bug["answer"]))
    assert state["item"]["hint_level"] == 3, "คำตอบผิดตรงรหัสในตาราง ไปเส้นของรหัสนั้น"
    fx = engine.submit(state, at(ctx, 1060), demo.other_wrong(content.item(item["id"]), 3))
    assert state["position"] == F.ACTIVITY and fx.activity == {"step": "sort"}
    assert engine.student_view(state, ctx)["activity"]["status"] == "pending"
    assert gemflow.set_activity(state, "sort", "เรียงขั้นตอนต่อไปนี้", "ขั้นไหนมาก่อน")
    view = engine.student_view(state, ctx)["activity"]
    assert view["text"] == "เรียงขั้นตอนต่อไปนี้" and view["response"] == "text"
    engine.reflect(state, at(ctx, 1100), "ลบก่อนแล้วหาร", {"pass": True, "score": 90})
    assert state["position"] == F.DONE


def test_designed_flow_must_map_every_guideline_to_a_step():
    flow = {
        "guidelines": [{"text": "Slip ให้คำใบ้ระดับ 1", "steps": ["hint_1"]}, {"text": "ทำครบแล้วจบ", "steps": ["missing"]}],
        "start": "work",
        "steps": [{"id": "work", "kind": "item", "pick": "main", "reason": "ทำโจทย์ทีละข้อ"},
                  {"id": "hint_1", "kind": "hint", "level": 1, "reason": "Slip ให้คำใบ้ระดับ 1"},
                  {"id": "end", "kind": "end"}],
        "edges": [{"from": "work", "to": "end", "when": "correct and mains_left == 0"},
                  {"from": "work", "to": "hint_1", "when": 'wrong and bug_type == "slip"'},
                  {"from": "work", "to": "work", "when": ""}, {"from": "hint_1", "to": "work", "when": ""}],
    }
    checked = flowspec.validate(flow)
    assert any("ทำครบแล้วจบ" in e for e in checked["errors"]), "แนวทางที่ไม่มีขั้นรองรับต้องส่งกลับให้ AI แก้"
    assert checked["spec"]["steps"][1]["reason"] == "Slip ให้คำใบ้ระดับ 1"
    flow["guidelines"][1]["steps"] = ["end"]
    assert not flowspec.validate(flow)["errors"]


def test_back_returns_to_the_item_step_the_student_came_from(subject):
    flow = {
        "start": "a",
        "steps": [{"id": "a", "kind": "item", "pick": "main"}, {"id": "b", "kind": "item", "pick": "main"},
                  {"id": "h", "kind": "hint", "level": 1}, {"id": "e", "kind": "end"}],
        "edges": [{"from": "a", "to": "b", "when": "correct"}, {"from": "a", "to": "h", "when": ""},
                  {"from": "b", "to": "e", "when": "correct"}, {"from": "b", "to": "h", "when": ""},
                  {"from": "h", "to": "back", "when": ""}],
    }
    checked = flowspec.validate(flow)
    assert not checked["errors"]
    assert any(e["target"] == "h" and e["source"] == "h" for e in flowspec.map_view(checked["spec"])["edges"])
    content = gem_content(subject, flow)
    state, ctx = start(content)
    engine.submit(state, at(ctx, 1020), demo.correct_raw(it_of(content, state)))
    assert step(state) == "b"
    second = state["item"]["id"]
    engine.submit(state, at(ctx, 1050), demo.other_wrong(it_of(content, state)))
    assert step(state) == "b" and state["item"]["id"] == second and state["item"]["hint_level"] >= 1
