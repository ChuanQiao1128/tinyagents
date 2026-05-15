# Lesson Template

_The fixed structure every course lesson in `docs/course/` follows. Use this template for any new lesson, and check existing lessons against it when you suspect they've drifted._

---

## Why a fixed template?

A teaching-first project loses its teaching quality the moment two lessons follow different shapes. The reader has to re-orient on every page. A fixed template means:

- The reader knows what they're about to get and where to skim.
- Authors can't accidentally skip a load-bearing section (like "Dogfood Evidence").
- Future-you can update a single section across all lessons without rewriting whole files.

The template is below. Modules `01-four-step-loop.md` through `04-auto-loop-and-review.md` were written against an earlier 5-question shape that *is compatible* with this 8-section template — sections 1–5 of the template are a direct expansion of the five teaching questions. New lessons should follow the full 8-section form. Old lessons can be incrementally retrofitted to add the "Command to Run" and "Pass Criteria" sections if they're missing.

---

## The template

```markdown
# Lesson XX · <Name>

_One-line summary of what this lesson teaches._

---

## 1. Problem

What concrete failure happens without this layer? **Anchor in a real loop number** wherever possible — generic claims are not evidence. Two or three sentences max; this is the hook, not the explanation.

## 2. Concept

What this layer is, in conceptual terms that would apply to any AI Agent SDLC — not specific to TinyAgents yet. Why this layer is a *new* layer rather than a tweak to the previous one. Where its boundary sits relative to the layer below it.

## 3. TinyAgents Implementation

How TinyAgents specifically realizes the concept:
- Which CLI command(s) drive it.
- Which functions / regions of `tiny_agents.py` implement it.
- Which decisions are deterministic vs LLM-mediated.
- Which constants or thresholds the learner can tune.

This is the "look at the code" section. Cross-reference line numbers or function names so a learner can `grep` and find ground truth.

## 4. Dogfood Evidence

Which loop folder(s) in `loops/` demonstrate this layer? What did that loop show that earlier layers couldn't? Brief — 3–6 lines. Point at the relevant file inside the loop, don't quote large blocks.

Example shape:
> **Loop 002 (`002-...`)** — Claude hit `Reached max turns (8)`. The summarizer correctly routed to "Fix Claude executor failure", not a code-fix loop. Read `loops/002-.../next-loop.md` for the routing decision.

## 5. Artifact

What new file lands on disk because of this layer? What does it contain? Who reads it downstream? If the layer doesn't create a new file but adds to an existing one, say so explicitly — that distinction matters.

## 6. Command to Run

The exact shell commands a learner can run to exercise this layer themselves. Include both the minimal invocation and a real-project example. The point is to give the learner something they can paste and see happen — passive reading isn't enough.

Example shape:
```bash
# Minimal — produce a test report against the target's package.json scripts
python3 tiny_agents.py test --project ../portfolio-site

# Real example — same, but writes into the latest loop folder
python3 tiny_agents.py test --project ../portfolio-site
cat loops/$(ls -1t loops/ | head -1)/test-report.md
```

## 7. Learning Checkpoint

3–5 questions that test whether the learner has actually absorbed the layer. Each question is followed by a one-line **hint** describing the key idea a correct answer should contain — not a full answer, just enough for the learner to self-grade.

Example shape:
> **Q: Why is the install gate before `test`, not after?**
> _Hint: test's commands depend on installed deps; running test first would silently fail with confusing "cannot find module" errors. Ordering is correctness, not optimization._

## 8. Pass Criteria

A short paragraph (or 3–5 bullets) describing what "I understand this layer" looks like in practice. Phrase it as capabilities the learner gains, not facts they memorize:

- "Can predict which failure routing will fire for a given `claude.log` excerpt."
- "Can extend the gate with one more failure mode without breaking downstream consumers."
- "Can defend the decision to make this its own gate rather than a step inside the previous one."

Pass criteria should be observable. If you can't tell from the outside whether the criterion is met, sharpen it.

---

(end of template)
```

---

## A worked example: applying the template to Lesson 03 (Gates and Failure Taxonomy)

The current `03-gates-and-failure-taxonomy.md` was written against the earlier 5-question shape. If we retrofit it onto this 8-section template, the mapping looks like:

| Template section | Existing module's content |
|---|---|
| 1. Problem | The "What concrete failure happens without this layer?" subsection (loop 002 max-turns example). |
| 2. Concept | The "What does this layer make possible?" + "Where is the boundary..." subsections. |
| 3. TinyAgents Implementation | The "Four gates" walkthrough (install / test / review / approval). |
| 4. Dogfood Evidence | The "A real example: loop 002" subsection. |
| 5. Artifact | The "What new artifact does this layer leave on disk?" subsection. |
| 6. Command to Run | **MISSING** — to add: example commands for `tiny_agents.py test`, `tiny_agents.py review`, and how to inspect each gate's output. |
| 7. Learning Checkpoint | The existing "Checkpoint questions" with hints. |
| 8. Pass Criteria | **PARTIALLY THERE** — implied in checkpoint hints, but not consolidated. |

So the existing module is ~80% template-compliant. The retrofit work is small: add a "Command to Run" section and a "Pass Criteria" section. The body of the lesson does not need rewriting.

---

## Tone rules

These apply to every lesson written with this template.

1. **Anchor every claim in evidence**. If the claim is "loop 008 had 27/27 hard pass but review still surfaced issues", the loop folder must exist and the count must match. Lessons that drift from `loops/` are how teaching projects start lying.
2. **Don't oversell**. "TinyAgents can do X" is acceptable only when there's a `python3 tiny_agents.py ...` command that produces X. If X is planned-but-not-built, the lesson should not exist yet — see `00-overview.md`.
3. **Don't pad**. A lesson that runs to 30 KB to avoid feeling thin is worse than a lesson that runs to 8 KB and has every section earning its space. Sections 4 (Dogfood) and 7 (Checkpoint) are where lessons get padded most; keep them tight.
4. **Speak to the learner, not about them**. Use second person ("you can run …") in command and checkpoint sections; use third-person impersonal ("the gate records …") in concept and implementation. Avoid the marketing voice ("TinyAgents is excited to teach you …").
5. **Keep code blocks runnable**. If you put a shell command in section 6, it must work as written against the current repo, with no `<placeholder>` syntax to fill in. Use `../portfolio-site` as the canonical example target.

---

## When a lesson outgrows the template

Some layers might need an additional section — for example, an "Open Design Questions" section if the layer has known unresolved trade-offs that the curriculum wants to expose to the learner. Add the new section *after* the existing 8, not in between. The first 8 are the contract; anything beyond is local extension.

If you find yourself wanting to *remove* one of the 8 sections, that's a signal the lesson isn't fully a layer yet. Common culprits:

- No "Dogfood Evidence" → the layer isn't real yet; revisit `progress-map.md` and decide whether to defer the lesson.
- No "Command to Run" → the layer might be conceptual-only (e.g. a meta-essay) and probably belongs in `docs/concepts/` or `docs/comparison/`, not in `docs/course/`.
- No "Pass Criteria" → you haven't decided what understanding looks like; this is hard to skip and is the section most worth wrestling with.

---

_See also: `docs/course/00-overview.md` for the curriculum's framing, `docs/course/01-four-step-loop.md` through `04-auto-loop-and-review.md` for existing lessons that mostly conform to this template._
