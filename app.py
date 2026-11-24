"""Study Buddy: Flask app. Run `python app.py`, then open http://127.0.0.1:5000 (student)
and http://127.0.0.1:5000/lecturer. Mock mode is the default and needs no API key."""
import hmac
import os
import sys

from flask import Flask, Response, jsonify, render_template, request

from sb import disputes, lecturer, quiz
from sb.context import Ctx
from sb.llm import LLMError

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(path):
    """Minimal .env reader so no extra dependency is needed. Existing env vars win."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def create_app(data_dir=None, mode=None):
    load_dotenv(os.path.join(ROOT, ".env"))
    mode = (mode or os.environ.get("SB_MODE") or "mock").lower()
    ctx = Ctx(data_dir or os.environ.get("SB_DATA_DIR") or os.path.join(ROOT, "data"), mode)
    app = Flask(__name__)
    app.config["CTX"] = ctx

    # Optional shared password for the lecturer page and API. Unset means open (fine on localhost).
    lecturer_pw = os.environ.get("SB_LECTURER_PASSWORD", "")

    @app.before_request
    def lecturer_guard():
        if lecturer_pw and (request.path.startswith("/lecturer") or request.path.startswith("/api/lecturer")):
            auth = request.authorization
            if not auth or not hmac.compare_digest(auth.password or "", lecturer_pw):
                return Response("Lecturer login required.", 401, {"WWW-Authenticate": 'Basic realm="Study Buddy lecturer"'})

    def body():
        return request.get_json(silent=True) or {}

    @app.errorhandler(quiz.QuizError)
    def bad(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(LLMError)
    def llm_bad(e):
        return jsonify(error=str(e)), 502

    # ---- pages ----
    @app.get("/")
    def student_page():
        return render_template("student.html")

    @app.get("/lecturer")
    def lecturer_page():
        return render_template("lecturer.html")

    # ---- student API ----
    @app.get("/api/modules")
    def modules():
        m = ctx.module()
        return jsonify(mode=ctx.mode, students=ctx.students(),
                       modules=[{"id": m["id"], "name": m["name"], "topics": ctx.topics()}])

    @app.get("/api/student/<student>/scores")
    def scores(student):
        if student not in ctx.students():
            raise quiz.QuizError("Unknown student.")
        return jsonify([dict(ctx.get_score(student, t["id"]), topic=t["id"], label=t["label"]) for t in ctx.topics()])

    @app.post("/api/session")
    def new_session():
        b = body()
        s = quiz.start_session(ctx, b.get("student"), b.get("mode"), b.get("topic"))
        return jsonify(session=s["id"], **quiz.next_question(ctx, s))

    @app.post("/api/session/<sid>/next")
    def nxt(sid):
        b = body()
        s = quiz.get_session(ctx, sid)
        return jsonify(quiz.next_question(ctx, s, force_id=b.get("question_id"), easier=bool(b.get("easier"))))

    @app.post("/api/session/<sid>/answer")
    def answer(sid):
        b = body()
        return jsonify(quiz.submit_answer(ctx, quiz.get_session(ctx, sid), b.get("answer"), bool(b.get("idk"))))

    @app.post("/api/session/<sid>/dispute")
    def dispute(sid):
        return jsonify(disputes.dispute(ctx, quiz.get_session(ctx, sid), body().get("note", "")))

    @app.post("/api/session/<sid>/end")
    def end(sid):
        return jsonify(quiz.end_session(ctx, quiz.get_session(ctx, sid)))

    # ---- lecturer API ----
    @app.post("/api/lecturer/upload")
    def upload():
        files = request.files.getlist("files")
        if not files:
            raise quiz.QuizError("Choose at least one file.")
        res = None
        for f in files:
            res = lecturer.save_upload(ctx, f.filename, f.read())
        return jsonify(res)

    @app.get("/api/lecturer/samples")
    def samples():
        return jsonify(lecturer.samples(ctx))

    @app.post("/api/lecturer/review")
    def review():
        b = body()
        return jsonify(lecturer.review(ctx, b.get("question_id"), b.get("action"), b.get("key")))

    @app.get("/api/lecturer/flags")
    def flags():
        return jsonify(lecturer.flag_list(ctx))

    @app.post("/api/lecturer/flags/resolve")
    def resolve():
        b = body()
        return jsonify(lecturer.resolve_flag(ctx, b.get("question_id"), b.get("action"), b.get("key")))

    @app.get("/api/lecturer/class")
    def class_view():
        return jsonify(lecturer.class_view(ctx))

    @app.get("/api/lecturer/suggestion")
    def suggestion():
        return jsonify(lecturer.suggestion(ctx))

    return app


if __name__ == "__main__":
    try:
        application = create_app()
    except LLMError as e:
        sys.exit(f"Can't start: {e}\nUnset SB_MODE (or set SB_MODE=mock) to run without a key.")
    print(f"Study Buddy running in {application.config['CTX'].mode.upper()} mode.")
    application.run(host="127.0.0.1", port=int(os.environ.get("SB_PORT", "5000")), debug=False)
