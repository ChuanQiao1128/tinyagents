# TinyAgents: A Case Study in AI Agent SDLC

_A learning project that builds a local SDLC loop around an LLM coding agent. Dogfooded over 13 loops against a real Next.js portfolio target between 2026-05-11 and 2026-05-12._

---

## 1. What TinyAgents Is (and Isn't)

**TinyAgents is a local AI Agent SDLC learning engine.** It is a single Python script (`tiny_agents.py`) that wraps an LLM coding agent (Claude Code, in this build) with the surrounding scaffolding a software-development lifecycle actually needs: a goal spec, research, planning, build, install, test, summarization, review, and a multi-loop driver that decides what to do next.

What TinyAgents is NOT:

- **Not a production SaaS.** It runs on a laptop. There is no hosted service, no auth, no multi-tenant anything.
- **Not just a coding assistant.** A coding assistant is the "Build" step. TinyAgents is the loop around the coding assistant — the part that decides what to ask it, what to check after it answers, and whether to ask again.
- **Not a wrapper that hides the agent's failures.** Almost every stage in this project exists because a previous stage exposed a class of failure that needed to be caught explicitly. Failures stay visible — in `claude.log`, `test-report.md`, `review-report.md`, `review-decision.json` — and they shape what the next loop does.

What it tries to be:

> **A system for making AI development explicit, testable, reviewable, and auditable.**
>
> - _Explicit_: every loop writes its inputs (goal, research, plan, prompt) and outputs (logs, test report, review report) to disk before the next loop starts.
> - _Testable_: every loop ends in a real `npm run build` / `npm run lint` against the real target project.
> - _Reviewable_: a separate review pass runs after tests, with five categories (functional, scope, security, content/docs, design) and a five-level severity model.
> - _Auditable_: every loop folder is a self-contained artifact. You can reconstruct what happened from `loops/<NNN>-<slug>/` alone, with no shared session state.

That auditable property is the bet. If the goal is "use AI to ship real software", the bottleneck is not Claude's coding ability — it's our ability to know whether to trust the output of any given run. Putting the artifacts on disk in a fixed shape is the cheapest way to get that.

---

## 2. The Core SDLC Loop

```
                ┌─────────────────────────────────────────────────────┐
                │                                                     │
   Goal         │                                                     ▼
  (manual) ──►  new ──► scan ──► prompt ──► run (Claude) ──► install ──► test ──► summarize
                                                                                    │
                                                                                    ▼
                                                                                 review*
                                                                                    │
                                                                                    ▼
                                                                             next-loop.md
                                                                                    │
                                              ◄──────────── auto (loops back) ──────┘

   * review is currently a separate command (`tiny_agents.py review`); it's
     wired into the auto driver as a post-test gate.
```

Each phase maps to a deterministic artifact on disk. There is no
hidden state.

| Phase | Command | Artifact(s) | Question it answers |
|---|---|---|---|
| Goal | _(manual)_ | `goals/<name>.md` | What are we trying to build? What's the hard-criteria contract? |
| Loop start | `tiny_agents.py new` | `loops/<NNN>-<slug>/` folder created | Where does the evidence for this iteration live? |
| Research | `tiny_agents.py scan` | `research.md` | What's already in the target project? What does the goal demand? |
| Plan | `tiny_agents.py prompt` | `plan.md`, `implementation-prompt.md` | What should change in this loop, and what's the prompt we'll feed Claude? |
| Build | _(part of_ `run`_)_ | `artifacts/claude.log` | Did Claude actually execute and edit files? |
| Install | _(part of_ `run`_)_ | `artifacts/install.log` | Did new deps install cleanly? |
| Test | `tiny_agents.py test` | `test-report.md`, `artifacts/{build,lint,test,typecheck}.log` | Does the code build, lint, and pass tests after Claude's edits? |
| Summarize | `tiny_agents.py summarize` | `next-loop.md` | What kind of next loop does this outcome demand? |
| Review | `tiny_agents.py review` | `review-report.md`, `review-decision.json`, `design-review.md`, `human-questions.md` | Should we accept this loop, or does something need a human decision? |
| Auto | `tiny_agents.py auto` | `auto-report.md` (top-level) | What happened across the N loops we just chained? Why did the chain stop? |

Two things are worth noting about this table:

1. **The artifacts are the API**, not the function signatures inside `tiny_agents.py`. Anything reading a `next-loop.md` doesn't need to know how summarization works internally — only that the file is there with the expected sections. This is what makes the system auditable: the contract is on disk.
2. **`review-decision.json` is the only machine-readable file in the loop folder.** Everything else is markdown for humans. The split is deliberate: humans read the why, machines read the what.

---

## 3. Stages and What Each Taught

Each subsection below describes one stage, in the order it landed, and
the problem it solved that the previous stage couldn't.

### Stage 1 — CLI loop skeleton (`init` / `new` / `status`)

Lays down the `loops/<NNN>-<slug>/` convention and the `config.json` that
later stages all read.

> **Lesson**: filesystem layout is part of the API. Every later stage
> assumes it can write a `next-loop.md` (or a `review-report.md`, or an
> `artifacts/build.log`) without coordination. The minimum viable agent
> SDLC starts with picking the folder structure.

A small follow-up patch capped `slugify()` at 100 characters after a
long auto-loop title produced an ~1,100-char folder name that exceeded
macOS HFS+'s 255-byte per-component limit. The bug taught a more general
rule: any path the system constructs from model output needs an upper
bound, because models will happily write paragraphs into a "title"
field.

### Stage 2 — Project scanner (`scan`)

Read-only inspection of the target project (package.json scripts,
declared deps, file tree) and the goal file (hard criteria, soft
criteria, forbidden deps). Produces `research.md`.

> **Lesson**: separating "look at what's there" from "change what's
> there" is the single highest-leverage decision in the loop. It means
> the Plan step can be deterministic and re-runnable, and it means
> debugging a bad Claude run starts by comparing `research.md` vs the
> actual state.

### Stage 3 — Prompt generator (`prompt`)

Combines `research.md` + goal-spec + scope rules ("don't touch `.env`",
"stay inside Allowed changes", "don't add forbidden deps") into
`implementation-prompt.md`. **No LLM is called in this stage.**

> **Lesson**: a well-formed prompt is the boundary between "the agent
> succeeded" and "the agent did something weird". Building the prompt
> deterministically from on-disk inputs means every loop is reproducible
> at the prompt layer — you can't get a different prompt by running the
> command twice.

### Stage 4 — Test runner (`test`)

Run whatever the target's `package.json` declares as `build`, `lint`,
`typecheck`, `test`, capture each output to `artifacts/<command>.log`,
and write `test-report.md`. Does not auto-fix. Distinguishes three
outcomes: `no-tests-run`, `passed`, `failed`.

> **Lesson**: the test runner has to be honest. Reporting "passed"
> because no tests existed (vs because all tests succeeded) is a
> different shape of evidence, and the next stage will route on that
> distinction. Loop 001's `no-tests-run` outcome is a real example —
> `package.json` didn't exist yet, so the test runner refused to lie
> about it.

### Stage 5 — Summarizer (`summarize`)

Reads the loop's test-report (and later, review-report) and emits
`next-loop.md` with a recommended next-loop title + prompt. The
summarizer routes by failure mode:

- `no-tests-run` → "Add verification scripts to target project" loop.
- `passed` → "Pick the next small feature" loop.
- `failed` (test/build/lint) → focused fix loop scoped to the failure.
- `failed` (Claude executor itself) → "Fix Claude executor" loop, not a
  code-fix loop.

> **Lesson**: the summarizer is where the system learns to ask the
> right next question, not just answer the current one. Without this
> stage, a max-turns failure looks like a code failure, and the next
> loop tries to "fix the code" — which can't help, because no code was
> ever written.

### Stage 6 — One-loop driver (`run`)

End-to-end: `new → scan → prompt → (Claude execute) → install → test →
summarize`. The "one button" version of the loop.

> **Lesson**: composing the earlier stages into a single command is
> only safe once each sub-stage has clear inputs/outputs on disk. The
> driver is thin; almost all the intelligence lives in the sub-stages.

### Stage 6.5 — Install gate

Run `npm install` (or the project's package manager) after Claude
edits and before `test`. Discovered when Claude added a new dep and the
next-loop's build failed with "module not found" — a class of failure
that's easy to fix automatically and embarrassing to not fix.

> **Lesson**: any agent that can write dependency changes needs the
> orchestrator to materialize those changes. Don't make the human do
> `npm install` after Claude.

### Stage 6.6 — Executor failure gate

Distinguish "Claude itself failed" (max-turns, not logged in, API
error, permission error) from "Claude's code failed tests". The two
recover differently. **This stage exists because Loop 002 hit
`Reached max turns (8)` and the system initially routed it as a
code-fix loop. It isn't a code-fix loop — there was no code to fix.**

> **Lesson**: every wrapper around an agent has to give the agent's
> own failure modes a first-class slot in its routing logic. Otherwise
> you'll burn a fix-loop on a problem that fix-loops can't solve.

### Stage 6.7 — Permission / completion gate

Detect cases where Claude reports success but no files actually
changed: silent permission denial, refusal, or empty edit. Treat as
failure even if the executor returned exit 0.

> **Lesson**: don't trust the agent's self-report. A successful exit
> code is a hint, not proof. The proof is the before/after snapshot of
> the target's filesystem.

### Stage 6.8 — Subprocess hygiene _(not in the canonical stage list, but in the code)_

Three concurrent patches that ended a class of hangs and ghost processes:

- `stdin=subprocess.DEVNULL` on every Claude / npm / next call — the
  ESLint first-run config wizard is interactive and was hanging the
  test step forever.
- Per-command timeouts.
- `start_new_session=True` + `os.killpg(pid, SIGKILL)` so when a
  timeout fires, the whole process group dies, not just the parent.

> **Lesson**: any orchestrator that spawns long-running CLI tools
> needs to assume those tools will sometimes hang, sometimes prompt,
> and sometimes leave children behind. The default `subprocess` defaults
> aren't safe for an autonomous loop.

### Stage 6.9 — Partial-implementation gate _(not in the canonical list, but in the code)_

If Claude exits non-zero but files genuinely changed (snapshot
before/after the run), proceed to `test` rather than aborting. Captures
the common "max-turns hit mid-task but useful code was written" case.

> **Lesson**: an exit code is a coarse signal. The fine signal is "did
> the agent leave the target in a different state?". The partial
> result is often worth running through the test and review stages
> anyway, because the next loop has a better starting point if it does.

### Stage 8 — Multi-loop auto runner (`auto`)

Chain N one-loops, where each loop's `summarize` decides the next.
Stops on `done`, on `needs-human-feedback`, or after `max-loops`.
Writes a top-level `auto-report.md`.

> **Lesson**: this is where the SDLC stops being a fancy command-runner
> and starts being an autonomous loop. The interesting question isn't
> "can we chain calls?" but "can the chain decide to stop?". Loop 008's
> auto run hit `done` on the first iteration because all 27 hard
> criteria passed — that's the loop demonstrating that it knows when
> the work is finished, not just when the call has returned.

### Stage 9.5 — Functional review

Boot the target in production mode and run HTTP probes against the
running server: `GET /` should return 200, `POST /api/studio/save`
should return 403 in production, `portfolio.json` should not change
after a hostile POST, etc. Findings go into `review-report.md` +
`review-decision.json`.

> **Lesson**: unit tests prove the code can run. Functional review
> proves the running code does the right thing under realistic
> requests. They aren't the same thing.

### Stage 9.6 — Scope / security / content / docs review

Single-pass quality review across four non-functional categories
(plus the Stage 9.5 functional category). Findings are classified by:

- **Severity** (5 levels): blocker / must-fix / should-fix /
  nice-to-have / human-decision.
- **Decision** (4 states): done / done-with-warnings / continue-fix /
  needs-human-feedback.

Human-decision items get extracted into `human-questions.md` for the
user to answer asynchronously.

> **Lesson**: "does this pass tests?" is one question. "Should we
> accept it?" is a different, larger question. Review answers the
> second. It catches the class of problem where structure looks right
> but behavior, security, design, or scope is wrong.

### Stage 9.7 — Visual review (multimodal)

Capture full-page screenshots of routes via Playwright headless
Chromium (`scripts/screenshot.mjs`), then call Claude per-screenshot
with the goal's Visual Direction brief and ask for findings. Writes
`design-review.md`.

Two practical constraints shaped the implementation:

- Multi-image attachment in `claude -p` was unreliable, so the loop
  calls Claude once per screenshot.
- The CLI silently drops attachments over ~255 KB ("permission was not
  granted to read the image file"), so the screenshots are JPEG quality
  72 — visually indistinguishable for design review, but small enough
  to consistently land.

A cheap source preflight (h1 count across the homepage component tree,
responsive-class presence, Studio monolith size heuristic) runs first
to catch issues a screenshot can't see.

> **Lesson**: a code reviewer can't see whether the page is visually
> balanced. A multimodal reviewer can. They're complementary, not
> redundant. Loops 011 and 012 are the strongest argument for this stage
> existing — see §4 below.

---

## 4. Failure Modes Discovered Through Dogfood

Every entry below is grounded in a real loop in `loops/`. The format is
**what happened → why it mattered → what it led to**.

### 4.1 Claude executor failed (max-turns reached)

**Where**: Loop 002 (`002-create-ai-engineer-personal-portfolio-homepage`).

**What happened**: `claude -p` hit `Reached max turns (8)` before
producing any usable output. The test step then ran against the same
empty target and reported `no-tests-run` (no `package.json` existed
yet). The two reports together looked like "the project is empty
because tests are missing" — but the actual root cause was upstream:
the executor never got far enough to write code.

**Why it mattered**: a code-fix loop can't repair an executor failure.
You'd burn turns asking Claude to add files when the previous run
already shows Claude couldn't write to the filesystem.

**What it led to**: Stage 6.6 (executor failure gate). The summarizer
now parses `claude.log` for the canonical failure strings ("Reached max
turns", "Invalid API key", "not logged in", "permission was not
granted") and routes to a "Fix Claude executor failure" loop instead of
a code-fix loop. The wording of `next-loop.md` for Loop 002 explicitly
recommends "fixing the executor or authentication, **not** the
project's code."

### 4.2 Claude asked for write permission but didn't write files

**Where**: pattern observed across early loops; codified in Stage 6.7.

**What happened**: Claude completed the run with exit 0, but the
target's filesystem was unchanged. The model had asked for write
permission (or hit a permission prompt the orchestrator didn't see) and
silently declined to write.

**Why it mattered**: relying on Claude's self-reported success means
the next loop starts from a wrong assumption — that the code now
exists. Tests then "pass" because nothing was changed to break.

**What it led to**: Stage 6.7 (permission / completion gate). Snapshot
the target before and after the executor run; if exit was 0 but no
files changed, treat it as failure. Don't trust the agent's word over
the filesystem's.

### 4.3 Install was required before build, but didn't run

**Where**: implied by early build-failure noise; codified in Stage 6.5.

**What happened**: Claude added a dependency in `package.json`, the
test step ran `npm run build`, and the build failed with "Cannot find
module". The dep was declared but never installed.

**Why it mattered**: this is a class of failure that's a 5-second fix
and a 30-minute confused-human debug if the orchestrator doesn't handle
it.

**What it led to**: Stage 6.5 (install gate). After Claude edits and
before `test`, run `npm install` (or equivalent). The install log is
written to `artifacts/install.log` so failures here look different from
failures downstream.

### 4.4 Lint failed after build succeeded

**Where**: Loop 005 (build passed, lint failed) → Loop 006 (focused fix
passed).

**What happened**: `npm run build` succeeded — TypeScript compiled, the
page would have rendered — but `npm run lint` flagged real style/usage
issues. The summarizer correctly classified this as `failed` and
recommended a fix loop scoped only to "fix lint failure from 005".

**Why it mattered**: a build-pass / lint-fail outcome is common in real
codebases and shouldn't be treated as success. The summarizer needed to
route it as a fixable problem, and the next loop needed to be narrowly
scoped — "fix lint", not "redo the feature".

**What it led to**: the focused-fix loop pattern. Loop 006's title is
literally `fix-lint-failure-from-005-...`, and it's a Claude run
constrained to that one job. The pattern reappears later for "fix
review findings from loop 008" and "fix mobile horizontal overflow
blockers identified by visual review in loop 011".

### 4.5 Hard criteria passed, but review was still needed

**Where**: Loop 008 (`auto`-run, 27/27 hard criteria pass, full Builder
Studio shipped end-to-end). The top-level `auto-report.md` records this
loop's outcome.

**What happened**: every mechanical check the goal-spec demanded passed.
But "did Claude actually wire the production guard?", "does the public
page actually render from the saved JSON?", "is the upload endpoint
safe to expose?" — none of those questions had been answered. The user
had to manually verify them, and missed one.

**Why it mattered**: hard criteria check structure; they don't check
behavior. A 27/27 pass can ship a Studio that looks complete but has a
production guard that doesn't actually guard anything.

**What it led to**: Stages 9.5–9.7 (the Review system as a whole).
Tests prove "did anything obviously break?". Review answers "is this
actually a good, safe, publishable product?". The two questions need
different machinery.

### 4.6 Visual review revealed a real blocker invisible to the code reviewer

**Where**: Loop 012 (`012-fix-mobile-horizontal-overflow-blockers-identified-by-visual-review-in-loop-011-two-distinct-issues`).

**What happened**: Loop 011's design review identified that at 375 px
viewport width, the Hero role badge, the intro paragraph, and the
BASED IN / CURRENTLY grid all overflowed horizontally; the Studio gate
card extended past the viewport. None of these were visible from
reading the source — they only existed in the rendered pixels.

**Why it mattered**: this is the case the multimodal reviewer was built
for. A linter doesn't see "the page is wider than the viewport". A unit
test doesn't see it. The user, eventually, sees it; but only after the
work has shipped and a friend has tried the URL on their phone. Visual
review surfaces the problem at the review step, before it ships.

**What it led to**: Stage 9.7 staying in the build. (At one point during
implementation, mobile was deferred behind a commented-out viewport
entry in `scripts/screenshot.mjs` to focus on desktop visual quality;
loop 012 is the data point that says re-enabling mobile is real work,
not paranoia.)

### 4.7 Goal-spec should override an overzealous reviewer

**Where**: Loop 010 (`010-fix-loop-009-review-findings-critical-context-the-previous-fix-introduced-a-regression-by-making-app`).

**What happened**: Loop 009 followed a Review Agent finding ("make the
public page dynamic via `force-dynamic + readPortfolioFromDisk`") and
introduced a regression. The goal spec for this product explicitly
called for "ship the static site exactly as the generator already
supports" — the dynamic-render suggestion violated that. The reviewer
had given a generic best-practice that was wrong for this specific
goal. Loop 010 reverted.

**Why it mattered**: review findings are recommendations, not
commandments. A review agent that has read the codebase but not the
goal-spec will sometimes give advice that's right in general and wrong
here. If the orchestrator follows every review finding blindly, the
loop turns into a "fix everything the reviewer flagged" treadmill that
diverges from the actual product intent.

**What it led to**: an explicit precedence rule that lives in the
prompts and the human-feedback flow: **goal-spec outranks reviewer
findings**. Review findings that contradict the goal-spec should
surface as `human-decision` items, not as auto-actionable next tasks.
This rule is also why `human-questions.md` exists as a deliberate
escape hatch from the auto loop.

---

## 5. Why Review Matters

The orchestration insight that organizes Stages 9.5–9.7 is one
sentence:

> **Tests prove the code can run. Review checks whether it should be accepted.**

The two questions are different in kind, and they need different
machinery.

| Layer | Mechanism | Asks |
|---|---|---|
| Test | `npm run build` / `lint` / `test` | Does the code compile and pass mechanical checks? |
| Hard criteria | `file_exists`, `file_absent`, `script_passes`, `forbidden_dep` | Did the structural contract hold? |
| Scope gate | diff vs goal's "Allowed changes" | Did the agent stay inside the lane? |
| **Functional review** | HTTP probes, route-level access control checks, side-effect containment | Does the running system enforce what the goal says it should? |
| **Security review** | secret scan, write-API hardening checks, FS sandboxing | Are we one careless edit away from a leak or a writable endpoint? |
| **Scope review** | diff classification, risky-path detection | Did the agent touch files that should be off-limits? |
| **Content / docs review** | TODO-leak scan, README claims vs component behavior | Does the README oversell what the code actually does? |
| **Visual / design review** | Playwright screenshots + multimodal Claude vs Visual Direction brief | Does the rendered page meet the design contract? |
| **Human-decision items** | `human-questions.md` | What does the system explicitly NOT decide on its own? |

The last row matters. Some decisions shouldn't be made by the
orchestrator at all — accent-color choices, whether a particular taste
call lands, whether a security trade-off is acceptable for this project
in this context. Those go into `human-questions.md` and the auto loop
pauses on `needs-human-feedback`. The system's job is to surface the
right questions, not to answer them.

---

## 6. What TinyAgents Is Not Yet

A learning project is allowed to have a sharp edge between what it
demonstrates and what it doesn't. Being honest about that edge is part
of what makes it worth reading.

What's missing today, in roughly increasing scope:

- **No frontend Studio.** The orchestrator is CLI-only. There's no UI
  for picking goals, watching loops, or browsing review findings —
  although a Studio surface for the _target_ project (`portfolio-site`)
  was built as a separate exercise. A web-based Studio for TinyAgents
  itself would be a separate stage entirely.
- **No Git publish gate.** The system can produce a portfolio that
  passes review. It cannot, today, commit and push that portfolio to
  its own Git repo automatically. The target's git state is the user's
  responsibility.
- **No Vercel (or other) deploy gate.** Following from the above:
  TinyAgents doesn't ship to hosting. There's no `vercel --prod` step,
  no Cloudflare Pages step, no Netlify step. A future Stage 10 would
  gate this on `review-decision.json` having `publishable: true`.
- **No domain binding gate.** And no DNS-touching automation. By
  intent — domain binding is a high-blast-radius action that should
  stay manual until everything upstream is rock-solid.
- **No production monitoring.** Once something ships, TinyAgents has no
  visibility into how it behaves. No log forwarding, no error
  reporting, no usage metrics. The loop closes at "review passed", not
  at "users are happy".
- **No enterprise-grade audit system.** The loop folders are
  audit-shaped (every input/output written to disk in a stable
  format), but there's no signing, no immutable storage, no policy
  enforcement. Calling it auditable is honest at the prototype level
  and dishonest at the compliance level.
- **No full autonomous release management.** No rollback decisions, no
  canary deploys, no progressive rollout, no automated postmortem
  generation. A real release-management surface would need a lot more
  state than "loop folder".

None of this is a flaw in the current build. It's the unbuilt part of
the staircase. The point of a learning project is to keep climbing,
not to pretend the staircase is finished.

---

## 7. What the Next Learning Steps Are

Ordered by smallest-first / highest-learning-per-line-of-code:

1. **Human Feedback Loop (Stage 9.8)** — today the orchestrator only
   WRITES `human-questions.md`. The next stage should READ the user's
   `Answer:` lines on the next loop and feed those answers into the
   implementation prompt. This is the smallest change that closes the
   "review surfaces a question → human answers → next loop acts on the
   answer" loop. It also turns review from a one-way wall into a
   two-way dialogue.

2. **Approval Gate** — an explicit human-confirm step before any
   non-reversible action. This is the prerequisite for Git Publish and
   Deploy gates: any time the orchestrator is about to do something it
   can't undo, it should require human confirmation through a
   structured prompt (and log the approval in a loop artifact).

3. **Git Publish Gate (Stage 10)** — `git add` / `git commit` / `git
   push` for the target project, gated on `review-decision.json`'s
   `publishable: true` flag. This is where TinyAgents starts producing
   real shippable output instead of just confident-feeling output.

4. **Vercel Deploy Gate** — `vercel --prod` (or the
   Cloudflare/Netlify/etc. equivalent), gated on git publish having
   succeeded and on a separate deploy-only review pass (preview URL
   probes, smoke tests against the live deploy).

5. **TinyAgents Studio frontend** — a web UI that visualizes a loop's
   progress in real time, lets you browse `loops/` and review findings
   without `cat`-ing markdown, and surfaces `human-questions.md` as
   forms you can answer in-place. This is the biggest scope jump and
   the latest payoff, which is why it's last. It also turns the
   project from a CLI tool into something a teammate without
   command-line comfort could approach.

The recommended order is 9.8 → Approval Gate → 10 → Deploy → Studio.
Each step's failure modes need to be understood before the next step
becomes safe to build.

---

## Appendix: where to find the evidence

| Topic | File / loop |
|---|---|
| Executor failure handling | `loops/002-.../next-loop.md` |
| Test-fail → focused-fix pattern | `loops/005-.../test-report.md`, `loops/006-.../test-report.md` |
| First multi-loop success | `loops/008-.../*`, plus the top-level `auto-report.md` snapshot |
| Goal-spec > reviewer | `loops/010-.../{review-report.md, plan.md}` |
| First visual review | `loops/011-.../design-review.md` |
| Visual review catches mobile blockers | `loops/012-.../design-review.md` |
| Review system design | `docs/review-system-design.md` |
| Stage roadmap | `docs/stage-roadmap.md` |
| Repository hygiene | `docs/repository-hygiene.md` |

Each loop folder is self-contained — you can read it standalone, in
order, and reconstruct what TinyAgents was thinking at each step. That
property is the case study's actual subject.
