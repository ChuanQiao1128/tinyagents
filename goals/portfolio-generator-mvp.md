# Goal: User-editable Personal Portfolio Generator MVP

## Goal

Build a beautiful, professional, user-editable personal portfolio template.

This is **not** a one-off hardcoded portfolio page. It is a reusable portfolio
generator where all personal content is supplied by the user through editable
content files.

The generated website should look polished by default, but the user must be
able to replace the content without editing the layout components.

## First task

Transform the current portfolio project into a content-driven personal portfolio template.

The page should remain visually polished, but all personal content should come
from a dedicated content file (`src/content/portfolio.ts`).

## Product Concept

The portfolio should work like this:

1. The user edits a content file.
2. The content file contains:
   - name
   - headline
   - location
   - short bio
   - long bio
   - projects
   - skills
   - contact links
   - image paths
3. The homepage reads that content and renders a professional portfolio.
4. The user can add, remove, or update projects by editing the content file.
5. The user can upload images into `public/projects/` and reference them from
   the content file.

## Target User

The user is a programmer, AI engineer, full-stack developer, designer-developer,
or technical job seeker who wants a professional portfolio but does not want to
redesign the site every time they update content.

## Design Goal

The design must look good **before** the user adds final real content.

The visual style should be:

- clean
- modern
- technical
- professional
- polished
- spacious
- easy to scan
- suitable for AI Engineer / software engineer / full-stack developer roles

The design should feel like:

- an engineering portfolio
- a technical case study hub
- a polished personal website
- a serious job-search portfolio

The design should NOT feel like:

- a generic AI-generated landing page
- a startup marketing template
- a random Tailwind demo
- a plain resume converted into HTML
- an over-animated portfolio

## Design Research Instructions

Before coding, analyze the desired portfolio design.

The implementation should choose:

- layout style (single-column vs two-column, where each is used)
- spacing scale (consistent rhythm — e.g. 4 / 8 / 16 / 24 / 48)
- typography hierarchy (hero / section title / body / caption)
- color palette (background, surface, accent, muted, text levels)
- card style (border, shadow, radius)
- project card layout (image / placeholder, title, tech chips, links)
- mobile behavior (single column, readable tap targets)
- image treatment (aspect ratio, fallback for missing images)
- CTA layout (primary vs secondary, hero CTAs, project links)

Do not start coding until the design direction is clear. The final design
should have a distinctive hero, strong section rhythm, polished project cards,
good contrast, a responsive layout, and no clutter.

## Visual Requirements

The homepage should include:

1. A strong **hero** section
   - name
   - role / headline
   - short bio
   - primary CTA
   - secondary CTA

2. A profile / **about** section
   - long bio paragraphs
   - location
   - current focus
   - optional avatar support

3. **Featured projects** section
   - project cards
   - project status
   - project image support (with placeholder fallback)
   - tech stack chips
   - links to GitHub / demo / case study
   - project highlights

4. **Skills** section
   - grouped skill categories
   - clean visual hierarchy
   - not just a wall of tags

5. **How I Work / Philosophy** section
   - optional user-provided working principles
   - good layout even if there are only 3-4 items

6. **Contact** section
   - email
   - GitHub
   - LinkedIn
   - resume link
   - optional location

## Visual Direction

Use a premium technical portfolio style:

- dark neutral background (or a clearly intentional light variant — pick one and commit)
- subtle gradient or texture accents, not loud color blocks
- glass / card surfaces for project cards and grouped sections
- thin borders rather than heavy shadows
- large readable hero typography
- two-column desktop layout where useful (e.g. hero + portrait, about + sidebar)
- single-column mobile layout
- project cards with image OR a tasteful placeholder block (never broken images)
- consistent spacing rhythm across all sections
- restrained animation, if any (no parallax, no excessive scroll effects)

Avoid:

- loud / saturated colors
- generic Tailwind "marketing page" blocks
- huge walls of body text
- too many badges or chips per project
- fake 3D effects
- a cluttered resume-converted-to-HTML feel

## Content Rules

All user-facing personal content must come from the content file.

Do NOT hardcode personal content directly inside React components, except
generic UI labels such as:

- "Projects", "Skills", "Contact"
- "View project", "GitHub", "Demo", "Case study"

If sample content is needed for the template to render at all, mark it
clearly as TODO or example content.

Do NOT invent:

- real names
- fake companies
- fake job titles
- fake project metrics ("served 10M users")
- fake GitHub / LinkedIn / portfolio URLs
- fake screenshots
- fake production claims

Use placeholders like:

- `TODO: Your name`
- `TODO: Project title`
- `TODO: Add your GitHub URL`

## Required Content File

Create:

`src/content/portfolio.ts`

This file should export a single object (e.g. `portfolio`) shaped roughly like
the example below. The exact fields can be refined for clarity, but the
overall shape — profile, contact, projects, skillGroups, workPrinciples —
should be preserved.

```ts
export const portfolio = {
  profile: {
    name: "TODO: Your name",
    role: "TODO: Your role, e.g. AI Engineer / Full-stack Developer",
    location: "TODO: Your city / country",
    headline: "TODO: One-line headline",
    shortBio: "TODO: Short intro for the hero section",
    longBio: [
      "TODO: About paragraph 1",
      "TODO: About paragraph 2",
    ],
    avatar: "",       // optional: e.g. "/avatar.jpg"
    resumeUrl: "",    // optional: e.g. "/resume.pdf"
  },

  contact: {
    email: "TODO: your@email.com",
    github: "TODO: https://github.com/your-handle",
    linkedin: "TODO: https://linkedin.com/in/your-handle",
  },

  projects: [
    {
      title: "TODO: Project title",
      status: "In progress",
      summary: "TODO: One-line summary",
      description: "TODO: Project description",
      image: "",                   // optional: e.g. "/projects/project-1.png"
      tech: ["TODO: Tech 1", "TODO: Tech 2"],
      highlights: [
        "TODO: What did you build?",
        "TODO: What problem did it solve?",
        "TODO: What does it demonstrate?",
      ],
      links: {
        github: "",
        demo: "",
        caseStudy: "",
      },
    },
  ],

  skillGroups: [
    {
      title: "TODO: Skill category, e.g. AI Engineering",
      skills: ["TODO: Skill 1", "TODO: Skill 2"],
    },
  ],

  workPrinciples: [
    {
      title: "TODO: Principle title",
      description: "TODO: Principle description",
    },
  ],
};
```

This file must be easy for a non-expert user to edit. Comments explaining
each section are welcome.

## Image Support

Create:

`public/projects/`

The portfolio should support project image paths like `/projects/project-1.png`.

If a project's `image` is empty or the file is missing, the UI must still look
good — render a tasteful placeholder card (e.g. a soft gradient block with the
project's first initial or a neutral pattern). Do NOT require the user to
upload any images for the page to work.

## Component Structure

Create reusable components where useful:

- `Hero`
- `About`
- `ProjectCard`
- `Skills`
- `Contact`
- `Section` (a layout primitive for consistent section padding / titles)

Do not over-componentize. The code should stay readable and easy to edit.

## Scope

**Allowed changes:**

- `app/page.tsx`
- `app/layout.tsx`
- `app/globals.css`
- `src/content/portfolio.ts`
- `src/components/*`
- `public/projects/*`
- `README.md`
- `package.json` only if needed for the existing Next.js setup (no new
  dependencies unless absolutely required for the design)

**Forbidden:**

- backend code
- database
- authentication
- payment
- CMS
- external API integration
- AI chatbot
- analytics
- deployment automation
- fake generated personal claims (see Content Rules)

## Hard Criteria

- file_exists: package.json
- file_exists: app/page.tsx
- file_exists: app/layout.tsx
- file_exists: app/globals.css
- file_exists: src/content/portfolio.ts
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

## Additional Hard Requirements

The implementation must satisfy these even if the automated checker cannot
fully verify them:

- Homepage content is driven by `src/content/portfolio.ts`.
- React components do not hardcode personal profile / project content.
- The user can add a new project by editing the `projects` array.
- The user can update contact links by editing the content file.
- The design remains good with the TODO placeholder content.
- Missing images do not break layout.
- No backend, database, auth, payment, CMS, or external API is added.

## Soft Criteria

- The homepage looks polished out of the box (before the user fills in real content)
- The layout has strong visual hierarchy (hero / sections / cards clearly distinguished)
- The hero section feels distinctive (not a generic Tailwind centered headline)
- Project cards look professional even with placeholder images
- The design feels suitable for an AI Engineer / full-stack developer
- Spacing and typography feel intentional, not default-Tailwind
- Mobile layout (375px) is usable without horizontal scroll
- Desktop layout (1024px+) uses the extra width meaningfully (e.g. two-column hero or sidebar)
- The page does not feel like a generic AI-generated landing template
- Content editing feels straightforward (TODO markers are obvious and well-commented)
- README explains how to update content and where to put images

## Done Definition

The MVP is done when:

1. The portfolio builds successfully (`npm run build` passes)
2. Lint passes (`npm run lint`)
3. The homepage is visually polished with placeholder content
4. All user-editable content lives in `src/content/portfolio.ts`
5. The user can update profile, projects, skills, and contact links from the content file
6. The README explains how to edit the portfolio and where to add images
7. No forbidden features (backend, DB, auth, payments, CMS, AI chatbot, analytics) are added
