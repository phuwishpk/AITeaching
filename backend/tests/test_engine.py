"""ทดสอบกฎ 3 ด่าน บันไดคำใบ้ Isomorphic Test และ Remedial Loop ด้วยนาฬิกาจำลอง"""

from app import demo
from app.engine import core as engine
from app.engine import flow as F
from app.engine.core import Fx


def at(ctx, t):
    ctx.now = t
    return ctx


def current(content, state):
    return content.item(state["item"]["id"])


def test_begin_serves_first_main_item(fresh):
    state, _ = fresh
    assert state["position"] == F.ANSWERING
    assert state["item"]["id"] == "T-01"


def test_correct_first_try_weight_one(fresh, content):
    state, ctx = fresh
    fx = engine.submit(state, at(ctx, 1010), demo.correct_raw(current(content, state)))
    assert fx.result["kind"] == "correct"
    assert state["mastery"]["C-TWO"][0]["w"] == 1.0


def test_rapid_guess_voids_without_error_count(fresh, content):
    state, ctx = fresh
    engine.submit(state, at(ctx, 1001), demo.other_wrong(current(content, state)))
    assert state["position"] == F.LOCK
    assert state["item"]["error_count"] == 0
    assert state["item"]["voided"]


def test_lock_releases_after_time(fresh, content):
    state, ctx = fresh
    engine.submit(state, at(ctx, 1001), demo.other_wrong(current(content, state)))
    fx = Fx()
    engine.resolve_timers(state, at(ctx, 1020), fx)
    assert state["position"] == F.ANSWERING


def test_hint_ladder_with_delay(fresh, content):
    state, ctx = fresh
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it, 0))
    assert state["position"] == F.DELAY
    fx = Fx()
    engine.resolve_timers(state, at(ctx, 1036), fx)
    assert state["position"] == F.HINT_L1
    engine.submit(state, at(ctx, 1060), demo.other_wrong(it, 1))
    assert state["position"] == F.HINT_L2
    engine.submit(state, at(ctx, 1080), demo.other_wrong(it, 2))
    assert state["position"] == F.HINT_L3  # เวลาคิดไม่ได้ยาวขึ้นต่อเนื่อง


def test_misconception_sets_floor_l2(fresh, content):
    state, ctx = fresh
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.bug_answer(it, "M-SIGN"))
    assert state["item"]["hint_floor"] == 2
    assert state["item"]["pending_hint"] == 2
    fx = Fx()
    engine.resolve_timers(state, at(ctx, 1040), fx)
    assert state["position"] == F.HINT_L2
    assert set(state["item"]["hints"]) == {"1", "2"}


def test_self_correction_during_delay_weight(fresh, content):
    state, ctx = fresh
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it))
    engine.submit(state, at(ctx, 1028), demo.correct_raw(it))
    assert state["mastery"]["C-TWO"][0]["w"] == 0.8


def wrong_three_times_rising(state, ctx, content):
    """เวลาคิด 20 → 35 → 55 วินาที (คำใบ้ขึ้นที่ t = 1035 หลังหน่วงเวลา)"""
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.bug_answer(it, "M-SIGN"))
    engine.submit(state, at(ctx, 1070), demo.other_wrong(it, 0))
    engine.submit(state, at(ctx, 1125), demo.other_wrong(it, 1))


def test_rising_time_on_third_error_is_impasse(fresh, content):
    state, ctx = fresh
    wrong_three_times_rising(state, ctx, content)
    assert state["position"] == F.REMEDIAL
    assert state["remedial"]["concept"] == "C-EQP"  # ผูกกับ Misconception ย้ายข้างไม่เปลี่ยนเครื่องหมาย


def test_remedial_pass_returns_to_item(fresh, content):
    state, ctx = fresh
    wrong_three_times_rising(state, ctx, content)
    t = 1125
    for _ in range(2):
        t += 15
        engine.submit(state, at(ctx, t), demo.correct_raw(current(content, state)))
    assert state["position"] == F.ANSWERING
    assert state["item"]["id"] == "T-01"
    assert state["item"]["error_count"] == 0


def test_hinted_pass_leads_to_isomorphic(fresh, content):
    state, ctx = fresh
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it))
    engine.resolve_timers(state, at(ctx, 1040), Fx())
    engine.submit(state, at(ctx, 1060), demo.correct_raw(it))
    assert state["position"] == F.ISO
    assert state["item"]["iso_source"] == "T-01"


def test_isomorphic_double_fail_falls_back(fresh, content):
    state, ctx = fresh
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it))
    engine.resolve_timers(state, at(ctx, 1040), Fx())
    engine.submit(state, at(ctx, 1060), demo.correct_raw(it))
    iso = current(content, state)
    engine.submit(state, at(ctx, 1080), demo.other_wrong(iso, 0))
    assert state["position"] == F.ISO
    engine.submit(state, at(ctx, 1100), demo.other_wrong(iso, 1))
    assert state["position"] == F.ANSWERING
    assert state["mastery"]["C-TWO"][-1]["w"] == 0.0  # ข้อที่ผ่านด้วยคำใบ้ได้น้ำหนัก 0


def test_hint_button_waits_then_abuse(fresh):
    state, ctx = fresh
    assert engine.request_hint(state, at(ctx, 1010)).result["kind"] == "wait"
    assert engine.request_hint(state, at(ctx, 1031)).result["kind"] == "hint"
    assert state["item"]["hint_level"] == 1
    engine.request_hint(state, at(ctx, 1032))
    assert engine.request_hint(state, at(ctx, 1033)).result["kind"] == "abuse"
    assert state["hint_abuse_index"] == 1


def test_isomorphic_hides_hint(fresh, content):
    state, ctx = fresh
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it))
    engine.resolve_timers(state, at(ctx, 1040), Fx())
    engine.submit(state, at(ctx, 1060), demo.correct_raw(it))
    assert engine.request_hint(state, at(ctx, 1100)).result["kind"] == "hidden"


def test_fast_track_and_finish(fresh, content):
    state, ctx = fresh
    t = 1000
    for _ in range(3):
        t += 8
        engine.submit(state, at(ctx, t), demo.correct_raw(current(content, state)))
        if state["position"] == F.DONE:
            break
    assert state["position"] == F.DONE
    assert state["challenge_correct"]


def test_distress_levels(fresh):
    state, ctx = fresh
    engine.on_distress(state, at(ctx, 1010), "self_harm")
    assert state["position"] == F.SAFETY


def test_undo_restores(fresh, content):
    state, ctx = fresh
    engine.submit(state, at(ctx, 1020), demo.other_wrong(current(content, state)))
    engine.undo(state, at(ctx, 1025))
    assert state["item"]["error_count"] == 0
    assert state["position"] == F.ANSWERING
    assert engine.undo(state, at(ctx, 1026)).result["kind"] == "blocked"


def test_teacher_release_from_deadlock(content):
    result = demo.test_deadlock(content)
    assert result["passed"], result


def test_all_stress_cases_pass(content):
    for case, fn in demo.STRESS_TESTS.items():
        result = fn(content)
        assert result["passed"], (case, result)


def test_student_view_has_no_answer_or_risk(fresh):
    state, ctx = fresh
    view = engine.student_view(state, ctx)
    text = str(view)
    assert "answer" not in view["item"]
    assert "risk" not in text
    assert "bugs" not in text


def test_high_risk_sends_silent_alert_only(fresh):
    state, ctx = fresh
    state.update(attempts_total=10, correct_total=1, rapid_total=6, idle_count=3, hint_abuse_index=3)
    position = state["position"]
    fx = Fx()
    engine.check_burnout_risk(state, ctx, fx)
    assert [a["kind"] for a in fx.alerts] == ["burnout_risk"]
    assert fx.alerts[0]["level"] == "silent"
    assert state["position"] == position


def test_student_view_counts_main_items(fresh, content):
    state, ctx = fresh
    engine.submit(state, at(ctx, 1010), demo.correct_raw(current(content, state)))
    progress = engine.student_view(state, ctx)["progress"]
    assert progress == {"main_done": 1, "main_total": 6, "max_items": 20}


# ---------------------------------------------------------------- Gem: เครื่องมือเริ่มต้น สร้างโจทย์สด AI ขัดข้อง

def gem_run(subject, tools=None, live_cap=10, mains=None):
    """เริ่มชุดคำถามตัวอย่างในฐานะ Gem ที่ครูตั้งเครื่องมือไว้"""
    from app import settings_store
    from app.engine.core import Content, Ctx

    subject = {**subject, "gem": {"id": "gem-x", "tools": tools or {}, "live_cap": live_cap}}
    if mains is not None:
        subject["question_sets"] = [{**subject["question_sets"][0], "main_items": mains, "challenge_items": []}]
    content = Content(subject, "QS-1")
    state = engine.new_state("G", subject["id"], "QS-1", 1, 1000.0)
    ctx = Ctx(content, settings_store.params(), 1.0, 1000.0)
    engine.begin(state, ctx)
    if mains is not None:
        # คลังหมดจริงเมื่อข้อคู่ขนานที่ใช้ฝึกเพิ่มก็หมดแล้วด้วย
        state["used_iso"] = [iso["id"] for m in mains for iso in content.isomorphs(m)]
    return state, ctx, content


def test_hints_off_means_retry_then_impasse(subject):
    state, ctx, content = gem_run(subject, {"hints": False})
    it = current(content, state)
    fx = engine.submit(state, at(ctx, 1020), demo.other_wrong(it))
    assert state["position"] == F.ANSWERING and "e_g3_nohint" in fx.decisions[-1]["edges"]
    assert engine.request_hint(state, at(ctx, 1030)).result["kind"] == "hidden"
    assert engine.student_view(state, ctx)["hint_button"]["visible"] is False
    engine.submit(state, at(ctx, 1050), demo.other_wrong(it, 0))
    engine.submit(state, at(ctx, 1080), demo.other_wrong(it, 1))
    assert state["position"] == F.REMEDIAL  # ผิดครบ 3 ครั้งเป็น Impasse


def test_isomorphic_off_skips_the_parallel_test(subject):
    state, ctx, content = gem_run(subject, {"isomorphic": False})
    it = current(content, state)
    engine.submit(state, at(ctx, 1020), demo.other_wrong(it))
    engine.resolve_timers(state, at(ctx, 1040), Fx())
    engine.submit(state, at(ctx, 1060), demo.correct_raw(it))
    assert state["position"] == F.ANSWERING and state["item"]["mode"] != "isomorphic"


def test_remedial_off_hands_impasse_to_teacher(subject):
    state, ctx, content = gem_run(subject, {"remedial": False})
    wrong_three_times_rising(state, ctx, content)
    assert state["position"] == F.DEADLOCK


def test_walkthrough_off_skips_example_after_break(subject):
    state, ctx, content = gem_run(subject, {"walkthrough": False})
    engine.on_distress(state, at(ctx, 1010), "stress")
    assert state["position"] == F.CB
    fx = Fx()
    engine.resolve_timers(state, at(ctx, 1200), fx)
    assert state["position"] == F.ANSWERING
    assert any("ครูปิด Walkthrough" in d["rule"] for d in fx.decisions)


def test_empty_bank_asks_ai_then_outage_then_retry(subject):
    state, ctx, content = gem_run(subject, mains=["T-01"])
    fx = engine.submit(state, at(ctx, 1020), demo.correct_raw(current(content, state)))
    assert state["position"] == F.LIVE and fx.generate and "e_path_live" in fx.decisions[-1]["edges"]

    fx = engine.after_live(state, at(ctx, 1030), [], "Gemini มีผู้ใช้มากชั่วคราว")
    assert state["position"] == F.OUTAGE and fx.alerts[0]["kind"] == "ai_outage"
    assert engine.student_view(state, ctx)["outage"]["error"] == "Gemini มีผู้ใช้มากชั่วคราว"

    fx = Fx()
    engine.resolve_timers(state, at(ctx, 1061), fx)  # ครบ 30 วินาที ลองใหม่เอง
    assert state["position"] == F.LIVE and fx.generate

    # ได้โจทย์ใหม่: เพิ่มเข้าคลังแล้วพากลับไปทำต่อ
    new = {**content.item("T-02"), "id": "L-01", "isomorphs": []}
    content.items["L-01"] = new
    content.qs["main_items"].append("L-01")
    engine.after_live(state, at(ctx, 1070), ["L-01"], None)
    assert state["position"] == F.ANSWERING and state["item"]["id"] == "L-01" and state["live_count"] == 1


def test_no_live_generation_outside_gems_or_past_the_cap(subject):
    state, ctx, content = gem_run(subject, mains=["T-01"], live_cap=0)
    engine.submit(state, at(ctx, 1020), demo.correct_raw(current(content, state)))
    assert state["position"] == F.ENDED
