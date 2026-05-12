# TinyLocalAgents

TinyLocalAgents is a small local CLI tool that helps you run a structured,
four-step AI development loop on your own machine. Each loop captures the
research, plan, prompt, test report, and follow-ups for one small change.

It is deliberately minimal: Python 3 standard library only, no external
dependencies, no database, no web UI, no automatic code editing.

## The four-step loop

Every loop walks through the same four stages, plus a hand-off to the next
loop:

1. **Research** — understand the problem, the user, and the goal.
2. **Plan** — decide what will change, what won't, and how you'll know it worked.
3. **Implement** — hand a structured prompt to an AI coding agent (or a human).
4. **Test** — verify the change actually does what the plan promised.
5. **Next loop** — record what to do next.

Each loop lives in its own numbered folder under `loops/` and contains five
markdown files matching those stages.

## Requirements

- Python 3.9+ (any modern Python 3 will do)
- No third-party packages

## Quick start

```bash
# 1. Initialize the project (creates loops/, templates/, config.json)
python tiny_agents.py init

# 2. Create a new loop for a task
python tiny_agents.py new "Create programmer personal portfolio homepage"

# 3. Check what loops exist
python tiny_agents.py status
```

## Commands

### `init`
Creates the working directories and `config.json` if they don't already exist.
Safe to run more than once.

```bash
python tiny_agents.py init
```

### `new "<task title>"`
Creates the next numbered loop folder under `loops/`, using a slug derived from
the task title. For example:

```bash
python tiny_agents.py new "Create programmer personal portfolio homepage"
# -> loops/001-create-programmer-personal-portfolio-homepage/
```

Each loop folder is created with these starter files:

- `research.md` — problem, user, goal, in/out of scope
- `plan.md` — work, allowed changes, forbidden changes, acceptance criteria
- `implementation-prompt.md` — structured prompt for an AI coding agent
- `test-report.md` — build, lint, manual check, scope check, conclusion
- `next-loop.md` — recap, next steps, open questions

### `status`
Reports whether the project is initialized, lists existing loop folders, and
highlights the latest one.

```bash
python tiny_agents.py status
```

### `scan --project <path>`
Inspects a target project folder and writes a readable summary into the
**latest** loop as `context-summary.md`. Useful for handing an AI coding
coworker a quick orientation document for the codebase it's about to work on.

```bash
python tiny_agents.py scan --project ../portfolio-site
```

What `context-summary.md` contains:

- Basic project facts (path, name, whether `package.json` / `README.md` / `.git` exist)
- Detected stack (Next.js, TypeScript, Tailwind) with the signals that triggered each detection
- Package manager guess (npm / pnpm / yarn / bun) based on lockfiles
- Available npm scripts (`build`, `dev`, `lint`, `test`, `typecheck`)
- Important files and folders (homepage, layout, components, styles, configs)
- Safe-context guidance: files useful for frontend tasks, files that should
  stay read-only, and files/folders that should never be sent to AI
- Scanner notes: missing files, assumptions made, warnings

**The scanner never modifies the target project.** It is strictly read-only.

**The scanner never reads or prints `.env` files** or anything inside
generated directories like `node_modules`, `.next`, `dist`, `build`, `out`,
`coverage`, or `.git`. Detection is heuristic — confirm by reading the actual
files before making structural changes.

Run `scan` after creating a loop with `new`, since the summary is written
into the latest loop folder.

### `prompt`
Synthesizes `research.md`, `plan.md`, and (if present) `context-summary.md`
from the **latest** loop into a single structured `implementation-prompt.md`
that can be pasted into Claude Code, Cursor, Codex, or another AI coding
coworker.

```bash
python tiny_agents.py prompt
```

What the generated `implementation-prompt.md` contains:

- A clear **Role** for the coding coworker (one scoped loop, then stop)
- The **Current Task** (taken from `research.md`'s heading, falling back to
  the loop folder name)
- **Research Context** embedded from `research.md`
- **Implementation Plan** embedded from `plan.md`
- **Project Context** embedded from `context-summary.md` (or a warning that
  the project has not been scanned yet)
- **Scope Rules** (do not overbuild, no unrelated features, no forbidden
  files, no `.env`/`node_modules`/build folders)
- **Expected Deliverables** the coworker must report
- **Acceptance Criteria** extracted from `plan.md`'s `## Acceptance criteria`
  section
- **Testing Instructions** built from the npm scripts in
  `context-summary.md`, using the detected package manager (`npm`, `pnpm`,
  `yarn`, or `bun`)
- A **Stop Condition** telling the coworker not to continue past this loop

The workflow is: `new` → fill in `research.md` and `plan.md` → optionally
`scan --project <path>` → `prompt`. You can re-run `prompt` after editing the
notes to regenerate the implementation prompt.

**Stage 3 still does not call any AI automatically.** It only writes a
markdown file you can copy into your coding agent of choice. No API calls,
no automatic edits, no test execution.

### `test --project <path> [--timeout N]`
Runs the target project's own verification scripts (`typecheck`,
`type-check`, `build`, `lint`, `test`) under whichever package manager the
project uses, captures per-command output, and writes:

- `loops/<latest>/test-report.md` — a structured Markdown summary
- `loops/<latest>/artifacts/<script>.log` — full stdout/stderr for each
  command that actually ran

```bash
python tiny_agents.py test --project ../portfolio-site
```

What it does:

- Reads `package.json` from the target project (gracefully handles missing
  or malformed `package.json`).
- Detects the package manager from lockfiles: `pnpm-lock.yaml` →
  `pnpm`, `yarn.lock` → `yarn`, `bun.lockb`/`bun.lock` → `bun`,
  `package-lock.json` → `npm` (default `npm` otherwise).
- Runs only scripts that **actually exist** in `package.json`. Missing
  scripts are listed under "Skipped Checks" — they are not invented.
- Runs them in a safe order: typecheck → type-check → build → lint → test.
- Sets `CI=1` in the subprocess environment, which makes most JS tools
  (jest, react-scripts, etc.) drop out of interactive watch mode.
- Wires the subprocess `stdin` to `/dev/null` so any tool that still tries
  to prompt gets immediate EOF instead of hanging the orchestrator. This
  is the fix for the class of bug where e.g. `next lint`'s first-run
  ESLint setup wizard would block forever waiting on arrow keys.
- Applies a per-command **timeout** (`--timeout`, default 600s). Any
  single script that runs longer is killed and recorded as `failed` with
  exit code 124 and an error summary like `Timed out after 600s — likely
  interactive prompt or watch mode`. `summarize` then produces a normal
  fix-loop recommendation pointing at the timed-out script.
- Continues running the remaining scripts even if one fails, so you see
  the full picture.

What `test-report.md` contains:

- Summary block (project, loop, package manager, overall result, start /
  completed times).
- A `## Commands Run` section with command, status, exit code, duration,
  and the relative path to the full log for each script.
- A `## Skipped Checks` section listing scripts that were not defined.
- A `## Failure Summary` section that surfaces one concise line per
  failed command (full output stays in `artifacts/*.log`).
- A `## Scope Notes` section reminding you that `test` does not auto-fix
  failures and that recovery should happen in a new loop.
- A `## Conclusion` line: `passed`, `failed`, or `no-tests-run`.

What `artifacts/<script>.log` contains: the exact command, working
directory, start / completed times, duration, exit code, full stdout, and
full stderr for that one script.

What Stage 4 does **not** do:

- It does not edit the target project.
- It does not auto-fix failures.
- It does not run `dev`, `start`, `watch`, or other non-verification
  scripts.
- It does not call any AI API.
- It does not read or print `.env` files or anything inside
  `node_modules`, `.next`, `dist`, `build`, `out`, `coverage`.

Exit codes: `0` if all discovered commands pass (or none are found),
`1` if at least one discovered command fails, and non-zero for setup
errors (missing project path, no loop yet, etc.).

### `summarize`
Reads the latest loop's `test-report.md` (and optionally `plan.md`,
`research.md`, `context-summary.md` for the task title) and writes a clear
`next-loop.md` with a focused recommendation for what to do next.

```bash
python tiny_agents.py summarize
```

What `next-loop.md` contains:

- A **Current Loop** block (loop folder, task title, overall result, time).
- A **What Happened** paragraph adapted to the loop's state.
- **Passed Checks**, **Failed Checks**, and **Skipped Checks** lists pulled
  out of `test-report.md`. Failed checks include the short error summary
  and a pointer to `artifacts/*.log`.
- A **Recommended Next Loop** paragraph with a concrete focus and a
  suggested loop title.
- A **Suggested Next Loop Prompt** code block with a copy-pasteable
  command (either `python tiny_agents.py new "..."` for a follow-up loop
  or `python tiny_agents.py test --project <path>` if tests haven't run).
- A **Notes** block reminding you that this command does not call any AI,
  does not edit code, and does not auto-fix failures.

The four states `summarize` distinguishes:

- **passed** — all discovered verification commands passed. Recommends a
  manual review or the next small feature loop.
- **failed** — one or more discovered commands failed. Recommends a fix
  loop scoped to the failing checks only.
- **no-tests-run** — `package.json` had no supported verification
  scripts. Recommends adding scripts or doing manual review.
- **tests-not-run** / **no-report** — there is no real `test-report.md`
  yet (missing file or starter template). Recommends running
  `tiny_agents.py test --project <path>` first.

What Stage 5 does **not** do:

- It does not call any AI API.
- It does not edit the target project.
- It does not run tests.
- It does not auto-fix failures.
- It does not invent results that are not in `test-report.md`.

Exit codes: `0` after writing `next-loop.md`. Non-zero only for
structural errors (project not initialized, no loops directory, etc.).

### `run --project <path> --task "<task>" --agent claude [--create-if-missing] [--execute] [--install] [--claude-permission-mode {default|acceptEdits}] [--max-turns N] [--timeout N]`
Orchestrates **one** complete development loop end-to-end by chaining the
earlier stages and invoking Claude Code as a subprocess:

```bash
python tiny_agents.py run \
  --project ../portfolio-site \
  --task "Create AI Engineer personal portfolio homepage" \
  --agent claude \
  --create-if-missing \
  --execute \
  --max-turns 8
```

Steps it runs, in order:

1. Optionally create the target project folder (with a placeholder
   `README.md`) when `--create-if-missing` is passed and the folder does
   not exist.
2. Create a new numbered loop folder, the same way `new` does.
3. Auto-fill `research.md` and `plan.md`. For the AI-Engineer-portfolio
   task ("create … AI Engineer … portfolio … homepage" in the title), a
   specialized template is used (audience, target roles, in/out of scope,
   six required sections, three featured projects, allowed/forbidden
   changes, acceptance criteria). For other task titles, the generic
   Stage 1 starter is used — fill those in before running with
   `--execute`.
4. Run `scan` against the target project to write `context-summary.md`.
5. Run `prompt` to write `implementation-prompt.md`.
6. **If `--execute` is passed:** invoke
   `claude -p "<prompt>" --max-turns <N>` with `cwd` set to the target
   project. Output is streamed to your terminal and captured to
   `loops/<latest>/artifacts/claude.log`.
7. **If `--install` is also passed:** detect the package manager from
   lockfiles (same logic as `scan` / `test`) and run `<pm> install` in the
   target project. Output is streamed and captured to
   `loops/<latest>/artifacts/install.log`. See "About `--install`" below.
8. **If `--execute` is passed:** run `test` against the target project to
   produce `test-report.md` and `artifacts/*.log` (skipped only when
   `--install` ran and failed — see below).
9. **If `--execute` is passed:** run `summarize` to write `next-loop.md`.

**Dry run (no `--execute`)** stops after step 5, prints the exact `claude`
command it *would* run, and writes a dry-run note into `next-loop.md`. Use
it to inspect `implementation-prompt.md` before committing to a Claude
session. `--install` is silently ignored in dry-run (a note is printed) —
TinyLocalAgents never installs dependencies without `--execute`.

**About `--timeout`.** Per-subprocess timeout in seconds, default 600
(10 minutes). Applies to **every** subprocess `run` invokes: Claude
itself, `<pm> install` (if `--install`), and each verification script
that the inner `test` step runs (build / lint / typecheck / test).

The timeout exists for one reason: keep multi-step orchestration from
hanging forever on accidental interactive prompts or watch-mode scripts.
Together with `stdin=/dev/null` on every subprocess, this means
TinyLocalAgents will never silently wait on a TTY prompt — a
misconfigured `next lint`, a `jest --watch`, or any other tool that
expects a human will get either an EOF on stdin (and exit fast) or be
killed at the deadline. The failure shows up as a normal failed command
with exit code 124 and a `Timed out after Ns` error summary, which
`summarize` then handles like any other failure.

The default is generous so legitimate slow steps (a large `npm install`,
a Claude session with `--max-turns 60`) won't trip it. Override with
`--timeout 1800` for unusual workloads.

**About `--claude-permission-mode`.** Controls the permission mode that
TinyLocalAgents passes to Claude Code. Two values are accepted (anything
else, including `bypassPermissions`, is rejected by argparse):

- `default` (the default) — TinyLocalAgents does **not** pass any
  `--permission-mode` flag to Claude. Claude will ask for per-edit
  approval. Good for interactive sessions where you want to review each
  write before it happens.
- `acceptEdits` — TinyLocalAgents appends `--permission-mode acceptEdits`
  to the Claude argv. File edits are auto-approved by Claude. Use this
  for unattended `run --execute` invocations where you want Claude to
  actually scaffold a project end-to-end.

TinyLocalAgents intentionally does **not** support `bypassPermissions` or
`--dangerously-skip-permissions`. `acceptEdits` is a safer middle ground —
it lets edits proceed without manual approval, but Claude still respects
its own remaining tool-use guardrails. The permission mode is shown in
both the dry-run output and the redacted argv recorded in
`artifacts/claude.log`.

**Claude executor failure handling.** `run` distinguishes three failure
modes:

- **Spawn failure** (the `claude` binary isn't on PATH, can't be exec'd,
  etc.) is a *structural* error. `run` writes `artifacts/claude.log` with
  exit-code 127 and the spawn error, then exits **1**. Install and test
  are not attempted.
- **Non-zero exit** (Claude spawned, ran briefly, exited with code ≠ 0 —
  for example missing API key, a network failure, or a permission
  denial) is treated as an **executor failure**. `run`:
  - Skips `--install` (even when requested) — there is no `package.json`
    yet, and installing into a project Claude didn't modify would just
    produce misleading signal.
  - Skips the `test` step for the same reason.
  - Writes a synthetic `test-report.md` whose only failed "command" is
    `claude`, with the first meaningful line of Claude's output as the
    error summary. This lets `summarize` parse the run with the same
    machinery used for build/lint/test failures.
  - Runs `summarize`. Because the only failed command is `claude`,
    `summarize` recognizes an executor failure and recommends
    `python tiny_agents.py new "Fix Claude executor failure from
    <loop>"`, *not* a "add verification scripts" loop (which would
    misread the symptom).
  - Exits **0** — the failure is captured as input to the next loop,
    consistent with how install/test failures are handled.
- **Partial implementation** (Stage 6.9). Claude spawned and exited
  **non-zero**, but the project-file snapshot before vs. after Claude
  shows actual file changes. The most common cause is `Error: Reached
  max turns (N)` — Claude was interrupted mid-scaffold but the work it
  did is real and verifiable. When this fires, `run`:
  - Prints a clear note showing the file diff
    (`diff: +N added, ~N changed, -N removed`) and the first meaningful
    line of Claude's output.
  - **Does NOT** write a synthetic failure report.
  - **Proceeds normally** with `--install` (if requested), `test`, and
    `summarize` — so the actual `build` / `lint` / `test` outcome drives
    the next-loop recommendation instead of "fix Claude executor".
  - The final run summary's Claude line shows
    `(exit N — partial, proceeded)` so the partial status is visible at
    a glance.

  The Stage 6.6 executor-failure path still fires when Claude exits
  non-zero **and** made zero file changes — that's the true "Claude
  couldn't do anything" case (not logged in, missing API key, network
  unreachable before the first edit).

- **Implementation incomplete** (Stage 6.7 completion gate). Claude
  spawned and exited 0, but produced no implementation. Detected only
  when **all three** conditions are true: no `package.json` exists in the
  target, no homepage entry (`app/page.tsx`, `pages/index.tsx`, …)
  exists, and Claude's own output contains permission-request language
  ("I need permission", "approve", "permission to write", "ready to
  scaffold", "once you approve"). When this fires, `run`:
  - Skips `--install` and the `test` step (there is nothing to verify).
  - Writes a synthetic `test-report.md` whose only failed "command" is
    `claude`, with an error summary containing the word "permission".
  - Runs `summarize`. Because the error text mentions permission,
    `summarize` recommends the **acceptEdits re-run**, not the generic
    "fix Claude executor" loop:
    `python tiny_agents.py new "Rerun portfolio creation with Claude
    acceptEdits permission"`, with the exact `run` command (including
    `--claude-permission-mode acceptEdits`) embedded in the next-loop
    focus paragraph.
  - Exits **0**, same as the other expected-failure paths.

`artifacts/claude.log` is the source of truth: it records the exact
argv, working directory, timing, exit code, and the full Claude stdout
and stderr. Always read it when `next-loop.md` recommends a Claude-fix
loop.

**About `--install`.** Useful with `--create-if-missing`: Claude can
scaffold a fresh Next.js project with a `package.json`, but `npm run build`
will fail until dependencies are installed. `--install` runs the
appropriate `<pm> install` between Claude and the test step:

- `pnpm-lock.yaml` → `pnpm install`
- `yarn.lock` → `yarn install`
- `bun.lockb` / `bun.lock` → `bun install`
- `package-lock.json` → `npm install`
- otherwise → `npm install`

`--install` is **opt-in** because it can modify the target project by
creating `node_modules/` and a lockfile, and may download a substantial
amount of data. It is skipped automatically if `package.json` does not
exist after Claude completes (nothing to install).

`artifacts/install.log` records the install command, working dir, start /
completed times, duration, exit code, full stdout, and full stderr.

If `--install` fails (non-zero exit, or the package manager binary isn't
on PATH), TinyLocalAgents **skips the test step** — running `npm run
build` against a project without `node_modules/` is just noise. Instead it
writes a synthetic `test-report.md` that records the install failure with
`Overall result: failed` and points to `install.log`, then runs
`summarize`. The resulting `next-loop.md` recommends a fix loop scoped to
the install failure.

What `run` does **not** do:

- It does not call any AI API. Claude Code runs as a normal subprocess
  on your machine.
- It does not pass `--dangerously-skip-permissions` to Claude Code.
  Claude will ask you for permissions normally; you remain in control.
- It does not deploy anything.
- It does not modify production systems.
- It does not loop. `run` orchestrates exactly **one** loop and stops.
- It does not auto-fix anything. If `test` fails after Claude runs (for
  example because `npm install` hasn't been run yet), that failure is
  expected — `summarize` captures it and recommends the fix loop.

Exit codes: `0` after a complete dry run, or after a complete
execute run where Claude was spawned successfully (test **and** install
failures are *expected input* to the next loop and do not fail `run`).
Non-zero for structural errors: invalid agent, no init, missing project
path without `--create-if-missing`, failed prompt generation, or failure
to spawn the `claude` binary.

### `review --project <path> --goal-file <file> --agent claude [--port N] [--max-turns N] [--timeout N]`

Stage 9.5 review agent. Inspects, probes, and reports — **never edits the
project, never deploys, never auto-fixes**. Use it to verify the kinds of
things `test` and `hard criteria` cannot:

- Does production actually block `/studio` and `/api/studio/*`?
- Does the public page render from `portfolio.json` (or is it hardcoded)?
- Does the README explain how to edit content?
- Does the implementation feel like a usable local builder?

```bash
python tiny_agents.py review \
  --project ../portfolio-site \
  --goal-file goals/portfolio-builder-studio-mvp.md \
  --agent claude \
  --max-turns 5 \
  --timeout 600
```

Six categories run per loop:

1. **Scope** — deterministic. New files at risky paths (`/auth/`,
   `/admin/`, `/db/`, `/payments/`, `.env`, etc.); forbidden / `*-cli`
   dependencies in `package.json`; unusually large diffs (>100 files
   touched → `human-decision`).
2. **Security** — deterministic. `.env*` files in the diff (blocker);
   high-confidence secret patterns (AWS access keys, OpenAI / GitHub /
   Slack tokens, PEM private keys); API route handlers that write files
   without a `NODE_ENV` guard (must-fix); upload routes without
   filename sanitization (must-fix).
3. **Content / Docs** — deterministic. `portfolio.json` valid JSON;
   `app/page.tsx` references the loader; no obvious hardcoded `TODO:`
   blocks in `app/page.tsx`; `README.md` mentions Studio / portfolio
   editing.
4. **Functional** — runs `npm run build` then `npm start` on a non-3000
   port (default 3737), polls until ready, and probes the routes listed
   under `## Functional Review Criteria` in the goal file. Before any
   POST probe, takes a byte-level backup of `src/content/portfolio.json`
   and restores it if a production POST mutated it. Server is killed
   cleanly (process-group SIGKILL) after all probes.
5. **Quality (Claude)** — a short `claude -p` pass (default
   `--max-turns 5`) focused on what deterministic checks can't catch:
   architectural drift, scope creep, README/code mismatch, JSX-level UX
   issues, subjective design calls. Output is JSON, parsed defensively.
6. **Design (Stage 9.7, visual review)** — **opt-in** via
   `--visual-review`. Runs in two parts:

   1. A cheap deterministic **source preflight** that always runs:
      heading hierarchy in `app/page.tsx`, Tailwind responsive class
      density across `app/**/*.tsx`, and a monolithic-component
      heuristic on `src/components/studio/StudioClient.tsx`.
   2. A **screenshot-based, multimodal design-critic Claude pass** that
      only runs when `--visual-review` is set. It captures
      **full-page** screenshots of `/` and `/studio` at desktop
      (1440×1200) and mobile (390×844) using **Playwright via a small
      Node helper** (`scripts/screenshot.mjs`), then hands the four PNGs
      + the goal's Visual Direction / Design Goal / Studio Requirements
      sections to Claude via `claude -p ... @/abs/path/to.png` syntax.
      Claude returns a JSON array of design issues with the standard
      5-level severity, extended with `subcategory` / `target` /
      `viewport` / `requires_rendered_review` fields specific to design
      review.

   Outputs land at `loops/<latest>/design-review.md` (focused),
   `loops/<latest>/artifacts/screenshots/*.png`, and
   `loops/<latest>/artifacts/visual-review-claude.log`. The combined
   `review-report.md` and `review-decision.json` also include the
   design category under `category="design"`. If Playwright isn't
   installed or the production server fails to start, visual review is
   **skipped** with a clear message — the rest of the review continues
   normally and `design-review.md` says the screenshot capture was
   unavailable rather than pretending the visual review passed.

   **Installing Playwright** (one-time, ~200 MB browser binaries):

   ```bash
   cd /path/to/TinyLocalAgents
   npm install
   npx playwright install chromium
   ```

   After that, `--visual-review` works on any `review` or `auto` run:

   ```bash
   python3 tiny_agents.py review \
     --project ../portfolio-site \
     --goal-file goals/portfolio-builder-studio-mvp.md \
     --agent claude --visual-review \
     --max-turns 5 --visual-max-turns 5 --timeout 600

   python3 tiny_agents.py auto \
     --project ../portfolio-site \
     --goal-file goals/portfolio-builder-studio-mvp.md \
     --agent claude --install --claude-permission-mode acceptEdits \
     --visual-review --max-loops 3 --max-turns 40 --timeout 900
   ```

   In `auto`, a design **blocker** or **must-fix** turns into a
   `continue-fix` next-loop task (the polish task). Design
   **should-fix** / **nice-to-have** items are recorded in
   `auto-report.md` but don't block `done`. Design issues that need a
   subjective user call (e.g. accent color choice) become
   `human-decision` items in `human-questions.md`.

   **The visual reviewer never edits code** — it judges screenshots
   and returns JSON. The builder agent does any fixes in the next
   loop.

Each issue is severity-tagged with the 5-level model: `blocker` /
`must-fix` / `should-fix` / `nice-to-have` / `human-decision`. The
combined verdict becomes one of: **`done`** (clean or only
nice-to-have), **`done-with-warnings`** (only should-fix), **`continue-fix`**
(blocker or must-fix → next loop has a real task), or
**`needs-human-feedback`** (human-decision items present → auto pauses).

Outputs land in the loop folder:

- `review-report.md` — human-readable, multi-category Markdown report.
- `review-decision.json` — machine-readable, consumed by `auto`'s state
  machine. Has the full `categories`, `counts`, `change_summary`,
  `decision`, and `suggested_next_task` fields.
- `human-questions.md` — written only when human-decision items exist.
  Stage 9.6 only writes this file; reading the answers back and feeding
  them to the next loop is Stage 9.8 work.
- `artifacts/review-claude.log` — full Claude transcript.

For standalone runs (no current loop), all of the above land in
`reviews/<timestamp>/`.

#### Goal-file syntax for runtime probes

Add a section to your goal file:

```markdown
## Functional Review Criteria

- production_allows_path: /
- production_blocks_path: /studio
- production_blocks_post: /api/studio/save
- production_blocks_post: /api/studio/upload
```

Header text matching is case-insensitive and accepts either "Functional
Review Criteria" or "Review Criteria" — pick whichever fits the goal.

#### Auto integration

When `auto` runs and the per-loop hard criteria all pass, **the review
agent runs automatically before `auto` declares `done`**. If review finds
any blocker, `auto`'s decision becomes `review-incomplete` instead of
`done`, and the next loop's task is taken from the top blocker's
`suggested_next_task`. This is what turns "structural pass" into "actually
works": `auto` cannot mark a project done while a working `/studio` is
served in production, or while a POST to `/api/studio/save` succeeds in
production, or while the public page is hardcoded.

You can tune the review's behavior on `auto` with two extra flags:

- `--review-port N` — port for the production-server probes (default 3737)
- `--review-max-turns N` — `--max-turns` for the Claude quality pass
  (default 5)

If the goal file has no `## Functional Review Criteria` section, the
functional review is skipped (it reports `unavailable`) but the static and
Claude reviews still run.

#### What review does NOT do

- Never edits, deploys, or auto-fixes anything.
- Never stores tokens.
- Never claims success it cannot verify — invalid Claude JSON output is
  surfaced verbatim in the report rather than silently passed.

### `auto --project <path> --goal-file <file> --agent claude [...]`
Multi-loop runner. Chains up to `--max-loops` `run` invocations until
either the goal-spec's hard criteria all pass or one of the safety gates
fires. This is the **Target B** entry point: hand it a project + a goal
file, walk away, come back to either a finished MVP or a precise
recommendation of what to fix next.

```bash
python tiny_agents.py auto \
  --project ../portfolio-site \
  --goal-file goals/portfolio-mvp.md \
  --agent claude \
  --create-if-missing \
  --install \
  --claude-permission-mode acceptEdits \
  --max-loops 3 \
  --max-turns 30 \
  --timeout 600
```

#### Goal-spec format

A goal file is a Markdown document with three structured sections.
`goals/portfolio-mvp.md` ships as a working example.

- `## First task` — the title used for loop 1. Override with `--task`.
- `## Hard criteria` — lines that `auto` evaluates after every loop:
  - `- file_exists: <path>` (glob OK)
  - `- file_absent: <pattern>` (glob OK)
  - `- script_passes: <npm-script-name>`
  - `- forbidden_dep: <package-name>`
- `## Soft criteria` — free-text bullets that `auto` *does not* evaluate
  mechanically. They are surfaced as a `- [ ]` checklist in
  `auto-report.md` for you to tick after looking at the project.

When all hard criteria pass, `auto` stops with action `done`.

#### Per-loop pipeline

For each loop iteration, `auto`:

1. Snapshots the project file tree (skipping `node_modules`, `.next`,
   etc. — same exclusions as `scan`).
2. **Injects the goal spec into the new loop's `research.md` and `plan.md`**
   so Claude actually sees the full design brief (Visual Direction,
   Content Rules, hard/soft criteria) in the implementation prompt.
   Without this injection, the goal file would only be consumed by
   `auto`'s decision logic *after* each loop and Claude would never see
   it.
3. Calls `cmd_run` with the current task title. That handles
   create-loop → scan → prompt → Claude → (install) → test → summarize.
3. Re-snapshots and computes a per-loop diff (added / changed /
   removed files).
4. Evaluates hard criteria against the new state.
5. Runs the scope gate (see below) over the diff and the current
   `package.json`.
6. Reads the just-written `next-loop.md` for `summarize`'s "Suggested
   loop title" — that becomes the *next* loop's task on `continue`.
7. Calls the **decision state machine** to pick the next action.

#### Decision state machine

After each loop, exactly one outcome is selected:

- `done` — all hard criteria pass. Stop.
- `continue` — keep going. Either:
  - the test step passed but hard criteria are unmet (auto crafts a
    "Refine portfolio to satisfy missing criteria: …" task), or
  - the test step failed and `summarize` suggested a fix-loop title.
- `executor-blocked` — Claude itself failed (Stage 6.6/6.7 path) — the
  only failed "command" was `claude`. Stop and ask the human to fix
  permissions / auth.
- `blocked-repeat` — the same set of failed scripts repeated two loops
  in a row. Stop instead of burning more turns on a stuck failure.
- `blocked-scope` — the scope gate fired (see below). Stop immediately.
- `max-loops` — hit the `--max-loops` cap without satisfying hard
  criteria. Stop.
- `needs-human-review` — no clear next task could be derived. Stop.

#### Scope gate

A small safety net that compares the project's file tree before and
after each loop, plus the current `package.json`. It flags as
`blocked-scope`:

- Any `.env`, `.env.*` file written or modified.
- Any dependency in `package.json` that is on the **default red-line
  list** (`stripe`, `prisma`, `mongoose`, `mongodb`, `next-auth`,
  `clerk`, `firebase`, `firebase-admin`, `pg`, `mysql2`, `redis`,
  `ioredis`) or matches `*-cli`. Override per-run with
  `--allow-deps stripe,next-auth`.
- Pathologically large changes (>200 files added in a single loop).

The goal file's `forbidden_dep:` entries are unioned with the default
list, so you can add domain-specific bans without losing the defaults.

#### Outputs

- Each loop writes its own normal `loops/NNN-…/` folder with
  `claude.log`, `install.log` (if `--install`), per-script test logs,
  `test-report.md`, and `next-loop.md`.
- After the run, `auto-report.md` is written at the TinyLocalAgents
  root. It records the goal, the settings used, the per-loop history
  (task, test state, file diff, hard-criteria pass/fail count,
  decision), the full final hard-criteria breakdown, and the soft
  criteria as a `- [ ]` checklist.

#### Safety properties

- 3-second sleep before invoking Claude in each loop, so a `Ctrl-C`
  cleanly aborts before a new Claude session starts.
- `auto` never enables permission bypass. `--claude-permission-mode`
  values are still restricted to `default` / `acceptEdits`.
- All Stage 6.8 hardening (process-group SIGKILL on timeout,
  `stdin=/dev/null`) applies inside each loop — `auto` cannot hang on
  an interactive prompt.
- Structural exit code is **0** if the orchestration ran at all
  (whether the outcome was `done`, `blocked-*`, `max-loops`, or
  `needs-human-review`). The `auto-report.md` plus `next-loop.md`
  files tell you what happened. Non-zero exit only for setup errors:
  uninitialized project, missing goal file, missing project path
  without `--create-if-missing`, etc.

## Project layout

After running `init` and creating one loop, the directory looks like:

```
TinyLocalAgents/
  tiny_agents.py
  config.json
  README.md
  loops/
    001-create-programmer-personal-portfolio-homepage/
      research.md
      plan.md
      implementation-prompt.md
      test-report.md
      next-loop.md
  templates/
```

## Scope (Stages 1–6)

Stage 1: CLI skeleton (`init`, `new`, `status`) and per-loop markdown
templates.

Stage 2: `scan` command that produces `context-summary.md` for the latest
loop based on a read-only inspection of a target project folder.

Stage 3: `prompt` command that synthesizes the loop's notes and project
context into a single `implementation-prompt.md` to hand to an AI coding
coworker.

Stage 4: `test` command that runs the target project's verification scripts
and writes a `test-report.md` plus per-command logs under `artifacts/`.

Stage 5: `summarize` command that reads `test-report.md` and writes a
`next-loop.md` with a focused recommendation for the next loop.

Stage 6: `run` command that orchestrates one complete loop end-to-end and
optionally invokes Claude Code via the local `claude` CLI.

Stage 6.8: process-group SIGKILL on timeout + `stdin=/dev/null` + per-command
`--timeout` so multi-loop runs can't hang on interactive prompts or runaway
subprocesses.

Stage 8: `auto` multi-loop runner with goal spec, hard/soft criteria,
scope gate, and decision state machine — the entry point for "give me a
finished portfolio MVP" workflows.

Stage 9.5: `review` command — Functional + Static + single-pass Quality
review with 3-level severity + auto integration via `review-incomplete`.

Stage 9.6: Code/Scope/Security/Content/Docs review categories + 5-level
severity model (`blocker` / `must-fix` / `should-fix` / `nice-to-have` /
`human-decision`) + `review-decision.json` schema +
`human-questions.md` generation + auto state machine extended with
`continue-fix` / `done-with-warnings` / `needs-human-feedback`.

Stage 9.7: **Visual Review Agent** — Playwright full-page screenshot
capture + dedicated design-critic Claude call. Opt-in via
`--visual-review`. Lives behind the same `review` / `auto` commands,
emits design issues with extended schema (subcategory / target /
viewport / requires_rendered_review).

Future stages (not yet implemented) intentionally do **not** include:

- AI API calls
- A database
- A web UI
- Deployment tooling
- Automatic code editing

Those may arrive in later stages once the loop workflow itself feels right.
