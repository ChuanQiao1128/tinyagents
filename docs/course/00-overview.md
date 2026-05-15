# 00 · Overview

_The frame for everything else in `docs/course/`._

---

## What TinyAgents is

TinyAgents is a **local, learning-first AI Agent SDLC engine**. It is a single Python script (`tiny_agents.py`) that wraps an LLM coding agent (Claude Code, in this build) with the scaffolding a software-development lifecycle needs to be **explicit, testable, reviewable, and auditable**:

- a goal spec on disk,
- a deterministic Research → Plan → Implementation prompt pipeline,
- a test runner that produces a structured report,
- a summarizer that classifies what the loop just did and recommends what kind of loop should run next,
- a multi-loop auto driver,
- a Review system that asks *should we accept this?* (distinct from *does it run?*),
- and a folder layout where every step writes evidence to disk in markdown / JSON.

If you can read a `loops/<NNN>-<slug>/` folder bottom-up, you can reconstruct everything TinyAgents was thinking at that point in time. The folder, not the running process, is the source of truth.

## What TinyAgents is **not**

- Not a production SaaS. It runs on your laptop. No multi-tenant, no auth, no hosted service.
- Not just a coding assistant. A coding assistant is the "Build" step. TinyAgents is the loop around the coding assistant — the part that decides what to ask it, what to verify after it answers, and whether to ask again.
- Not a competitor to LangGraph / OpenHands / AutoGen / SWE-agent / Claude Code. Those are runtimes, platforms, frameworks, benchmarks, and IDEs. TinyAgents sits one layer up: it *orchestrates* a coding agent and exposes every orchestration decision to the learner.

## Why teaching-first

Most agent projects optimize for *capability* (more tools, more agents, more domains). TinyAgents optimizes for **explanation**: every stage exists to answer one question the previous stage couldn't, and every stage's answer lands on disk in a fixed shape so a reader can verify the claim.

That means the project's primary product is not the script — it's the **chain of decisions a learner can walk through**:

```
Goal → Research → Plan → Build → Install → Test → Summarize → Review → Auto → ...
```

Each arrow is a learning module in `docs/course/`. The script is the runnable demonstration that the arrows actually mean what the docs say.

## The 4-axis model

A common framing trap is to treat "minimal → complete AI Agent SDLC" as a single linear progress bar. That hides what's really going on. TinyAgents grows along **four independent axes**:

| Axis | Question it answers | Range |
|---|---|---|
| **A. Pipeline depth** | How many stages does *one* iteration have? | LLM call → test gate → review gate → approval gate |
| **B. Iteration count** | What happens after a single iteration fails? | one-shot → manual retry → auto-routed retry → multi-loop auto |
| **C. Human integration** | When and how does the human enter? | reads output → reruns → answers async questions → approves irreversible actions |
| **D. Output destination** | Where does the work end up? | scratch → local target project → committed to git → preview deploy → production → monitored |

A useful capability often **advances one axis without touching the other three**. That decoupling is what makes the project teachable: each new layer changes exactly one shape of failure, so the learner can isolate cause and effect.

`progress-map.md` shows TinyAgents' current state across all four axes. It is intentionally **not** a single percentage.

## Where this project starts

Module 01 starts at the simplest meaningful loop: **Research → Plan → Implement → Test**. Four steps, four artifacts, one Claude call in the middle.

That is the *floor* of useful AI Agent SDLC — anything less than this is "I pasted a prompt into a chat and copied the answer". Each later module adds one carefully-chosen capability on top of this floor.

If you only ever do Module 01, you still get something useful. Each module above it is optional, but each one solves a specific failure mode that the modules below couldn't see. The course's structure mirrors the order capabilities were actually added to TinyAgents through dogfood — see `docs/case-studies/tinyagents-sdlc-learning.md` for the dogfood narrative.

## How TinyAgents differs from a "Large AI Agent SDLC Studio"

This is a critical distinction:

- **TinyAgents** is a learning-first **engine**. CLI only. One file of Python. A folder of markdown. It is meant to be read by a learner top to bottom.
- A **Large AI Agent SDLC Studio** (capitalized intentionally — that name refers to a *separate*, *future* productization project, not to TinyAgents) would be the production-grade web product: a control plane with auth, multi-user, hosted runtime, plugin marketplace, observability, billing, audit signing, role-based access. None of that lives here.

If TinyAgents ever grows a web UI, it will be a **viewer of the same loops/ folder** — not a server with its own database. The day we add a database is the day we stop being a teaching project. Module 00 (anti-patterns) writes this rule down explicitly.

## What stays out, on purpose

Three things this project deliberately refuses, even as it scales:

1. **No database**. `loops/<NNN>-<slug>/*.md` and `*.json` files are the source of truth for the system's state. Future visualizations, search, and even a Studio frontend should read those files, not a serialization of them.
2. **No multi-agent swarm**. One Claude session per role, swapped via different prompts and different artifact subsets. Multi-agent orchestration hides the responsibility boundary inside an agent-communication protocol that the learner can't see. We keep responsibility visible.
3. **No autonomous deploy**. Even when the Publish Gate eventually ships, the human approves the actual `git push` and the actual `vercel --prod`. The agent assembles; the human commits.

See `00-anti-patterns.md` for the full list and the reasoning.

## How to read this course

```
00-overview.md                       ← you are here
00-anti-patterns.md                  ← what we deliberately don't do
progress-map.md                      ← 4-axis status, honest
01-four-step-loop.md                 ← the floor
02-artifacts.md                      ← evidence on disk
03-gates-and-failure-taxonomy.md     ← how the loop refuses to lie
04-auto-loop-and-review.md           ← multi-loop + judgment beyond test
```

The four-step-loop module is the prerequisite. After that the order is reasonably free, though gates (03) tend to come up when you read auto-loop (04).

Each later module follows the same teaching shape and answers the same five questions:

1. **What does this layer make possible?**
2. **What concrete failure happens without this layer?**
3. **Where is the boundary between this layer and the previous one?**
4. **What new artifact does this layer leave on disk?**
5. **Where would the SDLC break if this layer were skipped?**

That five-question rubric is the contract of every module. If a future module can't answer one of the five, it isn't a layer yet — it's an idea.

---

_See also: `docs/case-studies/tinyagents-sdlc-learning.md` for the dogfood narrative; `docs/stage-roadmap.md` for the engineering-side stage list; `docs/review-system-design.md` for the Review system's spec._
