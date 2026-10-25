"""RAG ฝั่งดึงข้อมูล (Retrieval): ค้นย่อหน้าจากเอกสารวิชาด้วย BM25 ที่เขียนเอง

ภาษาไทยไม่มีช่องว่างระหว่างคำ จึงตัดคำด้วย PyThaiNLP (newmm) ก่อนนับคำ การค้นทำงานในเครื่อง
ตัวอ่าน PDF ในไฟล์นี้เป็นทางสำรอง เมื่อมี Gemini key ให้ Gemini อ่านไฟล์เอง (reader.py) และเอกสารของครู
ถูกส่งให้ AI ทั้งตอนอ่าน ตอนสร้างคลังโจทย์ และตอนสอน (ไม่มีข้อมูลนักเรียนอยู่ในเอกสาร)
"""

import io
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache

from pythainlp import word_tokenize
from pythainlp.corpus import thai_stopwords

STOPWORDS = set(thai_stopwords())
K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    tokens = word_tokenize(text or "", engine="newmm", keep_whitespace=False)
    result = []
    for token in tokens:
        token = token.strip().lower()
        if not token or token in STOPWORDS or re.fullmatch(r"[\W_]+", token):
            continue
        result.append(token)
    return result


def _split_long(paragraph: str, size: int) -> list[str]:
    """ย่อหน้าที่ยาวเกินไปแบ่งตามช่องว่าง (ภาษาไทยใช้ช่องว่างคั่นประโยค) ให้แต่ละชิ้นไม่เกิน size"""
    if len(paragraph) <= size:
        return [paragraph]
    pieces, buffer = [], ""
    for sentence in re.split(r"(?<=[\s.!?])\s*", paragraph):
        if buffer and len(buffer) + len(sentence) > size:
            pieces.append(buffer.strip())
            buffer = ""
        buffer += sentence if not buffer or buffer.endswith((" ", "\n")) else " " + sentence
    if buffer.strip():
        pieces.append(buffer.strip())
    return pieces


def chunk_text(text: str, size: int = 520) -> list[str]:
    """แบ่งเอกสารเป็นย่อหน้า ถ้าย่อหน้าสั้นเกินจะรวมกับย่อหน้าถัดไป ถ้ายาวเกินจะแบ่งตามประโยค"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=#)", text or "") if p.strip()]
    paragraphs = [piece for p in paragraphs for piece in _split_long(p, size)]
    chunks, buffer = [], ""
    for para in paragraphs:
        if len(buffer) + len(para) < size:
            buffer = f"{buffer}\n{para}".strip()
        else:
            if buffer:
                chunks.append(buffer)
            buffer = para
    if buffer:
        chunks.append(buffer)
    return chunks


THAI = r"\u0E00-\u0E7F"
HEADING = re.compile(r"^(?:#|\d+(?:\.\d+)*[.)]\s|บทที่|หัวข้อ|ตอนที่)")


def clean_pdf_text(text: str) -> str:
    """ข้อความจาก PDF ตัดบรรทัดตามความกว้างหน้ากระดาษ ไม่มีบรรทัดว่างคั่นย่อหน้า และสระบางตัวแยกเป็นสองอักขระ
    จึงต่อบรรทัดกลับเป็นย่อหน้า: บรรทัดที่สั้นกว่าปกติหรือบรรทัดหัวข้อถือเป็นจุดจบย่อหน้า"""
    text = unicodedata.normalize("NFC", text).replace("\u0e4d\u0e32", "\u0e33").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lengths = sorted(len(l) for l in lines if len(l) >= 20)
    typical = lengths[len(lengths) // 2] if lengths else 80
    paragraphs: list[str] = []
    current = ""
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if HEADING.match(line) and current:
            paragraphs.append(current)
            current = ""
        if not current:
            current = line
        elif re.search(f"[{THAI}]$", current) and re.match(f"[{THAI}]", line):
            current += line  # คำไทยที่ถูกตัดกลางบรรทัด ต่อกันโดยไม่เว้นวรรค
        else:
            current += " " + line
        if len(line) < typical * 0.6 or HEADING.match(line):
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return "\n\n".join(paragraphs)


def extract_text(filename: str, data: bytes) -> tuple[str, str | None]:
    """อ่านข้อความจากไฟล์ คืนค่า (ข้อความ, คำเตือน)"""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                reader.decrypt("")
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception:
            return "", "เปิดไฟล์ PDF นี้ไม่ได้ ไฟล์อาจเสียหายหรือตั้งรหัสผ่านไว้"
        text = "\n\n".join(clean_pdf_text(page) for page in pages if page.strip())
        if len(text.strip()) < 20:
            return "", "อ่านตัวอักษรจาก PDF นี้ไม่ได้ อาจเป็นภาพสแกนซึ่งยังไม่รองรับ (ต้องใช้ OCR)"
        empty = sum(1 for page in pages if len(page.strip()) < 20)
        warning = f"มี {empty} จาก {len(pages)} หน้าที่อ่านตัวอักษรไม่ได้ (อาจเป็นภาพสแกน)" if empty else None
        return text, warning
    if name.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in document.paragraphs if p.text.strip()), None
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace"), None
    return "", "รองรับเฉพาะไฟล์ PDF ที่มีตัวอักษร, DOCX, TXT และ MD"


class BM25Index:
    def __init__(self, docs: list[dict]):
        """docs: [{"doc_id", "filename", "text"}] แต่ละรายการคือหนึ่งย่อหน้า"""
        self.docs = docs
        self.tokens = [tokenize(d["text"]) for d in docs]
        self.lengths = [len(t) for t in self.tokens]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0
        self.df: Counter = Counter()
        for toks in self.tokens:
            self.df.update(set(toks))
        self.counts = [Counter(t) for t in self.tokens]

    def idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 3) -> tuple[list[str], list[dict]]:
        terms = tokenize(query)
        scored = []
        for index, counts in enumerate(self.counts):
            score = 0.0
            for term in set(terms):
                tf = counts.get(term, 0)
                if not tf:
                    continue
                denom = tf + K1 * (1 - B + B * self.lengths[index] / (self.avg or 1))
                score += self.idf(term) * tf * (K1 + 1) / denom
            if score > 0:
                scored.append((score, index))
        scored.sort(reverse=True)
        results = []
        for score, index in scored[:k]:
            doc = self.docs[index]
            results.append({"filename": doc["filename"], "text": doc["text"], "score": round(score, 3)})
        return terms, results


_indexes: dict[str, BM25Index] = {}


def build_index(subject_id: str, documents: list[dict]) -> BM25Index:
    chunks = []
    for document in documents:
        for chunk in document.get("chunks", []):
            chunks.append({"doc_id": document["id"], "filename": document["filename"], "text": chunk})
    index = BM25Index(chunks)
    _indexes[subject_id] = index
    return index


def get_index(subject_id: str) -> BM25Index | None:
    return _indexes.get(subject_id)


@lru_cache(maxsize=64)
def tokenize_demo(text: str) -> list[str]:
    """ใช้ในหน้า Admin แสดงผลการตัดคำภาษาไทย (สไลด์ 4.2)"""
    return word_tokenize(text, engine="newmm", keep_whitespace=False)
