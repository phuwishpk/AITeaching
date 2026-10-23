"""ลบข้อมูลส่วนตัวออกจากข้อความแชตก่อนส่งให้ Provider (PDPA)

แทนที่อีเมล เบอร์โทร เลขบัตรประชาชน และชื่อจริงที่อยู่ใน Roster ด้วยป้ายกลาง ๆ
"""

import re

PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[อีเมล]"),
    (re.compile(r"\b\d{1}[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d{1}\b"), "[เลขบัตร]"),
    (re.compile(r"(?<!\d)0\d{1,2}[-\s]?\d{3}[-\s]?\d{4}(?!\d)"), "[เบอร์โทร]"),
]


def scrub(text: str, names: list[str]) -> tuple[str, list[str]]:
    found: list[str] = []
    for pattern, label in PATTERNS:
        if pattern.search(text):
            found.append(label)
            text = pattern.sub(label, text)
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        for part in [name] + [p for p in name.split() if len(p) >= 2 and not p.startswith(("ด.", "นาย", "นาง"))]:
            if part and part in text:
                found.append("[ชื่อ]")
                text = text.replace(part, "[ชื่อ]")
    return text, found
