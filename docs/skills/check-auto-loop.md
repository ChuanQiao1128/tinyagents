# Skill · check-auto-loop

_Self-check prompt for `docs/course/04-auto-loop-and-review.md`._

---

## Purpose

Test whether you can walk the auto state machine without re-reading the lesson, defend the split between Test and Review on first principles (not catch-phrases), and predict what would happen across the system if you re-tuned the severity → decision mapping.

## How to use this skill

1. Paste the prompt below into your LLM of choice.
2. Answer each question — the third question is a small design exercise, do it on paper.
3. Compare against the rubric.

---

## The prompt

```
You are a TinyAgents course tutor. I'm checking my understanding of the
auto loop and the Review system — TinyAgents course Lesson 04
(docs/course/04-auto-loop-and-review.md).

Ask me these five questions one at a time. After each answer, briefly
say what key ideas it hit and missed; don't reveal the full answer
until I've tried. At the end, give a one-paragraph verdict on whether
I've completed the core teaching track of TinyAgents.

Questions:

1. The auto loop has five terminal outcomes (states the chain stops
   on). Name them and, for each, say what the human is expected to do
   next.

2. Why is Review described as "not another test"? Give two examples of
   findings that Review can produce in principle but a unit-test-style
   gate cannot, even with a very thorough test suite.

3. Walk through what happens, in order, inside `build_decision()` when
   the inputs are: 0 blockers, 0 must-fix, 1 should-fix, 0 nice-to-have,
   2 human-decision. What's the resulting decision state and why?

4. A proposal: change the severity→state mapping so that human-decision
   outranks must-fix (i.e. the chain pauses for human input even when
   there are objective bugs to fix first). What concrete behavior would
   change? Would the change be an improvement?

5. `--max-loops` defaults to 3. A user wants to set it to 50 for a
   long-running task. Other than "more LLM cost", what specifically
   would degrade as `--max-loops` grows?
```

---

## What a good answer looks like

**Q1 — five terminal outcomes.**

| State | Human's next move |
|---|---|
| `done` | Open a new feature loop. Or move to the next stage of the product. |
| `done-with-warnings` | Read the warnings; decide whether to open a polish loop or accept and move on. Auto stops cleanly either way. |
| `needs-human-feedback` | Open `human-questions.md`, fill in `Answer:` lines, decide whether to re-run auto. (Stage 9.8 — automatic answer injection — does not yet exist; today this is a manual checklist.) |
| `blocked` | Read `claude.log` / `test-report.md` / `review-report.md`; diagnose the blocker (executor auth, sandboxing, scope violation); resolve; re-run. |
| `max-loops` | Read the chain so far; decide whether to bump `--max-loops` and continue, or pause and reconsider scope. |

A pass: name 4/5 with reasonable "next move" descriptions. A miss is conflating `blocked` with `max-loops` — they have different causes.

**Q2 — Review-only findings.**
The strongest answers anchor in *category* of finding, not just an example:

- **Functional behavior under realistic load**: a unit test can mock `process.env.NODE_ENV` to verify a guard; only a functional probe boots the actual production server and confirms the guard *as deployed* refuses the POST. The mock and the reality can disagree.
- **Cross-origin attack surface**: no unit test thinks about Origin/Host headers from a third-party site. The security review's job is to ask "what could a hostile page running on `evil.com` do to my localhost dev server?".
- **README oversell**: unit tests can't compare prose claims to component behavior. The docs review reads the README and the code and notices when they diverge.
- **Scope drift**: unit tests don't read the goal-spec's "Allowed Changes" section. The scope review does.
- **Visual hierarchy / spacing / palette**: zero source-level checks can see "the hero card is visually too heavy relative to the headline" — that requires pixels. The visual review's multimodal Claude does.

A weaker answer is "Review uses LLMs and tests don't". True but missing the point — the point is that LLMs unlock specific *categories* of judgment.

**Q3 — `build_decision()` for `0/0/1/0/2`.**

Walk:

1. Counts come in: `blocker=0, must-fix=0, should-fix=1, nice-to-have=0, human-decision=2`.
2. First rule: `blocker > 0 OR must-fix > 0` → false. Move on.
3. Second rule: `human-decision > 0` → true. State = **`needs-human-feedback`**.
4. The fact that `should-fix=1` exists doesn't matter; later rules don't fire once an earlier one does.

The auto driver will pause; `human-questions.md` is written; the chain stops.

A common slip: people say "done-with-warnings" because they see a should-fix and think that wins. The rule order is the point — `human-decision` outranks `should-fix`. Get this right, you've internalized the precedence.

**Q4 — re-ordering: human-decision above must-fix.**

Concrete behavior change: the chain pauses for human input even when there are objective bugs to fix. The human is asked to make taste calls *before* the system has cleaned up the obvious problems. Two real consequences:

- The human ends up answering questions about code that may be partially broken; the answers are less useful because they're conditioned on an unfinished state.
- Auto loses its ability to "make obvious progress" in the absence of a human, since any review with any taste-call would stop the chain immediately.

So no, this isn't an improvement. The current order is "fix what's clearly broken, then ask about taste". The alternative inverts that for no real gain.

A weaker but correct answer: "it'd cause more human interrupts for less benefit". Full credit requires saying *why* — the answers become lower-quality when conditioned on broken code.

**Q5 — why large `--max-loops` degrades.**
Beyond LLM cost (which the question excluded):

- **Drift compounds.** Each loop's choice biases the next loop's prompt. Over 20+ iterations, small misalignments produce a chain whose later loops are working on something the human wouldn't recognize as their original goal.
- **Audit cost grows linearly.** A 50-loop chain produces 50 `next-loop.md` files, 50 `test-report.md`s, 50 review reports. Reading the chain to figure out what happened becomes its own job.
- **No memory layer means re-learning.** TinyAgents does not yet have cross-loop memory (L6.5 on progress map). Each loop is told things the previous loop also got told. Wasted context window, wasted cost, occasional contradictions.
- **The brake's safety value drops to zero.** The whole point of `--max-loops 3` is forcing a human checkpoint before drift gets unrecoverable. Setting it to 50 is operationally equivalent to disabling the brake. If you genuinely want 50 loops, do five `auto --max-loops 10` runs with human inspection between each.

A strong answer touches at least two of these. A weak answer is just "drift" without explaining what drifts.

## Overall pass criteria

You have completed the core teaching track if you can:

- Name the five auto terminal states with correct human-next-action mappings.
- Justify Review's separateness from Test with at least two finding categories.
- Walk `build_decision()` rule order for an arbitrary count vector without re-reading.
- Reason about the cost of re-ordering severity rules in terms of *what concretely happens*, not abstractions.
- Predict the failure modes of growing `--max-loops` without invoking cost.

If you missed two or more, re-read `docs/course/04-auto-loop-and-review.md`'s **Auto state machine** and **Severity → decision** sections.

---

## What comes after this

When you're confident on all five course skills (four-step-loop / artifacts / gates / failure-taxonomy / auto-loop), you've internalized **L4 of the 4-axis progress map**. The next layers (L5 → L10) are listed in `docs/course/progress-map.md` but are not yet built — they will get their own lessons and check-skills as the corresponding stages land.

In the meantime, the recommended next learning step is **T1: a test harness for TinyAgents itself**, as described in `progress-map.md`. That's a defensive investment, not a new layer, but it's what unblocks confident growth toward L5 and beyond.
