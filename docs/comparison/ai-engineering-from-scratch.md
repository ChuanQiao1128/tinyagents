# Comparison · `ai-engineering-from-scratch`

_Why TinyAgents looks at this project for teaching-design inspiration, what it borrows, and what it deliberately doesn't._

---

## What `ai-engineering-from-scratch` is

[`rohitg00/ai-engineering-from-scratch`](https://github.com/rohitg00/ai-engineering-from-scratch) is a public GitHub course that teaches AI engineering end-to-end. As of the time of writing, the project's README describes roughly **20 phases** spanning ~400+ lessons, covering everything from mathematical foundations through deep learning, transformers, LLM internals, agent engineering, infrastructure, observability, and a set of capstone projects (a terminal coding agent, a production RAG chatbot, a multi-agent software engineering team, etc.). The course is multi-language (Python / TypeScript / Rust / Julia) and explicitly AI-native — it includes its own learning skills (`/find-your-level`, `/check-understanding`) that learners can invoke against an LLM.

The project's design slogan in its own words: **Learn it. Build it. Ship it for others.** Every lesson is a folder with `code/`, `docs/en.md`, and `outputs/`. Each lesson is structured to ship a small reusable artifact — a prompt, a skill, an agent, an MCP server. The course explicitly rejects "watch the video and move on" pedagogy.

This is a fundamentally different shape of project from TinyAgents. We are NOT trying to recreate it, replicate its scale, or compete with its scope. We are looking at it because its **teaching architecture is well-engineered**, and several of its design choices map cleanly onto what TinyAgents needs to be.

---

## Five things we borrow

### 1. Fixed lesson structure

`ai-engineering-from-scratch` enforces that every lesson follows a fixed shape: code first, docs second, outputs as evidence. The lessons feel like the same kind of thing because they actually are.

**What we do**: `docs/lesson-template.md` defines an 8-section structure that every TinyAgents course lesson follows (Problem / Concept / TinyAgents Implementation / Dogfood Evidence / Artifact / Command to Run / Learning Checkpoint / Pass Criteria). Modules 01–04 in `docs/course/` are 80% template-compliant today; the residual retrofit is small and tracked in the template doc.

### 2. Every lesson ships an artifact

The upstream course is clear: a lesson is not "you read this and learned a thing", it's "you produced X". X is reusable: a prompt, a skill, a small agent.

**What we do**: every TinyAgents course module is anchored in an *on-disk artifact* the system produces during a real run (`research.md`, `plan.md`, `test-report.md`, `review-decision.json`, `next-loop.md`, etc.). This is a tight conceptual match: their "every lesson ships a reusable artifact" is our "every layer leaves a new artifact on disk". The artifacts are the curriculum.

### 3. Progress map

The upstream course publishes a phase/catalog/roadmap so learners know where they are. It is not a single percentage — it's a structured catalog.

**What we do**: `docs/course/progress-map.md` shows TinyAgents' real status across **four independent axes** (Pipeline depth / Iteration count / Human integration / Output destination) with L0–L10 reference points. Cells are honestly marked ✅ / 🟡 / ⬜ — including the cells that aren't done. The 4-axis form is deliberate: a single linear progress bar would hide the shape of growth.

### 4. AI-native self-check skills

The upstream course ships skills like `/find-your-level` and `/check-understanding <phase>` — markdown-shaped prompts that learners can paste into an LLM to test themselves. This is what "AI-native learning" looks like in practice: the LLM is the tutor, the markdown is the curriculum.

**What we do**: `docs/skills/` contains five paste-into-LLM prompts (`check-four-step-loop`, `check-artifacts`, `check-gates`, `check-failure-taxonomy`, `check-auto-loop`). Each prompts the LLM to interview the learner across 5 questions with a rubric for self-grading. These are *not* yet packaged as proper Claude Skills — they're markdown-form precursors that can be promoted to skills once the project grows a packaging story.

### 5. Build / run / ship mindset

The upstream course pushes hard against passive consumption: every lesson is something you *do*, then ship. Even the documentation is action-oriented.

**What we do**: every TinyAgents course module has a **Command to Run** section that gives a learner an actual shell command they can paste and execute against the real codebase. The repo is dogfooded against a real target (`../portfolio-site/`) and the `loops/` folder is the evidence of that dogfood — not screenshots of a video, real files a learner can `cat`.

---

## Three things we deliberately don't borrow

### 1. Scope: knowledge tree vs. workflow evolution

The upstream course is a **knowledge tree**: mathematical foundations → ML → deep learning → transformers → LLMs → agent engineering → production. The lessons accumulate domain depth.

TinyAgents is a **workflow evolution**: one LLM call → test gate → failure routing → auto loop → review → human feedback → approval → publish → monitoring. The lessons accumulate SDLC capabilities, not ML knowledge.

These are perpendicular axes. A learner taking `ai-engineering-from-scratch` could finish Phase 5 (transformer internals) without ever having shipped a real product. A learner taking TinyAgents could finish the whole course without ever having implemented an attention head from scratch. **Both gaps are intentional**, in both directions.

### 2. Breadth and scale

The upstream course is ~400 lessons across ~20 phases. That scale is appropriate for a multi-year educational arc covering an entire technical field.

TinyAgents stays small on purpose. The course is bounded by **L0 → L10** — roughly 10 layers, each a small lesson. The progress map will never grow to 20 layers; if it tried, the project would lose teaching coherence. We trade breadth for **density**: each lesson is ~10 KB of markdown, anchored in 1–2 real loops, with 5 checkpoint questions.

This is a fair trade. Density matches the project's promise (you can read the whole curriculum in an afternoon); scale would break it.

### 3. ML / model fundamentals

The upstream course teaches calculus, linear algebra, ML basics, deep learning, transformers from scratch, attention mechanisms, etc.

TinyAgents teaches **none of this**. It treats the LLM as an off-the-shelf component with documented failure modes. The course's questions are about what happens *around* the LLM (orchestration, evidence, gates, review, human-in-the-loop), not what's *inside* it.

Reasoning: there are excellent resources for ML fundamentals (the upstream course among them). There are far fewer resources that take "we have an LLM coding agent, how do we build the SDLC around it?" seriously. TinyAgents fills that specific niche by *not* fighting the ML-fundamentals fight.

---

## Positioning, in one sentence

The upstream course is **AI Engineering from Scratch** — how to build modern AI systems from the math up.

TinyAgents is **AI Agent SDLC from Scratch** — how to build the software-development lifecycle that wraps a working AI agent.

If you only read one, pick by your gap. If you don't yet know how transformers work, the upstream course is more useful. If you already use an LLM coding agent daily and your question is "what do I do *with* it that doesn't shoot me in the foot?", TinyAgents is more useful. The two complement each other.

---

## A note on respect and attribution

`ai-engineering-from-scratch` is a substantial public-good project produced over many months by [@rohitg00](https://github.com/rohitg00) and contributors. The five teaching-architecture ideas TinyAgents borrows from it are the upstream project's contribution to how AI-native curricula get built — they make this kind of project teachable in the first place. Where this doc cites specific numbers (20 phases, 400+ lessons, the slogan, the skill names), those come from the project's own README and website at the time of writing; check the upstream repo for current numbers.

We are not affiliated with that project and do not copy its content path. We do think it sets a useful bar for what teaching-first means in this space, which is why this comparison exists at all.

---

## What this comparison tells the reader of TinyAgents

If you've landed here from outside the project: TinyAgents is small on purpose, narrow on purpose, and teaching-oriented on purpose. The Five Borrowings above are concrete enough that you can verify them — open `docs/lesson-template.md`, `docs/course/progress-map.md`, `docs/skills/`, the Command-to-Run sections of any course module — and see for yourself.

If you're considering forking or extending: please don't try to make TinyAgents into the upstream course's clone. The differences listed above (scope / breadth / model fundamentals) are load-bearing constraints, not gaps waiting to be filled. The project is most useful when it stays small and stays focused on its specific question: *how do we build an AI Agent SDLC we can trust?*

---

_See also: `docs/course/00-overview.md` for the framing; `docs/course/00-anti-patterns.md` for what we refuse to do as we grow._
