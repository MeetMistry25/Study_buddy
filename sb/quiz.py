"""Question selection, grading, topic scores and session summary (spec sections 4 and 5)."""
import time
import uuid

from . import retrieval as R

DELTA = {"right": 0.15, "wrong": -0.10, "partial": -0.10, "idk": -0.05}
DIFFS = ["easy", "medium", "hard"]
SERVABLE = {"unreviewed", "approved", "flagged"}
MODES = {"quiz", "topic", "review"}
MAX_TRIES = 3  # first attempt plus two regenerations


class QuizError(ValueError):
    pass


def clamp(x):
    return round(min(1.0, max(0.0, x)), 3)


def difficulty_for(score):
    return "easy" if score < 0.35 else ("medium" if score <= 0.60 else "hard")


def public(ctx, q):
    return {"id": q["id"], "topic": q["topic"], "topic_label": ctx.topic_label(q["topic"]),
            "difficulty": q["difficulty"], "type": q["type"], "text": q["text"], "options": q.get("options", [])}


def source_info(ctx, q, passage=None):
    c = ctx.index.get(q["source"]) or {"lecture": "?", "slide": "?", "text": "", "lecture_title": ""}
    return {"chunk_id": q["source"], "lecture": c["lecture"], "slide": c["slide"],
            "lecture_title": c.get("lecture_title", ""), "text": c["text"], "passage": passage or c["text"],
            "label": f"Lecture {c['lecture']}, slide {c['slide']}"}


def removed_for(ctx, student):
    """Questions pulled from this student's quiz by a successful dispute the lecturer has not yet resolved."""
    return {f["question_id"] for f in ctx.flags()
            if f["student"] == student and f["kind"] == "key_wrong" and not f["resolved"]}


# ---------- sessions ----------

def start_session(ctx, student, mode, topic=None):
    if student not in ctx.students():
        raise QuizError("Unknown student.")
    if mode not in MODES:
        raise QuizError("Pick a mode: quiz, topic or review.")
    if mode == "topic" and topic not in [t["id"] for t in ctx.topics()]:
        raise QuizError("Pick a topic.")
    s = {"id": uuid.uuid4().hex[:10], "student": student, "mode": mode, "topic": topic,
         "asked": [], "asked_by_topic": {}, "asked_sources": [], "last_difficulty": "medium",
         "last_topic": None, "current": None, "answered": [], "ended": False, "started": time.time()}
    ctx.sessions[s["id"]] = s
    return s


def get_session(ctx, sid):
    s = ctx.sessions.get(sid)
    if not s:
        raise QuizError("Session not found. Start a new one.")
    return s


# ---------- choosing the next question ----------

def _topic_order(ctx, sess):
    topics = [t["id"] for t in ctx.topics()]
    if sess["mode"] == "topic":
        return [sess["topic"]]
    scored = []
    for i, t in enumerate(topics):
        rec = ctx.get_score(sess["student"], t)
        if sess["mode"] == "review" and not (rec["score"] < 0.5 and rec["answers"] >= 2):
            continue
        scored.append((rec["score"], sess["asked_by_topic"].get(t, 0), i, t))
    return [t for *_, t in sorted(scored)]


def target_difficulty(ctx, sess, topic):
    rec = ctx.get_score(sess["student"], topic)
    if rec["answers"] == 0:  # cold start: reuse the previous question's difficulty
        return sess["last_difficulty"]
    return difficulty_for(rec["score"])


def _pool(ctx, sess, topic):
    gone = removed_for(ctx, sess["student"])
    return [q for q in ctx.questions() if q["topic"] == topic and q["status"] in SERVABLE
            and q["id"] not in sess["asked"] and q["id"] not in gone]


def _verified(ctx, q):
    chunk = ctx.index.get(q["source"])
    return bool(chunk) and ctx.llm.verify(q, chunk) == "match"


def select_question(ctx, sess, topic, diff):
    want = DIFFS.index(diff)
    pool = _pool(ctx, sess, topic)
    exact = [q for q in pool if q["difficulty"] == diff]
    tries = 0
    for q in exact:
        if tries >= MAX_TRIES:
            break
        tries += 1
        if _verified(ctx, q):
            return q
    if ctx.mode == "live":  # generate fresh, verify, regenerate up to twice
        for _ in range(MAX_TRIES):
            chunks = ctx.index.search(f"{ctx.topic_label(topic)} {diff}", topic=topic, k=6)
            fresh = [c for c in chunks if c["id"] not in sess["asked_sources"]] or chunks
            made = ctx.llm.generate(topic, diff, fresh[:2])
            if made and ctx.llm.verify(made, ctx.index.get(made["source"])) == "match":
                return ctx.add_question(made)
    others = sorted((q for q in pool if q["difficulty"] != diff),
                    key=lambda q: abs(DIFFS.index(q["difficulty"]) - want))
    for q in others:
        if _verified(ctx, q):
            return q
    return None


def _serve(ctx, sess, q):
    sess["current"] = q["id"]
    sess["asked"].append(q["id"])
    sess["asked_by_topic"][q["topic"]] = sess["asked_by_topic"].get(q["topic"], 0) + 1
    sess["asked_sources"].append(q["source"])
    sess["last_difficulty"], sess["last_topic"] = q["difficulty"], q["topic"]
    return {"question": public(ctx, q), "mode": sess["mode"]}


def next_question(ctx, sess, force_id=None, easier=False, topic=None):
    if force_id and ctx.mode == "mock":  # demo hook: replay a specific question (README: failure demo)
        q = ctx.question(force_id)
        if q:
            if sess["current"]:  # swap out the unanswered question that was just served
                prev = sess["current"]
                sess["asked"] = [a for a in sess["asked"] if a != prev]
                sess["current"] = None
            return _serve(ctx, sess, q)
    if sess["current"]:
        return {"question": public(ctx, ctx.question(sess["current"])), "mode": sess["mode"]}
    if easier and sess["last_topic"]:
        order = [sess["last_topic"]]
        diff_override = DIFFS[max(0, DIFFS.index(sess["last_difficulty"]) - 1)]
    else:
        order, diff_override = ([topic] if topic else _topic_order(ctx, sess)), None
    if not order:
        return {"done": True, "message": "No weak topics yet. A topic needs a score under 0.5 from at least "
                                          "two answers. Try Quiz me instead."}
    for t in order:
        q = select_question(ctx, sess, t, diff_override or target_difficulty(ctx, sess, t))
        if q:
            return _serve(ctx, sess, q)
    return {"done": True, "message": "I have no more questions for you here. Finish the session to see your summary."}


# ---------- grading and scoring ----------

def grade(q, answer):
    answer = (answer or "").strip()
    if not answer:
        return "wrong"
    if q["type"] == "mcq":
        return "right" if answer.casefold() == q["key"].strip().casefold() else "wrong"
    terms = q.get("required_terms") or []
    if not terms:
        if R.supports(answer, q["key"], 0.75):
            return "right"
        return "partial" if R.supports(answer, q["key"], 0.4) else "wrong"
    atoks = set(R.tokens(answer))
    hits = sum(1 for t in terms if any(set(R.tokens(alt)) <= atoks for alt in t.split("|")))
    return "right" if hits == len(terms) else ("partial" if hits else "wrong")


def submit_answer(ctx, sess, answer, idk=False):
    if not sess["current"]:
        raise QuizError("There is no open question.")
    q = ctx.question(sess["current"])
    verdict = "idk" if idk else grade(q, answer)
    rec = ctx.get_score(sess["student"], q["topic"])
    before = rec["score"]
    rec["score"] = clamp(before + DELTA[verdict])
    rec["answers"] += 1
    rec["correct"] += 1 if verdict == "right" else 0
    ctx.set_score(sess["student"], q["topic"], rec)
    sess["answered"].append({"qid": q["id"], "topic": q["topic"], "verdict": verdict, "answer": answer,
                             "applied": round(rec["score"] - before, 3), "counted": True, "disputed": False})
    sess["current"] = None
    src = source_info(ctx, q)
    if verdict == "right":
        msg = f"Correct. ({src['label']})"
    elif verdict == "idk":
        msg = f"No problem. The answer is: {q['key']}. See {src['label']}."
    elif verdict == "partial":
        msg = f"Partly right, but that is not enough to count. The full answer is: {q['key']}. See {src['label']}."
    else:
        msg = f"That's incorrect. The answer is: {q['key']}. See {src['label']}."
    wrong = verdict != "right"
    return {"verdict": verdict, "correct": not wrong, "message": msg, "answer_key": q["key"], "source": src,
            "topic": q["topic"], "topic_label": ctx.topic_label(q["topic"]), "score_before": before,
            "score_after": rec["score"], "next_difficulty": difficulty_for(rec["score"]),
            "can_dispute": verdict in ("wrong", "partial"), "offer_easier": wrong, "ask_continue": True}


# ---------- summary ----------

def end_session(ctx, sess):
    sess["ended"] = True
    tallies = {}
    for a in sess["answered"]:
        if a["counted"]:
            t = tallies.setdefault(a["topic"], {"right": 0, "total": 0, "wrong_sources": []})
            t["total"] += 1
            t["right"] += 1 if a["verdict"] == "right" else 0
            if a["verdict"] != "right":
                t["wrong_sources"].append(ctx.question(a["qid"])["source"])
    topics = []
    for t, v in tallies.items():
        score = ctx.get_score(sess["student"], t)["score"]
        topics.append({"topic": t, "label": ctx.topic_label(t), "right": v["right"], "total": v["total"],
                       "score": score, "status": "strong" if score > 0.60 else "weak"})
    topics.sort(key=lambda x: x["score"])
    if not topics:
        return {"answered": 0, "correct": 0, "topics": [], "strong": [], "weak": [],
                "next_step": "You didn't answer any questions this time. Come back and try a few.", "saved": True}
    weakest = topics[0]
    refs = sorted({ctx.index.get(c)["lecture"] for c in tallies[weakest["topic"]]["wrong_sources"] if ctx.index.get(c)})
    where = ("Lecture " + ", ".join(map(str, refs))) if refs else weakest["label"]
    step = (f"Revise {weakest['label']} ({where}), then retry tomorrow." if weakest["status"] == "weak"
            else "Nice work. Try a harder topic or come back tomorrow to keep it fresh.")
    return {"answered": sum(t["total"] for t in topics), "correct": sum(t["right"] for t in topics),
            "topics": topics, "strong": [t["label"] for t in topics if t["status"] == "strong"],
            "weak": [t["label"] for t in topics if t["status"] == "weak"], "next_step": step, "saved": True}
