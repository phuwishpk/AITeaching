"""ข้อมูลเริ่มต้นตอนเปิดระบบครั้งแรก: วิชาตัวอย่าง เอกสารวิชา นักเรียนตัวอย่าง และกลุ่มนักเรียนจำลอง"""

import time

from . import db, demo, services
from .gems import manage
from .tutor import rag

# ชื่อสมมติสำหรับสาธิต ใช้ได้เฉพาะฝั่งครูผ่าน Roster
DEMO_STUDENTS = [
    ("S-01", "ภูมิ ใจดี"),
    ("S-02", "ปลายฟ้า ศรีสุข"),
    ("S-03", "ธนภัทร มั่นคง"),
    ("S-04", "กานต์ธิดา แก้วใส"),
    ("S-05", "ณัฐวุฒิ ทองดี"),
    ("S-06", "พิมพ์ชนก รักเรียน"),
]


def add_document(subject_id: str, filename: str, text: str, warning: str | None = None, reader: str = "local") -> int:
    chunks = rag.chunk_text(text)
    cursor = db.execute(
        "INSERT INTO documents (subject_id, filename, kind, chars, chunks, warning, uploaded_at, reader) VALUES (?,?,?,?,?,?,?,?)",
        (subject_id, filename, filename.rsplit(".", 1)[-1].lower(), len(text), db.dumps(chunks), warning, time.time(), reader),
    )
    rebuild_index(subject_id)
    return cursor.lastrowid


def rebuild_index(subject_id: str):
    rows = db.query("SELECT id, filename, chunks FROM documents WHERE subject_id = ?", (subject_id,))
    rag.build_index(subject_id, [{"id": r["id"], "filename": r["filename"], "chunks": db.loads(r["chunks"], [])} for r in rows])


def ensure_seed():
    # ไม่มีวิชาตัวอย่างติดมากับระบบแล้ว บทเรียนทุกชุดเป็น Gem ที่ครูสร้าง (ADR-0003)
    # วิชาที่ยังไม่เป็น Gem (สร้างจากหน้าแก้เนื้อหาแบบเดิม) แปลงเป็น Gem ให้
    manage.adopt_legacy()
    for subject in db.list_subjects():
        rebuild_index(subject["id"])
    for gem in db.list_gems():
        rebuild_index(gem["id"])
    now = time.time()
    if not db.query_one("SELECT code FROM students WHERE kind = 'real'"):
        for code, name in DEMO_STUDENTS:
            db.execute("INSERT OR IGNORE INTO students (code, kind, persona, created_at) VALUES (?,?,?,?)",
                       (code, "real", None, now))
            db.execute("INSERT OR REPLACE INTO roster (code, name) VALUES (?, ?)", (code, name))
    ensure_cohort()


def ensure_cohort():
    """นักเรียนจำลองสำหรับ K-Means และสถิติห้อง สร้างเมื่อมี Gem ที่พร้อมสาธิตแล้ว"""
    if not db.query_one("SELECT code FROM students WHERE kind = 'sim'"):
        try:
            demo.seed_cohort()
        except services.NotFound:
            pass
