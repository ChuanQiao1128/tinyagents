# 04 · Auto Loop and Review

_How one loop becomes many, how the system decides to stop, and why "the tests passed" is not enough to ship._

---

## The five teaching questions

### 1. What does this layer make possible?

Two things, intertwined:

- **Multi-loop autonomous execution**: `tiny_agents.py auto` runs back-to-back loops, each one's `summarize` deciding what the next one should be. The chain stops cleanly when the work is genuinely done, when a human is needed, or when a configured safety limit fires.
- **Judgment beyond test**: a separate Review pass runs after tests, asking "should we accept this?" rather than "does it run?". Review findings become the next loop's task — or, if a finding is a taste call, get surfaced to the human and pause the chain.

Together these turn the four-step loop (module 01) from a manual unit into a self-driving system that knows when to ask for help.

### 2. What concrete failure happens without this layer?

Without auto:

- Every loop is manually invoked. The human runs `new`, `scan`, `prompt`, `run`, `test`, `summarize` one at a time, or types `python tiny_agents.py run ...` over and over. Most loops are obvious continuations of the previous one; making the human drive each step adds friction without value.

Without review (just auto + test):

- Tests passing becomes the de facto "done" signal. But tests don't catch many real production failures: a production guard that doesn't actually guard, a security hole in a write API, a visual regression that no source check can see. Loop 008 had **27/27 hard criteria pass** and still had a production-guard test that was never actually verified — a human had to catch it by hand. Review is the layer that prevents that pattern from being the default.

### 3. Where is the boundary between this layer and the previous one?

Module 03 (gates) tells you *what kind of failure happened*. Module 04 is what *decides what to do about it*:

- The summarizer reads the gate output (`test-report.md`, `review-decision.json`) and produces a `next-loop.md` describing the recommended next iteration's title and prompt.
- The auto driver reads `next-loop.md` and either runs that loop, pauses for human input, or stops.

Module 03 is descriptive (it classifies). Module 04 is **prescriptive** (it acts on the classification).

### 4. What new artifact does this layer leave on disk?

Per-loop:
- `next-loop.md` (introduced in Stage 5, becomes load-bearing in Stage 8).
- `review-report.md`, `review-decision.json`, `design-review.md`, `human-questions.md` (Stages 9.5–9.7).

Per `auto` run, at the top level:
- `auto-report.md` — one-line per-loop summary of the chain, with the final outcome.

The Review artifacts are the new evidence at this layer. The auto-report is a one-shot summary of what the chain did, intentionally overwritten on each run.

### 5. Where would the SDLC break if this layer were skipped?

You'd have a working single-loop system that's pleasant to operate manually, but:

- Every multi-iteration task would require a human in the chair for every iteration.
- Review-shaped failures (production guards, security holes, design problems) would only be caught by humans reading reports — they'd never become next-loop tasks automatically.
- The auto-stop-on-human-decision pattern wouldn't exist, so human-in-the-loop questions would have no clean way to enter the system.

You'd have the floor (module 01) but no scaling story. The project would be a useful CLI tool, not a teaching artifact for how agent SDLCs actually grow.

---

## The auto state machine

`tiny_agents.py auto` is a small state machine with five terminal outcomes and one continue path.

```
            ┌───────────────────────────────────────────────────┐
            │                                                   │
            ▼                                                   │
        run loop ──► test ──► review (if --review enabled) ──► summarize ──► next-loop.md
                                                                                │
                                                                                ▼
                                                                          decision?
                                                                                │
       ┌────────────────────────┬───────────────────┬──────────────────┬────────┴─────────┐
       ▼                        ▼                   ▼                  ▼                  ▼
     done                continue-fix         continue-polish    needs-human          blocked
     STOP                back to run         back to run        STOP (pause)         STOP (error)
                                                                                     OR max-loops
                                                                                     STOP (limit)
```

The terminal states are deliberately named — each one means a different next action for the human.

### State: `done`

All hard criteria pass; review (if run) reports `decision_state: done`. Nothing more to do.

**What the human does next**: a different feature, or move to the next stage of the product.

### State: `continue-fix`

Either hard criteria failed, or review surfaced a `blocker` or `must-fix`. The chain continues automatically into a new loop scoped to fixing the specific failure.

**What the human does next**: ideally nothing — the chain keeps going. They can read `next-loop.md` to see what the auto driver decided.

### State: `continue-polish`

A variant of `continue-fix` where the goal-spec specifically marked a follow-up as polish work (Hard criteria pass + soft criteria has open items). Treated like `continue-fix` for routing purposes, but the title and scope are different.

### State: `needs-human-feedback`

Review surfaced one or more `human-decision` items, and the auto driver refuses to guess at them. `human-questions.md` is written with the open questions.

**What the human does next**: open `human-questions.md`, fill in the `Answer:` lines, decide whether to re-run `auto`. (Stage 9.8 — *answer injection* — does not yet exist, so the answers don't automatically flow into the next loop's prompt. That's a known gap on the progress map.)

### State: `blocked`

Something failed in a way the auto driver can't recover from — typically an executor-auth failure, a sandbox permission issue, or a scope-rule violation that requires a real human read.

**What the human does next**: read the `claude.log` / `review-report.md` / `test-report.md` to diagnose; resolve the blocking condition; re-run.

### State: `max-loops`

The auto driver hit `--max-loops` (defaults to 3 — deliberately small) without reaching `done`. This isn't an error per se — it's a safety brake. Long autonomous chains accumulate drift; the brake forces a human checkpoint.

**What the human does next**: read the chain so far, decide whether to bump `--max-loops` and continue, or to pause and reconsider scope.

---

## Why `next-loop.md` exists

`summarize` could have just printed its recommendation to stdout. Instead it writes `next-loop.md`. Three reasons:

1. **The auto driver needs it.** Auto reads `next-loop.md` from the previous loop to know what the next loop's title and prompt should be. If the recommendation were only on stdout, the multi-loop chain would need shared in-memory state.
2. **The human needs it.** When auto pauses on `needs-human-feedback`, the user wants to see *what auto would have done if it kept going*. `next-loop.md` is exactly that view.
3. **Audit.** Together with `test-report.md` and `review-report.md`, `next-loop.md` lets a reader reconstruct the chain's reasoning later. "Why did loop 010 attempt that specific fix?" — look at loop 009's `next-loop.md`.

It's a small file, but it's the **connective tissue** between iterations. Without it, the auto driver has no input; with it, every loop in a chain is reachable from the loop before it.

---

## Review: why it's not "another test"

This is the single most important conceptual move in module 04.

| Question | Answered by |
|---|---|
| "Does the code compile?" | `build` (Stage 4 test gate) |
| "Does the code lint cleanly?" | `lint` |
| "Do unit tests pass?" | `test` |
| "Does the structural contract hold?" | hard criteria (file_exists / file_absent / script_passes / forbidden_dep) |
| **"Does the *running system* actually enforce what the goal says it should?"** | **functional review (Stage 9.5)** |
| **"Did the agent stay inside the allowed scope?"** | **scope review (Stage 9.6)** |
| **"Are there security holes the test runner doesn't catch?"** | **security review (Stage 9.6)** |
| **"Does the README oversell what the code actually does?"** | **content / docs review (Stage 9.6)** |
| **"Does the page look right?"** | **visual review (Stage 9.7)** |

The lower half of the table — the bold rows — are categorically different questions. Tests check rules a machine can decide. Review checks rules where the judgment is at least partly LLM-mediated, multimodal, or about runtime behavior under realistic load.

The system keeps them visibly separate because **conflating them produces confidently-shipped broken systems**. Loop 008 was the proof: 27/27 hard pass, build clean, lint clean, and *also* a production write endpoint that had no Origin/Host check. The test layer cannot see that finding; only a security-category reviewer can.

---

## The five review categories, briefly

Each is documented in detail in `docs/review-system-design.md`. Here, just enough to recognize them:

| Category | What it does | What it produces |
|---|---|---|
| **Functional** | Boots the target in production mode, runs HTTP probes (`GET /` → 200; `POST /api/studio/save` → 403 in production; `portfolio.json` unchanged after POST attempts). | Pass/fail per check + a "portfolio modified" boolean. |
| **Scope** | Diff vs goal's "Allowed Changes". Flags files touched outside the lane. | List of out-of-scope file edits. |
| **Security** | Secret scan, write-API hardening checks, FS sandboxing, CORS / Origin checks. | Findings with severity classification. |
| **Content / Docs** | TODO leakage into user-visible text. README claims vs actual component behavior. | Findings about content-spec violations and doc drift. |
| **Visual** | Playwright screenshots → multimodal Claude → findings against the goal's Visual Direction. | `design-review.md` plus design-category issues in the main report. |

A sixth meta-category (`design preflight`) runs cheap source-side checks (h1 count across the homepage component tree, responsive-class presence, monolithic-component detection) before screenshots are even taken. It catches structural design issues that don't need pixels.

---

## How review findings become next-loop tasks

The review's `top_next_task` field (in `review-decision.json`, schema v2) carries the single highest-priority actionable task across all categories. The auto driver picks it up like this:

1. After review runs, `build_decision()` aggregates issues into a `decision_state`.
2. If `decision_state == "continue-fix"`: the auto driver builds a new loop whose **title** is `top_next_task`. That loop's prompt is constructed from the standard scan + plan pipeline, but anchored to the specific finding.
3. If `decision_state == "needs-human-feedback"`: auto stops. The user reads `human-questions.md`. The chain doesn't continue automatically.
4. If `decision_state == "done-with-warnings"`: auto stops cleanly. Findings exist but they're `should-fix` / `nice-to-have` — the human can choose to open a polish loop or accept the warnings.
5. If `decision_state == "done"`: nothing left.

This is the precise mechanism by which Review "becomes work". A blocker / must-fix finding *automatically* becomes the next loop. A human-decision finding *automatically pauses* the system. The mapping is fully visible in `review-decision.json` — no hidden state.

---

## Severity → decision: the mapping in one place

The rules (per `build_decision()` in `tiny_agents.py`):

```
counts.blocker > 0  OR  counts["must-fix"] > 0   → continue-fix
elif counts["human-decision"] > 0                → needs-human-feedback
elif counts["should-fix"] > 0                    → done-with-warnings
else                                             → done
```

Three things to note:

1. **`blocker` and `must-fix` outrank `human-decision`.** If there's something the agent should objectively fix, fix it first. Don't make the human answer taste questions before the obvious problems are resolved.
2. **`should-fix` is "done with warnings", not "continue".** Module 00 (anti-patterns) lists this as item #7 — treating `nice-to-have` and `should-fix` as blockers produces an endless polish treadmill.
3. **`nice-to-have` doesn't appear in the mapping at all.** It only affects the report, not the decision. The system records it; the human decides whether to act on it later.

---

## A worked example: `auto` against loop 008

When `tiny_agents.py auto` ran the Builder Studio task, here's the chain it actually produced (snapshot of `auto-report.md`):

- **Loop 1** (`008-add-a-local-only-builder-studio-...`): build + lint passed; hard criteria 27/27; review found some issues but they were `should-fix` / `human-decision`. Decision state: `done`. Chain stopped at 1 loop.

That's it — one loop in the chain. The system recognized that all hard criteria passed and there were no `blocker` / `must-fix` items. The auto driver said "I'm done". The fact that a single loop was enough to ship 19 new files (the entire Studio editor) is a useful real-world data point: most loops are tiny; some are big; the auto driver doesn't care.

`loops/009-...` and later were *separate* `auto` runs, not continuations of the same chain. Auto-runs are independent.

---

## Checkpoint questions

1. **`done-with-warnings` is a terminal state. What's the practical difference between `done` and `done-with-warnings`?**
   _Hint: `done` means there's nothing to do. `done-with-warnings` means there are open `should-fix` / `nice-to-have` items the human can choose to fix in a polish loop. Auto stops in both cases; the difference is what the human reads next._

2. **Why does `human-decision` cause a `needs-human-feedback` *pause* rather than blocking?**
   _Hint: blocking suggests something is wrong with the agent's work; pausing suggests something is right but needs a human judgment call. The two states route differently. Pausing also makes auto recoverable: the user answers, then re-runs. Blocking implies failure that requires diagnosis._

3. **Loop 008 had 27/27 hard criteria pass *and* a security hole in `/api/studio/upload`. Why didn't hard criteria catch the hole?**
   _Hint: hard criteria check structural facts (file exists, script passes, dep absent). They don't probe runtime behavior. The Origin/Host check exists only at the moment the API is called over the network — that requires functional or security review to surface, both of which run *after* hard criteria pass._

4. **The auto driver caps at `--max-loops 3` by default. Why is the cap so small?**
   _Hint: long autonomous chains accumulate drift. Each loop's choice affects the next; small misalignments compound. A cap forces a human checkpoint before drift becomes unrecoverable. The user can bump the cap explicitly if they want more — but the default punishes pretending you have stronger trust than you do._

5. **If review were a "deeper test" rather than its own gate, what concrete problem would arise?**
   _Hint: it would inherit test's contract — pass/fail. But review naturally produces *findings with severity*, and those findings need to drive different routing (continue-fix vs done-with-warnings vs needs-human-feedback). Collapsing review to pass/fail loses the severity surface and turns every review issue into a hard blocker. The state-machine richness comes from review being a separate, multi-state gate._

---

## What this layer does NOT do (yet)

Things that the auto driver doesn't do today, and are intentionally deferred:

- **No cross-loop memory.** Each loop starts with a fresh prompt built from scratch. Lessons learned in loop N do not automatically inform loop N+1's prompt. This is L6.5 on the progress map. (Loop 010's "goal-spec beats reviewer" lesson is exactly the case where cross-loop memory would have prevented loop 009's regression.)
- **No automatic answer injection.** The user writes answers into `human-questions.md`. The next loop's prompt does not yet read those answers. This is L6 on the progress map.
- **No approval gate.** Even at `done`, the auto driver doesn't commit, push, or deploy. Stage 10 is the publish gate, not yet implemented.

If you find yourself wanting these capabilities, that's the system telling you it's time to read the progress map and pick the next layer.

---

_See also: `docs/review-system-design.md` for the full Review specification; `02-artifacts.md` for the per-loop file contract that auto and review both read/write; `progress-map.md` for what's actually built versus what's planned._
