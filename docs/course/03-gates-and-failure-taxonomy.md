# 03 · Gates and Failure Taxonomy

_Why "the agent didn't crash" isn't the same as "the work succeeded", how TinyAgents tells the two apart, and how it routes each kind of failure to a different recovery path._

---

## The five teaching questions

### 1. What does this layer make possible?

A loop that **refuses to lie about its outcome**. When an agent run produces an ambiguous result (exit code 0 but no files written; exit code 1 but useful code landed; tests passed but tests don't exist), the gate layer classifies the situation into a category that the summarizer can route on. The output is always *one* of a small fixed set of states — not a free-form "it kinda worked".

### 2. What concrete failure happens without this layer?

Without gates, ambiguity propagates. Specific real-world examples observed during TinyAgents' dogfood:

- Loop 002: Claude hit `Reached max turns (8)`. Without an executor-failure gate, the summarizer would have treated this as "the code is broken — let's open a fix-code loop". But there was no code yet. A code-fix loop can't repair an executor that ran out of budget.
- An early run (now folded into the executor-failure pattern): Claude reported success with exit 0, but the target's filesystem was unchanged. Without a permission/completion gate, the next loop assumed the prior work existed and built on top of a phantom.
- A pre-Stage-6.5 run: Claude added a new dep but the orchestrator skipped `npm install` and ran `build` immediately. The build failed with "Cannot find module". Without an install gate, the failure looked like a code failure, not a dependency-setup failure.

Each is the same shape: **a failure that's invisible if you only look at the exit code**.

### 3. Where is the boundary between this layer and the previous one?

Module 01 (four-step loop) introduces the artifacts. Module 02 promotes them to first-class status. Module 03 introduces the rule that **artifacts can disagree with each other**, and the gates are how we make that disagreement load-bearing.

Specifically: `claude.log` says "session ended normally", but the filesystem snapshot says "nothing changed". The completion gate uses the disagreement between those two artifacts to fire a failure that the exit code alone wouldn't have surfaced.

### 4. What new artifact does this layer leave on disk?

Gates don't add a new top-level file. Instead, they *enrich existing artifacts*:

- `artifacts/claude.log` is parsed for canonical failure strings ("Reached max turns", "Invalid API key", "not logged in", "permission was not granted").
- A before/after filesystem snapshot of the target project is taken around the Claude run; the diff is read by the partial-implementation gate.
- `test-report.md` gets the gate's classification reflected in its `overall result` field (`failed-executor` vs `failed` vs `passed` vs `no-tests-run`).
- `next-loop.md` (from module 04's territory) gets a *routing decision* based on which gate fired.

So the new evidence at this layer is **machine-classified failure mode** added to the existing files, not a new file.

### 5. Where would the SDLC break if this layer were skipped?

Multi-loop auto (module 04) becomes unreliable, because the auto driver routes based on failure shape. Without gates:

- An executor failure (no code written) would trigger a code-fix loop that can't help.
- A partial implementation (code written, tests failed) would be discarded as a full failure even though useful work landed.
- An install failure would look like a code failure, leading to fix-loops that retry the same install over and over.

Every gate exists because a real loop in `loops/` exposed the corresponding ambiguity. Removing the gates puts the curriculum back into the state where dogfood produced those failures in the first place.

---

## The four gates

A "gate" in TinyAgents means a deterministic check, run at a specific point in the pipeline, that decides whether the next step is permitted. Each gate has the same shape:

```
read artifact(s) → classify → record → permit / reject
```

### Gate 1 — Install gate (Stage 6.5)

**Position**: after Claude finishes editing, before `test` runs.

**Input**: a list of new dependencies declared in the target's `package.json` (diff vs before).

**Check**: run `npm install`. Record output to `artifacts/install.log`.

**Output**:
- Permits `test` to run if install succeeds.
- Rejects with classification `failed-install` if install fails.

**Why this is a gate, not a step**: failing to install is a different *kind* of failure than failing a build. The install gate's job is to make the difference explicit in the artifacts.

### Gate 2 — Test gate (Stage 4)

**Position**: after install, before summarize.

**Input**: the target's `package.json` scripts.

**Check**: run each discoverable script (`build`, `lint`, `typecheck`, `test`), capture output, classify overall result.

**Output**:
- `test-report.md` with one of: `no-tests-run`, `passed`, `failed`.
- Per-command logs in `artifacts/`.

**Why "test gate" and not "test runner"**: it doesn't *fix* tests, it doesn't *retry* tests, it doesn't *interpret* tests. It runs them and writes down what happened. The interpretation is the summarizer's job (module 04).

### Gate 3 — Review gate (Stages 9.5–9.7)

**Position**: after `test` produces `passed`. (If `test` is `failed`, review is skipped — there's no point reviewing code that doesn't build.)

**Input**: the running target (Stage 9.5 functional probes), the target's source (Stages 9.6 scope/security/content/docs), the rendered screenshots (Stage 9.7 visual).

**Check**: produce findings across six categories with one of five severities.

**Output**:
- `review-report.md` (markdown, multi-category)
- `review-decision.json` (machine-readable: state, counts, top_next_task, can_publish, requires_human)
- `design-review.md` (visual subset)
- `human-questions.md` (if any `human-decision` findings)

**Why review is a gate, not "another test"**: tests answer *can it run?*. Review answers *should we accept it?*. The two questions need different machinery and produce different evidence. See module 04 and `docs/review-system-design.md` for the full split.

### Gate 4 — Approval gate (planned, NOT implemented)

**Position**: after Review produces `can_publish: true`, before any irreversible action (git push, deploy, domain bind).

**Input**: `review-decision.json` + a human-typed approval command.

**Check**: refuse to proceed unless the human has explicitly approved this specific decision.

**Output**: an approval record in the loop folder (file not yet designed) that downstream Stage 10 gates read.

**Why it's listed despite not existing yet**: the curriculum needs to surface the existence of this gate so learners don't conclude "review passed = ship". It's the most important gate the project doesn't yet implement, and the most important reason TinyAgents doesn't claim to be production-grade.

---

## The failure taxonomy

Nine kinds of failure show up in real loops. Each is a distinct shape that maps to a distinct recovery loop.

| Failure | What it looks like | Where it's detected | Recovery loop |
|---|---|---|---|
| **Executor auth failure** | "Invalid API key", "not logged in", no `claude.log` payload | `artifacts/claude.log` parsing | "Fix Claude executor / auth" (not a code-fix loop) |
| **Max-turns incomplete** | "Reached max turns" in `claude.log`; no file changes | `claude.log` + filesystem snapshot | Either: re-run with higher `--max-turns`, or split the task into smaller loops |
| **Permission incomplete** | exit 0; `claude.log` says "done"; filesystem unchanged | filesystem before/after snapshot | "Re-run with explicit write permission" or check sandboxing settings |
| **Install failure** | `npm install` exited non-zero | `artifacts/install.log` | "Fix package.json — resolve dependency conflict" |
| **Build failure** | `npm run build` exited non-zero | `artifacts/build.log` | Focused "Fix build error from loop N" loop |
| **Lint failure** | `npm run lint` exited non-zero, build passed | `artifacts/lint.log` | Focused "Fix lint failure from loop N" loop |
| **Review failure (functional)** | functional probe returned wrong status code; `portfolio.json` mutated through a guarded endpoint | `review-decision.json` `counts.blocker > 0` | "Fix production guard" loop |
| **Design issue** | visual review or design preflight flagged a real visual problem | `design-review.md` + `review-decision.json` | "Polish <specific issue>" loop |
| **Human-decision** | the review surfaced an item the system shouldn't decide alone | `human-questions.md` | Auto pauses with `needs-human-feedback`; the user fills in `Answer:` lines |

Two patterns to notice:

1. **Each failure has a *named* recovery, not just "retry"**. The summarizer picks a recovery loop whose title says what kind of work is going to happen. "Fix Claude executor failure from loop 002" is a different loop from "Fix lint failure from loop 005" — they share no code and no scope.

2. **`human-decision` is a failure mode**, in the sense that it's an outcome the deterministic part of the system can't act on. It is a *first-class* state, not an exception. The system's job is to surface it cleanly, not to guess at the answer.

---

## The DCRDR cycle

Every gate follows the same five-step shape. Naming this shape makes it teachable.

```
Detect → Classify → Record → Decide → Recover
```

- **Detect**: read the relevant artifact(s). E.g. parse `claude.log` for failure strings.
- **Classify**: map the observation to one of the nine failure modes (or "no failure").
- **Record**: write the classification into a stable artifact so downstream stages see the same thing. E.g. `test-report.md`'s `overall result` field.
- **Decide**: choose the next loop's *type* based on the classification. E.g. "executor failure" → "Fix Claude executor" loop.
- **Recover**: actually run the chosen next loop, or pause for human input.

The split between **Decide** and **Recover** is important. Decide is deterministic (a fixed mapping). Recover is the part that's allowed to be expensive (a whole new Claude run). This separation lets you test the routing logic without running an LLM at all.

Module 04 covers the auto driver, which is the loop that calls DCRDR for every iteration.

---

## A real example: loop 002 → loop X

In `loops/002-create-ai-engineer-personal-portfolio-homepage/`, the gate flow ran like this:

- **Detect**: `claude.log` contained `Error: Reached max turns (8)`.
- **Classify**: this matched the executor-failure pattern.
- **Record**: `test-report.md`'s overall result was `failed-executor` (not the same as `failed`); `next-loop.md` reflected the same classification.
- **Decide**: the summarizer chose the "Fix Claude executor failure" recovery shape, not the "Fix the code" shape.
- **Recover**: the recommended next loop's title was `Fix Claude executor failure from 002-create-ai-engineer-personal-portfolio-homepage`. The user's next action is at the Claude / API / auth layer, not in the project's source code.

Read `loops/002-.../next-loop.md` directly to see the actual evidence. The whole DCRDR cycle for this loop is ~40 lines of text on disk.

---

## What the gates do NOT do

For completeness:

- **Gates do not auto-fix**. The install gate runs install but doesn't decide to bump versions. The test gate runs tests but doesn't decide to change code. Gates classify; recovery loops fix.
- **Gates do not retry without classification**. If a gate fires, the system pauses long enough to record *why* before any next loop runs. This is what keeps auto-loops from spiraling.
- **Gates do not block on warnings**. A `should-fix` finding from review is not a gate rejection. It produces a `done-with-warnings` state, not a `continue-fix`. See module 04 for the severity ↔ state mapping.
- **Gates do not have side effects on the target project's code**. They read; they don't write.

---

## Checkpoint questions

1. **What's the practical difference between "test failed" and "executor failed"? Why does it matter for the next loop?**
   _Hint: test failed → there is code, but the code is broken; recovery is a code-fix. Executor failed → there may not be code at all; recovery is fixing the agent / auth, then re-running the build loop. Treating them the same wastes a Claude run._

2. **The permission/completion gate fires when "Claude says success but no files changed". Why is that classification a gate rather than just "the loop failed"?**
   _Hint: the recovery is different. Generic "the loop failed" leads to a code-fix loop. Permission-failure leads to a "check write permissions / sandbox settings" investigation. Conflating the two costs a debugging session._

3. **Why does the install gate run before `test`, not after?**
   _Hint: `test` runs commands that depend on installed deps. Running test before install would silently fail any check that needed the new dep, with a confusing "cannot find module" error. The dependency ordering forces install first._

4. **A `should-fix` finding from review does not gate the next step. Why not?**
   _Hint: severity levels exist precisely to avoid the "every finding is a blocker" treadmill. `should-fix` is a recommendation, not an obligation. Treating it as a gate would mean the auto loop never terminates on quality grounds. See module 04 for the full state-mapping logic._

5. **The approval gate doesn't exist yet. What concrete failure mode does its absence allow?**
   _Hint: a passing review can be misread as "ready to ship". With no approval gate, there's nothing between `review-decision.json` reporting `can_publish: true` and the human running `git push`. The gate's job is to require an explicit human action at exactly that point — without it, the bar for "shipping" is too easy to clear by accident._

---

_See also: `04-auto-loop-and-review.md` for how the auto driver consumes the gate output and chooses a next loop; `00-anti-patterns.md` for why we don't let the agent self-approve a publish; `docs/review-system-design.md` for the full Review system specification._
