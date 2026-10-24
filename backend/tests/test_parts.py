"""ทดสอบชิ้นส่วนย่อย: ตรวจคำตอบ, Answer-Leak Guard, Distress, Fuzzy, K-Means, RAG และ Readiness Check"""

from app.content.readiness import check_set
from app.engine.answers import check_answer, match_bug, parse_number
from app.ml import fuzzy, kmeans
from app.tutor import distress, guard, pii, rag


def test_parse_numbers_thai_and_fraction():
    assert parse_number("๔") == 4
    assert parse_number("x = −2") == -2
    assert parse_number("7/2") * 2 == 7
    assert parse_number("abc") is None


def test_check_answer_formats(content):
    t01 = content.item("T-01")
    assert check_answer(t01, "4").correct
    assert not check_answer(t01, "x=5").correct
    assert not check_answer(t01, "ไม่รู้").valid
    t03 = content.item("T-03")
    assert check_answer(t03, t03["answer"]["option"]).correct
    e04 = content.item("E-04")
    assert check_answer(e04, "สมบัติ การเท่ากัน").correct


def test_bug_matching(content):
    t01 = content.item("T-01")
    assert match_bug(t01, parse_number("7")) == "M-SIGN"
    assert match_bug(t01, parse_number("5")) == "S-ARITH"
    assert match_bug(t01, parse_number("-4")) == "S-SIGNFLIP"


def test_guard_blocks_answer(content):
    t01 = content.item("T-01")
    assert guard.check("ดังนั้น x = 4", t01).blocked
    assert guard.check("คำตอบคือ ๔ นะ", t01).blocked
    assert not guard.check("ลองลบ 3 ทั้งสองข้างก่อน จะเหลือ 2x เท่ากับเท่าไร", t01).blocked
    assert guard.check("[TRIGGER_CIRCUIT_BREAKER]", t01).trigger


def test_authored_hints_do_not_leak(subject):
    for item in subject["items"]:
        for level, text in item["hints"].items():
            result = guard.check(text, item)
            assert not result.blocked, (item["id"], level, result)


def test_distress_detection():
    assert distress.detect("เครียดดดดมากเลย")["level"] == "stress"
    assert distress.detect("ไม่อยากเรียนแล้ว")["level"] == "quit"
    assert distress.detect("อยากตาย")["level"] == "self_harm"
    assert distress.detect("ปวดท้องนิดหน่อย")["level"] is None


def test_pii_scrub():
    text, found = pii.scrub("ผมชื่อภูมิ ใจดี เบอร์ 081-234-5678", ["ภูมิ ใจดี"])
    assert "ภูมิ" not in text and "081" not in text
    assert found


def test_fuzzy_impasse_rising_vs_flat():
    assert fuzzy.impasse([20, 35, 55], 45)["output"] >= 55
    assert fuzzy.impasse([20, 20, 20], 45)["output"] < 55


def test_fuzzy_difficulty_monotonic():
    easy = fuzzy.difficulty(0.2, 1.5)["output"]
    hard = fuzzy.difficulty(0.95, 0.4)["output"]
    assert hard > easy


def test_kmeans_finds_four_named_groups():
    rows = []
    groups = {"fast": (10, 0.9, 25), "struggling": (60, 0.4, 25), "guesser": (4, 0.35, 18), "bite": (22, 0.7, 5)}
    for name, (rt, acc, session) in groups.items():
        for i in range(6):
            rows.append({"code": f"{name}{i}", "avg_rt": rt + i, "accuracy": acc + i * 0.01, "session_min": session + i * 0.3})
    model = kmeans.cluster_students(rows)
    by_code = {p["code"]: p["cluster"] for p in model["points"]}
    for name in groups:
        assert by_code[f"{name}0"] == name


def test_bm25_thai_search():
    index = rag.BM25Index([
        {"doc_id": 1, "filename": "a", "text": "สมบัติการเท่ากัน ลบจำนวนเดียวกันทั้งสองข้าง"},
        {"doc_id": 1, "filename": "a", "text": "จำนวนเต็มลบบนเส้นจำนวน"},
    ])
    _, results = index.search("ย้ายข้างสมการต้องใช้สมบัติการเท่ากัน")
    assert results and "สมบัติการเท่ากัน" in results[0]["text"]


def test_sample_set_is_ready(subject):
    report = check_set(subject, "QS-1")
    assert report["ok"], report


def test_spa_route_cannot_read_outside_dist(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    (tmp_path / "secret.txt").write_text("API-KEY")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    client = TestClient(main.app)
    for path in ("/..%2Fsecret.txt", "/%2E%2E/secret.txt"):
        response = client.get(path)
        assert "API-KEY" not in response.text
    assert client.get("/student").text == "<html>app</html>"


def test_pdf_rebuilds_paragraphs_and_thai_words():
    from pathlib import Path

    data = (Path(__file__).parent / "fixtures" / "lesson-th.pdf").read_bytes()
    text, warning = rag.extract_text("lesson-th.pdf", data)
    assert warning is None
    assert "สมการยังคงเป็นจริง" in text  # คำที่ PDF ตัดกลางบรรทัดถูกต่อกลับ
    chunks = rag.chunk_text(text)
    assert len(chunks) >= 3 and max(len(c) for c in chunks) <= 600
    index = rag.BM25Index([{"doc_id": 1, "filename": "lesson-th.pdf", "text": c} for c in chunks])
    _, results = index.search("ลบด้วยจำนวนลบ", 1)
    assert "จำนวนลบ" in results[0]["text"]


def test_pdf_cleanup_and_bad_files():
    assert rag.clean_pdf_text("นํา") == "นำ"  # สระอำที่แยกเป็นสองอักขระ
    text, warning = rag.extract_text("broken.pdf", b"%PDF-1.4 garbage")
    assert text == "" and "PDF" in warning
