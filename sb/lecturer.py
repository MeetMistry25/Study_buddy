"""Lecturer side (spec L1 to L5). Nothing here ever returns a student id."""
import os
import re

from . import quiz
from .retrieval import build_chunks

MIN_STUDENTS = 3


def save_upload(ctx, filename, data):
    name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(filename or ""))
    if not name.lower().endswith((".md", ".txt")):
        raise quiz.QuizError("Upload .md or .txt files (see data/module for the format).")
    text = data.decode("utf-8", errors="replace")
    from .retrieval import parse_markdown
    if not parse_markdown(text):
        raise quiz.QuizError("No slides found. Use '# Lecture N: Title' then '## Slide N' sections.")
    os.makedirs(ctx.module_dir, exist_ok=True)
    with open(os.path.join(ctx.module_dir, name), "wb") as f:
        f.write(data)
    ctx.store.save("chunks", build_chunks(ctx.module_dir))
    ctx.reload_index()
    ctx.store.save("samples", {"ids": []})  # new material means new samples
    return {"chunks": len(ctx.index.chunks), "topics": [t["label"] for t in ctx.topics()]}


def _full(ctx, q):
    c = ctx.index.get(q["source"]) or {}
    return {"id": q["id"], "topic": ctx.topic_label(q["topic"]), "difficulty": q["difficulty"], "type": q["type"],
            "text": q["text"], "options": q.get("options", []), "key": q["key"], "status": q["status"],
            "source": {"label": f"Lecture {c.get('lecture', '?')}, slide {c.get('slide', '?')}", "text": c.get("text", "")}}


def samples(ctx, n=3):
    ids = ctx.store.load("samples", {"ids": []})["ids"]
    if not ids:
        picks, seen = [], set()
        for q in ctx.questions():
            if q["topic"] not in seen and q["status"] in quiz.SERVABLE and len(seen) < n:
                seen.add(q["topic"])
                picks.append(q["id"])
        if ctx.mode == "live":
            for t in [t["id"] for t in ctx.topics()][:n]:
                if t in seen:
                    continue
                sess = {"asked_sources": [], "asked": [], "student": "_", "last_difficulty": "medium"}
                q = quiz.select_question(ctx, sess, t, "medium")
                if q:
                    picks.append(q["id"])
        ids = picks[:n]
        ctx.store.save("samples", {"ids": ids})
    return [_full(ctx, ctx.question(i)) for i in ids if ctx.question(i)]


def review(ctx, qid, action, key=None):
    q = ctx.question(qid)
    if not q:
        raise quiz.QuizError("Unknown question.")
    if action == "approve":
        ctx.update_question(qid, status="approved")
    elif action == "reject":
        ctx.update_question(qid, status="rejected")
    elif action == "edit":
        _set_key(ctx, q, key)
        ctx.update_question(qid, status="approved")
    else:
        raise quiz.QuizError("Action must be approve, reject or edit.")
    return _full(ctx, ctx.question(qid))


def _set_key(ctx, q, key):
    key = (key or "").strip()
    if not key:
        raise quiz.QuizError("The answer key can't be empty.")
    if q["type"] == "mcq" and key not in q["options"]:
        raise quiz.QuizError("For multiple choice, the key must be one of the options.")
    changes = {"key": key}
    if q["type"] == "short":
        changes["required_terms"] = []  # grade against the new key text
    ctx.update_question(q["id"], **changes)


def flag_list(ctx):
    by_q = {}
    for f in ctx.flags():
        by_q.setdefault(f["question_id"], []).append(f)
    out = []
    for qid, fl in by_q.items():
        q = ctx.question(qid)
        if not q:
            continue
        item = _full(ctx, q)
        item.update({"flags": len(fl), "kinds": sorted({f["kind"] for f in fl}),
                     "notes": [f["note"] for f in fl if f["note"]], "resolved": all(f["resolved"] for f in fl),
                     "last_flagged": max(f["time"] for f in fl)})
        out.append(item)
    out.sort(key=lambda x: (x["resolved"], x["last_flagged"]))
    return out


def resolve_flag(ctx, qid, action, key=None):
    q = ctx.question(qid)
    if not q:
        raise quiz.QuizError("Unknown question.")
    if action == "fix_key":
        _set_key(ctx, q, key)
        ctx.update_question(qid, status="approved", dispute_count=0)
    elif action == "remove":
        ctx.update_question(qid, status="removed")
    else:
        raise quiz.QuizError("Action must be fix_key or remove.")
    flags = ctx.flags()
    for f in flags:
        if f["question_id"] == qid:
            f["resolved"] = True
    ctx.store.save("flags", flags)
    return _full(ctx, ctx.question(qid))


def class_view(ctx):
    agg = {}
    for topics in ctx.store.load("scores", {}).values():  # student ids are dropped here
        for t, rec in topics.items():
            if rec["answers"] > 0:
                a = agg.setdefault(t, {"students": 0, "answers": 0, "correct": 0})
                a["students"] += 1
                a["answers"] += rec["answers"]
                a["correct"] += rec["correct"]
    shown, hidden = [], []
    for t in [t["id"] for t in ctx.topics()]:
        a = agg.get(t)
        if not a:
            continue
        if a["students"] >= MIN_STUDENTS:
            shown.append({"topic": t, "label": ctx.topic_label(t), "percent": round(100 * a["correct"] / a["answers"]),
                          "students": a["students"]})
        else:
            hidden.append(ctx.topic_label(t))
    shown.sort(key=lambda x: -x["percent"])
    return {"topics": shown, "hidden": hidden, "min_students": MIN_STUDENTS}


def suggestion(ctx):  # L5: suggests only, the lecturer decides
    shown = class_view(ctx)["topics"]
    if not shown:
        return None
    w = min(shown, key=lambda x: x["percent"])
    return {"topic": w["label"], "percent": w["percent"],
            "text": f"{w['label']} is the weakest topic ({w['percent']}% correct). "
                    f"Would a worked example help in the next lecture? It's your call."}
