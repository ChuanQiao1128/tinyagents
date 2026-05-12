# Repository Hygiene

_How this repo separates source code from runtime artifacts, and why. Companion to `.gitignore`. Last updated 2026-05-12._

TinyAgents is a small project that produces a lot of files. Most of those
files belong on disk for the duration of a development session, but only
a fraction belong in version control. This doc explains the line.

---

## Source code vs runtime artifacts

**Source code** is anything a human (or this project's documentation)
needs to read in order to understand or rebuild the project. It is
deterministic with respect to inputs and rarely changes. Examples:

- `tiny_agents.py` — the orchestrator.
- `scripts/screenshot.mjs` — the Playwright helper.
- `package.json`, `package-lock.json` — Node toolchain manifest.
- `README.md`, `docs/`, `goals/` — what the project is + how to use it.
- `.gitignore`, `config.json` — repo configuration.

**Runtime artifacts** are anything that TinyAgents itself writes during
a loop or run. They are non-deterministic (timestamps, model output,
captured screenshots) and would churn the diff on every commit.
Examples:

- `loops/<NNN>-<slug>/artifacts/*.log` — Claude / npm / lint logs.
- `loops/<NNN>-<slug>/artifacts/screenshots/*.jpg` — Playwright captures.
- `auto-report.md` (top-level) — overwritten on each `tiny_agents.py auto`
  run.
- `__pycache__/`, `node_modules/`, `.next/` — build / dependency caches.

The `.gitignore` is the executable version of this distinction.

---

## Why loops/artifacts is not all committed

A single visual-review loop can write multi-MB of full-page screenshots.
Three or four review-driven iterations push past the size where git diffs
remain readable and pushes remain fast. The screenshots are also not
useful for *future* runs — they describe a specific moment of a
non-deterministic process and would all need to be regenerated to mean
anything in a new environment.

What we DO want to keep is the **markdown evidence** of each loop:
`research.md`, `plan.md`, `implementation-prompt.md`, `test-report.md`,
`review-report.md`, `design-review.md`, `next-loop.md`,
`human-questions.md`. Those tell the story of the loop in a few KB and
are the actual learning artifact this project is producing.

So `.gitignore` ignores `loops/**/artifacts/` and
`loops/**/screenshots/`, but does NOT ignore the loop-folder markdown.
When the user runs `git add loops/`, git tracks the markdown and skips
the binaries automatically.

---

## What goes into Git

- `tiny_agents.py` and any future Python source.
- `scripts/` — helper scripts the orchestrator shells out to.
- `package.json`, `package-lock.json` — locked Node deps for the helper
  scripts (currently just Playwright).
- `README.md`, `docs/*.md`, `goals/*.md` — all human-readable
  documentation.
- `config.json` — TinyAgents per-project config (project name, loops dir
  name, templates dir name). Small, static, safe.
- `.gitignore` itself.
- Selected loop markdown under `loops/<NNN>-<slug>/` for whichever loops
  the user wants to keep as historical evidence (see below).

---

## What stays local

- `__pycache__/`, `*.pyc` — Python bytecode caches.
- `node_modules/`, `.next/`, `dist/`, `build/`, `coverage/` — Node /
  build outputs.
- `.env`, `.env.*` — environment variables and secrets.
- `*.log` — anywhere on disk.
- `loops/<NNN>-<slug>/artifacts/` — Claude logs, npm logs, screenshots.
- `loops/<NNN>-<slug>/artifacts/screenshots/` — full-page captures.
- `.playwright/`, `playwright-report/`, `test-results/` — Playwright
  browser-test artifacts.
- `portfolio-site/` (in any location) — the generated target project.

---

## How to preserve selected evidence

Some loops are educational milestones (first multi-loop success, first
Review Agent pass, first visual review, an instructive failure). To
promote one of these out of `loops/` and into the learning record:

1. Pick the loop folder, e.g. `loops/008-add-a-local-only-builder-studio/`.
2. Identify which markdown files tell the story — usually
   `next-loop.md` + `review-report.md` + `test-report.md`, sometimes
   `design-review.md` or `human-questions.md`.
3. Create a case-study under `docs/case-studies/<short-name>.md` that
   summarizes what happened, why it's interesting, and links into the
   loop folder. The case-study is a stable, curated artifact; the
   underlying loop folder can be left in place (unchanged) so the raw
   evidence stays adjacent.
4. Commit the case-study. The loop's own markdown can also be committed
   alongside — both are gitignore-safe (only `artifacts/` is excluded).

`auto-report.md` is special: it lives at the repo root and is
overwritten on every `tiny_agents.py auto` run. If you want to preserve
a specific run's `auto-report.md`, copy it into the case-study folder
under a unique name (e.g. `docs/case-studies/auto-report-loop-008.md`)
before the next `auto` run.

---

## Why the generated portfolio-site should usually be a separate repo

The portfolio-site (or any other target project TinyAgents generates) is
the product, not the tool. Mixing them in one repo creates several
problems:

- **History noise.** Every Claude-driven edit to the target lands as a
  big diff against TinyAgents history. The "did anything change in the
  orchestrator?" signal gets buried.
- **CI confusion.** Tooling that wants to build the target (Vercel, a
  preview deploy, a Lighthouse check) ends up trying to also reason
  about `tiny_agents.py`, which has different deps and a different
  entry point.
- **Ownership.** TinyAgents is the platform; the target is the deliverable.
  They typically have different licenses, different commit cadences,
  and different audiences.

The convention this repo uses: the target project lives in a sibling
directory (`../portfolio-site/`) and is `.gitignore`d here. Stage 10
(publish gate) will be responsible for committing and pushing the target
into ITS own repo, separately from this orchestrator's repo.

If you're learning by copying this repo, follow the same pattern: keep
your TinyAgents fork in one repo, keep whatever it generates in another.
