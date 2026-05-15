# Progress Map

_TinyAgents' real status across four independent axes. Not a percentage._

---

## The 4-axis frame

A single "% done" hides what's actually built and what isn't. TinyAgents grows along four axes that move independently. The honest status looks like a small grid, not a progress bar.

The L0–L10 levels below are reference points — capabilities a learner can recognize when they meet them in another agent project. A level being "current" means TinyAgents reliably demonstrates that capability today, with evidence in `loops/` or in committed code.

---

## Level reference (what each L number means)

| L | Capability | Lives on axis |
|---|---|---|
| **L0** | Goal → one LLM output | A — pipeline depth |
| **L1** | + test gate (build / lint / typecheck / test) | A |
| **L2** | + failure routing in the summarizer | B — iteration count |
| **L3** | + multi-loop auto with stop conditions | B |
| **L4** | + Review (functional / scope / security / content / docs / visual) | A |
| **L5** | + human-questions.md written for human-decision items | C — human integration |
| **L6** | + answer injection (next loop reads the user's answers) | C |
| **L6.5** | + cross-loop memory (lessons.md feeds future prompts) | E — meta / not in the 4 axes |
| **L7** | + approval gate for irreversible actions | C |
| **L8** | + git publish gate (commit + push, human-approved) | D — output destination |
| **L9** | + deploy gate (Vercel / CF / similar, gated on review) | D |
| **L10** | + Studio UI viewer + production monitoring hooks | D |

L6.5 is intentionally fractional: cross-loop memory is a *meta-capability* that touches the prompt-construction step rather than adding a new axis. It is its own design problem and gets its own course module when it lands.

---

## Where TinyAgents is today, by axis

```
            L0  L1  L2  L3  L4  L5  L6  L6.5 L7  L8  L9  L10
A (pipe)    ✅  ✅  ✅  ✅  🟡   —   —   —   —   —   —   —
B (iter)    ✅  ✅  ✅  ✅  —   —   —   —   —   —   —   —
C (human)   ✅  ✅  ✅  ✅  ✅  🟡   ⬜   ⬜   ⬜  —   —   —
D (output)  ✅  ✅  ✅  ✅  ✅   —   —   —   —   ⬜  ⬜  ⬜

Legend:  ✅ complete & dogfooded   🟡 partial / known gap   ⬜ planned   — n/a for that axis
```

**Read it as:**

- **Axis A — Pipeline depth: L4 (partial).** Review system runs end-to-end across five categories. The "partial" is in L4 specifically because (1) visual review's mobile viewport is intentionally deferred and (2) the dev-mode Studio screenshot path doesn't exist yet, so design review of the actual editor UI is impossible today.
- **Axis B — Iteration count: L3.** `tiny_agents.py auto` chains loops with summarizer-driven routing, stops on `done` / `needs-human-feedback` / `max-loops`. Evidence: loop 008's `auto-report.md` shows a single-loop completion with 27/27 hard criteria pass.
- **Axis C — Human integration: L5 (partial).** `human-questions.md` is written when review surfaces human-decision items. The reading side (L6) doesn't exist — the user answers in the markdown file, but the next loop doesn't yet consume those answers automatically. This is the most concrete gap and is what the planned R3 stage targets.
- **Axis D — Output destination: local target project.** Files land in `../portfolio-site/` (or wherever `--project` points). Nothing past that — no git commit, no push, no deploy, no domain.

---

## Concrete evidence for each ✅

(For learners who want to verify the status by reading something, not by trusting the table.)

| Cell | Verify by reading |
|---|---|
| A-L1 test gate | `loops/005-.../test-report.md` (lint fails) + `loops/006-.../test-report.md` (focused fix passes) |
| A-L4 review | `loops/008-.../review-report.md` + `loops/008-.../review-decision.json` |
| B-L2 failure routing | `loops/002-.../next-loop.md` ("Fix Claude executor failure", not "Fix the code") |
| B-L3 auto | top-level `auto-report.md` (loop 008's snapshot) |
| C-L5 human-questions | `loops/008-.../human-questions.md`, `loops/010-.../human-questions.md`, `loops/013-.../human-questions.md` |
| D — local project | the target lives at `../portfolio-site/`, `.gitignore`'d here |

Everything marked ✅ has at least one loop folder demonstrating it. Anything marked 🟡 or ⬜ explicitly does not — don't read the docs as evidence of working code in those cells.

---

## The next recommended learning step (NOT the next feature)

**T1 — Test harness for TinyAgents itself.**

Reasoning:

- The Review system's schema just changed (`schema_version` 1 → 2 in R2.2). Nothing automatically verifies that the renames didn't break a downstream consumer.
- As the project moves into L5 → L6 (Human Feedback), the surface area for "I edited the script and broke an existing path without noticing" grows fast.
- A test harness with a fake-Claude fixture (deterministic LLM responses) lets the project change its own code with confidence — which is exactly what every later layer requires.

**T1 specifically should produce:**

- `tests/` directory.
- `tests/fake_claude.py` — a deterministic stub that emits canned `claude.log` payloads keyed by prompt fingerprint.
- `tests/test_summarize.py` — covers Stage 5 routing across the 4 outcomes (`no-tests-run` / `passed` / `failed-tests` / `failed-executor`).
- `tests/test_review_decision.py` — covers `build_decision()` across the 4 decision states.
- `tests/fixtures/` — small canned `test-report.md` and category-issue lists.

T1 is **not** a new feature. It is a defensive investment that the project should have made one level earlier and is making now because it's about to add risk.

---

## What is explicitly NOT yet built

Listed here so a reader doesn't have to grep the table:

- **L5 (full)**: `human-questions.md` is written, but nothing reads the user's answers back into the next loop. The "loop" in human-feedback is currently a one-way wall.
- **L6**: answer injection.
- **L6.5**: cross-loop memory / lessons accumulation.
- **L7**: approval gate.
- **L8**: git publish gate.
- **L9**: deploy gate.
- **L10**: Studio UI viewer, production monitoring.

Each of these is a real piece of work, not a configuration flip. Course modules for L5/L6 onward will be written **after** the corresponding stage ships, not before — see `00-overview.md` for why we refuse to document fictional layers.

---

## Why the progress map is here at all

Three reasons:

1. **Anti-overclaim.** A reader who lands in `docs/course/` can see at a glance what TinyAgents really does versus what it could do.
2. **Anti-feature-creep.** When a new idea comes up (a YAML DSL, a multi-agent split, a plugin system), the map tells us whether we're moving along a useful axis or sideways into noise.
3. **A self-grading rubric.** Every time a new stage ships, the corresponding cell in this map flips from ⬜ to ✅. The map is the project's commit message at the architecture layer.

The map is updated by hand — see `docs/stage-roadmap.md` for the engineering-side stage-by-stage history.
