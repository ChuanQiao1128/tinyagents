# TinyAgents Stage Roadmap

_Status: design + status doc. Source of truth for "what's built, what's in flight, what's planned". Last updated 2026-05-12._

TinyAgents is an AI-Agent SDLC learning project. Each "stage" represents one
discrete capability layer added to the single-file orchestrator
`tiny_agents.py`. The numbering follows the order capabilities landed (or
are planned to land), not strict semver; sub-stages (e.g. 6.6 → 6.9) are
patches that hardened earlier stages after they shipped.

The goal of this document is to give a learner picking up the project a
single-page answer to: _which stages already work end-to-end, which are
known-shaky, and where to push next_.

---

## Status legend

- **✅ Complete** — implemented, exercised end-to-end against the
  portfolio-site target, and documented in a loop's evidence.
- **🟡 Partial** — implemented but with a known scope cut (e.g. mobile
  intentionally deferred) or fragile under specific inputs.
- **🟦 Designed** — design doc exists; no code yet.
- **⬜ Planned** — placeholder; not designed.

---

## Stage 1 — `init` / `new` / `status` &nbsp;✅

The orchestrator skeleton: create a TinyAgents project (`init`), start a
new loop with a slugified title (`new`), and inspect existing loops
(`status`). Establishes the `loops/<NNN>-<slug>/` convention every later
stage writes into.

Hardening notes:

- `slugify()` caps slugs at 100 characters to avoid macOS HFS+ 255-byte
  per-component path-too-long errors. (Discovered when a long auto-loop
  title produced an ~1,100-char folder.)

## Stage 2 — `scan` &nbsp;✅

Read the project + goal file and produce `research.md`: a snapshot of the
target's package.json scripts, deps, file tree, and the goal's
hard-criteria / soft-criteria / forbidden-deps. Read-only. Fast.

## Stage 3 — `prompt` &nbsp;✅

Produce `implementation-prompt.md`: the Claude Code instruction the next
stage will feed in. Combines goal-spec, research notes, scope rules
("don't touch .env", "stay inside Allowed changes"), and a `plan.md`
outline. Deterministic — no LLM.

## Stage 4 — `test` &nbsp;✅

Run the discoverable verification commands in the target project's
`package.json` (`build`, `lint`, `typecheck`, `test`). Writes
`test-report.md` + per-command logs into `artifacts/`. Does not auto-fix.
Distinguishes `no-tests-run` (no package.json yet) from `passed` /
`failed`.

## Stage 5 — `summarize` &nbsp;✅

Read the loop's test-report (and later, review-report) and emit
`next-loop.md` with a recommended next-loop title + prompt. The summarizer
classifies the loop's failure mode and routes appropriately:

- _no-tests-run_ → "Add verification scripts" loop.
- _failed_ → focused-fix loop scoped to the failure.
- _passed_ → "Pick next feature" loop.
- _claude-executor-failed_ → "Fix executor / auth" loop (NOT a code-fix
  loop). See **Stage 6.6**.

## Stage 6 — One-loop `run` &nbsp;✅

End-to-end driver that chains `new → scan → prompt → (Claude execute) →
test → summarize` in a single command. The "one button" version of the
loop.

### Stage 6.5 — Install gate &nbsp;✅

After Claude edits, run `npm install` (or equivalent) before `test`. Catch
dependency-add-but-not-installed errors at the right layer.

### Stage 6.6 — Executor failure gate &nbsp;✅

Distinguish "Claude itself failed" (max-turns, not logged in, API error,
permission error) from "Claude's code failed tests". The two recover
differently: the first needs a different next-loop, the second needs the
same code-fix loop. Evidence loop: **002** (Claude max-turns 8 → router
correctly recommended "Fix Claude executor failure", not "Fix the code").

### Stage 6.7 — Permission / completion gate &nbsp;✅

Detect cases where Claude reports success but no file changes occurred
(silent permission denial, refusal, or empty edit). Treat as failure.

### Stage 6.8 — Subprocess hygiene &nbsp;✅

Patch covering several real-world subprocess problems found during
dogfooding:

- `stdin=subprocess.DEVNULL` on every Claude / npm / next call to prevent
  interactive prompts (e.g. first-run ESLint config wizard) from hanging
  forever.
- Per-command timeouts.
- `start_new_session=True` + `os.killpg(pid, SIGKILL)` for process-group
  termination on timeout (otherwise child processes leak).

### Stage 6.9 — Partial-implementation gate &nbsp;✅

If Claude exits non-zero but files genuinely changed (snapshot
before/after), proceed to test rather than aborting. Captures the common
"Claude hit max-turns mid-task but still wrote useful code" case so the
loop doesn't lose work.

## Stage 8 — Multi-loop `auto` &nbsp;✅

Chain N one-loops back-to-back, where each loop's `summarize` decides the
next. Stops on `done`, on `needs-human-feedback`, or after `max-loops`.
Produces a top-level `auto-report.md` (overwritten on each run; copy into
`docs/case-studies/` to preserve a specific run). Evidence loop: **008**
(27/27 hard criteria pass, full Builder Studio shipped in one auto run).

## Stage 9.5 — Functional review &nbsp;✅

Boot the target in production mode and run HTTP probes against the
running server. For portfolio-site that means: GET `/` → 200, GET
`/studio` → 200 or 403 depending on env, POST `/api/studio/save` → 403 in
production, POST `/api/studio/upload` → 403 in production, plus a "does
`portfolio.json` survive a POST attempt" guard check. Writes
`review-report.md` + `review-decision.json`.

## Stage 9.6 — Scope / security / content / docs review &nbsp;✅

Single-pass quality review across five non-functional categories:

- **scope** — diff vs goal's "Allowed changes".
- **security** — secret scan, write-API hardening, FS sandboxing checks.
- **content** — TODO / placeholder leakage into user-visible text.
- **docs** — README claims vs actual component behavior.
- **functional** (overlap with 9.5) — runtime probes summarized into
  issues.

Findings are classified into a 5-level severity model (blocker / must-fix
/ should-fix / nice-to-have / human-decision) and a 4-state decision
(done / done-with-warnings / continue-fix / needs-human-feedback).
Human-decision items are exported to `human-questions.md` for the user to
answer.

## Stage 9.7 — Visual review (multimodal) &nbsp;🟡

Capture full-page screenshots of routes at desktop (and optionally
mobile) viewports via Playwright (Node helper at `scripts/screenshot.mjs`),
then call Claude per-screenshot with the goal's design brief and ask for
visual findings against Visual Direction. Writes `design-review.md` +
adds design findings into the unified review-report.

Current state:

- ✅ Desktop full-page capture (1440×1200) via Playwright headless
  Chromium.
- ✅ Per-screenshot Claude calls (multi-image attachment in a single
  prompt was unreliable in `claude -p`).
- ✅ JPEG output at quality 72 — keeps homepage capture <~200 KB so it
  stays under the Claude CLI attachment threshold (~255 KB empirical).
- ✅ Source-preflight checks (h1 count across the homepage component
  tree, responsive-class presence, Studio monolith heuristic) that don't
  need a screenshot.
- 🟡 Mobile capture (390×844) is wired up but intentionally commented
  out in `scripts/screenshot.mjs` and `SCREENSHOT_VIEWPORTS_PW` —
  re-enable when desktop visual quality is dialed in.
- 🟡 The Studio screenshot in production always shows the gated
  "local-only" card; reviewing the actual editor UI requires a
  dev-mode capture path that doesn't exist yet (see Stage 9.7b).

Evidence loops: **011** (first visual review), **012** (visual review
caught mobile horizontal overflow blockers), **013** (polish loop driven
by visual review findings).

### Stage 9.7b — Dev-mode Studio screenshot &nbsp;🟦 designed, not built

Today the visual reviewer only sees the production /studio gate card
because `tiny_agents review` boots the target in `npm run build && npm
start`. A second capture path that runs `NODE_ENV=development npm run
dev` and screenshots /studio at the editor UI would let the reviewer
actually evaluate the form layout, save bar, preview pane, and
upload/clear affordances. Scoped, not implemented.

## Stage 9.8 — Human Feedback Loop &nbsp;🟦 designed, not built

Today the orchestrator only WRITES `human-questions.md`. The next stage
should READ the user's `Answer:` lines on the next loop and feed those
answers into the implementation prompt, so a human-decision finding
turns into actionable instructions without the user having to manually
copy-paste. See `docs/review-system-design.md` for the full design.

## Stage 9.9 — Decision Engine refinement &nbsp;🟦 designed, not built

Current decision states are heuristic ("any must-fix → continue-fix; no
must-fix but human-decision → needs-human-feedback"). Stage 9.9 formalizes
the state transitions, adds the missing "done-with-warnings" path when
findings are all nice-to-have or human-decision-already-answered, and
adds a `publishable: true/false` boolean that Stage 10 will gate on.

## Stage 10 — Publish gate &nbsp;⬜ planned

Git commit + push to a remote, Vercel/Cloudflare/similar deploy, optional
domain wire-up. Gated on review `publishable: true`. Explicitly NOT in
scope for any earlier stage. Out of scope for Stage 9.x.

---

## What's complete

Stages 1–6.9 (the full one-loop pipeline including the failure gates),
Stage 8 (auto multi-loop), Stage 9.5/9.6 (functional + 4-category single
pass review), and the desktop slice of Stage 9.7 (visual review).

## What's in flight

Stage 9.7 mobile re-enable + dev-mode Studio capture (9.7b) are the
near-term TODOs for the review surface to stop being desktop-prod-only.

## What's planned

Stages 9.8 (human-feedback consumption) and 9.9 (decision engine) round
out the review surface. Stage 10 (publish gate) is the publish-ready
finish line. None of these has implementation code yet.

---

## Recommended next learning step

Pick one of:

1. **Stage 9.7 mobile re-enable** — smallest, highest learning-per-line
   ratio. Uncomment the mobile entry in `SCREENSHOT_VIEWPORTS_PW` and
   `scripts/screenshot.mjs`, run a review, watch the design critic see a
   second viewport for the first time. Demonstrates how a single config
   surface controls the whole capture matrix.

2. **Stage 9.8 human-feedback consumption** — medium-size, high
   conceptual payoff. The change is "read `human-questions.md` on loop
   start, inject answers into the next prompt." Teaches the difference
   between TinyAgents-writes-for-user vs TinyAgents-reads-from-user
   information flow.

3. **Stage 10 publish gate** — biggest, most concrete payoff (you can
   actually ship a real portfolio at the end). Touches more systems
   (git, hosting, DNS) and runs the highest risk of accidental
   destructive action, so the operator gate matters most here.

The recommended order is 9.7-mobile → 9.8 → 9.9 → 10. Each step is small
enough to fit in one focused loop, and each one unblocks the next.
