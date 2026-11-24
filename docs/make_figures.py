"""Draws the three storyboards from the app's real responses (mock mode, temp copy of data/).
Needs Pillow: pip install pillow. Output: docs/storyboard_*.png"""
import json, os, shutil, sys, tempfile
import matplotlib
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import create_app

FD = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
F = ImageFont.truetype(os.path.join(FD, "DejaVuSans.ttf"), 20)
FB = ImageFont.truetype(os.path.join(FD, "DejaVuSans-Bold.ttf"), 20)
FS = ImageFont.truetype(os.path.join(FD, "DejaVuSans.ttf"), 17)
FT = ImageFont.truetype(os.path.join(FD, "DejaVuSans-Bold.ttf"), 30)
INK, MUTE, LINE, BG = (27, 36, 48), (91, 102, 118), (200, 207, 218), (246, 247, 249)
BLUE, GOOD, GOODBG, BAD, BADBG, WARN, WARNBG = (47, 95, 208), (31, 122, 77), (231, 245, 238), (179, 38, 30), (253, 236, 234), (138, 97, 0), (255, 244, 214)
W, H, CAP, GAP = 560, 560, 84, 28


def wrap(d, text, font, width):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=font) <= width:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
    return lines


class Frame:
    def __init__(self, n, caption):
        self.img = Image.new("RGB", (W, H + CAP), "white")
        self.d = ImageDraw.Draw(self.img)
        self.y, self.caption, self.n = 56, caption, n
        self.d.rectangle([0, 0, W - 1, H - 1], outline=LINE, width=2)
        self.d.rectangle([0, 0, W - 1, 40], fill=(226, 232, 240))
        self.d.text((14, 8), f"{n}", font=FB, fill=INK)
        self.d.text((W - 14, 10), "Study Buddy", font=FS, fill=MUTE, anchor="ra")
        self.d.rectangle([0, H, W - 1, H + CAP - 1], fill=BG, outline=LINE, width=2)
        for i, l in enumerate(wrap(self.d, caption, FS, W - 28)[:3]):
            self.d.text((14, H + 8 + i * 24), l, font=FS, fill=INK)

    def box(self, text, x0, fill, outline, font=F, color=INK, w=None, tag=None):
        w = w or W - 80
        lines = wrap(self.d, text, font, w - 28)
        h = len(lines) * 26 + 16 + (22 if tag else 0)
        self.d.rounded_rectangle([x0, self.y, x0 + w, self.y + h], radius=14, fill=fill, outline=outline, width=2)
        yy = self.y + 8
        if tag:
            self.d.text((x0 + 14, yy), tag, font=FS, fill=MUTE); yy += 22
        for l in lines:
            self.d.text((x0 + 14, yy), l, font=font, fill=color); yy += 26
        self.y += h + 10

    def bot(self, t, tag=None): self.box(t, 16, BG, LINE, tag=tag)
    def me(self, t): self.box(t, W - 16 - 300, BLUE, BLUE, color="white", w=300) if False else self.right(t)
    def right(self, t):
        w = min(int(self.d.textlength(t, font=F)) + 40, W - 120)
        self.box(t, W - 16 - w, BLUE, BLUE, color="white", w=w)
    def good(self, t): self.box(t, 16, GOODBG, GOOD)
    def bad(self, t): self.box(t, 16, BADBG, BAD)
    def src(self, label, t):
        lines = wrap(self.d, t, FS, W - 100)
        h = 28 + len(lines) * 22 + 12
        self.d.rectangle([24, self.y, 28, self.y + h], fill=WARN)
        self.d.rectangle([29, self.y, W - 24, self.y + h], fill=WARNBG)
        self.d.text((40, self.y + 6), label, font=FB, fill=INK)
        for i, l in enumerate(lines):
            self.d.text((40, self.y + 32 + i * 22), l, font=FS, fill=INK)
        self.y += h + 12
    def opts(self, items, pick=None):
        for t in items:
            on = t == pick
            self.d.rounded_rectangle([24, self.y, W - 24, self.y + 38], radius=8, outline=BLUE if on else LINE, width=3 if on else 2, fill="white")
            self.d.text((38, self.y + 7), t, font=FS, fill=INK); self.y += 46
    def btns(self, items):
        x = 24
        for label, kind in items:
            w = int(self.d.textlength(label, font=FS)) + 28
            if x + w > W - 16: x = 24; self.y += 48
            fill, out, col = {"primary": (BLUE, BLUE, "white"), "danger": (BADBG, BAD, BAD), "plain": ("white", LINE, INK)}[kind]
            self.d.rounded_rectangle([x, self.y, x + w, self.y + 38], radius=8, fill=fill, outline=out, width=2)
            self.d.text((x + 14, self.y + 8), label, font=FS, fill=col); x += w + 10
        self.y += 50
    def bar(self, label, a, b):
        self.d.text((24, self.y), f"{label}: {round(a*100)}% to {round(b*100)}%", font=FS, fill=MUTE); self.y += 26
        self.d.rounded_rectangle([24, self.y, W - 24, self.y + 10], radius=5, fill=LINE)
        self.d.rounded_rectangle([24, self.y, 24 + (W - 48) * b, self.y + 10], radius=5, fill=BLUE); self.y += 24
    def done(self):
        if self.y > H - 6: print(f"WARNING frame {self.n} overflows by {self.y - H}", file=sys.stderr)
        return self.img


def sheet(title, frames, path):
    cols = 2
    rows = (len(frames) + 1) // 2
    cw, ch = W, H + CAP
    img = Image.new("RGB", (cols * cw + (cols + 1) * GAP, rows * ch + (rows + 1) * GAP + 64), "white")
    ImageDraw.Draw(img).text((GAP, 14), title, font=FT, fill=INK)
    for i, f in enumerate(frames):
        img.paste(f, (GAP + (i % cols) * (cw + GAP), 64 + GAP + (i // cols) * (ch + GAP)))
    img.save(path)


def run():
    out = os.path.join(ROOT, "docs")

    def fresh():  # a clean copy of the demo data for each storyboard
        global tmp
        tmp = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "data"), os.path.join(tmp, "data"))
        cl = create_app(os.path.join(tmp, "data"), mode="mock").test_client()
        return cl, (lambda u, **b: cl.post(u, json=b).get_json())

    c, P = fresh()
    key = {q["id"]: q["key"] for q in json.load(open(os.path.join(tmp, "data", "questions.json")))}

    # ---- storyboard 1: normal session ----
    r = P("/api/session", student="sam", mode="quiz"); sid = r["session"]; q1 = r["question"]
    a1 = P(f"/api/session/{sid}/answer", answer=key[q1["id"]])
    q2 = P(f"/api/session/{sid}/next")["question"]
    wrong = next(o for o in q2["options"] if o != key[q2["id"]])
    a2 = P(f"/api/session/{sid}/answer", answer=wrong)
    q3 = P(f"/api/session/{sid}/next", easier=True)["question"]
    P(f"/api/session/{sid}/answer", answer=key[q3["id"]])
    for _ in range(2):
        q = P(f"/api/session/{sid}/next")["question"]
        P(f"/api/session/{sid}/answer", answer=key[q["id"]] if q["topic"] == "joins" else next(o for o in q["options"] if o != key[q["id"]]))
    s = P(f"/api/session/{sid}/end")
    f1 = Frame(1, "Sam picks Quiz me. The first question is Joins at medium difficulty.")
    f1.bot(q1["text"], tag=f"{q1['topic_label']} \u00b7 {q1['difficulty']}"); f1.opts(q1["options"], key[q1["id"]]); f1.right(key[q1["id"]])
    f2 = Frame(2, "Right answer: confirmed with a source, score goes up, next question gets harder.")
    f2.good(a1["message"]); f2.bar(a1["topic_label"], a1["score_before"], a1["score_after"]); f2.bot(f"Next difficulty here: {a1['next_difficulty']}. Want to keep going?"); f2.btns([("Keep going", "primary"), ("Finish & see summary", "plain")])
    f3 = Frame(3, "Wrong answer on a hard question: called wrong, cites the slide, offers an easier one.")
    f3.bot(q2["text"], tag=f"{q2['topic_label']} \u00b7 {q2['difficulty']}"); f3.bad(a2["message"])
    f3.bar(a2["topic_label"], a2["score_before"], a2["score_after"]); f3.btns([("Dispute / show source", "danger"), ("Try a similar, easier one", "plain")])
    f4 = Frame(4, "After five questions: summary, weak topic and a next step. Scores are saved.")
    f4.bot("Session summary", tag="Joins 2/2 \u00b7 Normalisation 1/3")
    for t in s["topics"]:
        f4.bot(f"{t['label']}: {t['right']}/{t['total']} ({t['status']})")
    f4.bot("Next step: " + s["next_step"]); f4.bot("Your scores are saved for next time.")
    sheet("Storyboard 1: a normal session (Sam)", [f.done() for f in (f1, f2, f3, f4)], os.path.join(out, "storyboard_1_normal.png"))

    # ---- storyboard 2: failure and recovery ----
    c, P = fresh()
    r = P("/api/session", student="sam", mode="quiz"); sid = r["session"]
    q = P(f"/api/session/{sid}/next", question_id="nm5")["question"]
    a = P(f"/api/session/{sid}/answer", answer="2NF")
    d = P(f"/api/session/{sid}/dispute", note="my notes say 2NF")
    g1 = Frame(1, "The bot's answer key is wrong (3NF). The student answers 2NF, which is right.")
    g1.bot(q["text"], tag="Normalisation \u00b7 medium"); g1.opts(q["options"], "2NF"); g1.right("2NF")
    g2 = Frame(2, "Told she is wrong. The dispute button is there straight away.")
    g2.bad(f"That's incorrect. The answer is: {a['answer_key']}. See {a['source']['label']}."); g2.bar("Normalisation", a["score_before"], a["score_after"]); g2.btns([("Dispute / show source", "danger"), ("Keep going", "primary")])
    g3 = Frame(3, "She sends the dispute with a short note. The bot re-reads the slide and admits the mistake once.")
    g3.right("my notes say 2NF"); g3.src(d["source"]["label"], d["source"]["passage"]); g3.good(d["messages"][1])
    g4 = Frame(4, "Score restored, question pulled from her quiz and flagged, quiz carries on.")
    g4.bar("Normalisation", a["score_after"], d["score_restored"]); g4.bot(d["messages"][2]); nq = d["next"]["question"]
    g4.bot(d["messages"][3]); g4.bot(nq["text"], tag=f"{nq['topic_label']} \u00b7 {nq['difficulty']}")
    sheet("Storyboard 2: failure and recovery (wrong answer key)", [f.done() for f in (g1, g2, g3, g4)], os.path.join(out, "storyboard_2_failure.png"))

    # ---- storyboard 3: lecturer (continues from storyboard 2's data so the flag is there) ----
    smp = c.get("/api/lecturer/samples").get_json()
    flags = c.get("/api/lecturer/flags").get_json()
    cls = c.get("/api/lecturer/class").get_json()
    sug = c.get("/api/lecturer/suggestion").get_json()
    chunks = json.load(open(os.path.join(tmp, "data", "chunks.json")))
    h1 = Frame(1, "Dr Reid uploads slides and notes. These are the only material the bot may use.")
    h1.bot("Module files", tag="Lecturer page, step 1")
    for n in sorted(os.listdir(os.path.join(ROOT, "data", "module"))): h1.opts([n])
    h1.btns([("Upload and index", "primary")]); h1.good(f"Indexed {len(chunks)} slides/sections across: " + ", ".join(t["label"] for t in [{"label": x} for x in ["Relational model", "SQL basics", "Joins", "Normalisation", "Indexes"]]) + ".")
    h2 = Frame(2, "Three sample questions to check. She approves one, edits one key, rejects one.")
    for i, (qq, act) in enumerate(zip(smp, ["Approve", "Save edited key", "Reject"])):
        h2.bot(qq["text"], tag=f"{qq['topic']} \u00b7 key: {qq['key']}"); h2.btns([(act, "danger" if act == "Reject" else "plain")]) if False else None
    h2.btns([("Approve", "plain"), ("Edit key", "plain"), ("Reject", "danger")])
    h3 = Frame(3, "A student's dispute arrives on the review list. No student name is shown.")
    fq = flags[0] if flags else None
    h3.bot(fq["text"], tag=f"Review list \u00b7 {fq['topic']} \u00b7 {fq['flags']} flag") if fq else None
    h3.opts([o + ("  (key)" if o == fq["key"] else "") for o in fq["options"]]) if fq else None
    h3.src(fq["source"]["label"], fq["source"]["text"].split(". ")[0] + ".") if fq else None
    h3.btns([("Fix key", "plain"), ("Remove question", "danger")])
    h4 = Frame(4, "Class view is anonymous. Topics with under 3 students are hidden. She decides about the suggestion.")
    h4.bot("Class weak topics", tag="Lecturer page, step 4")
    for t in cls["topics"]: h4.bar(t["label"], 0, t["percent"] / 100) if False else h4.bot(f"{t['label']}: {t['percent']}% correct")
    h4.bot("Hidden (under 3 students): " + ", ".join(cls["hidden"])); h4.src("Suggestion", sug["text"])
    sheet("Storyboard 3: the lecturer's side (Dr Reid)", [f.done() for f in (h1, h2, h3, h4)], os.path.join(out, "storyboard_3_lecturer.png"))


if __name__ == "__main__":
    run()
