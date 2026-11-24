"""Acceptance tests T1 to T7 from the spec, run in mock mode against a temp copy of data/."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import create_app  # noqa: E402


@pytest.fixture
def env(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(os.path.join(ROOT, "data"), d)
    app = create_app(str(d), mode="mock")
    return app.test_client(), d


def jload(d, name):
    with open(d / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def qbank(d):
    return {q["id"]: q for q in jload(d, "questions")}


def start(c, student="sam", mode="quiz", topic=None):
    r = c.post("/api/session", json={"student": student, "mode": mode, "topic": topic})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def right(d, q):
    return qbank(d)[q["id"]]["key"]


def wrong(d, q):
    k = qbank(d)[q["id"]]["key"]
    return next(o for o in q["options"] if o != k)


def answer(c, sid, text=None, idk=False):
    return c.post(f"/api/session/{sid}/answer", json={"answer": text, "idk": idk}).get_json()


def nxt(c, sid, **kw):
    return c.post(f"/api/session/{sid}/next", json=kw).get_json()


def score(d, student, topic):
    return jload(d, "scores")[student][topic]["score"]


# ---------- T1 ----------
def test_T1_normal_session(env):
    c, d = env
    first = start(c)
    sid, q = first["session"], first["question"]
    assert (q["topic"], q["difficulty"]) == ("joins", "medium")           # starts on joins, medium
    assert answer(c, sid, right(d, q))["verdict"] == "right"
    assert score(d, "sam", "joins") == pytest.approx(0.65)                  # joins went up

    q = nxt(c, sid)["question"]                                             # hard normalisation
    assert (q["topic"], q["difficulty"]) == ("normalisation", "hard")
    r = answer(c, sid, wrong(d, q))
    assert r["verdict"] == "wrong" and r["source"]["label"] == "Lecture 4, slide 12"
    assert r["can_dispute"] and r["offer_easier"]
    assert score(d, "sam", "normalisation") == pytest.approx(0.52)          # went down

    q = nxt(c, sid, easier=True)["question"]                                # similar, easier
    assert (q["topic"], q["difficulty"]) == ("normalisation", "medium")
    assert answer(c, sid, right(d, q))["verdict"] == "right"

    q = nxt(c, sid)["question"]                                             # joins, hard
    assert (q["topic"], q["difficulty"]) == ("joins", "hard")
    assert answer(c, sid, right(d, q))["verdict"] == "right"

    q = nxt(c, sid)["question"]
    assert q["topic"] == "normalisation"
    assert answer(c, sid, wrong(d, q))["verdict"] == "wrong"

    s = c.post(f"/api/session/{sid}/end").get_json()
    assert s["answered"] == 5
    by = {t["topic"]: (t["right"], t["total"]) for t in s["topics"]}
    assert by == {"joins": (2, 2), "normalisation": (1, 3)}
    assert "Normalisation" in s["weak"] and "Joins" in s["strong"]
    assert "Normalisation" in s["next_step"] and "Lecture 4" in s["next_step"]
    assert score(d, "sam", "joins") == pytest.approx(0.80)                  # saved to disk
    assert score(d, "sam", "normalisation") == pytest.approx(0.57)


# ---------- T2 ----------
def play_failure(c, d):
    sid = start(c)["session"]
    q = nxt(c, sid, question_id="nm5")["question"]
    assert q["text"].startswith("Which normal form removes partial")
    before = score(d, "sam", "normalisation")
    r = answer(c, sid, "2NF")
    assert r["verdict"] == "wrong" and r["answer_key"] == "3NF" and r["can_dispute"]
    assert score(d, "sam", "normalisation") < before
    return sid, before


def test_T2_failure_and_recovery(env):
    c, d = env
    sid, before = play_failure(c, d)
    n_before = jload(d, "scores")["sam"]["normalisation"]["answers"]
    r = c.post(f"/api/session/{sid}/dispute", json={"note": "my notes say 2NF"}).get_json()
    assert r["outcome"] == "key_wrong" and r["correct_answer"] == "2NF"
    assert r["source"]["label"] == "Lecture 4, slide 9"
    text = " ".join(r["messages"])
    assert "my answer key was wrong" in text and "restored" in text
    assert score(d, "sam", "normalisation") == pytest.approx(before)        # score restored
    assert jload(d, "scores")["sam"]["normalisation"]["answers"] == n_before - 1
    flags = jload(d, "flags")
    assert len(flags) == 1 and flags[0]["question_id"] == "nm5" and flags[0]["student"] == "sam"
    assert qbank(d)["nm5"]["status"] == "flagged"
    nq = r["next"]["question"]                                              # carries on, same topic
    assert nq["topic"] == "normalisation" and nq["id"] != "nm5"
    answer(c, sid, wrong(d, nq))
    seen = {nq["id"]}
    for _ in range(10):                                                     # never served to Sam again
        n = nxt(c, sid)
        if "question" not in n:
            break
        seen.add(n["question"]["id"])
        answer(c, sid, right(d, n["question"]))
    assert "nm5" not in seen
    assert nxt(c, start(c)["session"], question_id=None) is not None


# ---------- T3 ----------
def test_T3_dispute_key_was_right(env):
    c, d = env
    sid = start(c)["session"]
    q = nxt(c, sid, question_id="jo2")["question"]
    r = answer(c, sid, "Zero")
    assert r["verdict"] == "wrong"
    after = score(d, "sam", "joins")
    out = c.post(f"/api/session/{sid}/dispute", json={}).get_json()
    assert out["outcome"] == "key_right"
    assert "NULL" in out["source"]["passage"]
    assert score(d, "sam", "joins") == pytest.approx(after)                 # unchanged
    assert jload(d, "flags") == []
    assert c.post(f"/api/session/{sid}/dispute", json={}).status_code == 400  # one dispute per answer


# ---------- T4 ----------
def test_T4_lecturer_session(env):
    c, d = env
    play_failure(c, d)
    sid = list(c.application.config["CTX"].sessions)[0]
    c.post(f"/api/session/{sid}/dispute", json={})
    samples = c.get("/api/lecturer/samples").get_json()
    assert len(samples) == 3 and len({s["topic"] for s in samples}) == 3
    a, b, rej = samples
    c.post("/api/lecturer/review", json={"question_id": a["id"], "action": "approve"})
    new_key = next(o for o in b["options"] if o != b["key"])
    c.post("/api/lecturer/review", json={"question_id": b["id"], "action": "edit", "key": new_key})
    c.post("/api/lecturer/review", json={"question_id": rej["id"], "action": "reject"})
    bank = qbank(d)
    assert (bank[a["id"]]["status"], bank[b["id"]]["status"], bank[rej["id"]]["status"]) == ("approved", "approved", "rejected")

    topic = next(t for t in ("relational_model", "sql_basics", "joins") if bank[rej["id"]]["topic"] == t)
    s2 = start(c, "alex", "topic", topic)["session"]                        # rejected never served
    served = []
    n = nxt(c, s2)
    while "question" in n and len(served) < 20:
        served.append(n["question"]["id"])
        answer(c, s2, "x")
        n = nxt(c, s2)
    assert rej["id"] not in served and served

    s3 = start(c, "priya")["session"]                                       # edited key is used
    nxt(c, s3, question_id=b["id"])
    assert answer(c, s3, new_key)["verdict"] == "right"

    flags = c.get("/api/lecturer/flags").get_json()                         # flag shows, no student name
    f = next(x for x in flags if x["id"] == "nm5")
    assert f["key"] == "3NF" and f["source"]["label"] == "Lecture 4, slide 9"
    blob = json.dumps(flags).lower()
    assert not re.search(r"\bsam\b|student", blob)


# ---------- T5 ----------
def test_T5_class_view(env):
    c, d = env
    v = c.get("/api/lecturer/class").get_json()
    assert {t["topic"] for t in v["topics"]} == {"relational_model", "sql_basics", "joins", "normalisation"}
    assert v["hidden"] == ["Indexes"]                                       # only 2 students answered it
    blob = json.dumps(v).lower()
    assert not any(n in blob for n in ("sam", "alex", "priya", "jamal", "mei"))
    assert all(0 <= t["percent"] <= 100 for t in v["topics"])
    sid = start(c, "priya", "topic", "indexes")["session"]                  # third student -> visible
    answer(c, sid, "x")
    v2 = c.get("/api/lecturer/class").get_json()
    assert "indexes" in {t["topic"] for t in v2["topics"]} and v2["hidden"] == []
    assert "normalisation" in c.get("/api/lecturer/suggestion").get_json()["text"].lower()


# ---------- T6 ----------
def test_T6_i_dont_know(env):
    c, d = env
    sid = start(c)["session"]
    nxt(c, sid, question_id="jo2")
    r = answer(c, sid, idk=True)
    assert r["verdict"] == "idk" and r["offer_easier"] and "jo2" not in r["message"]
    assert r["score_before"] - r["score_after"] == pytest.approx(0.05)      # smaller drop than wrong (0.10)
    assert score(d, "sam", "joins") == pytest.approx(0.45)


# ---------- T7 ----------
def test_T7_clean_folder_run(tmp_path):
    dest = tmp_path / "proj"
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(".env", "__pycache__", ".pytest_cache", "tests"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SB_", "ANTHROPIC"))}
    env["SB_PORT"] = str(port)
    p = subprocess.Popen([sys.executable, "app.py"], cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/modules", timeout=1) as r:
                    assert json.load(r)["mode"] == "mock"
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("server did not start")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
            assert b"Study Buddy" in r.read()
    finally:
        p.terminate()
        p.wait(5)


# ---------- extra checks on rules the spec leaves as design choices ----------
def test_bank_verification_and_recheck(env):
    """Verification should pass every bank question (including the planted bad one).
    The dispute re-check should flag only the planted one as key_wrong."""
    c, d = env
    ctx = c.application.config["CTX"]
    for q in ctx.questions():
        chunk = ctx.index.get(q["source"])
        assert ctx.llm.verify(q, chunk) == "match", q["id"]
        r = ctx.llm.recheck(q, chunk, "x", ctx.index)
        if q["id"] == "nm5":
            assert r["verdict"] == "key_wrong" and r["correct_answer"] == "2NF"
        else:
            assert r["verdict"] != "key_wrong", (q["id"], r)


def test_three_upheld_disputes_pull_question_for_everyone(env):
    c, d = env
    for who in ("sam", "alex", "priya"):
        sid = start(c, who)["session"]
        nxt(c, sid, question_id="nm5")
        answer(c, sid, "2NF")
        c.post(f"/api/session/{sid}/dispute", json={})
    assert qbank(d)["nm5"]["status"] == "removed"
    sid = start(c, "mei", "topic", "normalisation")["session"]
    ids = []
    n = nxt(c, sid)
    while "question" in n:
        ids.append(n["question"]["id"])
        answer(c, sid, "x")
        n = nxt(c, sid)
    assert "nm5" not in ids


def test_lecturer_fix_key_restores_question(env):
    c, d = env
    play_failure(c, d)
    sid = list(c.application.config["CTX"].sessions)[0]
    c.post(f"/api/session/{sid}/dispute", json={})
    r = c.post("/api/lecturer/flags/resolve", json={"question_id": "nm5", "action": "fix_key", "key": "2NF"}).get_json()
    assert r["key"] == "2NF" and r["status"] == "approved"


def test_scores_stay_between_0_and_1_and_review_mode(env):
    c, d = env
    r = c.post("/api/session", json={"student": "sam", "mode": "review"}).get_json()
    assert "question" not in r and "No weak topics" in r["message"]          # Sam has none under 0.5 yet
    sid = start(c, "alex", "review")["session"]                              # Alex: normalisation 0.40, 6 answers
    first = nxt(c, sid)
    assert first["question"]["topic"] == "normalisation"
    for _ in range(12):
        n = nxt(c, sid)
        if "question" not in n:
            break
        answer(c, sid, "x")
    assert 0 <= score(d, "alex", "normalisation") <= 1


# ---------- live mode, with the network call faked ----------
def test_live_mode_generates_verifies_and_disputes(tmp_path, monkeypatch):
    from sb import llm as llm_mod
    d = tmp_path / "data"
    shutil.copytree(os.path.join(ROOT, "data"), d)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    calls = []

    def fake_call(self, system, user, max_tokens=900):
        calls.append(user)
        if "Return JSON: {\"type\"" in user:  # generation
            cid = re.findall(r"\[(l\d+-s\d+)\]", user)[0]
            return json.dumps({"type": "mcq", "question": "What fills the right-table columns when a LEFT JOIN has no match?",
                               "options": ["NULL", "Zero", "Blank", "Left values"], "key": "NULL", "source": cid})
        if "STUDENT ANSWERED" in user:         # dispute re-check: pretend the key was wrong
            return json.dumps({"verdict": "key_wrong", "correct_answer": "Zero", "passage": "A LEFT JOIN returns every row."})
        return json.dumps({"verdict": "key_right", "correct_answer": "NULL", "passage": "..."})  # verification

    monkeypatch.setattr(llm_mod.LiveLLM, "_call", fake_call)
    c = create_app(str(d), mode="live").test_client()
    first = start(c, "sam", "topic", "joins")
    assert first["question"]["text"].startswith("What fills")
    saved = json.load(open(d / "questions_live.json"))
    assert saved[0]["status"] == "unreviewed" and saved[0]["source"].startswith("l3-")
    sid = first["session"]
    assert answer(c, sid, "Blank")["verdict"] == "wrong"
    out = c.post(f"/api/session/{sid}/dispute", json={}).get_json()
    assert out["outcome"] == "key_wrong" and out["correct_answer"] == "Zero"
    assert not os.path.exists(d / "questions.json.bak")


def test_live_mode_without_key_refuses_to_start(tmp_path, monkeypatch):
    from sb.llm import LLMError
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError):
        create_app(str(tmp_path), mode="live")


# ---------- deployment guard ----------
def test_lecturer_password_guard(tmp_path, monkeypatch):
    import base64
    d = tmp_path / "data"
    shutil.copytree(os.path.join(ROOT, "data"), d)
    monkeypatch.setenv("SB_LECTURER_PASSWORD", "s3cret")
    c = create_app(str(d), mode="mock").test_client()
    assert c.get("/api/lecturer/class").status_code == 401
    assert c.get("/lecturer").status_code == 401
    assert c.get("/").status_code == 200 and c.get("/api/modules").status_code == 200   # students stay open
    good = {"Authorization": "Basic " + base64.b64encode(b"lecturer:s3cret").decode()}
    assert c.get("/api/lecturer/class", headers=good).status_code == 200
    bad = {"Authorization": "Basic " + base64.b64encode(b"lecturer:nope").decode()}
    assert c.get("/api/lecturer/class", headers=bad).status_code == 401
