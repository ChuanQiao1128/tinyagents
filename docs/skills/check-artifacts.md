# Skill · check-artifacts

_Self-check prompt for `docs/course/02-artifacts.md`._

---

## Purpose

Test whether you can defend the choice to keep TinyAgents' state on disk as markdown + JSON files, explain which artifact carries which contract, and predict what would break if the convention changed.

## How to use this skill

1. Paste the prompt block below into Claude / GPT / your preferred LLM.
2. Answer each question — bullet points are fine; precise filenames matter more than full prose.
3. Compare against the rubric.

---

## The prompt

```
You are a TinyAgents course tutor. I'm checking my understanding of
artifacts as the project's external memory and API (TinyAgents course
Lesson 02, docs/course/02-artifacts.md).

Ask me these five questions one at a time. After each answer, say
briefly which key ideas it hit and which it missed; don't reveal the
full answer until I've tried. At the end, give a one-paragraph verdict
on whether I'm ready for Lesson 03 (Gates and Failure Taxonomy).

Questions:

1. Inside a TinyAgents loop folder, name at least eight files and what
   each one contains. (Don't worry about exact filename casing — concept
   matters.)

2. `review-decision.json` is the only machine-readable file in the loop
   folder; everything else is markdown. Why JSON for that one and not
   for the others?

3. A new contributor proposes moving loops/ state into a SQLite database
   for "fast querying". What's the architectural rebuttal that goes
   beyond just "it's faster to read files"?

4. `auto-report.md` lives at the repo top level, not inside any loop
   folder, and is overwritten on every `auto` run. Why both of those
   choices?

5. If you wanted to add a sixth review category called "accessibility",
   list the minimum set of files / locations you'd have to touch. (Be
   explicit — the artifact contract is what's being tested.)
```

---

## What a good answer looks like

**Q1 — eight files in a loop folder.**
Acceptable list (any 8 of these is fine):

- `context-summary.md`
- `research.md`
- `plan.md`
- `implementation-prompt.md`
- `artifacts/claude.log`
- `artifacts/install.log`
- `artifacts/build.log` (or other test-runner log)
- `test-report.md`
- `review-report.md`
- `review-decision.json`
- `design-review.md`
- `human-questions.md`
- `fixture-swap.md`
- `next-loop.md`
- `artifacts/screenshots/*.jpg`

You should be able to say what each one carries — not just name the file.

**Q2 — JSON for the decision file.**
The key idea: **different readers**. `review-decision.json` is the only file the *auto driver* needs to make a state-machine decision (it reads `decision_state`, `counts`, `can_publish`, `requires_human`, `top_next_task`). Machines need structured fields; humans need prose. Same underlying data, two presentations. A weaker but correct answer: "the auto driver needs to grep specific keys without parsing markdown".

**Q3 — rebuttal to the database proposal.**
A strong answer hits at least three of these:

- `cat` / `less` / any text editor is the universal viewer; a database costs the learner a client, a schema, and an access path.
- Markdown survives `git diff` and lets selected loops be committed as evidence; binary DB rows do not.
- Schema changes in JSON (e.g. R2.2's rename of `suggested_next_task` → `top_next_task`) are a search-and-replace + a `schema_version` bump. In a DB, the same change requires migration tooling and rollback paths.
- The whole pedagogical promise of TinyAgents is "every decision is visible on disk". A database breaks that promise.
- Performance was never the bottleneck — there are tens of files per loop, not millions.

If your answer is only "files are easier to read", that's a weak pass. The pedagogical argument is the load-bearing one.

**Q4 — `auto-report.md` location + overwrite.**

- *Top level*, not inside a loop folder: it summarizes a *multi-loop run*, not a single loop. Putting it inside any one loop folder would be misleading; putting it above the per-loop folders is structurally honest.
- *Overwritten*: append-only logs accrete and become unreadable. Each `auto` run produces one self-contained snapshot. If a specific run matters historically, you copy it into `docs/case-studies/`. The design pushes back against "log everything forever" because that habit buries the interesting events.

Either part can be answered correctly without the other; full credit needs both.

**Q5 — adding an "accessibility" review category.**
Minimal touchpoints:

- `review-report.md` rendering — add an "Accessibility" section in the markdown writer.
- `review-decision.json` schema — add a `categories.accessibility: {ran, summary, issues}` entry.
- `build_decision()` aggregator (in `tiny_agents.py`) — add accessibility issues into the unified issue list and the by-category grouping.
- The review prompt template (the Claude call for quality review) — instruct Claude to also produce findings with `category: "accessibility"`.

Things you would *not* need to touch: `test-report.md`, `research.md`, `next-loop.md` (it reads from `review-decision.json`'s aggregated state, not from individual categories). If your answer includes those, you're touching more than necessary.

## Overall pass criteria

You can move to Lesson 03 if you can:

- List 8+ artifacts and the role of each.
- Defend "markdown + JSON, not a database" with at least 3 distinct reasons.
- Predict the minimal change-set to add a new review category, without rewriting unrelated stages.

If you missed two or more, re-read `docs/course/02-artifacts.md`'s **What each artifact carries** table and the **Why markdown + JSON, not a database** section.
