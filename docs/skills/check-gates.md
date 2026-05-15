# Skill · check-gates

_Self-check prompt for the gates half of `docs/course/03-gates-and-failure-taxonomy.md`._

---

## Purpose

Test whether you can name the four gates in TinyAgents, place each one correctly in the pipeline, predict what each gate refuses to permit, and explain why the approval gate is the one that doesn't exist yet but matters most.

## How to use this skill

1. Paste the prompt block below into your preferred LLM (or read it aloud and answer yourself).
2. Answer each question — be specific about which gate fires where.
3. Compare against the rubric.

---

## The prompt

```
You are a TinyAgents course tutor. I'm checking my understanding of
gates — the deterministic checkpoints between pipeline stages
(TinyAgents course Lesson 03, docs/course/03-gates-and-failure-taxonomy.md,
"The four gates" section).

Ask me these five questions one at a time. After each answer, briefly
say which key idea it hit and missed. Don't reveal the full correct
answer until I've tried. At the end, give a one-paragraph verdict on
whether I'm ready to also tackle the failure-taxonomy half of Lesson 03
(see check-failure-taxonomy).

Questions:

1. Name the four gates in TinyAgents in pipeline order, and say what
   each one reads as input.

2. The install gate runs before the test gate. Construct a concrete
   scenario in which swapping the order would silently mislead the
   summarizer.

3. The review gate is described as "different in kind from the test
   gate". Give two specific examples of findings only the review gate
   can produce that the test gate, in principle, cannot.

4. The approval gate is listed but not yet implemented. What's the
   smallest realistic example of a thing TinyAgents could do today
   that, if done autonomously, would expose the absence of the approval
   gate?

5. A teammate proposes adding a fifth gate between Test and Review
   called "Smell Gate" that re-reads the Claude log and flags
   "suspicious-looking edits". Should TinyAgents add it? Why or why
   not — answer in terms of the gate contract, not "it'd be nice".
```

---

## What a good answer looks like

**Q1 — name and inputs.**

| # | Gate | Input |
|---|---|---|
| 1 | **Install gate** (Stage 6.5) | the target's `package.json` diff vs before; runs `npm install` |
| 2 | **Test gate** (Stage 4) | the target's discoverable scripts (`build`, `lint`, `typecheck`, `test`) |
| 3 | **Review gate** (Stages 9.5–9.7) | the running target (for functional probes), the source (for scope/security/content/docs), the rendered screenshots (for visual) |
| 4 | **Approval gate** (planned, not built) | `review-decision.json` + a human-typed approval command |

Order matters. Getting 3 of 4 right is a pass; getting Install and Test reversed is the common slip and counts against you because that's exactly what Q2 tests.

**Q2 — install-before-test ordering.**
The canonical scenario: Claude added a new dependency (say, `framer-motion`) to `package.json`. If `test` runs first, `npm run build` fails with `Cannot find module 'framer-motion'`. The summarizer reads that as a build failure and routes to a "Fix build error" loop — but the right routing is "install gate failed" → don't change the code, just install. Running install first turns the same situation into a clean install + a clean build. A weaker but correct answer references "dependencies-not-installed" without the routing detail.

**Q3 — review-only findings.**
Strong examples (any two):

- A production API endpoint that returns 200 in dev but should return 403 in production — only the functional review boots the production server and probes it.
- Origin/Host-header missing on a write endpoint, exposing it to cross-origin posts — only the security review thinks about cross-origin attack surface.
- README claims an upload UX that the component doesn't actually wire — only the docs review compares prose to component code.
- Hero card visually outweighs the headline at desktop width — only the visual review reads pixels.
- The agent touched files outside the goal's "Allowed Changes" lane — only the scope review reads the goal-spec for that.

Weak answer: "review catches semantic bugs". Too vague — the strength is in the specific category.

**Q4 — smallest current-day approval-gate failure.**
The clearest one: TinyAgents could already, in principle, write a `git commit && git push` invocation into a loop and execute it as soon as review passes. There's no code today that does this — but there's also no code that *prevents* it from being added in the same script. The absence of the approval gate means the only thing between "review passed" and "the world sees your bad commit" is the convention that the human runs `git push` themselves. Conventions break under pressure.

A second acceptable answer: a fixture-swap loop that forgets to restore `portfolio.json` would silently leave the target in fixture state. Today, `_deactivate_fixture` runs in a `finally` block, but there is no separate gate that *verifies the restore succeeded* before declaring the loop done. An approval gate would force a human-visible confirmation at that step.

**Q5 — should we add a "Smell Gate"?**
The strong answer: **no, not yet**. The gate contract is "deterministic check + named recovery". A "smell gate" that flags "suspicious-looking edits" is neither — it's LLM-mediated, fuzzy, and has no clear recovery loop. It also overlaps with the existing security and scope reviews. Adding it now would dilute the existing review gate's signal and introduce a new layer with no clear failure mode of its own.

A *weaker* but still acceptable answer: "wait for evidence". If three dogfood loops in a row produced the same class of suspicious edit that nothing currently catches, *then* design a gate around that specific pattern — not around the generic intuition.

A wrong answer: "yes, more gates are better." Gates are a tax on every loop; each one must earn its place by catching a class of failure no existing gate sees.

## Overall pass criteria

You can move to the failure-taxonomy check if you can:

- Name all four gates in order with their inputs.
- Justify install-before-test with a concrete scenario.
- Point at categories of review-only findings (production-runtime, cross-origin, design pixels, README drift, scope).
- Defend the absence of the approval gate as a real risk, not a minor gap.
- Reject "more gates" without specific evidence.

If you missed two or more, re-read `docs/course/03-gates-and-failure-taxonomy.md`'s **The four gates** and **What the gates do NOT do** sections.
