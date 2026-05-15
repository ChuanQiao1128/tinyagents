# Skill · check-failure-taxonomy

_Self-check prompt for the taxonomy half of `docs/course/03-gates-and-failure-taxonomy.md`._

---

## Purpose

Test whether you can name the nine failure modes TinyAgents distinguishes, classify a real-world `claude.log` excerpt into the right bucket, and walk the DCRDR cycle (Detect → Classify → Record → Decide → Recover) for an arbitrary failure.

## How to use this skill

1. Paste the prompt below into your LLM of choice.
2. Try the classification task literally — don't peek at the rubric.
3. Compare. If you misclassified one of the canonical patterns, re-read the lesson.

---

## The prompt

```
You are a TinyAgents course tutor. I'm checking my understanding of the
failure taxonomy — the nine distinct shapes of failure TinyAgents
recognizes and the DCRDR cycle that routes each one (Lesson 03,
docs/course/03-gates-and-failure-taxonomy.md).

Ask me these five questions one at a time. After each answer, say
which key ideas it hit and missed. Don't reveal the full correct
answer until I've tried. At the end, give a one-paragraph verdict on
whether I'm ready for Lesson 04 (Auto Loop and Review).

Questions:

1. Name the nine failure modes and, for each, the single most reliable
   signal (file or string) that distinguishes it.

2. Classify these four excerpts:

   (a) "Error: Reached max turns (8)" appears at the end of claude.log;
       filesystem diff shows ~0 changed files.
   (b) Claude finished cleanly, claude.log says "all changes complete";
       filesystem diff shows 0 changed files.
   (c) npm run build exit 0, npm run lint exit 1, lint.log shows
       6 ESLint errors.
   (d) review-decision.json says counts.must-fix > 0 and the issue is
       "POST /api/studio/upload has no Origin/Host check".

3. Walk through the full DCRDR cycle (Detect → Classify → Record →
   Decide → Recover) for excerpt (a) above. Be explicit about which
   artifact each step reads or writes.

4. Why is "human-decision" listed as a failure mode? It doesn't feel
   like a failure — the system is asking for input. What's the
   pedagogical reason for including it in the taxonomy?

5. The taxonomy has nine entries today. If you had to predict the
   tenth one TinyAgents will need based on the four axes of growth
   (Pipeline / Iteration / Human / Output), what would you nominate
   and why?
```

---

## What a good answer looks like

**Q1 — nine modes + signature signal.**

| Failure | Most reliable signal |
|---|---|
| Executor auth failure | `claude.log` strings: "Invalid API key", "not logged in", or the executor never produced any output |
| Max-turns incomplete | `claude.log` contains "Reached max turns" + filesystem snapshot shows few/no changes |
| Permission incomplete | exit 0 + `claude.log` reports success + filesystem snapshot shows zero changes |
| Install failure | `npm install` exit non-zero; `install.log` |
| Build failure | `build.log` exit non-zero, while install succeeded |
| Lint failure | `lint.log` exit non-zero, while build succeeded |
| Review failure (functional) | `review-decision.json` `counts.blocker > 0` in functional category |
| Design issue | `review-decision.json` has design-category issues with severity must-fix / should-fix, OR `design-review.md` has findings |
| Human-decision | `review-decision.json` `counts["human-decision"] > 0` |

If you confused "build failure" with "lint failure", that's the same mistake the system itself used to make pre-Stage-5 routing — re-read the loop 005/006 example.

**Q2 — classification.**

- (a) **Max-turns incomplete.** Both signals match.
- (b) **Permission incomplete.** Exit 0 + claimed success + no file changes is the canonical permission/sandboxing failure.
- (c) **Lint failure.** Build pass + lint fail. Loop 005's exact pattern.
- (d) **Review failure (security category)**, must-fix severity. The Origin/Host check is a Stage 9.6 security finding.

Two correct out of four is a soft fail — the conflation patterns are the precise place the taxonomy earns its keep. Three correct is a pass.

**Q3 — DCRDR for excerpt (a).**

- **Detect**: read `artifacts/claude.log`; observe "Reached max turns (8)". Take filesystem snapshot before and after the Claude run; observe ~0 changes.
- **Classify**: matches the max-turns-incomplete pattern (executor failure, not code failure).
- **Record**: `test-report.md`'s `overall result` becomes `failed-executor` (distinct from `failed`); `next-loop.md` reflects the classification.
- **Decide**: the summarizer chooses the "Fix Claude executor failure" recovery shape. Not a code-fix loop.
- **Recover**: the recommended next loop's title is `Fix Claude executor failure from <loop-slug>`. The actual remediation is at the Claude / max-turns / auth layer — bump `--max-turns`, split the task, or check auth.

A common gap: people remember the "Decide" step ("don't run a code-fix loop") but skip "Record" (writing the classification into a stable place where downstream stages can see it). Both matter.

**Q4 — why "human-decision" is in the taxonomy.**
The key idea: **the deterministic part of the system can't act on it, and pretending it can is exactly the wrong move**. By giving human-decision a slot in the taxonomy:

- The summarizer is allowed to route to "Auto pauses — see `human-questions.md`" rather than guessing.
- The auto driver has a named terminal state (`needs-human-feedback`) instead of "I'll just pick whatever".
- The curriculum surfaces human judgment as a first-class outcome of the loop, not an embarrassment.

In other words, the taxonomy is the system's vocabulary for "things that can happen, including things that mean *stop and ask*". A taxonomy without `human-decision` would silently expand the agent's authority into territory it shouldn't be in. That's a worse failure than any of the others on the list.

**Q5 — the tenth failure mode.**
Open-ended; the goal is whether the candidate's reasoning is grounded in one of the four axes.

Strong nominations (with the axis they sit on):

- **Cross-loop drift** (Axis C / E meta): the second loop in a chain ignored a lesson that the first loop already learned. Surfacing this requires a memory layer (L6.5 on the progress map) that doesn't exist yet — when it does, "drift" becomes a real classifiable failure.
- **Approval timeout** (Axis C): a human-decision item sat unanswered for N days. Today the system doesn't notice; with an approval gate, it could.
- **Publish-failure** (Axis D): `git push` rejected (e.g. non-fast-forward, protected branch). When the Publish Gate ships, this becomes a real bucket distinct from "the code is broken".
- **Deploy-smoke failure** (Axis D): the live deploy returned wrong content under a post-deploy probe. Distinct from review (which ran pre-deploy).

A weak nomination is something orthogonal to the axes ("a new ML model failure mode") — that suggests the candidate hasn't internalized why the taxonomy is shaped the way it is.

## Overall pass criteria

You can move to Lesson 04 (Auto Loop and Review) if you can:

- Name all nine failure modes and their signature signals.
- Classify at least three of the four excerpts correctly.
- Walk the DCRDR cycle for an unfamiliar failure without re-reading the lesson.
- Defend `human-decision`'s presence in the taxonomy in one sentence.
- Propose at least one realistic tenth failure mode that maps to a real axis of growth.

If you missed two or more, re-read `docs/course/03-gates-and-failure-taxonomy.md`'s **The failure taxonomy** table and the loop 002 worked example.
