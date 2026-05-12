# AI Engineer Personal Portfolio MVP

This is the goal spec consumed by `tiny_agents.py auto --goal-file
goals/portfolio-mvp.md`. It splits "done" into:

- **Hard criteria** — auto-verifiable by TinyLocalAgents after each loop.
  When all of these pass, `auto` stops with `done`.
- **Soft criteria** — written as a checklist for human review. `auto`
  surfaces them in the final `auto-report.md` but does NOT block on
  them.

Format:

- `- file_exists: <path>`    — file (or directory) must exist
- `- file_absent: <pattern>` — path must not exist; globs allowed (`.env*`)
- `- script_passes: <name>`  — npm script of this name must pass in the
  loop's `test-report.md`
- `- forbidden_dep: <name>`  — this dependency must NOT appear in
  `package.json` (the default red-line list is also enforced)

## First task

Create AI Engineer personal portfolio homepage

## Hard criteria

- file_exists: package.json
- file_exists: app/page.tsx
- file_exists: app/layout.tsx
- file_exists: app/globals.css
- file_absent: .env
- file_absent: .env.local
- file_absent: .env.production
- script_passes: build
- script_passes: lint
- forbidden_dep: stripe
- forbidden_dep: prisma
- forbidden_dep: mongoose
- forbidden_dep: mongodb
- forbidden_dep: next-auth
- forbidden_dep: clerk
- forbidden_dep: firebase
- forbidden_dep: firebase-admin
- forbidden_dep: pg
- forbidden_dep: mysql2
- forbidden_dep: redis
- forbidden_dep: ioredis

## Soft criteria

- Hero section presents a clear AI Engineer headline and one-line positioning
- About section has 2-3 paragraphs of narrative
- Featured Projects section includes TinyLocalAgents / Local Agent Dev Studio
- Featured Projects section includes Brand Voice Rewrite Studio
- Featured Projects section includes AI Engineering Learning Lab
- Skills / Tech Stack section groups capabilities meaningfully
- How I Work section has opinionated working-style notes
- Contact section has email and relevant profile links
- Copy clearly positions the author for AI Engineer / Full-stack AI Engineer roles
- Layout is responsive at 375px and 1024px widths
- No backend, database, auth, payment, CMS, or external API integration is added
