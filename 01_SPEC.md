# Study Buddy spec

Student ID: 3196490
Version: draft 2, updated after the prototype was built and tested. Draft 1 was written before any code.
Changes from draft 1 are listed in section 12. Requirements S1 to L5 are unchanged.

## 1. What it is

Study Buddy is a chatbot that quizzes a student on their own module material. It picks questions from the lecturer's slides and notes, makes the next question easier or harder depending on how the student is doing, and keeps a score per topic so it can say what to revise. When it gets something wrong, the student can dispute it and the bot checks its own source.

This spec turns my Lab 1 research and the Lab 2 design (interaction flow, three storyboards) into something I can build and test. The example module is Databases, with made-up content.

## 2. Users

Primary user: a first-year student revising for a test (Sam in the storyboards). She wants practice on her own module and a clear next step.

Secondary user: the module lecturer (Dr Reid). She supplies the material, checks sample questions, fixes flagged questions and reads class-level weak topics. She doesn't use the bot to study.

## 3. Scope

In scope for the prototype:

- Student chat with three modes: quiz me, pick a topic, review weak topics.
- Questions built from retrieved module slides and notes, with a source reference on every question.
- Adaptive difficulty and a score per topic, saved between sessions.
- A dispute button that re-checks the source and recovers if the answer key was wrong.
- A lecturer page for sample review, a review list of flagged questions, and anonymous class weak topics.
- A mock mode that runs with no API key, and a live mode that calls a model.

Out of scope: logins, real student data, more than one module, multi-user deployment, mobile layout, exam-grade question quality.

## 4. Requirements

Student side

| ID | Requirement |
|---|---|
| S1 | The student picks a module and then a mode (quiz me, pick a topic, review weak topics). |
| S2 | Every question is built from retrieved module content and shows its source (lecture and slide) once answered. |
| S3 | An answer is checked against the retrieved source, not against the model's general knowledge. |
| S4 | A correct answer gets a short confirmation. The topic score goes up. |
| S5 | A wrong or partly right answer is called wrong, explained with the lecture and slide, and the topic score goes down. The bot offers a similar, easier question. A vague answer is not praised. |
| S6 | "I don't know" is accepted as an answer and handled like a wrong one, with a smaller score drop. |
| S7 | After each question the bot asks whether to keep going. |
| S8 | Ending a session shows a summary: strong topics, weak topics, and a next step. Scores are saved for next time. |

Failure and recovery

| ID | Requirement |
|---|---|
| F1 | After every verdict on a wrong answer, the student sees a "Dispute / show source" button. |
| F2 | On dispute, the bot re-reads the retrieved source and compares it with the answer key. |
| F3 | If the key was wrong, the bot says so once without arguing, gives the right answer, restores the topic score, removes the question from that student's quiz, adds a flag to the lecturer's review list, and carries on with another question on the same topic. |
| F4 | If the key was right, the bot shows the source passage and leaves the score alone. |
| F5 | The student never has to type a reason for the dispute to work, but can. |

Lecturer side

| ID | Requirement |
|---|---|
| L1 | The lecturer loads the module files (slides and notes). They are the only material the bot may use. |
| L2 | After indexing, the lecturer sees three sample questions and can approve, edit the answer key, or reject each one. Rejected questions are never used. |
| L3 | Flags from student disputes appear on a review list with the question, the answer key and the source slide. The lecturer can fix the key or remove the question. |
| L4 | The class view shows percent correct per topic, summed across students, with no names. It only shows a topic once at least three students have answered it. |
| L5 | The bot suggests the weakest topic as something to spend lecture time on. The lecturer decides. (Build last, cut first.) |

## 5. How the rules work

Topic score. A number from 0 to 1 per student per topic. A topic with no history starts at 0.5, so the bot works without data on a new student (the cold-start problem in S7 of my Lab 1 notes).

| Event | Change |
|---|---|
| Right answer | +0.15 |
| Wrong or partly right | -0.10 |
| "I don't know" | -0.05 |
| Successful dispute | the drop from that question is undone |

Scores stay between 0 and 1.

Difficulty. Easy below 0.35, medium from 0.35 to 0.60, hard above 0.60. When a topic has no score yet, the first question uses the difficulty of the previous question. That is why Sam gets a hard normalisation question right after answering a joins question correctly.

Next topic. In quiz me, the bot picks the topic with the lowest score, and breaks ties by the topic asked least in this session. In review weak topics, it only picks from topics with a score under 0.5 and at least two answers. In pick a topic, the student chooses.

Answer checking. Multiple choice and short answers. For short answers, the bot compares the student's answer with the key and the retrieved passage, and treats anything missing a required term as partly right.

Retrieval. The module files are split into one chunk per slide or note section, each tagged with lecture and slide. A question is made from the top-ranked chunks for its topic. Ranking is TF-IDF or keyword matching, which is enough for one module (S10 in my shortlist found RAG better than retraining for small collections).

Question generation. The model gets one or two retrieved chunks and returns JSON: question, options, answer key, topic, difficulty, source. A verification step then checks the answer key against the source chunk. If it doesn't match or the check is unsure, the question is dropped and regenerated, up to two times. This is my answer to the wrong keys reported in S1 and S3. It is not a guarantee, and the dispute route exists because of that.

Review status of each question: unreviewed, approved, rejected, flagged, removed. Unreviewed questions can be served. The lecturer only sees three samples up front, so a bad key can get through. That is the gap the student dispute covers.

Pulling a question for everyone. The first dispute removes the question for that student and flags it. Three disputes from different students remove it for all students until the lecturer reviews it.

## 6. Data

Everything is stored in JSON files under `data/` (SQLite if that turns out easier).

- `chunks`: id, lecture, lecture_title, slide, topic, text. Built from `data/module/*.md`.
- `questions`: id, topic, difficulty, type (mcq or short), text, options, key, required_terms (short answers only), source chunk id, status, dispute count.
- `scores`: student id, topic, score, answers given, answers correct (the class view needs the correct count).
- `flags`: id, question id, student id (kept internally, never shown to the lecturer), time, optional note, kind (key_wrong or unsure), resolved.
- `students`: id and first name of the made-up demo users. `samples`: the three question ids shown to the lecturer.

Sam and a few other students are made-up demo users. No real names, emails or student numbers anywhere.

## 7. Modes and keys

Mock mode (default). Questions come from a hand-written bank in `data/questions.json`. One question in the bank is deliberately wrong (it says 3NF removes partial dependencies, which is wrong because 2NF does) and is built to get past verification, so the failure story can be replayed.

Live mode. `llm.py` calls a model to generate and verify questions. The key is read from an environment variable. The repo contains a `.env.example` with an empty value and a `.gitignore` entry for `.env`. No key is ever committed.

## 8. Architecture

A small Python and Flask app with one plain HTML page for the student chat and one for the lecturer. Modules: `retrieval.py`, `llm.py` (mock and live), `quiz.py` (selection, scoring, grading), `disputes.py`, `lecturer.py`, and JSON storage. Everything that touches the model goes through `llm.py`, so swapping mock for live changes one file.

## 9. Acceptance tests

Each of these comes from a storyboard and should run as a scripted test in mock mode.

| # | Scenario | Must be true at the end |
|---|---|---|
| T1 | Sam's normal session (storyboard 1). Right answer on joins, wrong answer on a hard normalisation question, five questions in all. | Joins score went up, normalisation score went down, the wrong answer cited Lecture 4 slide 12, an easier similar question was offered, the summary names normalisation as weak, scores are saved. |
| T2 | Failure and recovery (Lab 2 failure image). Sam answers 2NF to the question with the wrong key and disputes. | The bot admits the key was wrong and cites Lecture 4 slide 9, her score is back to what it was, the question is gone from her quiz, a flag exists, and a new question on the same topic follows. |
| T3 | Dispute where the key was right. | The source passage is shown and the score is unchanged. |
| T4 | Dr Reid's session (storyboard 2). She approves one sample, edits one key and rejects one. | The rejected question is never served, the edited key is used, and the flag from T2 shows on her review list with no student name. |
| T5 | Class view. | Topic percentages appear without names, and a topic with fewer than three students is hidden. |
| T6 | The student says "I don't know". | Handled as a wrong answer with the smaller score drop. |
| T7 | Clean-folder run. | The unzipped project starts in mock mode with no key and no other setup beyond installing the requirements. |

## 10. Risks and known limits

- A wrong key can still reach a student. Verification lowers the chance and the dispute button covers the rest, but only if the student notices.
- The re-check reads the same retrieved material. If retrieval picked the wrong slide, the bot could confirm its own mistake.
- Lecturer review covers three samples, not the whole pool.
- The score numbers and thresholds above are my starting guesses and will need tuning once I can run sessions.
- Students who most need revision may be the ones least likely to open the bot (S9). The prototype doesn't address this.
- The tracking part has the least precedent in my related work (S6 and S7 test on datasets, not a deployed bot), so the per-topic score is a simple design of my own, not a published method.

## 11. Build order

1. Module content and `chunks`.
2. Retrieval.
3. Mock bank and quiz loop (S1 to S8).
4. Dispute path (F1 to F5).
5. Storage and session summary.
6. Lecturer page (L1 to L4).
7. Tests T1 to T7.
8. Live mode in `llm.py`.
9. L5 suggestion, if there is time.

## 12. As built: changes from draft 1

Status: all of S1 to S8, F1 to F5 and L1 to L5 are implemented. Tests T1 to T7 pass as scripted tests in mock mode (`python -m pytest -q`), plus seven extra checks (live path with the network call faked, live mode refusing to start without a key, three upheld disputes pulling a question, lecturer fixing a key, review mode and score bounds, a check of every bank question, and the optional lecturer password used when hosting). Live mode has not been run against a real model.

Decisions the draft left open:

- Cold start. A topic with no answers yet uses the difficulty of the previous question (medium at the start of a session). Once it has answers, its score decides. This resolves the draft's two statements (new topics start at 0.5, and "no score yet uses the previous difficulty").
- Topic strengths in the summary. Strong is a score above 0.60, weak is 0.60 or below. These match the difficulty thresholds.
- Dispute undo. A successful dispute reverses the exact change that answer made, and removes it from the answer count. The answer no longer counts in the session summary.
- If the key was wrong but the student's answer was not the corrected one, the score is still restored (the question was bad) and the bot says the question shouldn't count, rather than "you were right".
- Pulling for everyone. Only disputes where the key was found wrong count, from three different students. A dispute where the key was right does not count.
- "Unsure" re-check. If the re-check cannot settle it, the bot shows the passage, leaves the score alone and flags the question for the lecturer (kind: unsure). It does not remove the question.
- One dispute per answer, and only on the most recent answer. "I don't know" answers do not show the dispute button, because there is no verdict to dispute.
- Status handling. Unreviewed, approved and flagged questions can be served. Rejected and removed ones cannot. A lecturer fix returns a question to approved and back to the disputing student too.
- Short answers. Each has a list of required terms (with "a|b" alternatives). All present is right, some present is partly right (treated as wrong), none is wrong. If the lecturer edits a short answer key, grading falls back to matching the new key text.
- Edit key (L2). For multiple choice, the new key must be one of the options.
- Ties and picking. Quiz me picks the lowest score, then the topic asked least this session, then module order. Easier-similar question: same topic, one difficulty level below the question just missed.
- Verification and re-check in mock mode. Verification only checks that the key's words appear in the source chunk, so the planted 3NF error passes. The dispute re-check reads the single best-matching sentence, which catches it. For 5 of 30 bank questions the mock re-check answers "unsure" instead of "key right". This is safe but untuned.
- Replay hook. In mock mode the next-question call accepts a question id, used by the "Demo: replay the wrong-key failure" button and by tests T2 to T4. It is ignored in live mode.
- Lecturer upload takes .md or .txt files with `# Lecture N: Title` and `## Slide N` headings. In mock mode new files are indexed, but only the hand-written bank can be asked. New material becomes questions in live mode.
- Seed data. Sam starts with joins 0.50 and normalisation 0.62 (other topics 0.80) so storyboard 1 plays out exactly. Indexes has answers from only two students, so it is hidden in the class view until a third answers.
- Live mode details. The key comes from `ANTHROPIC_API_KEY` (or a git-ignored `.env`). Mode comes from `SB_MODE`, default mock. Missing key in live mode stops the app with a clear message instead of falling back. Model name from `SB_MODEL`.
- Stack. Python 3, Flask, plain HTML and JavaScript, JSON files, TF-IDF written in pure Python. Only Flask (and pytest for tests) are installed.

Known limits added by building it: score deltas and thresholds are still untuned guesses; the dispute and flag data is stored in one process with a file lock, so it is not for multi-user deployment; the mock question bank has 30 questions across 5 topics.
