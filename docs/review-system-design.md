# TinyAgents Review System — Design

_Status: design document only. Stage 9.5 (Functional + Static + single-pass
Quality review) is implemented. Stages 9.6–9.9 are scoped here but not
yet implemented. This file is the spec for what should be built._

_Author: TinyAgents core. Last updated: 2026-05-12._

---

## 1. Why Review Exists

TinyAgents already has three layers that decide whether a loop is "done":

- **Tests** — `npm run build` / `lint` / `test` succeed in `cmd_test`.
- **Hard criteria** — mechanical checks from the goal file: `file_exists`,
  `file_absent`, `script_passes`, `forbidden_dep`.
- **Scope gate** — diff-based check for forbidden writes (`.env*`,
  red-line deps, large changes).

These three are sufficient to answer **"did anything obviously break?"**.
They are NOT sufficient to answer **"is this actually a good, safe,
publishable product?"**. Stage 7D and Stage 9 both produced cases where
all three layers said *done* but the project was not actually usable:

| Run | All three green | Real state |
|---|---|---|
| Stage 7D loop 007 | 21/23 hard pass + build / lint pass | Build/lint had *not been run* — Stage 6.6 misclassified Claude max-turns. Fixed in Stage 6.9. |
| Stage 9 loop 008 | 27/27 hard pass + build / lint pass | Studio existed but **no one verified** the production guard, the Save API actually wrote files, the public page actually rendered from JSON, or the README explained anything. User had to do all of this by hand and partially missed the production-guard test. |

Review is the answer to the second question. It catches the class of
problems where **structure looks right but behavior, security, design, or
scope is wrong**. Review findings become next-loop tasks when they are
actionable, and structured questions when they require a human decision.

Concretely, Review exists to:

- Verify runtime behavior the unit-level test step can't (production
  guards, route-level access control, side-effect containment).
- Verify scope adherence (did Claude stay inside `Allowed changes`?).
- Verify security (no committed secrets, no exposed write APIs, no
  unsafe filesystem operations).
- Verify design / UX intent (did Claude follow the Visual Direction?).
- Verify documentation alignment (does the README explain what was
  actually built?).
- Decide publish readiness (block Stage 10's Git/Vercel/domain actions
  until the above are clean and a human has signed off).

Review is **not**: a second test runner, an auto-fixer, a deploy
mechanism, or a way to bypass human judgment on subjective decisions.

---

## 2. Architecture Overview

Each review is structured as **two parallel layers**:

- **Deterministic layer** — pure code: regex scans, AST-light grep,
  HTTP probes, file diffs, manifest comparisons. Fast, free, repeatable.
  No LLM.
- **LLM layer** — short, JSON-output `claude -p` calls. Used for
  judgment that can't be expressed deterministically: "does this
  implementation match the goal's Visual Direction?", "is this change
  inside scope?".

Each category below specifies what belongs in each layer. The
deterministic layer is always preferred for correctness, cost, and
auditability. The LLM layer is used only where deterministic checks are
infeasible.

Each review produces three artifacts:

- `loops/<NNN-...>/review-report.md` — human-readable report.
- `loops/<NNN-...>/review-decision.json` — machine-readable, consumed by
  `cmd_auto`'s state machine.
- `loops/<NNN-...>/human-questions.md` — only when `human-decision` items
  exist; pauses auto and waits for user answers.

Review runs **inside `cmd_auto` between hard-criteria check and
`decide_next_action`**, OR standalone via `cmd_review`. The exact
sequencing is in §6.

---

## 3. Review Categories

Each subsection below follows the same structure: *Purpose*,
*Deterministic checks*, *LLM checks*, *Inputs*, *Outputs*, *Example
issues with severity*.

### 3.1 Functional Review (Stage 9.5, IMPLEMENTED)

**Purpose:** verify runtime behavior of the *production* build —
specifically, that routes which should be blocked are blocked, and that
APIs which should refuse writes do refuse them.

**Deterministic checks:**

- Run `npm run build && npm start` on a non-3000 port (default 3737),
  poll until ready (30s deadline), kill cleanly via process-group SIGKILL.
- For each `production_allows_path: X` in the goal: `GET X` must return
  200.
- For each `production_blocks_path: X`: `GET X` must return non-200, OR
  200 with a body containing a known disabled-message phrase ("local
  development only", "studio is only available", "disabled in
  production", "not available in production").
- For each `production_blocks_post: X`: `POST X` (empty JSON body) must
  return ≥400 (403 / 404 / 405).
- Before any POST probe, take a byte-level backup of
  `src/content/portfolio.json`. After all POSTs, compare; if mutated,
  flag as blocker and restore the file from backup.

**LLM checks:** none. Functional review is purely mechanical.

**Inputs:**

- Goal file `## Functional Review Criteria` section.
- Target project (must have `package.json` with a working `start`
  script).

**Outputs:**

- `functional` block in `review-decision.json`:
  ```json
  {
    "ran": true,
    "server_started": true,
    "checks": [
      {"kind": "GET", "path": "/", "status": 200, "pass": true},
      {"kind": "GET", "path": "/studio", "status": 200, "pass": false,
       "detail": "production server returns working content"}
    ],
    "portfolio_mutated_in_production": true
  }
  ```

**Example issues:**

| Severity | Example |
|---|---|
| **blocker** | `/studio` returns 200 with a working editor in production |
| **blocker** | `POST /api/studio/save` returns 200 in production |
| **blocker** | `portfolio.json` is byte-different after POST probes |
| **must-fix** | `GET /` returns 200 but body is suspiciously short (<200 bytes) |
| **should-fix** | Server took >15s to become ready (slow build, but not broken) |
| **nice-to-have** | The disabled-message body could be more informative |

### 3.2 Code / Scope Review (Stage 9.6, TO BUILD)

**Purpose:** verify the loop's file changes stayed inside the goal's
scope and didn't drift in dependencies or hardcoding.

**Deterministic checks:**

- Compare per-loop diff (already produced by `snapshot_project` /
  `diff_snapshots`) against the goal's `## Scope → Allowed changes` /
  `Forbidden` lists. Any added or modified file not covered by Allowed,
  OR explicitly listed in Forbidden, is a scope drift.
- Parse `package.json`'s `dependencies` / `devDependencies` /
  `peerDependencies` before vs after. Flag every newly-added dep that
  matches `DEFAULT_FORBIDDEN_DEPS`, ends with `-cli`, or isn't in the
  goal's allow-list.
- Grep changed `.tsx` / `.jsx` / `.ts` files for hardcoded patterns:
  - `"TODO:` / `'TODO:` string literal counts (already in 9.5 as a
    heuristic).
  - Email-looking literals not behind `{...}`.
  - URL-looking literals (github.com / linkedin.com / twitter.com) in
    `.tsx` files outside the content directory.

**LLM checks:**

- Read goal's `## Scope` + the list of changed files + a sample of
  changed file content. Ask Claude: "did this loop stay within scope?"
  Output is severity-tagged.
- Read the loop's `next-loop.md` + the actual diff. Ask Claude: "did
  the implementation match the recommended task, or did it expand?"

**Inputs:**

- Pre-Claude and post-Claude project snapshots (already collected by
  Stage 6.9).
- Goal file's `## Scope` section.
- `package.json` before / after (read via git or stored snapshot if
  not git-tracked).

**Outputs:**

- `scope` block in `review-decision.json`:
  ```json
  {
    "files_outside_allowed": ["app/api/auth/login/route.ts"],
    "files_in_forbidden": [],
    "new_deps": [{"name": "next-auth", "in_red_line": true}],
    "hardcoded_suspects": [
      {"file": "app/page.tsx", "pattern": "email literal", "count": 1}
    ],
    "llm_findings": [...]
  }
  ```

**Example issues:**

| Severity | Example |
|---|---|
| **blocker** | New dep `next-auth` added (red-line list) |
| **blocker** | New file `app/api/auth/login/route.ts` (auth is in Forbidden) |
| **must-fix** | `<h1>John Smith</h1>` hardcoded in `app/page.tsx` (should be `{profile.name}`) |
| **must-fix** | Diff includes 14 files outside Allowed |
| **should-fix** | One dependency added that could be replaced with a 5-line util |
| **nice-to-have** | A `Section.tsx` primitive could be extracted |

### 3.3 Security Review (Stage 9.6, TO BUILD)

**Purpose:** prevent secrets from being committed and ensure dangerous
APIs are guarded.

**Deterministic checks:**

- Regex scan every changed file (NOT `.env*`, NOT files under
  `node_modules/`) for:
  - `AKIA[0-9A-Z]{16}` (AWS access key)
  - `sk-[a-zA-Z0-9]{20,}` (OpenAI / generic secret)
  - `ghp_[a-zA-Z0-9]{36}` / `gho_[...]` / `ghu_[...]` (GitHub tokens)
  - `xox[bpars]-[0-9]{10,}` (Slack)
  - High-entropy 32+ char hex / base64 strings in `.ts` / `.tsx` /
    `.js` / `.json` (heuristic; high false-positive — emit as warning
    requiring human-decision review of the match)
- `.env*` files: must NOT be in the diff. If they are: blocker.
- For every API route handler in changed files, grep for one of:
  - `process.env.NODE_ENV`
  - `NODE_ENV === "production"`
  - `production` check via Next.js helper
  If a route mutates the filesystem (`writeFile`, `fs.appendFile`, etc.)
  AND no production guard is found: must-fix.
- Filesystem-write detection: any `writeFile` / `fs.appendFile` /
  `fs.cp` / `fs.rename` in a non-test file whose path argument isn't
  obviously sandboxed (look for `path.join(public, ...)` or a literal
  starting with `./public/` or `process.cwd() + "/public/"`).

**LLM checks:**

- Read API route handlers, ask Claude: "could any of these writes escape
  the project directory or write into user-controllable paths without
  validation?" Output severity-tagged.

**Inputs:**

- Full content of changed files (deterministic regex pass).
- A bounded sample of API route handlers (for LLM pass).
- The list of `.env*` files in the diff (always empty in correct code).

**Outputs:**

- `security` block in `review-decision.json`:
  ```json
  {
    "secret_matches": [
      {"file": "src/content/portfolio.json", "pattern": "high_entropy",
       "line": 42, "severity": "should-fix"}
    ],
    "env_files_in_diff": [],
    "unguarded_api_writes": [
      {"file": "app/api/studio/save/route.ts",
       "reason": "no NODE_ENV check before writeFile",
       "severity": "must-fix"}
    ],
    "path_traversal_suspects": [],
    "llm_findings": [...]
  }
  ```

**Example issues:**

| Severity | Example |
|---|---|
| **blocker** | `.env.production` is in the diff |
| **blocker** | `sk-...` literal found in `app/api/studio/save/route.ts` |
| **must-fix** | API route writes a file but has no `NODE_ENV === "production"` check |
| **should-fix** | A high-entropy string in `portfolio.json` (probably content, not a secret — but worth confirming) |
| **human-decision** | "Should we add a `.gitignore` rule for `public/projects/uploads/`?" |

### 3.4 Design / UX Review (Stage 9.7, TO BUILD)

**Purpose:** verify the implementation matches the goal's `## Visual
Direction` and `## Design Goal` sections. Text-based first (no
screenshots); visual-based later.

**Phase 1 — text-first (Stage 9.7a):**

**Deterministic checks:**

- Heading hierarchy in `app/page.tsx`: count `<h1>` / `<h2>` / `<h3>` /
  `<h4>` occurrences. A polished page typically has exactly one `<h1>`
  and a sensible cascade. Flag absent hierarchy.
- Responsive-class presence: count occurrences of `sm:`, `md:`, `lg:`
  in changed `.tsx` files. Zero responsive classes in a "design must be
  responsive" goal is a must-fix.
- Layout primitive reuse: if the goal lists components like `Section`,
  check whether they're actually imported and used in `app/page.tsx`.
- Tailwind class density per element: count classes per `className`
  attribute. Average >20 classes per element flags inconsistent /
  generated-feel layout.
- Copy hierarchy: count `<p>` density vs heading density. Wall-of-text
  detection: any `<p>` element whose literal child contains >500 chars
  is flagged.

**LLM checks:**

- Send Claude: the goal's Visual Direction + Design Goal sections, the
  full content of `app/page.tsx` and `app/layout.tsx`, the file list
  under `src/components/`. Ask: "list each Visual Direction line, and
  for each, say (a) implemented / (b) partially implemented / (c) not
  implemented / (d) cannot tell without rendering."
- Output is severity-tagged. Items in (d) become `human-decision` —
  they require visual review.

**Phase 2 — screenshots (Stage 9.7b, DEFERRED):**

Use a headless browser (Playwright via subprocess; not a Python dep but
an `npx playwright install` step done once). Navigate `/` and `/studio`
at 375px and 1280px widths, capture screenshots, send to multimodal
Claude with the Visual Direction. **This is explicitly out of scope for
9.5 / 9.6 / 9.7a.** Listed here for completeness.

**Inputs (Phase 1):**

- Goal's `## Visual Direction` + `## Design Goal` sections.
- All `.tsx` files in `app/` and `src/components/`.
- Studio-specific files if Studio is in scope.

**Outputs:**

- `design` block in `review-decision.json`:
  ```json
  {
    "heading_hierarchy": {"h1": 1, "h2": 4, "h3": 8, "ok": true},
    "responsive_classes_count": 23,
    "wall_of_text_paragraphs": 0,
    "primitive_reuse": {"Section": "used", "ProjectCard": "used"},
    "visual_direction_match": [
      {"line": "dark neutral background", "verdict": "implemented"},
      {"line": "two-column desktop layout where useful",
       "verdict": "cannot tell without rendering",
       "severity": "human-decision"}
    ]
  }
  ```

**Example issues:**

| Severity | Example |
|---|---|
| **must-fix** | Zero `<h2>` / `<h3>` in `app/page.tsx` (no hierarchy) |
| **must-fix** | No `sm:` / `md:` / `lg:` classes anywhere (no responsive design) |
| **should-fix** | `<p>` element with 800-char child (wall of text) |
| **should-fix** | Visual Direction said "subtle borders" but every section has `shadow-2xl` |
| **human-decision** | "Visual Direction says 'two-column desktop layout' — confirm visually whether this is implemented" |
| **nice-to-have** | More polish on mobile typography |

### 3.5 Content / Docs Review (Stage 9.6 or 9.7, TO BUILD)

**Purpose:** verify the implementation's content layer matches the
goal's content rules, and the README accurately documents what was
built.

**Deterministic checks:**

- For every required content file in the goal (e.g.
  `src/content/portfolio.json`): must exist (already in hard criteria),
  must be valid JSON, must contain the required top-level keys.
- README must contain at least one heading that mentions Studio /
  portfolio editing / content file (already heuristic in 9.5).
- README sections referenced by the goal (e.g. "Using the Studio",
  "How to add images") must exist as actual `##` headings.
- Hardcoded personal-content patterns in components: same set as scope
  review's hardcoded-suspects scan, but reported under content.

**LLM checks:**

- Send Claude: the README + the goal's `## Required Content File` /
  `## Image Support` / `## Component Structure` sections. Ask: "does
  the README explain how to do each thing the goal expects?" Output
  severity-tagged.

**Inputs:**

- README.md.
- Goal's content / docs sections.
- Content files (`portfolio.json`, `portfolio.schema.ts`, etc.).

**Outputs:**

- `content` block in `review-decision.json`:
  ```json
  {
    "content_files_valid": {"src/content/portfolio.json": "ok"},
    "missing_required_keys": [],
    "readme_sections_present": ["Using the Studio"],
    "readme_sections_missing": ["How to add images"],
    "hardcoded_in_components": [...],
    "llm_findings": [...]
  }
  ```

**Example issues:**

| Severity | Example |
|---|---|
| **blocker** | `src/content/portfolio.json` is invalid JSON |
| **must-fix** | README lacks the "Using the Studio" section the goal explicitly required |
| **must-fix** | Components import portfolio content but `portfolio.json` is missing 3 required top-level keys |
| **should-fix** | README mentions a `public/projects/` directory but doesn't say how to add images |
| **nice-to-have** | README's project description is one line; could be expanded |

### 3.6 Publish Readiness Review (Stage 9.9 + gates Stage 10+, TO BUILD)

**Purpose:** be the single gate between "TinyAgent says this is done"
and "TinyAgent will commit / push / deploy". Aggregates all other
reviews and adds publish-specific checks.

**Deterministic checks:**

- All other review categories: zero blocker, zero must-fix.
- `git status --porcelain` is empty (no uncommitted changes), OR the
  upcoming Git stage will commit them with explicit user approval.
- Production build last succeeded.
- No `.env*` file in the commit-staging area.
- A `loops/<latest>/human-approved.md` file exists with a timestamp
  newer than the latest review-decision.json.
- The goal file explicitly declares a publish target (e.g. has a
  `## Publish` section with `git_remote` and `vercel_project_name`).

**LLM checks:** none. Publish readiness is a synthesis, not a judgment.

**Inputs:**

- Latest `review-decision.json` for the project.
- `git status` output.
- Goal file's `## Publish` section (added in Stage 10's goal-spec).
- Human approval marker.

**Outputs:**

- `publish_readiness` block in `review-decision.json`:
  ```json
  {
    "all_other_reviews_clean": true,
    "git_status_clean": true,
    "build_recent_success": true,
    "no_env_in_diff": true,
    "human_approved": true,
    "human_approved_at": "2026-05-12T10:00:00",
    "publishable": true,
    "blockers": []
  }
  ```

**Example issues:**

| Severity | Example |
|---|---|
| **blocker** | Any other review still has a blocker |
| **blocker** | `git status` shows uncommitted changes the human hasn't approved |
| **must-fix** | `human-approved.md` is older than the latest review-decision.json (the user approved an older state) |
| **human-decision** | Which branch should be the production branch? |

---

## 4. Severity Model

Five levels. Higher severity always overrides lower when the same item
appears in multiple categories.

| Severity | Definition | Auto behavior |
|---|---|---|
| **blocker** | Product is broken, unsafe, or fundamentally misses the goal. | `continue-fix`. Never `done` while present. Always becomes next-loop task. |
| **must-fix** | Goal requirement not satisfied; product is degraded but not broken. | `continue-fix`. Never `done` while present (unless explicit `--allow-must-fix` override). |
| **should-fix** | Quality improvement that doesn't break the product. | `done` by default. `continue-polish` if `--auto-polish` is set. Always listed in auto-report.md. |
| **nice-to-have** | Pure improvement, no real downside if skipped. | `done`. Listed under "Polish ideas" in auto-report.md. Never becomes an auto-generated task. |
| **human-decision** | A choice the human must make (subjective UX call, publish target, branch strategy). | `needs-human-feedback`. Auto pauses, writes `human-questions.md`, exits 0. |

Migration from Stage 9.5's three-level model (blocker / warning / info):

- 9.5 `blocker` → stays `blocker`.
- 9.5 `warning` → split into `must-fix` (when it's a goal-rule
  violation) or `should-fix` (when it's a quality issue). The category
  field (`runtime` / `content` / `docs` / etc.) determines the default
  split; e.g. a `docs` warning is `should-fix`, a `runtime` warning is
  `must-fix`.
- 9.5 `info` → becomes `nice-to-have`.
- New: `human-decision` — emitted by Design/UX review and Publish
  readiness, never by deterministic checks alone.

---

## 5. Review Outputs

### 5.1 `review-report.md` (human-readable)

Already exists in Stage 9.5. Stage 9.6+ extends it with one section per
review category, plus a top-level severity-grouped summary. Structure:

```markdown
# Review Report

## Summary
- Overall: <decision-state>
- Counts: <blocker> / <must-fix> / <should-fix> / <nice-to-have> / <human-decision>
- Categories run: functional, scope, security, content, design

## Categories
### Functional Review
...

### Scope Review
...

(etc.)

## Issues by Severity
### Blockers
...
### Must-Fix
...
### Should-Fix
...
### Nice-to-Have
...
### Human Decisions
...

## Suggested Next Task
...

## Notes
- Review does not edit code.
- See `review-decision.json` for the machine-readable version.
- See `human-questions.md` if any human-decision items were found.
```

### 5.2 `review-decision.json` (machine-readable)

Consumed by `cmd_auto`'s state machine. Schema (one file per loop):

```json
{
  "schema_version": "1",
  "generated_at": "2026-05-12T10:00:00",
  "goal_file": "goals/portfolio-builder-studio-mvp.md",
  "goal_name": "Local Portfolio Builder Studio MVP (Stage 9)",
  "project_path": "/Users/qc/Documents/Claude/Projects/portfolio-site",
  "loop_path": "loops/008-...",
  "decision": "continue-fix",
  "categories": {
    "functional": { "ran": true,  "summary": {...}, "issues": [...] },
    "scope":      { "ran": true,  "summary": {...}, "issues": [...] },
    "security":   { "ran": true,  "summary": {...}, "issues": [...] },
    "design":     { "ran": true,  "summary": {...}, "issues": [...] },
    "content":    { "ran": true,  "summary": {...}, "issues": [...] },
    "publish_readiness": { "ran": false, "summary": null, "issues": [] }
  },
  "counts": {
    "blocker": 1, "must_fix": 2, "should_fix": 3,
    "nice_to_have": 1, "human_decision": 1
  },
  "suggested_next_task": "Add NODE_ENV guard to /api/studio/save before any writeFile call",
  "suggested_next_task_source": "security.unguarded_api_writes[0]",
  "human_questions_count": 1,
  "publish_readiness_blockers": [],
  "publishable": false
}
```

Each `issues[]` entry has a stable schema across categories:

```json
{
  "id": "security.unguarded_api_writes.0",
  "category": "security",
  "severity": "must-fix",
  "description": "/api/studio/save calls writeFile without checking NODE_ENV",
  "evidence": {
    "file": "app/api/studio/save/route.ts",
    "line": 12,
    "snippet": "await fs.writeFile(path, body);"
  },
  "suggested_next_task": "Add NODE_ENV guard to /api/studio/save",
  "auto_generated": true
}
```

### 5.3 `human-questions.md`

Only written when `human-decision` items exist. Schema:

```markdown
# Human Questions (loop 008)

Auto paused. Answer the questions below in this file, then re-run:

    python3 tiny_agents.py auto --project ... --goal-file ... [other flags]

Each `Answer:` line is read by the next auto run. Empty answer = "skip,
re-ask next time". Answers prefixed with `SKIP:` are recorded as
explicitly skipped and won't be asked again.

---

## Q1 [design / blocking]
**Visual Direction says "two-column desktop layout where useful". The
Studio's preview panel currently sits below the form on desktop. Is the
single-column desktop layout acceptable, or should preview sit beside
the form at 1024px+?**

Suggested answer format: one of: `single-column-ok`, `move-to-sidebar`,
`SKIP: explanation`.

Answer:

---

## Q2 [publish / non-blocking]
**Which Git branch should be the production branch when Stage 11 runs?**

Suggested answer format: a branch name (e.g. `main`).

Answer:
```

Auto reads this file at the start of each loop. Answered questions
become **constraints injected into research.md/plan.md** via the same
goal-injection mechanism Stage 8.1 already uses. Unanswered blocking
questions keep auto in `needs-human-feedback`.

---

## 6. Decision States

`decide_next_action` returns one of:

| State | Selected when | Auto action |
|---|---|---|
| `done` | hard pass + 0 blockers + 0 must-fix + (0 human-decision OR all human-decision answered) | Stop. Report success. |
| `continue-fix` | hard pass + ≥1 blocker OR ≥1 must-fix | Build next-loop task from top blocker/must-fix `suggested_next_task`. |
| `continue-polish` | hard pass + 0 blockers + 0 must-fix + ≥1 should-fix + `--auto-polish` flag set | Build next-loop task from top should-fix. |
| `needs-human-feedback` | hard pass + ≥1 unanswered human-decision blocking question | Write `human-questions.md`. Stop. Exit 0. |
| `needs-human-approval` | All reviews clean + no `human-approved.md` (only relevant when publish is in scope) | Stop. Prompt user to inspect, write `human-approved.md`, re-run. |
| `publish-ready` | All reviews clean + `human-approved.md` valid + publish goal-target present | (Stage 10+) Hand off to Git/Vercel/domain stages. |
| `blocked` | Scope violation, executor failure, blocked-repeat, or max-loops | Stop. Report which gate fired. |

State precedence (highest first): `blocked` > `needs-human-feedback` >
`continue-fix` > `continue-polish` > `needs-human-approval` >
`publish-ready` > `done`.

---

## 7. Integration with `auto`

Where review runs inside `cmd_auto`'s per-loop pipeline (existing steps
in plain text; new steps **in bold**):

1. Snapshot project before Claude.
2. Build per-loop run args; inject goal-derived research.md / plan.md
   (Stage 8.1) **+ inject answers from `human-questions.md` if any**.
3. Run `cmd_run` (scan → prompt → Claude → install → test → summarize).
4. Snapshot diff, check scope-violations.
5. Check hard criteria.
6. **If hard pass AND no scope-violations: run full review (all
   categories applicable to this goal).**
7. **Write `review-report.md` + `review-decision.json` into the loop
   folder.**
8. **If any human-decision items: write `human-questions.md`.**
9. `decide_next_action(state_info, hard_check, scope_violations,
   review_decision, ...)` returns one of the states from §6.
10. Append entry to `loop_history`.
11. If state ∈ {`done`, `blocked`, `needs-human-feedback`,
    `needs-human-approval`, `publish-ready`}: break.
12. Else: derive next task from decision's `next_task`, continue.

Review runs **once per loop**, after the loop's work has settled.
Standalone `cmd_review` runs the same pipeline but without the
surrounding `cmd_run` and writes to the latest loop (or to
`reviews/<timestamp>/` if no loop exists).

---

## 8. Design / UX Review Strategy

The design/UX category is the hardest to do well without screenshots.
The strategy:

**Phase 1 (Stage 9.7a) — text-first, no rendering.**

Catches the issues you'd catch by reading the source code:

- No heading hierarchy → must-fix.
- No responsive classes → must-fix.
- Wall-of-text paragraphs → should-fix.
- Components not actually used → should-fix.
- Visual Direction lines that the source clearly does or doesn't match
  → severity per line.

What text-first *cannot* catch:

- Whether the page actually looks polished.
- Whether the layout collapses at 375px in practice.
- Whether the typography reads well on real screens.
- Whether the chosen colors clash with each other.

Items in this gap are emitted as `human-decision` items, and surface
in `human-questions.md` as "Please look at the page yourself and
answer …".

**Phase 2 (Stage 9.7b) — screenshots, deferred.**

When ready:

- Use Playwright via Node subprocess (no Python dep). Install once
  with `npx playwright install`.
- For each route under review, capture screenshots at 375 / 768 / 1280.
- Save under `loops/<NNN-...>/artifacts/screenshots/`.
- Send to multimodal Claude with the Visual Direction section and ask
  for severity-tagged issues.
- Convert most `human-decision` items in §3.4 into
  `must-fix` / `should-fix` based on the rendered evidence.

**Phase 2 is explicitly OUT OF SCOPE for Stage 9.7a.** It is documented
here only so that 9.7a's design supports the eventual transition (e.g.
the issue schema already tolerates an `evidence.screenshot_path` field
that 9.7a never populates).

---

## 9. Human Feedback Loop

The full flow:

1. Loop N runs. Review produces ≥1 unanswered `human-decision` blocking
   item.
2. Auto writes `loops/<N>/human-questions.md` with one section per
   question, leaving `Answer:` blank.
3. Auto's terminal output ends with:
   ```
   Auto paused at loop N: needs human feedback.
   Edit loops/<N>/human-questions.md and re-run auto.
   ```
4. User edits the file, fills in `Answer:` lines, saves.
5. User re-runs the same `auto` command.
6. Auto detects that a previous loop produced unanswered questions, reads
   the file, finds the answers, and **injects them into the next loop's
   research.md and plan.md** as constraints (under a `## Decisions made by
   the human` section).
7. Loop N+1 proceeds with that context.
8. Each answered question is marked as resolved in
   `review-decision.json`. The same question is not re-asked.

If the user re-runs auto without answering, auto detects the unchanged
file and exits with the same `needs-human-feedback` state — no infinite
loop, no wasted Claude turns.

`SKIP: <reason>` answers are recorded as explicit skips. The review
agent must not generate the same question on subsequent loops.

---

## 10. Publish Readiness

Stage 10 (Git), Stage 11 (Vercel), Stage 12 (Domain) will all gate on
the publish-readiness review. What must be true:

- **All test scripts pass.** (Hard criteria.)
- **No blockers in any review category.** (review-decision.json
  `counts.blocker == 0`.)
- **No must-fix items, unless explicit `--allow-must-fix` flag.**
- **No secrets in any committed file.** (security review clean.)
- **No production editor exposure.** (functional review clean.)
- **No `.env*` file staged for commit.** (Verified at publish time.)
- **`human-approved.md` exists** in the latest loop, timestamped after
  the latest `review-decision.json`, with at minimum:
  ```markdown
  # Human Approval
  Approved at: 2026-05-12T10:00:00
  Approved by: <username from `git config user.name`>
  Approval covers loop: 010-...
  Review-decision.json hash: <sha256 of the file>
  Summary: <one-line human note>
  ```
- **`git status` clean OR the Git stage will commit with explicit
  per-file user approval.**

If any of these fail, the publish stage refuses to run and writes a
clear list of what's missing.

---

## 11. Implementation Roadmap

Each stage builds on the previous. Estimates are rough — actual line
counts will vary.

| Stage | What it adds | Builds on | Approx LOC |
|---|---|---|---|
| **9.5** ✅ | Functional + Static + single-pass Quality review. `cmd_review`. `review-incomplete` auto state. | Stage 8. | ~700 (shipped) |
| **9.6** | Code/Scope/Security review categories. `review-decision.json` schema. Severity model: 3-level → 5-level. Updated `decide_next_action`. | 9.5. | ~350 |
| **9.7a** | Design/UX review (text-only). Heading-hierarchy / responsive-class / primitive-reuse checks. LLM Visual Direction adherence pass. | 9.6. | ~250 |
| **9.8** | Human Feedback Loop: `human-questions.md` writer + parser, inject answers into research/plan, `needs-human-feedback` state. | 9.6 (uses severity model). | ~300 |
| **9.9** | Review Decision Engine: full state machine over 7 states, `--auto-polish` flag, `publish-readiness` category. Refactor `classify_review_outcome` → multi-category aggregator. | 9.6, 9.7a, 9.8. | ~250 |
| **9.7b** (deferred) | Screenshot-based design review via Playwright subprocess. | 9.7a + Node Playwright install. | ~250 + dependency |

Total new code (9.6–9.9): ~1150 lines on top of the existing ~700 in
9.5. Spread over 4 focused stages.

**Non-goals for any of these stages:**

- Auto-fixing review findings. Auto only emits next-loop tasks; the
  fixes come from Claude in the implementation step of the next loop.
- A separate review-only CLI binary. `cmd_review` and `cmd_auto`'s
  integrated review are the only entrypoints.
- A daemonized server. Functional review starts and kills its own
  production server per run.
- A web UI for reviewing. Review is CLI + Markdown reports only.
- LLM-based publish readiness. Publish readiness is a deterministic
  synthesis. No LLM call.

---

## 12. Non-Goals (entire system)

Review **never**:

- Modifies the target project.
- Calls `git commit`, `git push`, `vercel deploy`, or any state-changing
  external tool.
- Auto-fixes anything. Findings → next-loop tasks → Claude implements
  in the next loop.
- Stores credentials, tokens, or `.env` content in any output file. If a
  secret is detected, it is named by path + line + 4-char hash prefix
  only.
- Decides subjective design / UX questions. Those become
  `human-decision` items.
- Runs in production. Review is a pre-publish, local-only system.

---

## 13. Open Questions (to resolve before each stage)

These should be answered when the corresponding stage starts:

- **9.6:** How aggressive should the secret-scan regex be? Default
  high-entropy detector has high false positives. Initial cut: detect
  but classify as `should-fix` requiring human-decision review of the
  match.
- **9.7a:** When the goal's Visual Direction is vague, how many
  `human-decision` items can review emit before becoming noise? Cap
  per-loop at e.g. 5; truncate the rest with a count.
- **9.8:** How should auto handle a user who answers a question with
  obvious garbage (e.g. `Answer: asdfasdf`)? Probably accept it and let
  the next loop's Claude judge.
- **9.9:** Should `--auto-polish` be opt-in or opt-out by default?
  Recommendation: opt-in. Auto without the flag stops at `done` when
  only should-fix items remain.
- **10+:** Will publish-readiness ever be safe to run without
  `human-approved.md`? Default position: no, never. `--force-publish`
  flag is intentionally not added.
