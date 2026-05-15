# 00 · Anti-Patterns

_The negative space of TinyAgents. Things this project deliberately refuses, and why each refusal is a teaching choice, not an oversight._

---

A teaching-first project's hardest skill is **knowing what not to add**. New features are easy to defend ("it would also be useful"). But each feature has an opportunity cost: it dilutes the learning signal, hides responsibility, or introduces a class of failure the curriculum can't explain.

Below are eight specific patterns TinyAgents avoids today, with the reasoning. If you fork this project and want to grow it, treat this list as the **load-bearing constraints**. Removing any of them is a real architectural change, not a tweak.

---

## 1. Multi-agent orchestration is not the default

**Pattern**: builder-agent and reviewer-agent and planner-agent and approver-agent, all talking to each other over a message bus.

**Why we avoid it**: multi-agent setups push responsibility *into the protocol between agents*. The learner sees inputs going into a black box and outputs coming out, but can't see *why* a particular decision was made. The protocol becomes the magic, and magic is the opposite of teachable.

**What we do instead**: one Claude session per role. The "role" is just a different prompt and a different artifact subset. Builder, Reviewer, and Design Critic are all the same Claude binary called three times with three different inputs. The responsibility boundary is visible in the prompt files on disk.

**When this would change**: if a single Claude session can't hold enough context to do its job — e.g. a project so large that the implementation prompt + the codebase exceeds the context window. We are nowhere near that. When we get there, multi-agent gets its own course module explaining the *cost* of the split alongside the benefit.

---

## 2. Auto-deploy is never fully automatic

**Pattern**: review passes → `git push` → CI/CD → live in production, with the human optional or absent.

**Why we avoid it**: deploy is irreversible (or expensive to reverse). Confidence in the agent's output is built incrementally over many runs; treating "review passed" as equivalent to "humans approved" collapses two different decisions into one. It also robs the human of the moment where they look at the diff and commit-or-not. That moment is the cheapest unit of judgment we have.

**What we do instead**: even at the Publish Gate (planned, not yet implemented), the human always runs the actual `git push` and the actual deploy. The agent prepares the commit, the diff, the message, the deploy summary; the human executes. If you can't tell the difference between "the agent did it" and "the agent suggested it and I did it", the gate is broken.

---

## 3. Don't invent a DSL or YAML before markdown stops working

**Pattern**: structured goal specs in YAML, JSON schemas for prompts, a custom DSL for loop definitions.

**Why we avoid it**: a DSL is a tax on every contributor and every learner. They now have to learn the DSL *before* they can learn the system. Markdown is the universal-prior format — anyone in software can read and edit a markdown file with no documentation. Switching to YAML or a DSL is justified only when markdown produces real, repeated friction — e.g. ambiguous parses, machine-readable fields that humans keep mis-typing.

**What we do instead**: goal files are markdown with a small set of conventional headings (Hard Criteria, Soft Criteria, Visual Direction, etc.). The parser uses simple regex. When a heading's structure needs to be machine-readable, we pull it into a small JSON object inline (see `review-decision.json`), not migrate the whole file.

**When this would change**: if three separate users in succession express the same parser-related confusion, switch the affected section to JSON or a small front-matter block — not the whole file.

---

## 4. Don't add a plugin system early

**Pattern**: an entry-point system that lets third parties register new stages, new reviewers, new gates without touching the core script.

**Why we avoid it**: a plugin system is a contract with future contributors that you don't yet know how to write. Each plugin point becomes a public API that has to remain stable. Premature plugin surfaces accumulate cruft faster than they accumulate plugins.

**What we do instead**: contributors are encouraged to **fork** rather than plug. A fork is a clearer artifact than a plugin — you can read the whole modified script in one file. When the project has five forks that all do the same thing, *then* extract a plugin point that matches the observed pattern. Not before.

---

## 5. Don't hide artifacts in binary logs or databases

**Pattern**: structured logging into SQLite / Postgres / Elasticsearch / a proprietary log format. Once the loop volume grows, "obviously" we need queryable storage.

**Why we avoid it**: the moment the loop's state is in a database, the learner can no longer `cat loops/008-.../next-loop.md` to understand what happened. They need a query tool, a schema, and an access path. The pedagogical promise of "every decision is visible on disk" is broken.

**What we do instead**: `loops/<NNN>-<slug>/*.md` and `*.json` are the source of truth, full stop. If we ever need fast querying (we don't, today), we'll build an *index over the markdown* and rebuild that index on demand. The markdown stays primary.

**The hardcoded commitment**: even if TinyAgents grows a Studio frontend, that frontend reads markdown. It does not have its own database. The day we add a database is the day we stop being a teaching project.

---

## 6. Don't confuse Review with Test

**Pattern**: tests pass → ship.

**Why this is wrong**: tests prove *the code can run*. Review asks *should we accept this?*. They answer different questions and use different machinery. A run can pass all build / lint / type tests and still have a production guard that doesn't actually guard anything (loop 008 was 27/27 hard pass but the upload endpoint had no Origin/Host check). Without a separate Review pass, that class of bug ships unchecked.

**What we do instead**: keep Test (Stage 4) and Review (Stages 9.5–9.7) as visibly separate pipeline steps with separate output files (`test-report.md` vs `review-report.md` + `review-decision.json` + `design-review.md`). When the auto loop decides whether to continue, it consults *both* — a "passed" test alone never produces a "done" decision; review has to also clear.

---

## 7. Don't treat `nice-to-have` as a blocker

**Pattern**: any review finding triggers a new loop. The system grinds on indefinitely chasing polish.

**Why this is wrong**: review findings have severity levels for a reason. A `nice-to-have` is a recommendation, not an obligation. Treating all findings as actionable produces:

- An endless treadmill of small improvements that diverge from the goal-spec.
- A reviewer who learns it should produce *more* findings, because all of them get attention.
- A human who tunes out the next review report, because most of it is noise.

**What we do instead**: the 5-level severity model (`blocker / must-fix / should-fix / nice-to-have / human-decision`) maps to four distinct decision states (`done / done-with-warnings / continue-fix / needs-human-feedback`). `nice-to-have` items can be done with warnings — they don't gate progress. The user can always opt to fix them as a separate "polish" loop, but the auto driver doesn't.

---

## 8. Don't let the AI make publish decisions

**Pattern**: at the Publish Gate, the agent decides whether to push, deploy, or bind the domain, based on whether its own review says `can_publish: true`.

**Why we avoid it**: the agent's review is *the same model evaluating its own work*. Even with role separation, that self-evaluation is correlated. A publish decision is the last point at which an independent observer (the human) can stop a bad commit from spreading. If the agent makes that call, the system has effectively no error correction at the most expensive layer.

**What we do instead**: `review-decision.json` produces `can_publish: bool` as a *recommendation*. The Publish Gate (planned, not yet implemented) requires an explicit human approval action — typically an "approve" command the user types after reading the diff. The recommendation tells the human which way to lean; the human still decides.

A subtler version of this anti-pattern shows up earlier: never let the auto loop decide that an irreversible action has happened just because review state says it could. Approval is a separate axis (axis C in the 4-axis model), not a side effect of axis A.

---

## A note on tone

This document is short by intent. Each of these eight refusals could be a paper. The point of putting them in a single page is so that a learner reading the course can spot, immediately, what *kind* of choice they are looking at when they hit a design decision. The right reaction is not "TinyAgents doesn't have feature X" — it's "TinyAgents has *chosen against* feature X for this specific reason, and that reason becomes wrong under these specific future conditions".

That's the operative knowledge. Features are easy; reasons are the curriculum.

---

_See also: `00-overview.md` for the 4-axis framing; `02-artifacts.md` for why markdown stays primary; `04-auto-loop-and-review.md` for severity vs decision state in practice._
