import pytest

from app import db, settings_store
from app.content.sample_math_m2 import build_subject
from app.engine import core as engine
from app.engine.core import Content, Ctx


@pytest.fixture(autouse=True)
def memory_db(tmp_path, monkeypatch):
    db.use_memory_db()
    # เทสต์ต้องไม่เรียก AI Provider จริง: ไม่อ่าน key ในเครื่องและไม่อ่านจาก environment
    monkeypatch.setattr(settings_store, "SECRETS_PATH", tmp_path / "secrets.json")
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def subject():
    return build_subject()


@pytest.fixture
def content(subject):
    return Content(subject, "QS-1")


@pytest.fixture
def fresh(content):
    """state ใหม่ที่เริ่มชุดคำถามแล้ว พร้อมนาฬิกาจำลองที่ t = 1000"""
    state = engine.new_state("T", content.subject["id"], "QS-1", 1, 1000.0)
    ctx = Ctx(content, settings_store.params(), 1.0, 1000.0)
    engine.begin(state, ctx)
    return state, ctx
