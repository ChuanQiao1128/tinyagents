# Goal: Local Portfolio Builder Studio MVP (Stage 9)

## Goal

Add a local-only **Builder Studio** to the existing portfolio project so the user can edit their portfolio content through a web UI instead of editing TypeScript files by hand.

This is the first slice of a larger Builder + Publisher product. **This MVP is editor + save + preview only**. Git, Vercel, and custom-domain workflows are explicitly out of scope for this loop and will be addressed in subsequent goals.

The existing public portfolio page (the generator from the previous goal) must keep working and must still look polished. The Studio is added next to it, not in place of it.

## First task

Add a local-only Builder Studio to the existing portfolio: migrate content from `portfolio.ts` to `portfolio.json`, build a `/studio` editor page, and wire save / load / upload APIs.

## Product Concept

The user should be able to:

1. Open `http://localhost:3000/studio` while running the project locally.
2. See forms for **profile**, **projects**, **skills**, **work principles**, and **contact**.
3. Edit any field. Add, remove, or reorder projects, skill groups, and principles.
4. Upload project images, which save into `public/projects/` and become referenceable by `/projects/<filename>`.
5. Click **Save** — the content is written to `src/content/portfolio.json` on disk.
6. Click **Preview** (or have the preview pane auto-refresh) to see the public page reflect the saved content.
7. Close the editor, run `npm run build`, and ship the static site exactly as the generator already supports.

Nothing in this Stage 9 MVP commits, pushes, or deploys anything.

## Local-first Rule (CRITICAL)

The Studio is for **local development only**. Production builds must not serve a working editor.

Concretely:

- The `/studio` page must check `process.env.NODE_ENV` (or equivalent) and, in production, render a clear message such as *"Studio is only available in local development."* with no working form.
- All `/api/studio/*` route handlers must short-circuit with a 403 (or 404) response in production. They must never write files in a production environment.
- The Studio's existence must not affect the public `/` page's bundle size or static-export behavior in any user-visible way.

This is not optional. A deployed Studio is a security hole.

## Target User

A developer or AI engineer who is comfortable running the site locally (`npm run dev`) but wants to maintain portfolio content without editing React components or hand-shaped TypeScript objects.

## Migration from `portfolio.ts` to `portfolio.json`

The previous goal created `src/content/portfolio.ts` with typed content. This loop migrates it to a JSON-first shape so a form-driven editor can read and write it cleanly:

- New: `src/content/portfolio.json` — the content the user owns and edits. Starts from the values currently in `portfolio.ts` so nothing is lost.
- New: `src/content/portfolio.schema.ts` — TypeScript types (re-use or refactor the existing `Portfolio`, `PortfolioProject`, etc. types). These describe the shape of the JSON.
- New: `src/content/loadPortfolio.ts` — exports a function or pre-validated constant the components import. Reads `portfolio.json`, asserts it conforms to the schema, returns a typed `Portfolio`.

After migration:

- `src/content/portfolio.ts` may be removed, OR kept as a thin re-export of `loadPortfolio()` for backward compatibility (your call — keep whichever is cleaner).
- All public components (`Hero`, `About`, `Projects`, etc.) must import from `loadPortfolio` (or the typed JSON via the loader), not from a hand-written TS object.
- The public page (`/`) must render identically before and after this migration when given equivalent content.

## Design Goal

The Studio UI should look polished and professional. It should feel like a developer tool, not a generic admin dashboard.

Match the visual style of the existing public portfolio (same typography, spacing, color palette, neutrals). The Studio is the same product, just in edit mode.

## Design Research Instructions

Before coding the Studio UI, decide:

- Overall layout: single column of stacked forms? Two columns (form on left, preview on right)? Tabs per section?
- Field grouping: each section (Profile / Projects / Skills / etc.) gets its own card or panel.
- The Projects editor specifically needs: add-project button, per-project delete, reorder up/down, and inline image upload.
- Empty states: what does "no projects yet" look like? What does an unsaved-changes indicator look like?
- Save flow: explicit Save button vs auto-save? **Pick explicit Save** for Stage 9 — auto-save invites accidental overwrites and the diff with Git later will be cleaner.
- Preview: an iframe pointing at `/` with a Reload button is sufficient. No need for live in-form preview.
- Status surfaces: a small status strip at the top showing *Last saved at HH:MM* and the current Save / Reload state.

## Visual Direction

The Studio shares the public site's palette and typography:

- same background and surface treatments as the public page
- form inputs that feel native to the design (clear focus rings, no busy borders)
- consistent spacing rhythm with the public page
- buttons match the public page's CTA style for the primary Save
- destructive actions (delete project, remove principle) need a clearly secondary or muted color and ideally a confirm
- preview pane (if iframed) sits in a bordered surface like a project card
- mobile layout: the Studio doesn't need to be lovely on mobile — desktop-focused is fine, but it shouldn't break

Avoid:

- a generic SaaS admin look (don't suddenly switch to a totally different visual language)
- modal-heavy flows (everything inline)
- spinners that block the whole UI
- fake animations or marketing-style polish

## Content Rules

The Studio writes user-supplied content into `portfolio.json`. Therefore:

- Keep all sample / TODO placeholder values in `portfolio.json` for first-run usability. Do not invent real names, companies, or URLs.
- Do NOT hardcode any personal content inside Studio components or API handlers.
- Do not save tokens, API keys, or any secrets to `portfolio.json`. The JSON is content only.

## Studio Requirements

The Studio page at `/studio` must include:

1. **Profile editor** — name, role, location, headline, short bio, long bio (array of paragraphs), current focus, optional avatar path, optional resume path.
2. **Projects editor** — list of projects with add / delete / reorder. Per project: title, status, summary, description, image upload (or path), tech chips, highlights (bulleted), links (github / demo / case study).
3. **Skills editor** — list of skill groups with add / delete / reorder. Per group: title, skills (chips with add / remove).
4. **Work principles editor** — list of principles with add / delete / reorder. Per principle: title, description.
5. **Contact editor** — email, GitHub, LinkedIn.
6. **Image upload** — wired into the Projects editor. Uploaded files land in `public/projects/`. The project's `image` field becomes `/projects/<filename>`.
7. **Preview pane** — iframe pointing at `/`, with a Reload button. After Save succeeds, the iframe should be reloadable to see the new content.
8. **Save button** — calls `/api/studio/save`. On success, updates a "Last saved" indicator.
9. **Local-only banner** — a small notice somewhere on the page like *"Local development only. Changes are written to your local filesystem."*

## API Routes (Next.js Route Handlers)

All under `app/api/studio/`. All must respond 403 (or 404) in production.

- `GET /api/studio/load` — returns the current `portfolio.json` contents as JSON. Used to hydrate the form on page load.
- `POST /api/studio/save` — receives a JSON body, validates basic shape, writes to `src/content/portfolio.json`. Returns `{ ok: true, savedAt }` or a 400 with a useful error message.
- `POST /api/studio/upload` — receives `multipart/form-data` with a single image, validates the MIME type (allow png, jpg, jpeg, webp, gif, svg), sanitizes the filename, writes to `public/projects/`, returns `{ ok: true, path: "/projects/<filename>" }`.

Use the standard Web `Request` / `FormData` APIs available in Next.js route handlers — do NOT add new dependencies for multipart parsing.

Validation:

- Save: at minimum, reject if the body isn't an object or if `profile`, `projects`, `skillGroups`, `workPrinciples`, `contact` aren't all present (even if empty arrays / empty objects). The schema check from `portfolio.schema.ts` is the right place to live.
- Upload: cap file size at 5 MB. Reject anything outside the allowed MIME list. Sanitize the filename to `[a-z0-9._-]+` (lowercase, dots, dashes, underscores; reject anything else or rename it). Never let the path escape `public/projects/`.

## Image Support

- Uploaded images go to `public/projects/`.
- The Studio's image field on each project accepts either an uploaded file (which becomes a `/projects/<filename>` path) or a manually typed path.
- The public `ProjectCard` (already exists) must still render a tasteful placeholder when `image` is empty or missing.
- Don't delete the existing placeholder logic — preserve graceful degradation.

## Component Structure

Keep public components separate from Studio components so each can evolve cleanly:

- `src/components/` (existing) — public components used by `/`. Keep these.
- `src/components/studio/` (new) — Studio-only components: `ProfileForm`, `ProjectsEditor`, `ProjectRow` (single-project editor inside the list), `SkillsEditor`, `WorkPrinciplesEditor`, `ContactEditor`, `ImageUpload`, `PreviewPane`, `SaveBar`. Adjust names if a clearer split emerges.

Do not over-componentize. A 200-line `ProfileForm` is fine; eight components for one form is overengineered for this stage.

## Scope

**Allowed changes:**

- `app/page.tsx`, `app/layout.tsx`, `app/globals.css` (only to wire the loader; keep the existing visual design)
- `app/studio/page.tsx` (new)
- `app/api/studio/load/route.ts`, `app/api/studio/save/route.ts`, `app/api/studio/upload/route.ts` (new)
- `src/content/portfolio.json`, `src/content/portfolio.schema.ts`, `src/content/loadPortfolio.ts` (new)
- `src/content/portfolio.ts` (may be removed or kept as a back-compat re-export)
- `src/components/` (small edits to use the loader)
- `src/components/studio/*` (new)
- `public/projects/` (new uploads OK)
- `README.md` (explain how to use the Studio)
- `package.json` only if absolutely required — but per the API note above, no new dependencies should be needed.

**Forbidden in this loop (out of scope for Stage 9):**

- Git operations (`git init`, commit, push) — handled in a later goal
- Vercel deploy or CLI calls — handled in a later goal
- Custom domain binding — handled in a later goal
- Any `/api/studio/build-check`, `/api/studio/git-*`, `/api/studio/vercel-*`, `/api/studio/domain-*` route — defer
- Backend services, databases, auth, payments, CMS, analytics, AI chatbots
- Storing tokens or secrets anywhere in the repo
- Any `--dangerously-skip-permissions` or `bypassPermissions` reasoning
- Adding telemetry or analytics scripts
- Touching `.env*` files

## Hard Criteria

- file_exists: package.json
- file_exists: app/page.tsx
- file_exists: app/studio/page.tsx
- file_exists: app/api/studio/load/route.ts
- file_exists: app/api/studio/save/route.ts
- file_exists: app/api/studio/upload/route.ts
- file_exists: src/content/portfolio.json
- file_exists: src/content/portfolio.schema.ts
- file_exists: src/content/loadPortfolio.ts
- file_exists: README.md
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

## Visual Review Targets

These tell the Stage 9.7 visual-review agent which routes and viewports to
capture full-page screenshots of. The agent then asks a design-critic
Claude session to compare those screenshots against the Visual Direction /
Design Goal sections of this file.

- screenshot_path: /
- screenshot_path: /studio
- screenshot_viewport: desktop
- screenshot_viewport: mobile

The current screenshot helper (`scripts/screenshot.mjs`) uses:

- desktop: 1440×1200
- mobile: 390×844 (iPhone 14 / 15 Pro range, deviceScaleFactor 2)

If these viewports stop being useful, the Node helper's `VIEWPORTS` array
is the place to change them — the goal-spec values above are advisory for
now (the helper hard-codes its own real values to keep the spec/code
contract honest).

## Functional Review Criteria

These are exercised by the Stage 9.5 review agent. It runs `npm run build &&
npm start` on a non-3000 port and probes:

- production_allows_path: /
- production_blocks_path: /studio
- production_blocks_post: /api/studio/save
- production_blocks_post: /api/studio/upload

Pass conditions:

- `production_allows_path: /` must return HTTP 200 (the public homepage works).
- `production_blocks_path: /studio` must either return a non-200 status or
  return 200 with a clearly disabled-message page (e.g. "Studio is only
  available in local development"). A fully working editor in production
  is a **blocker**.
- `production_blocks_post: /api/studio/*` must return ≥400 (403 / 404 / 405).
  In addition, the review checks whether `src/content/portfolio.json` was
  modified by the POST probes — if it was, the production write-guard is
  broken and is reported as a **blocker** (the file is restored from the
  backup the review took before probing).

## Additional Hard Requirements

The implementation must satisfy these even if the automated checker cannot fully verify them:

- The public `/` page renders the same content as before from the new JSON-backed loader.
- React components do not import `portfolio.ts` directly — they go through `loadPortfolio`.
- `/studio` exists and presents working forms for profile, projects, skills, work principles, and contact.
- Saving from `/studio` writes to `src/content/portfolio.json` and the public page reflects the new content on next render.
- Uploading an image saves into `public/projects/` and returns a usable path.
- In production (`NODE_ENV=production`), `/studio` does NOT present a working editor and the `/api/studio/*` routes refuse to mutate files.
- No new npm dependencies were added (multipart parsing must use built-in `Request.formData()`).

## Soft Criteria

- The Studio shares the public site's visual language; it does not look like a separate admin app.
- Forms are easy to use: clear labels, sane defaults, obvious add / remove / reorder controls.
- The Projects editor in particular is pleasant — adding a fourth project should not feel painful.
- Image upload gives clear feedback (filename, preview thumbnail, or at least a "saved as /projects/foo.png" confirmation).
- The preview pane is genuinely useful (iframed `/` + Reload is enough).
- Error messages from the Save API are visible in the UI, not just dropped.
- The Studio's empty state on first load (everything still TODO) is not embarrassing.
- The local-only banner is informative without being scary.
- README has a short "How to use the Studio" section explaining `npm run dev`, opening `/studio`, and where the content / images live on disk.
- Studio code is readable — a future loop adding Git publish should not have to fight the structure.

## Done Definition

The MVP is done when:

1. The portfolio still builds (`npm run build` passes) and lints (`npm run lint` passes).
2. `src/content/portfolio.json` exists and the public homepage renders from it via `loadPortfolio`.
3. `/studio` exists in dev and presents working forms for all five content sections.
4. `POST /api/studio/save` writes to disk and the public page reflects the new content after refresh.
5. `POST /api/studio/upload` writes images into `public/projects/` and returns a usable public path.
6. In production, `/studio` and the `/api/studio/*` routes refuse to act.
7. No Git, Vercel, or domain code was added — those belong to later goals.
8. No new npm dependencies were introduced (multipart parsing uses Web FormData).
9. The README has a "Using the Studio" section.
10. No forbidden features (backend, DB, auth, payments, CMS, AI chatbot, analytics, secrets) were added.
