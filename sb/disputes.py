"""Dispute route (spec F1 to F5): re-read the source, compare with the key, recover if the key was wrong."""
import datetime

from . import quiz

PULL_THRESHOLD = 3  # distinct students whose disputes were upheld


def _add_flag(ctx, qid, student, note, kind):
    flags = ctx.flags()
    flags.append({"id": f"f{len(flags) + 1}", "question_id": qid, "student": student,
                  "time": datetime.datetime.now().isoformat(timespec="seconds"),
                  "note": (note or "").strip()[:500], "kind": kind, "resolved": False})
    ctx.store.save("flags", flags)


def dispute(ctx, sess, note=""):
    ans = sess["answered"][-1] if sess["answered"] else None
    if not ans or ans["verdict"] not in ("wrong", "partial") or sess["current"]:
        raise quiz.QuizError("There is no wrong answer to dispute right now.")
    if ans["disputed"]:
        raise quiz.QuizError("You've already disputed this one.")
    ans["disputed"] = True
    q = ctx.question(ans["qid"])
    chunk = ctx.index.get(q["source"])
    r = ctx.llm.recheck(q, chunk, ans["answer"], ctx.index)  # F2
    src = quiz.source_info(ctx, q, passage=r["passage"])

    if r["verdict"] == "key_wrong":  # F3
        correct = r["correct_answer"]
        rec = ctx.get_score(sess["student"], q["topic"])
        rec["score"] = quiz.clamp(rec["score"] - ans["applied"])
        rec["answers"] = max(0, rec["answers"] - 1)
        ctx.set_score(sess["student"], q["topic"], rec)
        ans["counted"] = False
        _add_flag(ctx, q["id"], sess["student"], note, "key_wrong")
        students = {f["student"] for f in ctx.flags() if f["question_id"] == q["id"] and f["kind"] == "key_wrong"}
        status = "removed" if len(students) >= PULL_THRESHOLD else ("flagged" if q["status"] in ("unreviewed", "approved") else q["status"])
        ctx.update_question(q["id"], dispute_count=len(students), status=status)
        if ans["answer"] and ans["answer"].strip().casefold() == correct.strip().casefold():
            first = "You were right and my answer key was wrong. Sorry."
        else:
            first = f"My answer key was wrong, so this one shouldn't count. The right answer is: {correct}."
        out = {"outcome": "key_wrong", "source": src, "correct_answer": correct, "score_restored": rec["score"],
               "messages": [f"Source: {src['label']}. \u201c{r['passage']}\u201d", first + " Your score is restored.",
                            "I've taken that question out of your quiz and flagged it for your lecturer to check.",
                            "Here is another one on the same topic."]}
        nxt = quiz.next_question(ctx, sess, topic=q["topic"])
        out["next"] = nxt
        return out

    kind_msg = {"key_right": "I re-checked the source and the answer key looks right. Here is the passage, "
                             "so you can compare it with your notes:",
                "unsure": "I re-checked the source but I can't settle this one. Here is the passage. "
                          "I've flagged the question for your lecturer."}[r["verdict"]]
    if r["verdict"] == "unsure":
        _add_flag(ctx, q["id"], sess["student"], note, "unsure")
    return {"outcome": r["verdict"], "source": src, "messages": [kind_msg], "score_kept": ctx.get_score(sess["student"], q["topic"])["score"]}
