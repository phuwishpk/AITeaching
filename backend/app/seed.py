"""ข้อมูลเริ่มต้นตอนเปิดระบบครั้งแรก: วิชาตัวอย่าง เอกสารวิชา นักเรียนตัวอย่าง และกลุ่มนักเรียนจำลอง"""

import time

from . import db, demo, services
from .content.sample_math_m2 import SAMPLE_DOCUMENT, SAMPLE_DOCUMENT_NAME, build_subject
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


def add_document(subject_id: str, filename: str, text: str, warning: str | None = None) -> int:
    chunks = rag.chunk_text(text)
    cursor = db.execute(
        "INSERT INTO documents (subject_id, filename, kind, chars, chunks, warning, uploaded_at) VALUES (?,?,?,?,?,?,?)",
        (subject_id, filename, filename.rsplit(".", 1)[-1].lower(), len(text), db.dumps(chunks), warning, time.time()),
    )
    rebuild_index(subject_id)
    return cursor.lastrowid


def rebuild_index(subject_id: str):
    rows = db.query("SELECT id, filename, chunks FROM documents WHERE subject_id = ?", (subject_id,))
    rag.build_index(subject_id, [{"id": r["id"], "filename": r["filename"], "chunks": db.loads(r["chunks"], [])} for r in rows])


def ensure_seed():
    if not db.list_subjects():
        subject = build_subject()
        db.save_subject(subject)
        add_document(subject["id"], SAMPLE_DOCUMENT_NAME, SAMPLE_DOCUMENT)
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
    if not db.query_one("SELECT code FROM students WHERE kind = 'sim'"):
        try:
            demo.seed_cohort()
        except services.NotFound:
            pass
