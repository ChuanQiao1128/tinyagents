# 02 · Artifacts

_Every meaningful step writes a file. The files are the API, the audit trail, and the next loop's context. Why TinyAgents commits to markdown + JSON on disk, and what each artifact carries._

---

## The five teaching questions

### 1. What does this layer make possible?

An AI Agent SDLC where **every decision is inspectable after the fact, without re-running anything**. A learner who lands in `loops/008-.../` can read the folder bottom-up and reconstruct exactly what the system thought at every step. The artifacts replace process state with file state. They are the project's external memory.

### 2. What concrete failure happens without this layer?

Without on-disk artifacts, every meaningful piece of information lives in the agent's head, in the terminal scrollback, or in chat history. Each of these is lossy:

- **Terminal scrollback** wraps and disappears.
- **Chat history** isn't structured — you can't tell at a glance which message contained the plan vs which contained the result.
- **Agent context** is non-deterministic and resets every session.

When something goes wrong (and at this stage, things go wrong all the time), the recovery cost is the cost of reconstructing the lost information. Artifacts make that cost ~zero — read the file. No artifacts means rerunning the whole flow, or guessing.

### 3. Where is the boundary between this layer and the previous one?

The previous layer (module 01, the four-step loop) already writes some files — `research.md`, `plan.md`, etc. This module is not the *introduction* of artifacts, it's the **promotion of artifacts to first-class status**: every later stage (review, auto, human-feedback) communicates with every other stage by reading and writing these files. The contract is on disk, not in function signatures.

Phrased differently: module 01 used files because it was convenient. Module 02 commits to files because that's the only thing that makes the rest of the project teachable.

### 4. What new artifact does this layer leave on disk?

The full set, organized by who writes them.

```
loops/<NNN>-<slug>/
├── context-summary.md       ← (Stage 1) loop header / metadata
├── research.md              ← (Stage 2) project + goal snapshot
├── plan.md                  ← (Stage 3) intended change
├── implementation-prompt.md ← (Stage 3) literal prompt to Claude
├── artifacts/
│   ├── claude.log           ← Claude executor transcript
│   ├── install.log          ← npm install output
│   ├── build.log            ← `npm run build` output
│   ├── lint.log             ← `npm run lint` output
│   ├── test.log             ← `npm test` output (when present)
│   └── screenshots/         ← (Stage 9.7) Playwright captures
├── test-report.md           ← (Stage 4) overall verification result
├── review-report.md         ← (Stage 9.5/9.6) judgment beyond test
├── review-decision.json     ← (Stage 9.6) machine-readable decision
├── design-review.md         ← (Stage 9.7) visual review only
├── human-questions.md       ← (Stage 9.6) human-decision items
├── fixture-swap.md          ← (Stage 9.7.5) when --fixture was used
└── next-loop.md             ← (Stage 5) what the next loop should do
```

Plus, at the top level of TinyAgents:

```
TinyLocalAgents/
├── goals/*.md               ← goal-spec (you write these)
└── auto-report.md           ← (Stage 8) one-line summary of an `auto` run
```

### 5. Where would the SDLC break if this layer were skipped?

Every later module assumes these files exist and have a stable shape. Skip artifacts and:

- **Module 04 (auto loop)** can't decide what kind of next loop to run — it reads `test-report.md` and `review-decision.json` to make that call.
- **Module 03 (gates)** can't classify failures — it reads `artifacts/claude.log` to distinguish "max-turns hit" from "code failed tests".
- **Review** has nothing to write its findings into.
- **Human feedback** has nowhere to leave the user's answers.

There is no later layer that survives the removal of artifacts. The whole rest of the curriculum is downstream of *files exist and are reliable*.

---

## What each artifact carries

The point of the table below isn't to summarize each file's content (you can `cat` them) — it's to make the **role** of each file explicit.

| File | Role | Writer | Readers |
|---|---|---|---|
| `goals/<name>.md` | The contract: hard criteria, soft criteria, scope rules, visual direction | the human | `scan`, `prompt`, every review category |
| `context-summary.md` | Loop header: task, time, agent, goal-file path | `new` | the human, the prompt builder |
| `research.md` | Project + goal snapshot at loop start | `scan` | `prompt`, future loops |
| `plan.md` | Human-readable outline of intended change | `prompt` | the human, Claude (indirectly via the implementation prompt) |
| `implementation-prompt.md` | The literal prompt Claude received | `prompt` | Claude (input), the human (audit) |
| `artifacts/claude.log` | Full Claude session transcript | the executor | the summarizer, the human |
| `artifacts/install.log` | `npm install` output (post-Claude) | the install gate | `test`, the human |
| `artifacts/*.log` (build / lint / test / typecheck) | Per-command verification output | `test` | `test-report.md`, the summarizer |
| `test-report.md` | Top-line result: `no-tests-run` / `passed` / `failed` | `test` | the summarizer, the review aggregator |
| `review-report.md` | Findings across 6 categories (functional / scope / security / content / docs / design) | `review` | the human, future loops |
| `review-decision.json` | Machine-readable decision: state, counts, top_next_task, can_publish, requires_human | `review` | the auto driver, future gates (Stage 10) |
| `design-review.md` | Visual review subset, broken out for easy reading | `review --visual-review` | the human |
| `human-questions.md` | Human-decision items the review surfaced | `review` | the human (writing answers) |
| `fixture-swap.md` | Evidence that `--fixture` was used and restored | `review --fixture` | the human (audit trail) |
| `next-loop.md` | Recommended next-loop title + prompt + reasoning | `summarize` | the human, the auto driver |
| `auto-report.md` | One-line per-loop result of a multi-loop `auto` run | `auto` | the human (overwritten per run) |

Two things to notice:

1. **Most files have multiple readers.** That's the contract — the file decouples the writer from the readers. The summarizer doesn't call into the test runner's internals; it reads `test-report.md`. The auto driver doesn't call the review function; it reads `review-decision.json`. This is what makes the file layout an API.
2. **`review-decision.json` is the only machine-readable file in the per-loop set.** It exists because the auto driver needs structured fields (`decision`, `counts`, `can_publish`, `requires_human`) to make a state-machine decision. Everything else is markdown because it's read by humans first and machines second.

---

## Why markdown + JSON, not a database

This decision is load-bearing for the whole project. The reasoning, in order of importance:

### Reason 1 — `cat` is the universal viewer

A learner with a terminal can read every loop's state with `cat`, `less`, or any text editor. No client, no schema, no migration. The cost of "I want to understand what happened" is one shell command. This is the project's primary product, and the moment we add a database we lose it.

### Reason 2 — markdown survives across versions

`tiny_agents.py` will change. Its internal data structures will change. The `loops/` folder from 6 months ago will still be readable, because markdown is markdown. A binary log or a serialized object graph would require the writer-version to be available, and that constraint propagates everywhere.

### Reason 3 — git diffs work

Selected loops are committed to git as evidence (see `docs/repository-hygiene.md`). `git diff` between two loop folders is human-readable. If the folders were binary, that diff would be useless and the curriculum would lose one of its primary self-grading tools.

### Reason 4 — the schema is easy to break and easy to fix

Adding a new field to `review-decision.json` doesn't require a migration. Renaming a field (we did exactly that in R2.2, `suggested_next_task` → `top_next_task`) is a search-and-replace in one Python file plus a `schema_version` bump. A database-backed system would need migration tooling, downtime planning, and rollback paths — overkill at this scale.

### Reason 5 — debugging always starts with `ls`

When something goes wrong, the first thing every contributor (or learner, or future maintainer) does is list the loop folder. If the answer is in `human-questions.md`, they see `human-questions.md`. If the loop crashed before review, they see no `review-report.md` — and that absence is itself information. This pattern only works because the filesystem is the state.

---

## What this commits us to refusing

(Cross-references to `00-anti-patterns.md`.)

- **No database**, ever, while we remain a teaching project. If a future Studio frontend wants fast queries, it builds an index *over the markdown*, not under it.
- **No binary log format**. If we ever need richer log data, we add new fields to `claude.log` (which is already text) — not switch to a structured binary log.
- **No plugin system that hides artifacts**. A contributed reviewer can add new fields to `review-report.md` and new keys to `review-decision.json`. It cannot write its data into a place we don't read by default.

---

## A note on `auto-report.md`

It lives at the *top level* of TinyAgents, not inside a loop folder. That's deliberate — `auto-report.md` summarizes a multi-loop run, so it belongs above the per-loop folders.

The trade-off: **it's overwritten on every `auto` run**. Each run clobbers the previous one. If a specific run is important enough to preserve, copy it into `docs/case-studies/<name>.md` before the next `auto`. The R0 hygiene doc covers this convention.

Today, the on-disk `auto-report.md` is the snapshot of loop 008 (the first multi-loop success). When you next run `auto`, that snapshot is gone unless you've saved it elsewhere.

---

## Checkpoint questions

1. **Why is `review-decision.json` JSON while `review-report.md` is markdown — they describe the same review?**
   _Hint: different readers. The JSON is for the auto driver (machine, needs structured fields); the markdown is for the human (needs prose context, severity grouping, source citations). Same data, two presentation formats._

2. **What does it mean that "the artifacts are the API"?**
   _Hint: stages communicate by reading and writing files rather than by calling each other's functions. `summarize` doesn't import from `test`; it reads `test-report.md`. This is a decoupling that lets you replace any stage's implementation without breaking downstream readers._

3. **If you wanted to add a sixth review category, what's the minimum set of artifacts you'd have to update?**
   _Hint: `review-report.md` (add a "Sixth Category" section), `review-decision.json` (add a `categories.sixth: {ran, issues}` entry), and the `build_decision()` aggregator. You wouldn't need to change `test-report.md`, `research.md`, etc. — they don't read review output._

4. **A learner says: "isn't writing all these files just inefficient overhead?" What's the rebuttal?**
   _Hint: yes, it is some overhead — measured in kilobytes per loop. The benefit is that the system becomes inspectable, reproducible, and teachable. For a teaching-first project, the trade is overwhelmingly worth it. For a production high-throughput agent fleet, it might not be — different project, different optimization._

5. **Why is `auto-report.md` overwritten each run rather than appended to?**
   _Hint: append-only logs accrete and quickly become unreadable. The per-run snapshot is small and self-contained; if you want a history, you copy specific runs into case-studies. The design pushes back against "log everything forever" because that habit hides the interesting events under the boring ones._

---

_See also: `01-four-step-loop.md` for the first five files in the list; `03-gates-and-failure-taxonomy.md` for how artifacts get read by the failure router; `04-auto-loop-and-review.md` for how `review-decision.json` drives the auto state machine._
