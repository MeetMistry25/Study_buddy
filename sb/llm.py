"""Everything that touches a model lives here. Swapping mock for live changes only this file.

Interface (both classes):
  generate(topic, difficulty, chunks)       -> question dict or None
  verify(question, chunk)                   -> "match" | "mismatch" | "unsure"
  recheck(question, chunk, student_answer, index)
                                            -> {"verdict": "key_right"|"key_wrong"|"unsure",
                                                "correct_answer": str, "passage": str}
"""
import json
import os
import re
import urllib.error
import urllib.request

from . import retrieval as R


class LLMError(RuntimeError):
    pass


class MockLLM:
    """No API key needed. Questions come from the hand-written bank (data/questions.json).

    verify() is deliberately simple: it only checks that the answer key's words appear in the
    source chunk. That is why the planted '3NF removes partial dependencies' question gets past it:
    the chunk mentions both 2NF and 3NF. The dispute re-check is stricter, because it looks at the
    single best-matching sentence, which is how the planted error gets caught.
    """
    mode = "mock"

    def generate(self, topic, difficulty, chunks):
        return None  # the bank is the only source in mock mode

    def verify(self, q, chunk):
        return "match" if R.supports(chunk["text"], q["key"], 0.6) else "mismatch"

    def recheck(self, q, chunk, student_answer, index):
        sent = index.best_sentence(chunk["text"], q["text"])
        if q["type"] == "short" or not q.get("options"):
            ok = R.supports(sent, q["key"], 0.8)
            return {"verdict": "key_right" if ok else "unsure", "correct_answer": q["key"], "passage": sent}
        supported = [o for o in q["options"] if R.supports(sent, o, 0.8)]
        if q["key"] in supported:
            return {"verdict": "key_right", "correct_answer": q["key"], "passage": sent}
        if len(supported) == 1:
            return {"verdict": "key_wrong", "correct_answer": supported[0], "passage": sent}
        return {"verdict": "unsure", "correct_answer": q["key"], "passage": sent}


class LiveLLM:
    mode = "live"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self):
        self.key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not self.key:
            raise LLMError("Live mode needs ANTHROPIC_API_KEY (set it in your environment or .env).")
        self.model = os.environ.get("SB_MODEL", "claude-sonnet-5-5")

    # ---- plumbing ----
    def _call(self, system, user, max_tokens=900):
        body = json.dumps({"model": self.model, "max_tokens": max_tokens, "system": system,
                           "messages": [{"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.URL, data=body, headers={
            "content-type": "application/json", "x-api-key": self.key, "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
        except (urllib.error.URLError, TimeoutError) as e:
            raise LLMError(f"Model call failed: {e}")
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    @staticmethod
    def _json(text):
        a, b = text.find("{"), text.rfind("}")
        if a < 0 or b < a:
            raise LLMError("Model did not return JSON.")
        return json.loads(text[a:b + 1])

    # ---- interface ----
    def generate(self, topic, difficulty, chunks):
        src = "\n\n".join(f"[{c['id']}] Lecture {c['lecture']}, slide {c['slide']}: {c['text']}" for c in chunks)
        system = ("You write revision questions for a university module. Use ONLY the source text supplied. "
                  "Never use outside knowledge. Reply with one JSON object and nothing else.")
        user = (f"Topic: {topic}\nDifficulty: {difficulty} (easy = recall, medium = understanding, "
                f"hard = multi-step or edge cases)\n\nSOURCE:\n{src}\n\n"
                'Return JSON: {"type":"mcq"|"short","question":str,"options":[4 strings, [] if short],'
                '"key":str (must equal one option exactly for mcq),"required_terms":[strings, short only; '
                'use "a|b" for alternatives],"source":"<chunk id>"}')
        try:
            d = self._json(self._call(system, user))
        except (LLMError, json.JSONDecodeError):
            return None
        ids = {c["id"] for c in chunks}
        if d.get("source") not in ids or not d.get("question") or not d.get("key"):
            return None
        if d.get("type") == "mcq" and (len(d.get("options", [])) < 2 or d["key"] not in d["options"]):
            return None
        return {"topic": topic, "difficulty": difficulty, "type": d.get("type", "mcq"), "text": d["question"],
                "options": d.get("options", []) if d.get("type") == "mcq" else [], "key": d["key"],
                "required_terms": d.get("required_terms", []), "source": d["source"]}

    def _judge(self, q, chunk, student_answer=None):
        opts = "\n".join(f"- {o}" for o in q.get("options", [])) or "(short answer)"
        system = ("You check answer keys against a source passage. Use ONLY the passage. "
                  "If the passage does not settle it, say unsure. Reply with one JSON object and nothing else.")
        user = (f"PASSAGE (Lecture {chunk['lecture']}, slide {chunk['slide']}): {chunk['text']}\n\n"
                f"QUESTION: {q['text']}\nOPTIONS:\n{opts}\nANSWER KEY: {q['key']}\n"
                + (f"STUDENT ANSWERED: {student_answer}\n" if student_answer else "") +
                'Return JSON: {"verdict":"key_right"|"key_wrong"|"unsure",'
                '"correct_answer":str (an option exactly, or the right short answer),'
                '"passage":str (the single sentence copied from the passage that settles it)}')
        return self._json(self._call(system, user, 500))

    def verify(self, q, chunk):
        try:
            v = self._judge(q, chunk).get("verdict")
        except (LLMError, json.JSONDecodeError):
            return "unsure"
        return {"key_right": "match", "key_wrong": "mismatch"}.get(v, "unsure")

    def recheck(self, q, chunk, student_answer, index):
        try:
            d = self._judge(q, chunk, student_answer)
        except (LLMError, json.JSONDecodeError):
            return {"verdict": "unsure", "correct_answer": q["key"], "passage": chunk["text"]}
        v = d.get("verdict") if d.get("verdict") in ("key_right", "key_wrong", "unsure") else "unsure"
        correct = d.get("correct_answer") or q["key"]
        if v == "key_wrong" and q.get("options") and correct not in q["options"]:
            v = "unsure"
        return {"verdict": v, "correct_answer": correct, "passage": d.get("passage") or chunk["text"]}


def get_llm(mode):
    return LiveLLM() if mode == "live" else MockLLM()
