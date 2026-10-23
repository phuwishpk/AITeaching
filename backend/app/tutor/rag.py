"""RAG ฝั่งดึงข้อมูล (Retrieval): ค้นย่อหน้าจากเอกสารวิชาด้วย BM25 ที่เขียนเอง

ภาษาไทยไม่มีช่องว่างระหว่างคำ จึงตัดคำด้วย PyThaiNLP (newmm) ก่อนนับคำ
ทั้งหมดทำงานในเครื่อง เอกสารไม่ถูกส่งออกไปนอกเครื่อง
"""

import io
import math
import re
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


def chunk_text(text: str, size: int = 520) -> list[str]:
    """แบ่งเอกสารเป็นย่อหน้า ถ้าย่อหน้าสั้นเกินจะรวมกับย่อหน้าถัดไป"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=#)", text or "") if p.strip()]
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


def extract_text(filename: str, data: bytes) -> tuple[str, str | None]:
    """อ่านข้อความจากไฟล์ คืนค่า (ข้อความ, คำเตือน)"""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if len(text.strip()) < 20:
            return "", "อ่านตัวอักษรจาก PDF นี้ไม่ได้ อาจเป็นภาพสแกนซึ่งยังไม่รองรับ (ต้องใช้ OCR)"
        return text, None
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
