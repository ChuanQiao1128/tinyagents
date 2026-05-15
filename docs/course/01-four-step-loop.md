# 01 · The Four-Step Loop

_Research → Plan → Implement → Test. The floor of useful AI Agent SDLC, and the first layer any later module sits on top of._

---

## The five teaching questions

### 1. What does this layer make possible?

A single iteration where an LLM coding agent (Claude) makes a code change against a real target project, and where a learner can read what happened afterwards. Four files on disk encode "what was true before", "what we planned to do", "what we asked the agent", and "did the change work":

```
loops/<NNN>-<slug>/
    research.md
    plan.md
    implementation-prompt.md
    artifacts/claude.log
    test-report.md
```

If you only ever use TinyAgents at this layer, you still have a real workflow: pick a small task, run the loop, read the report, repeat. Everything beyond this module is a layer that *catches a failure mode this one can't see*.

### 2. What concrete failure happens without this layer?

Without the four-step loop, the alternative is "I ran a prompt in a chat and pasted the answer into my editor". The failures that produces are familiar:

- No record of what you asked → you can't reproduce the result.
- No record of what the model saw of the project → you can't tell whether the answer was based on stale assumptions.
- No automatic verification → the code may or may not build, and you find out by manually running things.
- No way to recover from "the model lost the thread" → you start a new chat and re-explain everything.

Each of those is a real loss of information that the four-step loop fixes by putting the corresponding fact on disk.

### 3. Where is the boundary between this layer and the previous one?

The previous layer is "no orchestration at all" — `Goal → one LLM output`. The boundary is the introduction of **on-disk evidence + a verification step**. A loop that has a goal and an LLM call but no `research.md` and no `test-report.md` is still the previous layer; it just happens inside TinyAgents.

### 4. What new artifact does this layer leave on disk?

Five files (one folder).

| File | Written by | Reads it | What it freezes |
|---|---|---|---|
| `research.md` | `tiny_agents.py scan` | `prompt` step, next loops | Project state + goal-spec snapshot at loop start |
| `plan.md` | `tiny_agents.py prompt` | the human, the next prompt | The intended change for this loop |
| `implementation-prompt.md` | `tiny_agents.py prompt` | Claude (as input) | The literal prompt Claude received |
| `artifacts/claude.log` | Claude executor | the summarizer, the human | What Claude said and did |
| `test-report.md` | `tiny_agents.py test` | the summarizer, the next loop | Pass/fail of build/lint/typecheck/test |

The folder is the **API contract**. Any later module reads from these files; none of them depends on internal state of `tiny_agents.py`.

### 5. Where would the SDLC break if this layer were skipped?

This is the floor. Skipping it means there is no SDLC at all — just a chat session. Every later module assumes the four-step loop exists and runs; if you remove it, none of them have anywhere to plug in.

---

## Walkthrough: what each step does

### Step 1 — Research (`scan`)

**Purpose**: produce `research.md` — a read-only snapshot of (a) what the target project currently contains, (b) what the goal-spec demands.

**Input**:
- `--project` path
- `--goal-file` path

**Output**: `loops/<NNN>-<slug>/research.md` containing:
- The target's `package.json` scripts and declared dependencies.
- A high-level file tree.
- The goal's Hard Criteria, Soft Criteria, and Forbidden Deps.
- The goal's Allowed Changes section (the "lane" Claude must stay in).

**Why this is a separate step**: research is **read-only**. No code changes happen here, no LLM call happens here. By isolating "what's true now" into its own deterministic step, we make the project's view of itself reproducible: running `scan` twice in a row produces the same `research.md`. Any LLM nondeterminism is therefore quarantined in step 3.

### Step 2 — Plan (`prompt`)

**Purpose**: produce `plan.md` (the intended change for this loop) and `implementation-prompt.md` (the literal prompt Claude will see).

**Input**: the loop folder's `research.md` and the task title from `new`.

**Output**:
- `plan.md` — a short outline of the change.
- `implementation-prompt.md` — the full prompt: goal-spec text + research + scope rules ("don't touch `.env`, stay inside Allowed Changes, don't add forbidden deps") + plan.

**Why this is a separate step**: same logic as research — building the prompt deterministically from on-disk inputs means you can re-run it without getting a different prompt. If a loop fails, the failure is in Claude's reasoning *given a known prompt*, not in some hidden prompt construction logic.

**Note**: this step uses no LLM. `prompt` is pure templating.

### Step 3 — Implement (`run` invokes Claude)

**Purpose**: hand `implementation-prompt.md` to Claude, let it edit files in the target project, capture everything it said and did to `artifacts/claude.log`.

**Input**:
- `implementation-prompt.md`
- The target project's filesystem (Claude has direct read/write access via the Claude Code CLI).

**Output**:
- File changes in the target project.
- `artifacts/claude.log` with the full session transcript.

**Why this step is the most fragile**: the LLM call is the only non-deterministic step in the loop. It is also where most failure modes live. Gates and the failure taxonomy (module 03) exist specifically because of how many ways this step can fail.

### Step 4 — Test (`test`)

**Purpose**: run the target's discoverable verification commands (`npm run build`, `npm run lint`, `npm run typecheck`, `npm test`) and produce `test-report.md`.

**Input**: the target project's current state (post-Claude-edit).

**Output**:
- `test-report.md` with a top-line overall result: `no-tests-run` / `passed` / `failed`.
- Per-command logs in `artifacts/<command>.log`.

**Why this step is honest**: `test` does not auto-fix. It does not run dev servers. It runs the same commands a human would run before merging a PR, and it records the result. If `package.json` doesn't exist, the result is `no-tests-run`, not `passed`. The summarizer later uses this distinction to pick the right kind of next loop.

---

## A worked example: loop 005 → 006

A pair of real loops from `loops/` that illustrates the four-step loop's value as a *unit of recoverable work*.

**Loop 005** had this shape:

- Step 1 (research): saw a fresh Next.js project, no portfolio components yet.
- Step 2 (plan): asked Claude to build the AI-engineer homepage.
- Step 3 (Claude): edited ~10 files, build succeeded.
- Step 4 (test): `build` passed (`exit 0`), `lint` failed (`exit 1`).

The four-step loop didn't *fix* the lint failure. It produced enough evidence for the next loop to know exactly what to fix.

**Loop 006** then had this shape:

- Step 1 (research): saw loop 005's lint failure recorded in `test-report.md`.
- Step 2 (plan): scope = "fix lint failure from 005, nothing else".
- Step 3 (Claude): made the minimal change.
- Step 4 (test): `build` passed, `lint` passed.

The narrowness of loop 006 is the point. Each loop is one unit of recoverable work. The bigger machinery — the failure router, the auto driver, the review system — exists to choose *which kind of loop comes next*. The four-step loop is the unit those choices are made about.

---

## Checkpoint questions

Answer these before reading module 02. Hint lines below each question give the answer's key idea — match the idea, not the wording.

1. **Why is `research.md` written by a separate step rather than inside `prompt`?**
   _Hint: deterministic reproducibility — running the same `scan` twice should produce the same file. Separating concerns also means each step has a clean input/output contract._

2. **What is the difference between `no-tests-run` and `passed` in `test-report.md`? Why does the distinction matter?**
   _Hint: `no-tests-run` means there was nothing to test (e.g. no `package.json`); `passed` means tests ran and succeeded. The summarizer's next-loop recommendation differs: the first triggers "Add verification scripts"; the second triggers "Pick the next feature"._

3. **Could step 2 (`prompt`) be merged into step 1 (`scan`)? What would you lose?**
   _Hint: you would lose the ability to inspect `research.md` independently of `implementation-prompt.md`, and re-running just step 2 with the same research becomes impossible. Mixing concerns also makes step 1's read-only guarantee harder to verify._

4. **The loop is "the unit of recoverable work". What does *recoverable* mean here?**
   _Hint: a loop produces enough on-disk evidence that the next loop can be defined precisely (often as "fix the specific failure from loop N"). The work is recoverable because the next loop has a clear starting point — not because the loop can undo itself._

5. **If you had to skip one of the four steps, which is least dangerous to skip and why?**
   _Hint: trick question. Skipping any of the four breaks a downstream contract. The closest to "less dangerous" is `plan.md` (because `implementation-prompt.md` can be built without an explicit outline), but you'd lose the human-readable summary of intent. None of the four is safe to remove permanently._

If you can answer all five, you've internalized the four-step loop. Module 02 explains why those five files are markdown / JSON on disk and not log entries in a database.

---

## What this layer specifically does NOT do

For learners coming from other agent projects, here's what is *not* in the four-step loop. Each of these is a separate, later layer.

- **No automatic retry**. If `test` fails, the loop stops. A human or the auto driver decides whether and how to retry. (That's module 04.)
- **No review of behavior**. `test` runs unit-level checks (does it build, does lint pass). It does not exercise the running server, check security, or audit scope. (That's module 04.)
- **No human-in-the-loop questions**. The loop doesn't ask the human anything. The human reads the output and decides what to do next. (That's the L5–L6 stages on the progress map; not yet a separate module.)
- **No git / deploy**. Files land in the target project's working tree. Whether to commit, push, or deploy is the human's call. (That's L8–L9, planned.)

If you find yourself wanting one of these capabilities, that's a real signal — you're ready for the next module up.

---

_See also: `02-artifacts.md` for the artifact-as-evidence model that makes the four-step loop reproducible; `03-gates-and-failure-taxonomy.md` for what happens when one of the four steps misbehaves._
