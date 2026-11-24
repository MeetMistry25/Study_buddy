"""Shared app state: storage, retrieval index, model, and live sessions."""
import os

from .llm import get_llm
from .retrieval import Index, build_chunks
from .storage import Store


class Ctx:
    def __init__(self, data_dir, mode="mock"):
        self.mode = mode
        self.store = Store(data_dir)
        self.llm = get_llm(mode)
        self.module_dir = os.path.join(data_dir, "module")
        self.qfile = "questions" if mode == "mock" else "questions_live"
        self.sessions = {}
        self.reload_index(rebuild=not self.store.load("chunks"))

    # ---- module / chunks ----
    def reload_index(self, rebuild=False):
        if rebuild:
            self.store.save("chunks", build_chunks(self.module_dir))
        self.index = Index(self.store.load("chunks", []))

    def module(self):
        return self.store.load("module", {"id": "module", "name": "Module", "topics": {}})

    def topics(self):
        labels = self.module().get("topics", {})
        seen = []
        for c in self.index.chunks:
            if c["topic"] not in seen:
                seen.append(c["topic"])
        return [{"id": t, "label": labels.get(t, t.replace("_", " ").title())} for t in seen]

    def topic_label(self, topic):
        return next((t["label"] for t in self.topics() if t["id"] == topic), topic)

    def students(self):
        return self.store.load("students", {})

    # ---- questions ----
    def questions(self):
        return self.store.load(self.qfile, [])

    def question(self, qid):
        return next((q for q in self.questions() if q["id"] == qid), None)

    def update_question(self, qid, **changes):
        qs = self.questions()
        for q in qs:
            if q["id"] == qid:
                q.update(changes)
                self.store.save(self.qfile, qs)
                return q
        return None

    def add_question(self, q):
        qs = self.questions()
        n = 1 + max([int(x["id"][3:]) for x in qs if x["id"].startswith("gen") and x["id"][3:].isdigit()] or [0])
        q = dict(q, id=f"gen{n}", status="unreviewed", dispute_count=0)
        qs.append(q)
        self.store.save(self.qfile, qs)
        return q

    # ---- scores / flags ----
    def get_score(self, student, topic):
        return dict(self.store.load("scores", {}).get(student, {}).get(topic, {"score": 0.5, "answers": 0, "correct": 0}))

    def set_score(self, student, topic, rec):
        d = self.store.load("scores", {})
        d.setdefault(student, {})[topic] = rec
        self.store.save("scores", d)

    def flags(self):
        return self.store.load("flags", [])
