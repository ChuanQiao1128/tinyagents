# Skill · check-four-step-loop

_Self-check prompt for `docs/course/01-four-step-loop.md`._

---

## Purpose

Test whether you can explain — without re-reading the lesson — why the four-step loop is the floor of useful AI Agent SDLC, what each step's contract is, and what's lost if any step is collapsed into another.

## How to use this skill

1. Paste the prompt block below into Claude / GPT / your preferred LLM, or ask a peer to act as the interviewer.
2. Answer each question in turn — out loud is fine, written is better.
3. After all five questions, compare your answers against the rubric at the bottom.

This is not a graded exam. It's a sanity check that the lesson actually landed in your head, not just on disk.

---

## The prompt

```
You are a TinyAgents course tutor. I'm checking my understanding of the
four-step loop (Research → Plan → Implement → Test) — the first lesson
in the TinyAgents AI Agent SDLC course (docs/course/01-four-step-loop.md).

Ask me these five questions one at a time. After each answer I give,
briefly say which key idea it hit and which it missed. Don't tell me the
full correct answer until I've tried. At the end, give a one-paragraph
overall verdict on whether I can move to Lesson 02 (Artifacts).

Questions:

1. Walk me through the four steps of one TinyAgents loop and the
   filename that step produces.

2. Why is "Research" a separate step rather than just the first part of
   "Plan"?

3. The Test step distinguishes "no-tests-run" from "passed" and
   "failed". Why does that three-way distinction matter for what
   happens next?

4. Loop 005 and loop 006 form a pair: 005 built code with a lint
   failure; 006 was scoped narrowly to fix lint. Why is that two
   loops, not one bigger loop?

5. If you had to merge two of the four steps into one, which pair would
   you choose, and what specific capability would you lose?
```

---

## What a good answer looks like

For each question, the key idea your answer should hit:

**Q1 — the four steps and their artifacts.**
- Research → `research.md` (snapshot of project + goal)
- Plan → `plan.md` and `implementation-prompt.md` (intended change + literal prompt)
- Implement (Claude execute) → `artifacts/claude.log` (transcript + files actually changed in target)
- Test → `test-report.md` + per-command logs in `artifacts/`

If you got 3/4 file names right and the order correct, that's a pass. Missing the distinction between `plan.md` and `implementation-prompt.md` is the most common gap.

**Q2 — research is separate.**
The key idea: **deterministic reproducibility**. Running `scan` twice should produce the same `research.md`. Mixing research into the prompt step couples "what's true now" with "what we're going to do about it", which makes debugging harder and breaks re-runnability. A weaker but still acceptable answer: separation of concerns / read-only vs read-write.

**Q3 — three-way Test outcomes.**
The key idea: **each outcome routes to a different kind of next loop**. `no-tests-run` triggers "Add verification scripts"; `passed` triggers "Pick the next feature"; `failed` triggers a focused fix. Collapsing `no-tests-run` into `passed` (or `failed`) loses the routing signal — the system would either run a fix loop on code that builds fine or report success on code that was never verified.

**Q4 — loop 005 → loop 006.**
The key idea: **a loop is the unit of recoverable work**. Each loop has a narrow scope. Loop 006's scope is literally "fix lint failure from 005, nothing else". A single big loop would have to do both the feature and the fix; if Claude got the second part wrong, the first part's work would be tangled into the same blast radius. Narrow loops also keep `next-loop.md` recommendations interpretable.

**Q5 — merge two steps.**
There's no "right" answer here — the question is testing whether you can articulate the cost of merging. Reasonable merges (with their costs):

- Merge Plan into Research: lose deterministic re-runnability of `prompt`. Also makes `research.md` non-trivial to re-read because it now contains both "what is" and "what we'll do".
- Merge Implement into Test: lose the ability to inspect what Claude did before testing. Failed runs become harder to classify because the test failure absorbs the implementation log.
- Merge Plan into Implement: lose the human-readable intent doc. `implementation-prompt.md` would still exist but `plan.md` (the outline) goes away, hurting the audit trail.

A weak answer is "I'd merge them because it's faster". The trick is to surface what *specific capability* the merge costs.

## Overall pass criteria

You can move to Lesson 02 if you can:

- Name all five files the four-step loop produces.
- Explain why research is separate from plan in one sentence.
- Predict the routing differences across the three Test outcomes.
- Defend the loop-as-unit-of-work pattern with loops 005/006 as evidence.

If you missed two or more, re-read `docs/course/01-four-step-loop.md`'s **Walkthrough** section and try again.
