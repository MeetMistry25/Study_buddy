"""Chunking, TF-IDF retrieval, and the small text heuristics the mock model uses.

No third-party packages: for one module, plain TF-IDF is enough (spec section 5).
"""
import math
import os
import re
from collections import Counter

STOPWORDS = set(
    "a an the of in on at to for and or is are was were be been it its this that these those "
    "with as by from which what who whom when why how do does did can could should would "
    "than then so such if into onto also very".split()
)


def stem(w):
    """Very light stemmer so 'removes', 'removed' and 'removing' all match."""
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def tokens(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def supports(text, answer, threshold=0.8):
    """True if at least `threshold` of the answer's content words appear in `text`."""
    a = set(tokens(answer))
    if not a:
        return False
    return len(a & set(tokens(text))) / len(a) >= threshold


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# ---------- chunking ----------

def parse_markdown(text):
    """One chunk per slide or notes section. See data/module/*.md for the format."""
    lecture, title, topic = None, "", "general"
    chunks, cur, notes_n = [], None, 0

    def flush():
        if cur and cur["text"].strip():
            cur["text"] = " ".join(cur["text"].split())
            chunks.append(cur)

    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"#\s+Lecture\s+(\d+)\s*[:\-]?\s*(.*)", s, re.I)
        if m:
            flush()
            cur = None
            lecture, title = int(m.group(1)), m.group(2).strip()
            continue
        m = re.match(r"topic:\s*(\S+)", s, re.I)
        if m and cur is None:
            topic = m.group(1).lower()
            continue
        if lecture is None:
            if s:
                raise ValueError("File must start with a heading like '# Lecture 4: Normalisation'.")
            continue
        m = re.match(r"##\s+Slide\s+(\d+)", s, re.I)
        if m:
            flush()
            n = int(m.group(1))
            cur = {"id": f"l{lecture}-s{n}", "lecture": lecture, "lecture_title": title,
                   "slide": n, "topic": topic, "text": ""}
            continue
        m = re.match(r"##\s+Notes?\s*[:\-]?\s*(.*)", s, re.I)
        if m:
            flush()
            notes_n += 1
            cur = {"id": f"l{lecture}-n{notes_n}", "lecture": lecture, "lecture_title": title,
                   "slide": "notes: " + (m.group(1).strip() or str(notes_n)), "topic": topic, "text": ""}
            continue
        if cur is not None and s:
            cur["text"] += " " + s
    flush()
    return chunks


def build_chunks(module_dir):
    chunks = []
    if not os.path.isdir(module_dir):
        return chunks
    for name in sorted(os.listdir(module_dir)):
        if name.lower().endswith((".md", ".txt")):
            with open(os.path.join(module_dir, name), encoding="utf-8") as f:
                chunks.extend(parse_markdown(f.read()))
    return chunks


# ---------- retrieval ----------

class Index:
    def __init__(self, chunks):
        self.chunks = chunks
        self.by_id = {c["id"]: c for c in chunks}
        self.docs = [Counter(tokens(c["text"] + " " + c.get("topic", "").replace("_", " "))) for c in chunks]
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        self.n = len(chunks)
        self.idf = {t: math.log((self.n + 1) / (df[t] + 1)) + 1 for t in df}

    def idf_of(self, t):
        return self.idf.get(t, math.log(self.n + 1) + 1)

    def get(self, chunk_id):
        return self.by_id.get(chunk_id)

    def search(self, query, topic=None, k=3):
        q = Counter(tokens(query))
        qv = {t: c * self.idf_of(t) for t, c in q.items()}
        qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
        scored = []
        for chunk, doc in zip(self.chunks, self.docs):
            if topic and chunk.get("topic") != topic:
                continue
            dv = {t: c * self.idf_of(t) for t, c in doc.items()}
            dn = math.sqrt(sum(v * v for v in dv.values())) or 1.0
            dot = sum(qv[t] * dv.get(t, 0.0) for t in qv)
            scored.append((dot / (qn * dn), chunk))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:k]]

    def best_sentence(self, text, query):
        sents = sentences(text)
        if not sents:
            return text
        qt = set(tokens(query))
        best, best_score = sents[0], -1.0
        for s in sents:
            score = sum(self.idf_of(t) for t in qt & set(tokens(s)))
            if score > best_score:
                best, best_score = s, score
        return best
