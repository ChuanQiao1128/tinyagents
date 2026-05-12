#!/usr/bin/env python3
"""
TinyLocalAgents - a local CLI tool for managing a simple four-step
AI development loop: Research -> Plan -> Implement -> Test -> Next Loop.

Stage 1: CLI skeleton and loop folder generation only.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


# ----- Paths -----

ROOT = Path(__file__).resolve().parent
LOOPS_DIR = ROOT / "loops"
TEMPLATES_DIR = ROOT / "templates"
CONFIG_PATH = ROOT / "config.json"


# ----- Helpers -----

SLUG_MAX_LEN = 100  # well under macOS / ext4 / NTFS per-component limits


def slugify(title: str) -> str:
    """Turn a free-form title into a filesystem-friendly slug, capped at
    SLUG_MAX_LEN so very long task titles can't blow past per-path-component
    limits (macOS / HFS+ / APFS cap each path component at 255 bytes).

    The full task title is preserved in research.md / plan.md /
    implementation-prompt.md — only the loop folder name is shortened.
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > SLUG_MAX_LEN:
        slug = slug[:SLUG_MAX_LEN].rstrip("-")
    return slug or "loop"


def next_loop_number() -> int:
    """Find the next loop number based on existing folders in loops/."""
    if not LOOPS_DIR.exists():
        return 1
    numbers = []
    for entry in LOOPS_DIR.iterdir():
        if not entry.is_dir():
            continue
        match = re.match(r"^(\d+)-", entry.name)
        if match:
            numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def list_loops() -> list[Path]:
    """Return existing loop folders sorted by their numeric prefix."""
    if not LOOPS_DIR.exists():
        return []
    loops = []
    for entry in LOOPS_DIR.iterdir():
        if entry.is_dir() and re.match(r"^\d+-", entry.name):
            loops.append(entry)
    loops.sort(key=lambda p: int(p.name.split("-", 1)[0]))
    return loops


def is_initialized() -> bool:
    return CONFIG_PATH.exists() and LOOPS_DIR.exists()


# ----- Templates -----

def tpl_research(title: str) -> str:
    return f"""# Research: {title}

## What problem are we solving?
(Describe the underlying problem in one or two paragraphs.)

## Who is the user?
(Who benefits from solving this? What do they currently do instead?)

## What is the goal?
(One sentence describing the desired outcome of this loop.)

## What is in scope?
- (List specific things that this loop will address.)

## What is out of scope?
- (List specific things that this loop will NOT address.)

## Notes / References
- (Links, prior loops, screenshots, examples, etc.)
"""


def tpl_plan(title: str) -> str:
    return f"""# Plan: {title}

## What will be done in this loop?
(A short, specific description of the work for this loop.)

## Allowed changes
- (Files, modules, or areas that may be touched.)

## Forbidden changes
- (Files, modules, or areas that must NOT be touched.)

## Acceptance criteria
- [ ] (Concrete, checkable condition #1)
- [ ] (Concrete, checkable condition #2)
- [ ] (Concrete, checkable condition #3)

## Risks / Unknowns
- (Anything that might block or complicate this loop.)
"""


def tpl_implementation_prompt(title: str) -> str:
    return f"""# Implementation Prompt

You are an AI coding agent working on the following task.

## Task
{title}

## Goal
(Restate the goal of this loop in one or two sentences. Replace this with the
goal from plan.md once it has been finalized.)

## Constraints
- Only modify the files listed under "Allowed changes" in plan.md.
- Do not touch the files listed under "Forbidden changes" in plan.md.
- Keep the change small and easy to review.
- Prefer the simplest implementation that satisfies the acceptance criteria.
- Do not add external dependencies unless explicitly approved.

## Acceptance criteria
(Copy the acceptance criteria from plan.md here as a checklist.)
- [ ] ...
- [ ] ...

## Deliverables
- Updated source files.
- A short note describing what changed and why.
- Anything the human reviewer should manually verify.
"""


def tpl_test_report(title: str) -> str:
    return f"""# Test Report: {title}

## Build result
(Did the project build / run without errors? Paste commands and key output.)

## Lint result
(Linter / type-checker output, if applicable.)

## Visual / manual check
(What did you actually click through, look at, or run by hand?)

## Scope check
- Did the change stay within "Allowed changes"? (yes / no)
- Were any "Forbidden changes" touched? (yes / no — explain if yes)
- Did all acceptance criteria pass? (yes / no — list any that failed)

## Conclusion
(Pass / Needs another loop / Blocked — and a one-line justification.)
"""


def tpl_next_loop(title: str) -> str:
    return f"""# Next Loop

## What happened?
(Brief recap of this loop: what was attempted, what worked, what didn't.)

## What should be done next?
- (Concrete suggestion for the next loop's focus.)
- (Optional: alternative directions to consider.)

## Open questions
- (Things we still don't know and need to decide before the next loop.)

## Carry-over notes
(Anything from this loop that the next loop should keep in mind: links,
known gotchas, half-finished work, etc.)
"""


LOOP_FILES = {
    "research.md": tpl_research,
    "plan.md": tpl_plan,
    "implementation-prompt.md": tpl_implementation_prompt,
    "test-report.md": tpl_test_report,
    "next-loop.md": tpl_next_loop,
}


# ----- Scanner -----
#
# The scanner inspects a *target* project folder (separate from this CLI's own
# directory) and writes a context-summary.md into the latest loop. It is
# strictly read-only with respect to the target project, never reads .env
# files, and skips large generated directories.

EXCLUDED_DIRS = {
    "node_modules", ".next", "dist", "build", "out", "coverage",
    ".git", ".turbo", ".cache", ".vercel", ".parcel-cache", ".svelte-kit",
    "__pycache__", ".venv", "venv", ".idea", ".vscode",
}

HOMEPAGE_CANDIDATES = [
    "app/page.tsx", "app/page.jsx",
    "pages/index.tsx", "pages/index.jsx",
    "src/app/page.tsx", "src/app/page.jsx",
    "src/pages/index.tsx", "src/pages/index.jsx",
]

LAYOUT_CANDIDATES = [
    "app/layout.tsx", "app/layout.jsx",
    "src/app/layout.tsx", "src/app/layout.jsx",
]

COMPONENT_DIRS = ["components", "src/components"]
APP_DIRS = ["app", "src/app"]
STYLE_FILES = ["app/globals.css", "src/app/globals.css"]
STYLE_DIRS = ["styles", "src/styles"]
CONFIG_FILES = [
    "package.json", "tsconfig.json",
    "next.config.js", "next.config.ts", "next.config.mjs",
    "tailwind.config.js", "tailwind.config.ts",
    "postcss.config.js", "vercel.json",
]

GLOBALS_CSS_MAX_BYTES = 200_000
TS_SCAN_MAX_DEPTH = 3


def _shallow_walk(root: Path, max_depth: int):
    """Yield files under root, depth-limited, skipping excluded/hidden dirs."""
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in EXCLUDED_DIRS or entry.name.startswith("."):
                    continue
                if depth + 1 <= max_depth:
                    stack.append((entry, depth + 1))
            elif entry.is_file():
                yield entry


def _read_package_json(root: Path) -> dict | None:
    pkg_path = root / "package.json"
    if not pkg_path.is_file():
        return None
    try:
        return json.loads(pkg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _has_dep(pkg: dict | None, name: str) -> bool:
    if not pkg:
        return False
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = pkg.get(section) or {}
        if isinstance(deps, dict) and name in deps:
            return True
    return False


def _detect_typescript(root: Path, pkg: dict | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if (root / "tsconfig.json").is_file():
        reasons.append("tsconfig.json exists")
    if _has_dep(pkg, "typescript"):
        reasons.append("typescript listed in package.json")
    # Look for a single .ts/.tsx file in common source roots.
    for sub_name in ("app", "src", "pages", "components", "lib"):
        sub = root / sub_name
        if not sub.is_dir():
            continue
        for path in _shallow_walk(sub, TS_SCAN_MAX_DEPTH):
            if path.suffix in (".ts", ".tsx") and not path.name.endswith(".d.ts"):
                reasons.append(f".ts/.tsx files found (e.g. {path.relative_to(root)})")
                return True, reasons
    return bool(reasons), reasons


def _detect_nextjs(root: Path, pkg: dict | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if _has_dep(pkg, "next"):
        reasons.append("next listed in package.json")
    for name in ("next.config.js", "next.config.ts", "next.config.mjs"):
        if (root / name).is_file():
            reasons.append(f"{name} exists")
            break
    for candidate in HOMEPAGE_CANDIDATES:
        if (root / candidate).is_file():
            reasons.append(f"{candidate} exists")
            break
    return bool(reasons), reasons


def _detect_tailwind(root: Path, pkg: dict | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for name in ("tailwind.config.js", "tailwind.config.ts"):
        if (root / name).is_file():
            reasons.append(f"{name} exists")
            break
    if _has_dep(pkg, "tailwindcss"):
        reasons.append("tailwindcss listed in package.json")
    # Small, safe peek at globals.css for Tailwind directives.
    for css_rel in STYLE_FILES:
        css_path = root / css_rel
        if not css_path.is_file():
            continue
        try:
            if css_path.stat().st_size > GLOBALS_CSS_MAX_BYTES:
                continue
            content = css_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if (
            "@tailwind" in content
            or '@import "tailwindcss"' in content
            or "@import 'tailwindcss'" in content
        ):
            reasons.append(f"{css_rel} contains Tailwind directives")
            break
    return bool(reasons), reasons


def _guess_package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (root / "yarn.lock").is_file():
        return "yarn"
    if (root / "bun.lockb").is_file() or (root / "bun.lock").is_file():
        return "bun"
    if (root / "package-lock.json").is_file():
        return "npm"
    if (root / "package.json").is_file():
        return "npm (guessed; no lockfile)"
    return "unknown"


def scan_project(root: Path) -> dict:
    """Inspect a project directory and return a structured findings dict.

    This is read-only; it never writes to or modifies the target project.
    """
    pkg = _read_package_json(root)
    ts_used, ts_reasons = _detect_typescript(root, pkg)
    next_used, next_reasons = _detect_nextjs(root, pkg)
    tw_used, tw_reasons = _detect_tailwind(root, pkg)

    scripts = {}
    if pkg and isinstance(pkg.get("scripts"), dict):
        scripts = pkg["scripts"]

    interesting_scripts: dict[str, str] = {}
    for name in ("build", "dev", "start", "lint", "test", "typecheck", "type-check"):
        if name in scripts:
            interesting_scripts[name] = scripts[name]

    missing: list[str] = []
    if not pkg:
        missing.append("package.json")
    if not ((root / "README.md").is_file() or (root / "readme.md").is_file()):
        missing.append("README.md")
    if not (root / "tsconfig.json").is_file():
        missing.append("tsconfig.json")
    if next_used and not any((root / c).is_file() for c in HOMEPAGE_CANDIDATES):
        missing.append("homepage entry (app/page.tsx or pages/index.tsx)")

    warnings: list[str] = []
    if not pkg:
        warnings.append("No package.json found — JS/TS detection is necessarily incomplete.")
    if (root / "package.json").is_file() and pkg is None:
        warnings.append("package.json exists but could not be parsed as JSON.")

    return {
        "root": root,
        "name": root.name,
        "has_package_json": pkg is not None,
        "has_readme": (root / "README.md").is_file() or (root / "readme.md").is_file(),
        "has_git": (root / ".git").exists(),
        "typescript": ts_used,
        "typescript_reasons": ts_reasons,
        "nextjs": next_used,
        "nextjs_reasons": next_reasons,
        "tailwind": tw_used,
        "tailwind_reasons": tw_reasons,
        "package_manager": _guess_package_manager(root),
        "scripts": interesting_scripts,
        "homepage_candidates": [p for p in HOMEPAGE_CANDIDATES if (root / p).is_file()],
        "layout_candidates": [p for p in LAYOUT_CANDIDATES if (root / p).is_file()],
        "component_dirs": [d for d in COMPONENT_DIRS if (root / d).is_dir()],
        "app_dirs": [d for d in APP_DIRS if (root / d).is_dir()],
        "style_files": [f for f in STYLE_FILES if (root / f).is_file()],
        "style_dirs": [d for d in STYLE_DIRS if (root / d).is_dir()],
        "config_files": [f for f in CONFIG_FILES if (root / f).is_file()],
        "missing": missing,
        "warnings": warnings,
    }


def _bullets(items: list[str], empty: str = "(none found)") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- `{item}`" if not item.startswith("(") else f"- {item}" for item in items)


def _plain_bullets(items: list[str], empty: str = "(none found)") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in items)


def render_context_summary(findings: dict) -> str:
    framework = "Next.js" if findings["nextjs"] else "(not detected)"
    language = "TypeScript" if findings["typescript"] else "JavaScript / unknown"
    styling = "Tailwind CSS" if findings["tailwind"] else "(not detected)"

    script_lines = []
    for name in ("build", "dev", "lint", "test", "typecheck"):
        value = findings["scripts"].get(name)
        if value is None and name == "typecheck":
            value = findings["scripts"].get("type-check")
        if value:
            script_lines.append(f"- {name}: `{value}`")
        else:
            script_lines.append(f"- {name}: (not defined)")

    reasons_blocks = []
    if findings["typescript_reasons"]:
        reasons_blocks.append("**TypeScript signals:**\n" + "\n".join(f"  - {r}" for r in findings["typescript_reasons"]))
    if findings["nextjs_reasons"]:
        reasons_blocks.append("**Next.js signals:**\n" + "\n".join(f"  - {r}" for r in findings["nextjs_reasons"]))
    if findings["tailwind_reasons"]:
        reasons_blocks.append("**Tailwind signals:**\n" + "\n".join(f"  - {r}" for r in findings["tailwind_reasons"]))
    reasons_text = "\n\n".join(reasons_blocks) if reasons_blocks else "_(no specific framework signals were detected)_"

    important_sections = [
        ("Homepage candidates", findings["homepage_candidates"]),
        ("Layout files", findings["layout_candidates"]),
        ("Components directories", findings["component_dirs"]),
        ("App directories", findings["app_dirs"]),
        ("Style files", findings["style_files"]),
        ("Style directories", findings["style_dirs"]),
        ("Config files", findings["config_files"]),
    ]
    important_block_parts = []
    for label, items in important_sections:
        important_block_parts.append(f"### {label}\n{_bullets(items)}")
    important_block = "\n\n".join(important_block_parts)

    frontend_useful = [
        "app/page.tsx (or pages/index.tsx) — homepage entry",
        "app/layout.tsx — root layout / metadata",
        "components/ — reusable UI components",
        "app/globals.css — base styles, Tailwind directives",
        "package.json — dependency context (read-only)",
        "tsconfig.json — TypeScript compiler options (read-only)",
        "tailwind.config.* — design tokens / theme (read-only)",
    ]
    readonly_files = [
        "package.json",
        "tsconfig.json",
        "next.config.*",
        "tailwind.config.*",
        "postcss.config.*",
        "vercel.json",
    ]
    do_not_send = [
        ".env, .env.local, .env.* — never read or include",
        "any secret keys, tokens, certificates, or credential files",
        "node_modules/",
        ".next/, dist/, build/, out/, coverage/",
        "logs/, *.log",
        "user data exports, database dumps",
        "database migration files (unless the task explicitly requires them)",
        "billing / payment / customer-PII files (unless the task explicitly requires them)",
    ]

    assumptions = [
        "Detection is heuristic — confirm by reading the files before making structural changes.",
        "Only common source directories were sampled for TypeScript signals; deeply nested files may be missed.",
        "Hidden folders and generated directories (node_modules, .next, dist, build, out, coverage, .git) were skipped.",
        "The scanner never reads .env files or any file inside excluded directories.",
    ]

    generated_at = datetime.now().isoformat(timespec="seconds")

    return f"""# Context Summary

_Generated by `tiny_agents.py scan` on {generated_at}._

## Project
- Project path: `{findings["root"]}`
- Project name: `{findings["name"]}`
- package.json: {"yes" if findings["has_package_json"] else "no"}
- README: {"yes" if findings["has_readme"] else "no"}
- Git repo: {"yes" if findings["has_git"] else "no (no .git found)"}

## Detected Stack
- Framework: {framework}
- Language: {language}
- Styling: {styling}
- Package manager guess: {findings["package_manager"]}

{reasons_text}

## Available Commands
{chr(10).join(script_lines)}

## Important Files

{important_block}

## Safe Context Notes

### Files useful for frontend tasks
{_plain_bullets(frontend_useful)}

### Files that should usually be read-only
{_plain_bullets(readonly_files)}

### Files / folders that should NOT be sent to AI
{_plain_bullets(do_not_send)}

## Scanner Notes

### Missing files
{_plain_bullets(findings["missing"], empty="(nothing notable missing)")}

### Assumptions
{_plain_bullets(assumptions)}

### Warnings
{_plain_bullets(findings["warnings"], empty="(none)")}
"""


# ----- Commands -----

def cmd_init(_args: argparse.Namespace) -> int:
    created = []
    already = []

    if LOOPS_DIR.exists():
        already.append("loops/")
    else:
        LOOPS_DIR.mkdir(parents=True)
        created.append("loops/")

    if TEMPLATES_DIR.exists():
        already.append("templates/")
    else:
        TEMPLATES_DIR.mkdir(parents=True)
        created.append("templates/")

    if CONFIG_PATH.exists():
        already.append("config.json")
    else:
        config = {
            "project": "TinyLocalAgents",
            "version": "0.1.0",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "loops_dir": "loops",
            "templates_dir": "templates",
        }
        CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        created.append("config.json")

    print("TinyLocalAgents init complete.")
    if created:
        print("  Created:")
        for name in created:
            print(f"    + {name}")
    if already:
        print("  Already existed:")
        for name in already:
            print(f"    = {name}")
    print()
    print("Next step: python tiny_agents.py new \"<your task title>\"")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    title = args.title.strip()
    if not title:
        print("Error: task title must not be empty.", file=sys.stderr)
        return 2

    if not is_initialized():
        print(
            "Project is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    number = next_loop_number()
    slug = slugify(title)
    folder_name = f"{number:03d}-{slug}"
    loop_path = LOOPS_DIR / folder_name

    if loop_path.exists():
        print(f"Error: loop folder already exists: {loop_path}", file=sys.stderr)
        return 1

    loop_path.mkdir(parents=True)

    for filename, builder in LOOP_FILES.items():
        (loop_path / filename).write_text(builder(title), encoding="utf-8")

    print(f"Created new loop: {folder_name}")
    print(f"  Path: {loop_path.relative_to(ROOT)}")
    print("  Files:")
    for filename in LOOP_FILES:
        print(f"    + {filename}")
    print()
    print("Suggested next steps:")
    print("  1. Fill out research.md")
    print("  2. Fill out plan.md")
    print("  3. Use implementation-prompt.md with your coding agent")
    print("  4. Record results in test-report.md")
    print("  5. Capture follow-ups in next-loop.md")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    initialized = is_initialized()
    print("TinyLocalAgents status")
    print("----------------------")
    print(f"Initialized: {'yes' if initialized else 'no'}")
    print(f"Root:        {ROOT}")
    print(f"Config:      {CONFIG_PATH if CONFIG_PATH.exists() else '(missing)'}")
    print(f"Loops dir:   {LOOPS_DIR if LOOPS_DIR.exists() else '(missing)'}")

    if not initialized:
        print()
        print("Run `python tiny_agents.py init` to set things up.")
        return 0

    loops = list_loops()
    print(f"Loop count:  {len(loops)}")
    if loops:
        print()
        print("Existing loops:")
        for loop in loops:
            print(f"  - {loop.name}")
        print()
        print(f"Latest loop: {loops[-1].name}")
    else:
        print()
        print("No loops yet. Create one with:")
        print("  python tiny_agents.py new \"<your task title>\"")
    return 0


# ----- Prompt generator -----
#
# Stage 3 glues the per-loop notes together into a single, structured prompt
# that can be pasted into Claude Code / Cursor / Codex / another coding agent.
# It is text-only — no AI APIs, no project edits, no test execution.

def get_latest_loop() -> Path | None:
    loops = list_loops()
    return loops[-1] if loops else None


def _read_text_safe(path: Path) -> str | None:
    """Return the text content of `path`, or None if missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _demote_headings(text: str) -> str:
    """Push every ATX heading down one level (## -> ###, capped at ######)."""
    lines = []
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})(\s+\S.*)$", line)
        if m:
            new_hashes = "#" * min(len(m.group(1)) + 1, 6)
            line = new_hashes + m.group(2)
        lines.append(line)
    return "\n".join(lines)


def _strip_leading_h1(text: str) -> str:
    """Drop the file's top-level H1 (and any blank lines around it) so the
    embedded content slots cleanly under the prompt's section headings."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and re.match(r"^#\s+\S", lines[i]):
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    return "\n".join(lines[i:])


def _embed(text: str) -> str:
    """Strip a file's top H1 and demote remaining headings by one level."""
    return _demote_headings(_strip_leading_h1(text).strip())


def _extract_section(text: str, heading_pattern: str) -> str | None:
    """Return the body under the first heading matching `heading_pattern`.

    The body runs until the next heading of equal or higher level. The
    pattern is matched case-insensitively against the heading text.
    """
    lines = text.splitlines()
    start: int | None = None
    start_level: int | None = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m and re.search(heading_pattern, m.group(2), flags=re.IGNORECASE):
            start = i + 1
            start_level = len(m.group(1))
            break
    if start is None or start_level is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        m = re.match(r"^(#{1,6})\s+", lines[j])
        if m and len(m.group(1)) <= start_level:
            end = j
            break
    return "\n".join(lines[start:end]).strip() or None


def _title_from_research(research_md: str | None) -> str | None:
    if not research_md:
        return None
    for line in research_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("# Research:"):
            return stripped[len("# Research:"):].strip() or None
        if stripped.startswith("#"):
            return None
    return None


def _title_from_folder(loop_path: Path) -> str:
    name = loop_path.name
    parts = name.split("-", 1)
    slug = parts[1] if len(parts) == 2 and parts[0].isdigit() else name
    words = slug.replace("-", " ").split()
    if not words:
        return name
    return " ".join([words[0].capitalize()] + words[1:])


def extract_available_commands_from_context_summary(context_md: str | None) -> dict[str, str]:
    """Pull `- name: \\`value\\`` lines out of the Available Commands section."""
    if not context_md:
        return {}
    section = _extract_section(context_md, r"^available commands$")
    if not section:
        return {}
    commands: dict[str, str] = {}
    for line in section.splitlines():
        m = re.match(r"^-\s+([A-Za-z][\w-]*)\s*:\s*`([^`]+)`\s*$", line)
        if m:
            commands[m.group(1).lower()] = m.group(2)
    return commands


def _extract_package_manager(context_md: str | None) -> str:
    if not context_md:
        return "npm"
    section = _extract_section(context_md, r"^detected stack$") or context_md
    m = re.search(
        r"^-\s+Package manager guess:\s+(.+?)\s*$",
        section,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not m:
        return "npm"
    value = m.group(1).strip().lower()
    for known in ("pnpm", "yarn", "bun", "npm"):
        if value.startswith(known):
            return known
    return "npm"


def _format_test_commands(commands: dict[str, str], pkg_mgr: str) -> list[str]:
    """Map detected npm scripts to runnable command lines for the prompt."""
    run_prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun run", "npm": "npm run"}.get(pkg_mgr, "npm run")
    out: list[str] = []
    if "build" in commands:
        out.append(f"`{run_prefix} build` — build the project")
    if "lint" in commands:
        out.append(f"`{run_prefix} lint` — lint the project")
    if "test" in commands:
        out.append("`npm test` — run tests" if pkg_mgr == "npm" else f"`{run_prefix} test` — run tests")
    for tc_key in ("typecheck", "type-check"):
        if tc_key in commands:
            out.append(f"`{run_prefix} {tc_key}` — type-check")
            break
    return out


def render_implementation_prompt(
    loop_path: Path,
    research_md: str | None,
    plan_md: str | None,
    context_md: str | None,
) -> str:
    task_title = _title_from_research(research_md) or _title_from_folder(loop_path)

    research_block = (
        _embed(research_md)
        if research_md and research_md.strip()
        else "_`research.md` is missing or empty. Fill it in (problem, user, goal, in/out of scope) and regenerate this prompt._"
    )
    plan_block = (
        _embed(plan_md)
        if plan_md and plan_md.strip()
        else "_`plan.md` is missing or empty. Fill it in (work, allowed/forbidden changes, acceptance criteria) and regenerate this prompt._"
    )

    if context_md and context_md.strip():
        context_block = _embed(context_md)
        context_warning = ""
    else:
        context_block = "_`context-summary.md` has not been generated yet._"
        context_warning = (
            "\n> **Heads up:** the target project has not been scanned yet. "
            "Project context, stack detection, and test commands below are incomplete.\n"
            "> Run `python tiny_agents.py scan --project <path-to-target-project>` and then regenerate this prompt with `python tiny_agents.py prompt`.\n"
        )

    ac_section = _extract_section(plan_md or "", r"^acceptance criteria$")
    acceptance_block = (
        ac_section
        if ac_section
        else "_No `## Acceptance criteria` section was found in `plan.md`. Add one and regenerate this prompt._"
    )

    commands = extract_available_commands_from_context_summary(context_md)
    pkg_mgr = _extract_package_manager(context_md)
    test_cmds = _format_test_commands(commands, pkg_mgr)
    if test_cmds:
        testing_block = (
            "Run these commands (inferred from `context-summary.md`):\n\n"
            + "\n".join(f"- {c}" for c in test_cmds)
            + "\n\nIf any of these commands is missing or fails, do **not** invent a substitute — "
            "inspect the project's `package.json` first and report what you found."
        )
    elif context_md:
        testing_block = (
            "_No `build` / `lint` / `test` / `typecheck` scripts were detected in `context-summary.md`._\n\n"
            "Inspect `package.json` yourself before running anything. Do not invent commands."
        )
    else:
        testing_block = (
            "_No project scan has been run, so no specific test commands are available._\n\n"
            "Inspect `package.json` first and report which scripts exist. Do not invent commands."
        )

    generated_at = datetime.now().isoformat(timespec="seconds")

    return f"""# Implementation Prompt
{context_warning}
_Generated by `tiny_agents.py prompt` on {generated_at}._
_Loop: `{loop_path.name}`_

## Role
You are my AI coding coworker. You will implement exactly **one** scoped development loop — the one described below. You are not building the whole product; you are completing this loop and stopping.

## Current Task
{task_title}

(Loop folder: `{loop_path.name}`. The original research notes, plan, and project context for this task follow.)

## Research Context
The content below is from `research.md` for this loop. Use it to understand the problem, the user, and the goal — do not expand scope beyond what it states.

{research_block}

## Implementation Plan
The content below is from `plan.md`. Treat its "Allowed changes", "Forbidden changes", and "Acceptance criteria" as authoritative.

{plan_block}

## Project Context
The content below is from `context-summary.md` (generated by `tiny_agents.py scan`). Treat it as a heuristic orientation document — confirm by reading the actual files before making structural changes.

{context_block}

## Scope Rules
- Implement only this loop's work, as described in `plan.md` above.
- Do not overbuild. No extra features, refactors, or "while we're at it" cleanups.
- Do not add unrelated features.
- Do not add dependencies unless the plan explicitly allows it.
- Do not modify files listed under "Forbidden changes" in the plan.
- Do not touch secrets, `.env*` files, user data, generated build folders (`.next`, `dist`, `build`, `out`, `coverage`), or `node_modules`.
- Prefer simple, readable code over clever code.
- Keep changes small and reviewable.

## Expected Deliverables
When you are done, report back with:
- Files changed (with a one-line reason for each)
- Files added
- Files deleted
- Whether any dependency was added (and which)
- Any assumptions you made that the plan did not specify
- The exact commands a reviewer should run to verify your changes

## Acceptance Criteria
The change is done when **all** of the following pass. Copy this checklist into your final report and mark each item.

{acceptance_block}

## Testing Instructions
{testing_block}

Do not edit code to silence a failing check without first understanding why it failed. Report failures honestly rather than working around them.

## Stop Condition
- Stop after completing this loop's implementation and reporting what changed.
- Do not begin the next loop's work.
- Do not implement future stages of TinyLocalAgents itself.
- If the plan is ambiguous, ask a clarifying question instead of guessing in a way that expands scope.
"""


def cmd_prompt(_args: argparse.Namespace) -> int:
    if not is_initialized():
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    latest = get_latest_loop()
    if latest is None:
        print(
            "No loops exist yet. Create one first:\n"
            "  python tiny_agents.py new \"<your task title>\"",
            file=sys.stderr,
        )
        return 1

    print(f"Generating implementation prompt for latest loop:")
    print(f"  {latest.relative_to(ROOT)}")

    research_md = _read_text_safe(latest / "research.md")
    plan_md = _read_text_safe(latest / "plan.md")
    context_md = _read_text_safe(latest / "context-summary.md")

    read_list = []
    missing_list = []
    for label, content in (
        ("research.md", research_md),
        ("plan.md", plan_md),
        ("context-summary.md", context_md),
    ):
        (read_list if content is not None else missing_list).append(label)

    print("Read:")
    for name in read_list:
        print(f"  - {name}")
    if missing_list:
        print("Missing (will be noted in the prompt):")
        for name in missing_list:
            print(f"  - {name}")

    prompt_md = render_implementation_prompt(latest, research_md, plan_md, context_md)
    out_path = latest / "implementation-prompt.md"
    out_path.write_text(prompt_md, encoding="utf-8")

    print("Wrote:")
    print(f"  - {out_path.relative_to(ROOT)}")

    if context_md is None:
        print()
        print("Tip: run `python tiny_agents.py scan --project <path>` first to enrich the prompt with project context.")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()

    if not project_path.exists():
        print(f"Error: project path does not exist: {project_path}", file=sys.stderr)
        return 1
    if not project_path.is_dir():
        print(f"Error: project path is not a directory: {project_path}", file=sys.stderr)
        return 1

    if not is_initialized():
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    loops = list_loops()
    if not loops:
        print(
            "No loops exist yet. Create one first:\n"
            "  python tiny_agents.py new \"<your task title>\"",
            file=sys.stderr,
        )
        return 1
    latest = loops[-1]

    print(f"Scanning project: {project_path}")
    print(f"Latest loop: {latest.relative_to(ROOT)}")

    findings = scan_project(project_path)

    summary_parts = []
    if findings["nextjs"]:
        summary_parts.append("Next.js")
    if findings["typescript"]:
        summary_parts.append("TypeScript")
    if findings["tailwind"]:
        summary_parts.append("Tailwind")
    if summary_parts:
        print(f"Detected: {' + '.join(summary_parts)}")
    else:
        print("Detected: (no specific framework signals)")

    out_path = latest / "context-summary.md"
    out_path.write_text(render_context_summary(findings), encoding="utf-8")
    print(f"Wrote: {out_path.relative_to(ROOT)}")
    return 0


# ----- Test runner -----
#
# Stage 4 runs the *target* project's own verification scripts (typecheck,
# build, lint, test) under whichever package manager the project uses, then
# writes per-command logs into artifacts/ and a structured test-report.md
# into the latest loop. It does not edit the project, does not auto-fix
# failures, does not run dev/watch/start scripts, and does not call any AI.

ALLOWED_SCRIPTS = ("typecheck", "type-check", "build", "lint", "test")
# Execution order: type-check first (fastest signal), then build, lint, tests.
RUN_ORDER = ("typecheck", "type-check", "build", "lint", "test")

# Stage 6.8: per-command timeout. 600s (10 min) is generous enough for npm
# install, Next.js builds, and Claude with --max-turns 30 on small projects,
# while still being short enough to break us out of interactive-prompt hangs
# (next lint wizard, jest watch mode, etc.) within a reasonable wait.
DEFAULT_TIMEOUT_S = 600
TIMEOUT_EXIT_CODE = 124  # conventional, matches GNU `timeout`(1)


def _normalize_pkg_mgr(guess: str) -> str:
    """Collapse `_guess_package_manager`'s output to a clean tag."""
    g = (guess or "").lower()
    for known in ("pnpm", "yarn", "bun", "npm"):
        if g.startswith(known):
            return known
    return "npm"


def _command_for(pkg_mgr: str, script: str) -> list[str]:
    """Build the argv list for running `script` under the given package manager."""
    if pkg_mgr == "yarn":
        return ["yarn", script]
    if pkg_mgr == "bun":
        return ["bun", "run", script]
    if pkg_mgr == "pnpm":
        return ["pnpm", "test"] if script == "test" else ["pnpm", "run", script]
    # default: npm
    return ["npm", "test"] if script == "test" else ["npm", "run", script]


def _summarize_failure(stderr: str, stdout: str) -> str:
    """Pick a short, informative line out of the captured output."""
    for blob in (stderr, stdout):
        if not blob:
            continue
        for raw in blob.splitlines():
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if (
                "error" in low
                or "fail" in low
                or "timed out" in low
                or "timeout" in low
            ):
                return line[:300]
    last_nonempty = ""
    for blob in (stderr, stdout):
        for raw in (blob or "").splitlines():
            if raw.strip():
                last_nonempty = raw.strip()
    return (last_nonempty or "(no output captured)")[:300]


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Send SIGKILL to the entire process group of `proc`.

    `proc` must have been launched with `start_new_session=True` so it leads
    its own session/process group. This is the only reliable way to kill
    grandchildren (e.g. `bash -c "node ..."` → npm → node), which is what
    happens with most package-manager script invocations.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        # Group may already be gone; fall back to killing the immediate child.
        try:
            proc.kill()
        except OSError:
            pass


def _run_one(cmd: list[str], cwd: Path, timeout: int | None = DEFAULT_TIMEOUT_S) -> dict:
    """Run a single subprocess and capture stdout/stderr/exit code/timing.

    Stage 6.8 hardening:
    - stdin is wired to /dev/null so any tool that tries to read interactive
      input gets immediate EOF instead of hanging the parent (the bite-causing
      example was `next lint`'s first-run ESLint setup wizard).
    - Each subprocess is launched in its own session so we can SIGKILL the
      *entire process group* on timeout — otherwise grandchildren (e.g.
      `npm` -> `bash -c '...'` -> `node`) keep stdout pipes open and the
      parent hangs in `communicate()` even after the immediate child is dead.
    - A timeout (default DEFAULT_TIMEOUT_S) kills the group and records
      partial output with exit code TIMEOUT_EXIT_CODE.
    """
    started = datetime.now()
    # CI=1 nudges most JS tools (jest, react-scripts, etc.) into non-interactive
    # mode so they don't accidentally fall into watch mode here.
    env = {**os.environ, "CI": "1"}
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        completed = datetime.now()
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "started": started.isoformat(timespec="seconds"),
            "completed": completed.isoformat(timespec="seconds"),
            "duration": (completed - started).total_seconds(),
            "exit_code": 127,
            "stdout": "",
            "stderr": f"{cmd[0]} was not found on PATH: {exc}",
        }
    except OSError as exc:
        completed = datetime.now()
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "started": started.isoformat(timespec="seconds"),
            "completed": completed.isoformat(timespec="seconds"),
            "duration": (completed - started).total_seconds(),
            "exit_code": 1,
            "stdout": "",
            "stderr": f"failed to run {' '.join(cmd)}: {exc}",
        }

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Extremely unusual — even SIGKILL didn't drain the pipes in 5s.
            stdout, stderr = "", ""
        stderr = (stderr or "") + (
            f"\n[TinyLocalAgents: timed out after {timeout}s — "
            f"likely interactive prompt or watch mode]\n"
        )
        exit_code = TIMEOUT_EXIT_CODE

    completed = datetime.now()
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "started": started.isoformat(timespec="seconds"),
        "completed": completed.isoformat(timespec="seconds"),
        "duration": (completed - started).total_seconds(),
        "exit_code": exit_code,
        "stdout": stdout or "",
        "stderr": stderr or "",
    }


def _format_log(result: dict) -> str:
    """Render the per-command artifact log."""
    cmd_str = " ".join(result["cmd"])
    return (
        f"Command:    {cmd_str}\n"
        f"Working dir: {result['cwd']}\n"
        f"Started:    {result['started']}\n"
        f"Completed:  {result['completed']}\n"
        f"Duration:   {result['duration']:.2f}s\n"
        f"Exit code:  {result['exit_code']}\n"
        f"\n=== stdout ===\n{result['stdout'] or '(empty)'}\n"
        f"\n=== stderr ===\n{result['stderr'] or '(empty)'}\n"
    )


def _run_scripts(
    project_path: Path,
    discovered: dict[str, str],
    pkg_mgr: str,
    artifacts_dir: Path,
    timeout: int | None = DEFAULT_TIMEOUT_S,
) -> list[dict]:
    """Run each discovered script in RUN_ORDER, write its log, return results."""
    results: list[dict] = []
    for script in RUN_ORDER:
        if script not in discovered:
            continue
        cmd = _command_for(pkg_mgr, script)
        print(f"- {' '.join(cmd)} ... ", end="", flush=True)
        result = _run_one(cmd, project_path, timeout=timeout)
        result["script"] = script
        result["status"] = "passed" if result["exit_code"] == 0 else "failed"
        if result["exit_code"] == TIMEOUT_EXIT_CODE:
            print(f"timed out after {timeout}s")
        else:
            print(result["status"])

        log_path = artifacts_dir / f"{script}.log"
        log_path.write_text(_format_log(result), encoding="utf-8")
        result["log_path"] = log_path
        results.append(result)
    return results


def render_test_report(
    project_path: Path,
    loop_path: Path,
    pkg_mgr: str,
    results: list[dict],
    skipped: list[tuple[str, str]],
    overall: str,
    started_overall: str,
    completed_overall: str,
    package_json_missing: bool,
) -> str:
    generated_at = datetime.now().isoformat(timespec="seconds")
    loop_rel = f"loops/{loop_path.name}"

    out: list[str] = []
    out.append("# Test Report")
    out.append("")
    out.append(f"_Generated by `tiny_agents.py test` on {generated_at}._")
    out.append("")
    out.append("## Summary")
    out.append(f"- Project: `{project_path}`")
    out.append(f"- Loop: `{loop_path.name}`")
    out.append(f"- Package manager: {pkg_mgr}")
    out.append(f"- Overall result: **{overall}**")
    out.append(f"- Started: {started_overall}")
    out.append(f"- Completed: {completed_overall}")
    out.append("")

    if package_json_missing:
        out.append("> `package.json` was not found at the project root. No npm scripts were run.")
        out.append("")

    out.append("## Commands Run")
    if results:
        for r in results:
            out.append(f"### {r['script']}")
            out.append(f"- Command: `{' '.join(r['cmd'])}`")
            out.append(f"- Status: {r['status']}")
            out.append(f"- Exit code: {r['exit_code']}")
            out.append(f"- Duration: {r['duration']:.2f}s")
            out.append(f"- Log file: `{loop_rel}/artifacts/{r['script']}.log`")
            if r["status"] == "failed":
                out.append(f"- Error summary: {_summarize_failure(r['stderr'], r['stdout'])}")
            out.append("")
    else:
        out.append("_No commands were run._")
        out.append("")

    out.append("## Skipped Checks")
    if skipped:
        for name, reason in skipped:
            out.append(f"- `{name}`: skipped because {reason}")
    else:
        out.append("- (none)")
    out.append("")

    out.append("## Failure Summary")
    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        for r in failed:
            summary = _summarize_failure(r["stderr"], r["stdout"])
            out.append(f"- **{r['script']}** (`{' '.join(r['cmd'])}`): {summary}")
            out.append(f"  - Full log: `{loop_rel}/artifacts/{r['script']}.log`")
    else:
        out.append("- (no failures)")
    out.append("")

    out.append("## Scope Notes")
    out.append("- This command does not edit code.")
    out.append("- This command does not auto-fix failures.")
    out.append("- Dev / watch / start scripts are intentionally NOT run.")
    out.append("- If failures occurred, create a new loop focused on fixing them:")
    out.append("  `python tiny_agents.py new \"Fix <thing> from loop " + loop_path.name + "\"`")
    out.append("")

    out.append("## Conclusion")
    conclusion_text = {
        "passed": "**passed** — all discovered commands passed.",
        "failed": "**failed** — one or more discovered commands failed. See logs in `artifacts/`.",
        "no-tests-run": "**no-tests-run** — no supported scripts were found.",
    }.get(overall, overall)
    out.append(f"- {conclusion_text}")
    out.append("")

    return "\n".join(out)


def cmd_test(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()

    if not project_path.exists():
        print(f"Error: project path does not exist: {project_path}", file=sys.stderr)
        return 1
    if not project_path.is_dir():
        print(f"Error: project path is not a directory: {project_path}", file=sys.stderr)
        return 1

    if not is_initialized():
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    latest = get_latest_loop()
    if latest is None:
        print(
            "No loops exist yet. Create one first:\n"
            "  python tiny_agents.py new \"<your task title>\"",
            file=sys.stderr,
        )
        return 1

    print(f"Testing project: {project_path}")
    print(f"Latest loop: {latest.relative_to(ROOT)}")

    started_overall_dt = datetime.now()
    started_overall = started_overall_dt.isoformat(timespec="seconds")

    pkg = _read_package_json(project_path)

    # Case 1: package.json missing — write a report, skip everything, exit 0.
    if pkg is None:
        print("Package manager: (n/a — no package.json found)")
        skipped = [(name, "no package.json found") for name in ALLOWED_SCRIPTS]
        report = render_test_report(
            project_path=project_path,
            loop_path=latest,
            pkg_mgr="(n/a)",
            results=[],
            skipped=skipped,
            overall="no-tests-run",
            started_overall=started_overall,
            completed_overall=datetime.now().isoformat(timespec="seconds"),
            package_json_missing=True,
        )
        out_path = latest / "test-report.md"
        out_path.write_text(report, encoding="utf-8")
        print("Wrote:")
        print(f"  - {out_path.relative_to(ROOT)}")
        print("Overall result: no-tests-run (no package.json found)")
        return 0

    pkg_mgr = _normalize_pkg_mgr(_guess_package_manager(project_path))
    print(f"Package manager: {pkg_mgr}")

    scripts = pkg.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}

    discovered = {name: scripts[name] for name in ALLOWED_SCRIPTS if name in scripts}
    skipped = [
        (name, f"no `{name}` script in package.json")
        for name in ALLOWED_SCRIPTS
        if name not in scripts
    ]

    # Case 2: package.json exists but no supported scripts — report and exit 0.
    if not discovered:
        print("No supported scripts found in package.json (looked for: " + ", ".join(ALLOWED_SCRIPTS) + ").")
        report = render_test_report(
            project_path=project_path,
            loop_path=latest,
            pkg_mgr=pkg_mgr,
            results=[],
            skipped=skipped,
            overall="no-tests-run",
            started_overall=started_overall,
            completed_overall=datetime.now().isoformat(timespec="seconds"),
            package_json_missing=False,
        )
        out_path = latest / "test-report.md"
        out_path.write_text(report, encoding="utf-8")
        print("Wrote:")
        print(f"  - {out_path.relative_to(ROOT)}")
        print("Overall result: no-tests-run")
        return 0

    # Case 3: run discovered scripts in order.
    timeout = getattr(args, "timeout", DEFAULT_TIMEOUT_S)
    print(f"Running: (per-command timeout: {timeout}s)")
    artifacts_dir = latest / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    # Clear stale logs from a previous run so the directory reflects this run.
    for stale in ALLOWED_SCRIPTS:
        stale_log = artifacts_dir / f"{stale}.log"
        if stale_log.exists():
            try:
                stale_log.unlink()
            except OSError:
                pass
    results = _run_scripts(project_path, discovered, pkg_mgr, artifacts_dir, timeout=timeout)

    any_failed = any(r["status"] == "failed" for r in results)
    overall = "failed" if any_failed else "passed"

    report = render_test_report(
        project_path=project_path,
        loop_path=latest,
        pkg_mgr=pkg_mgr,
        results=results,
        skipped=skipped,
        overall=overall,
        started_overall=started_overall,
        completed_overall=datetime.now().isoformat(timespec="seconds"),
        package_json_missing=False,
    )
    out_path = latest / "test-report.md"
    out_path.write_text(report, encoding="utf-8")

    print("Wrote:")
    print(f"  - {out_path.relative_to(ROOT)}")
    for r in results:
        print(f"  - {r['log_path'].relative_to(ROOT)}")
    print(f"Overall result: {overall}")
    if any_failed:
        print("See:")
        print(f"  - {out_path.relative_to(ROOT)}")
        for r in results:
            if r["status"] == "failed":
                print(f"  - {r['log_path'].relative_to(ROOT)}")
        return 1
    return 0


# ----- Loop summary -----
#
# Stage 5 reads the latest loop's test-report.md and writes a clear
# next-loop.md summary plus a focused recommendation for the next loop.
# Local files only — no AI calls, no project edits, no test runs.

_VALID_OVERALL = ("passed", "failed", "no-tests-run", "unknown")


def _extract_overall_result(text: str) -> str | None:
    """Pull `- Overall result: <value>` (with optional bold markers) out of the report."""
    m = re.search(
        r"^-\s+Overall result:\s+\*{0,2}([A-Za-z][A-Za-z\-]*)\*{0,2}",
        text,
        flags=re.MULTILINE,
    )
    if not m:
        return None
    value = m.group(1).strip().lower()
    return value if value in _VALID_OVERALL else None


def _extract_command_results(text: str) -> list[dict]:
    """Parse the `## Commands Run` section into one dict per `### <script>` block."""
    section = _extract_section(text, r"^commands run$")
    if not section:
        return []
    blocks = re.split(r"^###\s+", section, flags=re.MULTILINE)
    results: list[dict] = []
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        script = lines[0].strip()
        body = "\n".join(lines[1:])
        status_m = re.search(r"^-\s+Status:\s+(\w+)", body, flags=re.MULTILINE)
        log_m = re.search(r"^-\s+Log file:\s+`([^`]+)`", body, flags=re.MULTILINE)
        err_m = re.search(r"^-\s+Error summary:\s+(.+?)\s*$", body, flags=re.MULTILINE)
        results.append({
            "script": script,
            "status": (status_m.group(1).lower() if status_m else "unknown"),
            "log": log_m.group(1) if log_m else None,
            "error": err_m.group(1) if err_m else None,
        })
    return results


def _extract_skipped(text: str) -> list[str]:
    """Pull `- \\`<script>\\`: skipped because ...` lines out of the Skipped Checks section."""
    section = _extract_section(text, r"^skipped checks$")
    if not section:
        return []
    out: list[str] = []
    for line in section.splitlines():
        m = re.match(r"^-\s+`([^`]+)`\s*:", line)
        if m:
            out.append(m.group(1))
    return out


def _extract_failure_summaries(text: str) -> list[dict]:
    """Parse the `## Failure Summary` section into structured entries."""
    section = _extract_section(text, r"^failure summary$")
    if not section:
        return []
    failures: list[dict] = []
    current: dict | None = None
    for line in section.splitlines():
        m = re.match(
            r"^-\s+\*\*([^*]+)\*\*\s*\(`([^`]*)`\)\s*:\s*(.*?)\s*$",
            line,
        )
        if m:
            current = {
                "script": m.group(1).strip(),
                "command": m.group(2).strip(),
                "summary": m.group(3).strip(),
                "log": None,
            }
            failures.append(current)
            continue
        log_m = re.match(r"^\s+-\s+Full log:\s+`([^`]+)`", line)
        if log_m and current is not None:
            current["log"] = log_m.group(1)
    return failures


def _summarize_loop_state(test_report_md: str | None) -> dict:
    """Classify a test report into one of: no-report, tests-not-run, passed, failed, no-tests-run, unknown."""
    if test_report_md is None:
        return {
            "state": "no-report",
            "overall": None,
            "passed": [],
            "failed": [],
            "skipped": [],
            "failures": [],
        }
    overall = _extract_overall_result(test_report_md)
    if overall is None:
        # Stage 1 starter template, or a user-written report without a
        # machine-readable Overall result line.
        return {
            "state": "tests-not-run",
            "overall": None,
            "passed": [],
            "failed": [],
            "skipped": [],
            "failures": [],
        }
    cmds = _extract_command_results(test_report_md)
    return {
        "state": overall,
        "overall": overall,
        "passed": [c for c in cmds if c["status"] == "passed"],
        "failed": [c for c in cmds if c["status"] == "failed"],
        "skipped": _extract_skipped(test_report_md),
        "failures": _extract_failure_summaries(test_report_md),
    }


def _build_recommendation(state_info: dict, task_title: str, loop_name: str) -> dict:
    """Return {focus, next_title, next_command} for the given loop state."""
    state = state_info["state"]
    failed_scripts = [c["script"] for c in state_info["failed"]]
    if state == "failed":
        # When the only failed "command" is the Claude executor itself, point
        # the user at the executor / auth / permissions, not at the project's
        # verification scripts. We further distinguish two sub-cases by
        # inspecting the captured error summary:
        #   - Stage 6.7: permission/permission-mode → re-run with acceptEdits
        #   - Stage 6.6: anything else              → generic "fix executor"
        if failed_scripts == ["claude"]:
            error_text = ""
            for c in state_info["failed"]:
                if c["script"].lower() == "claude" and c.get("error"):
                    error_text = c["error"]
                    break
            if not error_text:
                for f in state_info["failures"]:
                    if f["script"].lower() == "claude" and f.get("summary"):
                        error_text = f["summary"]
                        break
            low = error_text.lower()
            permission_keywords = (
                "permission",
                "approve",
                "ready to scaffold",
                "acceptedits",
            )
            if any(kw in low for kw in permission_keywords):
                next_title = "Rerun portfolio creation with Claude acceptEdits permission"
                return {
                    "focus": (
                        "Claude exited cleanly but did not write any files — it asked for write permission "
                        "and stopped. Re-run the same `run` command with `--claude-permission-mode "
                        "acceptEdits` so file edits are auto-approved.\n\n"
                        "```bash\n"
                        "python tiny_agents.py run --project <path> --task \"<same task>\" \\\n"
                        "  --agent claude --create-if-missing --execute --install \\\n"
                        "  --claude-permission-mode acceptEdits --max-turns 30\n"
                        "```\n\n"
                        "TinyLocalAgents intentionally does **not** support `bypassPermissions` or "
                        "`--dangerously-skip-permissions`."
                    ),
                    "next_title": next_title,
                    "next_command": f'python tiny_agents.py new "{next_title}"',
                }
            next_title = f"Fix Claude executor failure from {loop_name}"
            return {
                "focus": (
                    "The Claude Code executor itself failed before any implementation work could happen — for "
                    "example, not logged in, missing API key, or a network / permission issue. The next loop "
                    "should focus on fixing the executor or authentication, **not** on the project's code. "
                    "Inspect `artifacts/claude.log` for the exact error."
                ),
                "next_title": next_title,
                "next_command": f'python tiny_agents.py new "{next_title}"',
            }
        if len(failed_scripts) == 1:
            next_title = f"Fix {failed_scripts[0]} failure from {loop_name}"
        elif failed_scripts:
            next_title = f"Fix {len(failed_scripts)} verification failures from {loop_name}"
        else:
            next_title = f"Fix verification failures from {loop_name}"
        return {
            "focus": (
                "One or more verification commands failed. The next loop should focus **only** on fixing the failing "
                "checks. Do not add new features in this fix loop."
            ),
            "next_title": next_title,
            "next_command": f'python tiny_agents.py new "{next_title}"',
        }
    if state == "passed":
        next_title = f"Review {task_title} and pick the next feature"
        return {
            "focus": (
                "All discovered verification commands passed. This loop appears ready for manual review. "
                "Decide on the next small feature loop — keep its scope to a single concern."
            ),
            "next_title": next_title,
            "next_command": f'python tiny_agents.py new "{next_title}"',
        }
    if state == "no-tests-run":
        next_title = "Add verification scripts to target project"
        return {
            "focus": (
                "No supported verification scripts were found in the target project's `package.json`. Decide whether "
                "to add basic verification scripts (`typecheck` / `build` / `lint` / `test`) or proceed with manual "
                "review only."
            ),
            "next_title": next_title,
            "next_command": f'python tiny_agents.py new "{next_title}"',
        }
    # "tests-not-run" or "no-report" or "unknown"
    return {
        "focus": (
            "No real test results were found for this loop. Run the test command and then re-run `summarize` "
            "before planning the next implementation loop."
        ),
        "next_title": None,
        "next_command": "python tiny_agents.py test --project <path-to-target-project>",
    }


def render_next_loop_summary(
    loop_path: Path,
    task_title: str,
    state_info: dict,
    recommendation: dict,
) -> str:
    state = state_info["state"]
    overall_label = {
        "passed": "passed",
        "failed": "failed",
        "no-tests-run": "no-tests-run",
        "tests-not-run": "tests not run yet",
        "no-report": "no test report found",
        "unknown": "unknown",
    }.get(state, state)

    if state == "passed":
        what_happened = (
            "The discovered verification commands completed successfully. This loop appears ready for manual "
            "review or for moving on to the next feature loop."
        )
    elif state == "failed":
        what_happened = (
            "One or more verification commands failed. The next loop should focus only on fixing the failing "
            "checks before adding new features."
        )
    elif state == "no-tests-run":
        what_happened = (
            "No supported verification scripts were found in the target project's `package.json`. The next loop "
            "should decide whether to add basic verification scripts or proceed with manual review."
        )
    elif state == "tests-not-run":
        what_happened = (
            "A `test-report.md` exists but does not contain machine-readable results — most likely the starter "
            "template, or a report that was never produced by `tiny_agents.py test`. Run the test command and "
            "then re-run `summarize` before planning the next loop."
        )
    elif state == "no-report":
        what_happened = (
            "No `test-report.md` was found in this loop. Run the test command to generate one before planning the "
            "next loop."
        )
    else:
        what_happened = (
            "The loop's state could not be determined from the available files. Inspect the loop folder manually."
        )

    def _bul(items: list[str], empty: str) -> str:
        return "\n".join(f"- {x}" for x in items) if items else empty

    passed_block = _bul(
        [f"`{c['script']}`" for c in state_info["passed"]],
        "_(no passed checks recorded)_",
    )

    if state_info["failed"]:
        failed_lines: list[str] = []
        # Index failure summaries by script for richer error lines.
        failures_by_script = {f["script"].lower(): f for f in state_info["failures"]}
        for c in state_info["failed"]:
            extra = failures_by_script.get(c["script"].lower())
            summary = (extra or {}).get("summary") or c.get("error") or ""
            line = f"`{c['script']}`"
            if summary:
                line += f" — {summary}"
            failed_lines.append(line)
            if c.get("log"):
                failed_lines.append(f"  - Log: `{c['log']}`")
            elif extra and extra.get("log"):
                failed_lines.append(f"  - Log: `{extra['log']}`")
        failed_block = "\n".join(f"- {x}" if not x.startswith("  -") else x for x in failed_lines)
    else:
        failed_block = "_(no failed checks recorded)_"

    skipped_block = _bul(
        [f"`{s}`" for s in state_info["skipped"]],
        "_(none)_",
    )

    title_line = (
        f"Suggested loop title: **{recommendation['next_title']}**"
        if recommendation["next_title"]
        else "_(No new loop is suggested yet — run the test command first.)_"
    )

    generated_at = datetime.now().isoformat(timespec="seconds")

    return f"""# Next Loop

_Generated by `tiny_agents.py summarize` on {generated_at}._

## Current Loop
- Loop: `{loop_path.name}`
- Task: {task_title}
- Overall result: {overall_label}
- Summary generated: {generated_at}

## What Happened
{what_happened}

## Passed Checks
{passed_block}

## Failed Checks
{failed_block}

## Skipped Checks
{skipped_block}

## Recommended Next Loop
{recommendation['focus']}

{title_line}

## Suggested Next Loop Prompt
```bash
{recommendation['next_command']}
```

## Notes
- This summary is based only on local report files (`test-report.md`).
- TinyLocalAgents does not auto-fix code in Stage 5 — recovery requires running a new loop manually.
- Inspect `loops/{loop_path.name}/artifacts/*.log` for full failure output.
"""


def cmd_summarize(_args: argparse.Namespace) -> int:
    if not is_initialized():
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    latest = get_latest_loop()
    if latest is None:
        print(
            "No loops exist yet. Create one first:\n"
            "  python tiny_agents.py new \"<your task title>\"",
            file=sys.stderr,
        )
        return 1

    print("Summarizing latest loop:")
    print(f"  {latest.relative_to(ROOT)}")

    test_report_md = _read_text_safe(latest / "test-report.md")
    plan_md = _read_text_safe(latest / "plan.md")
    research_md = _read_text_safe(latest / "research.md")
    context_md = _read_text_safe(latest / "context-summary.md")

    read_list: list[str] = []
    for label, content in (
        ("test-report.md", test_report_md),
        ("plan.md", plan_md),
        ("research.md", research_md),
        ("context-summary.md", context_md),
    ):
        if content is not None:
            read_list.append(label)

    print("Read:")
    if read_list:
        for name in read_list:
            print(f"  - {name}")
    else:
        print("  - (none — loop folder is empty?)")

    state_info = _summarize_loop_state(test_report_md)
    task_title = _title_from_research(research_md) or _title_from_folder(latest)
    recommendation = _build_recommendation(state_info, task_title, latest.name)

    print(f"Detected overall result: {state_info['state']}")

    out_md = render_next_loop_summary(latest, task_title, state_info, recommendation)
    out_path = latest / "next-loop.md"
    out_path.write_text(out_md, encoding="utf-8")

    print("Wrote:")
    print(f"  - {out_path.relative_to(ROOT)}")
    print("Recommended next step:")
    print(f"  {recommendation['next_command']}")
    return 0


# ----- Run: one-loop auto orchestrator -----
#
# Stage 6 chains the earlier stages end-to-end: create loop, fill task notes,
# scan, prompt, invoke Claude Code, test, summarize. ONE loop only. No
# permission bypass, no AI API calls (Claude Code is invoked as an external
# subprocess), no deployment, no multi-loop autonomy.

DEFAULT_MAX_TURNS = 8
SUPPORTED_AGENTS = ("claude",)


def _is_ai_engineer_portfolio_task(task: str) -> bool:
    t = task.lower()
    return ("ai engineer" in t or "ai-engineer" in t) and (
        "portfolio" in t or "homepage" in t
    )


def _ai_engineer_research_md(task: str) -> str:
    return f"""# Research: {task}

## What problem are we solving?
We need a focused, static portfolio homepage that positions the author for AI
Engineer / Full-stack AI Engineer roles. The page must communicate, at a
glance, that the author builds production-style AI applications, RAG systems,
and agentic developer tools.

## Who is the user?
- **Audience:** recruiters, hiring managers, technical interviewers.
- **Target roles:** AI Engineer, Applied AI Engineer, Full-stack AI Engineer,
  GenAI Engineer.
- **Behavior:** skims quickly, looks for proof of relevant work, then decides
  whether to reach out.

## What is the goal?
Ship a small, well-organized static homepage that makes the author's
positioning and most relevant work immediately legible.

## What is in scope?
- A single static homepage built with Next.js + TypeScript + Tailwind.
- All six required sections (Hero, About, Featured Projects, Skills / Tech
  Stack, How I Work, Contact).
- Copy that clearly positions the author for AI Engineer roles.
- Three featured projects:
  - TinyLocalAgents / Local Agent Dev Studio
  - Brand Voice Rewrite Studio
  - AI Engineering Learning Lab

## What is out of scope?
- Backend
- Database
- Authentication
- CMS / blog
- Payments
- External API integrations
- AI chatbot

## Core message
"I build production-style AI applications, RAG systems, and agentic developer
tools."

## Notes / References
- This loop is orchestrated by `tiny_agents.py run`.
"""


def _ai_engineer_plan_md(task: str) -> str:
    return f"""# Plan: {task}

## What will be done in this loop?
Create (or update) a minimal Next.js + TypeScript + Tailwind project
containing a single static portfolio homepage with six required sections.

## Required homepage sections
1. **Hero** — name, headline, one-line positioning.
2. **About** — short narrative, 2–3 paragraphs.
3. **Featured Projects** — three project cards.
4. **Skills / Tech Stack** — grouped capabilities.
5. **How I Work** — short, opinionated working-style notes.
6. **Contact** — email and relevant profile links.

## Featured projects
- **TinyLocalAgents / Local Agent Dev Studio**
- **Brand Voice Rewrite Studio**
- **AI Engineering Learning Lab**

## Allowed changes
Because the target folder may be empty (`--create-if-missing`), file creation
is permitted across the standard Next.js layout:
- `app/page.tsx`
- `app/layout.tsx`
- `app/globals.css`
- `package.json`
- `tsconfig.json`
- `next.config.*` (if needed)
- `tailwind.config.*` (if needed)
- Any homepage-related components under `components/` or `app/`

If the project already exists and has a `package.json`, avoid unnecessary
dependency changes.

## Forbidden changes
- No backend code
- No database
- No authentication
- No CMS
- No payments
- No external API integration
- No AI chatbot
- No secrets or `.env*` files

## Acceptance criteria
- [ ] The project has a valid `package.json`.
- [ ] `npm install` can be run cleanly by the user.
- [ ] `npm run build` passes after dependencies are installed.
- [ ] The homepage renders all six required sections.
- [ ] Copy clearly positions the author for AI Engineer / Full-stack AI
      Engineer roles.
- [ ] No backend, database, auth, payment, or external API integration is
      added.
- [ ] The implementation stays small and reviewable.

## Risks / Unknowns
- The build will fail if dependencies have not been installed yet; that
  failure is expected and feeds into the next loop.
"""


def _placeholder_readme(task: str) -> str:
    return f"""# Placeholder

This folder was created by `tiny_agents.py run --create-if-missing` for the
task:

> {task}

Claude Code will create the actual project files inside this folder when
invoked with `--execute`.
"""


def _create_loop_for_task(task: str) -> Path:
    """Create a numbered loop folder for the task; mirrors cmd_new's core."""
    number = next_loop_number()
    slug = slugify(task)
    folder_name = f"{number:03d}-{slug}"
    loop_path = LOOPS_DIR / folder_name
    if loop_path.exists():
        raise FileExistsError(str(loop_path))
    loop_path.mkdir(parents=True)
    for filename, builder in LOOP_FILES.items():
        (loop_path / filename).write_text(builder(task), encoding="utf-8")
    return loop_path


def _tee_run(cmd: list[str], cwd: Path, timeout: int | None = DEFAULT_TIMEOUT_S) -> dict:
    """Run a subprocess, streaming stdout/stderr to terminal while capturing.

    Stage 6.8 hardening:
    - stdin is wired to /dev/null. Claude is invoked with `-p` (print mode) and
      doesn't read stdin; `npm install`, `pnpm install`, etc. are
      non-interactive by design. Removing the inherited stdin avoids the class
      of bug where a tool tries to prompt and the orchestrator deadlocks.
    - A timeout (default DEFAULT_TIMEOUT_S) kills the subprocess if it doesn't
      finish. We mark it as exit code TIMEOUT_EXIT_CODE and append a clear
      note to the captured stderr so the failure surfaces in claude.log /
      install.log and gets a useful error summary.
    """
    started = datetime.now()
    env = {**os.environ}
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,  # never block on interactive input
            text=True,
            bufsize=1,  # line-buffered
            env=env,
            start_new_session=True,  # lead our own process group for clean kill
        )
    except FileNotFoundError as exc:
        completed = datetime.now()
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "started": started.isoformat(timespec="seconds"),
            "completed": completed.isoformat(timespec="seconds"),
            "duration": (completed - started).total_seconds(),
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "spawn_error": True,
        }

    stdout_buf: list[str] = []
    stderr_buf: list[str] = []

    def _reader(stream, buf, terminal_stream):
        try:
            for line in iter(stream.readline, ""):
                buf.append(line)
                terminal_stream.write(line)
                terminal_stream.flush()
        finally:
            stream.close()

    # daemon=True is a belt-and-suspenders measure: if for any reason a
    # reader thread can't exit (e.g. an orphaned grandchild keeps the pipe
    # alive), it won't block process exit.
    t_out = threading.Thread(
        target=_reader, args=(proc.stdout, stdout_buf, sys.stdout), daemon=True
    )
    t_err = threading.Thread(
        target=_reader, args=(proc.stderr, stderr_buf, sys.stderr), daemon=True
    )
    t_out.start()
    t_err.start()

    timed_out = False
    try:
        exit_code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # SIGKILL the *entire process group* so any grandchild (e.g.
        # `bash -c "node ..."` or `npm` spawning a child) is also killed and
        # the stdout/stderr pipes actually drain.
        _kill_process_group(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        exit_code = TIMEOUT_EXIT_CODE
        timed_out = True

    # Reader threads exit on their own once the streams hit EOF, which
    # happens after the process group is fully dead. A bounded join is a
    # final safety net so we never block the orchestrator on a pathological
    # process that refused to release its pipes.
    t_out.join(timeout=10)
    t_err.join(timeout=10)

    if timed_out:
        timeout_note = (
            f"\n[TinyLocalAgents: timed out after {timeout}s — "
            f"likely interactive prompt or watch mode]\n"
        )
        stderr_buf.append(timeout_note)
        sys.stderr.write(timeout_note)
        sys.stderr.flush()

    completed = datetime.now()
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "started": started.isoformat(timespec="seconds"),
        "completed": completed.isoformat(timespec="seconds"),
        "duration": (completed - started).total_seconds(),
        "exit_code": exit_code,
        "stdout": "".join(stdout_buf),
        "stderr": "".join(stderr_buf),
        "spawn_error": False,
    }


def _install_command_for(pkg_mgr: str) -> list[str]:
    """Argv list for the package manager's install command."""
    return {
        "pnpm": ["pnpm", "install"],
        "yarn": ["yarn", "install"],
        "bun": ["bun", "install"],
        "npm": ["npm", "install"],
    }.get(pkg_mgr, ["npm", "install"])


def _synthesize_install_failed_test_report(
    project_path: Path,
    loop_path: Path,
    pkg_mgr: str,
    install_result: dict,
) -> str:
    """When `<pm> install` fails we skip the test step but still produce a
    coherent test-report.md so `summarize` can recommend the next loop."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    loop_rel = f"loops/{loop_path.name}"
    cmd_str = " ".join(install_result["cmd"])
    err_summary = _summarize_failure(install_result["stderr"], install_result["stdout"])
    return f"""# Test Report

_Generated by `tiny_agents.py run --install` on {generated_at} after the install step failed._

## Summary
- Project: `{project_path}`
- Loop: `{loop_path.name}`
- Package manager: {pkg_mgr}
- Overall result: **failed**
- Started: {install_result['started']}
- Completed: {install_result['completed']}

> Dependency install (`{cmd_str}`) failed before any verification scripts could run.
> `build` / `lint` / `typecheck` / `test` were intentionally skipped because they would fail with missing modules.

## Commands Run
### install
- Command: `{cmd_str}`
- Status: failed
- Exit code: {install_result['exit_code']}
- Duration: {install_result['duration']:.2f}s
- Log file: `{loop_rel}/artifacts/install.log`
- Error summary: {err_summary}

## Skipped Checks
- `typecheck`: skipped because install failed
- `type-check`: skipped because install failed
- `build`: skipped because install failed
- `lint`: skipped because install failed
- `test`: skipped because install failed

## Failure Summary
- **install** (`{cmd_str}`): {err_summary}
  - Full log: `{loop_rel}/artifacts/install.log`

## Scope Notes
- This command does not edit code.
- This command does not auto-fix failures.
- The test step was skipped because dependencies were not installed.
- If failures occurred, create a new loop focused on fixing them:
  `python tiny_agents.py new "Fix install failure from {loop_path.name}"`

## Conclusion
- **failed** — dependency install failed; verification scripts were skipped.
"""


def _synthesize_executor_failed_test_report(
    project_path: Path,
    loop_path: Path,
    claude_result: dict,
    redacted_argv: list[str],
) -> str:
    """When `claude` spawns but exits non-zero, install/test are skipped and we
    write a coherent test-report.md whose only failed command is `claude` so
    `summarize` recommends fixing the executor (Stage 6.6)."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    loop_rel = f"loops/{loop_path.name}"
    cmd_str = " ".join(redacted_argv)
    err_summary = _summarize_failure(claude_result["stderr"], claude_result["stdout"])
    return f"""# Test Report

_Generated by `tiny_agents.py run` on {generated_at} after the Claude executor exited non-zero._

## Summary
- Project: `{project_path}`
- Loop: `{loop_path.name}`
- Package manager: (n/a — executor failed before any project work)
- Overall result: **failed**
- Started: {claude_result['started']}
- Completed: {claude_result['completed']}

> The Claude Code executor exited with a non-zero status before producing any implementation work.
> `install` / `typecheck` / `build` / `lint` / `test` were intentionally skipped because there is
> nothing meaningful to verify yet. Read `{loop_rel}/artifacts/claude.log` for the full executor output.

## Commands Run
### claude
- Command: `{cmd_str}`
- Status: failed
- Exit code: {claude_result['exit_code']}
- Duration: {claude_result['duration']:.2f}s
- Log file: `{loop_rel}/artifacts/claude.log`
- Error summary: {err_summary}

## Skipped Checks
- `install`: skipped because Claude executor failed
- `typecheck`: skipped because Claude executor failed
- `type-check`: skipped because Claude executor failed
- `build`: skipped because Claude executor failed
- `lint`: skipped because Claude executor failed
- `test`: skipped because Claude executor failed

## Failure Summary
- **claude** (`{cmd_str}`): {err_summary}
  - Full log: `{loop_rel}/artifacts/claude.log`

## Scope Notes
- This command does not edit code.
- This command does not auto-fix failures.
- The implementation step itself failed; nothing was attempted afterwards.
- The next loop should fix the executor / authentication, not the project's code.

## Conclusion
- **failed** — Claude executor exited non-zero; install and test were skipped.
"""


_INCOMPLETE_HOMEPAGE_CANDIDATES = (
    "app/page.tsx", "app/page.jsx",
    "pages/index.tsx", "pages/index.jsx",
    "src/app/page.tsx", "src/app/page.jsx",
    "src/pages/index.tsx", "src/pages/index.jsx",
)

_INCOMPLETE_PERMISSION_PHRASES = (
    "i need permission",
    "permission to write",
    "approve writes",
    "ready to scaffold",
    "once you approve",
    "approve",
)


def _is_implementation_incomplete(project_path: Path, claude_result: dict) -> bool:
    """Stage 6.7 completion gate. Returns True iff Claude exited 0 but the
    target project shows no sign of implementation AND Claude's output looks
    like it asked for write permission and stopped.

    All three conditions must be true to avoid false positives:
      1. No package.json in the target project.
      2. No homepage entry under any of the standard Next.js paths.
      3. Claude's stdout/stderr contains a known permission-request phrase.
    """
    if (project_path / "package.json").is_file():
        return False
    if any((project_path / h).is_file() for h in _INCOMPLETE_HOMEPAGE_CANDIDATES):
        return False
    text = (
        (claude_result.get("stdout") or "")
        + "\n"
        + (claude_result.get("stderr") or "")
    ).lower()
    return any(phrase in text for phrase in _INCOMPLETE_PERMISSION_PHRASES)


def _synthesize_implementation_incomplete_test_report(
    project_path: Path,
    loop_path: Path,
    claude_result: dict,
    redacted_argv: list[str],
    err_summary: str,
) -> str:
    """test-report.md written when Claude exits 0 but nothing happened.

    The error summary must contain the word "permission" so that summarize's
    Stage 6.7 permission detector fires and recommends `--claude-permission-mode
    acceptEdits` instead of the generic "fix Claude executor" message.
    """
    generated_at = datetime.now().isoformat(timespec="seconds")
    loop_rel = f"loops/{loop_path.name}"
    cmd_str = " ".join(redacted_argv)
    return f"""# Test Report

_Generated by `tiny_agents.py run` on {generated_at} after Claude exited 0 without producing any implementation._

## Summary
- Project: `{project_path}`
- Loop: `{loop_path.name}`
- Package manager: (n/a — implementation incomplete)
- Overall result: **failed**
- Started: {claude_result['started']}
- Completed: {claude_result['completed']}

> Claude exited with code 0 but did not write any files. The target project still has no
> `package.json` and no homepage entry (`app/page.tsx`, `pages/index.tsx`, …), and Claude's
> own output contained permission/request language. This usually means Claude asked for
> write permission and stopped instead of editing.
>
> Re-run the same command with `--claude-permission-mode acceptEdits` so Claude can write
> files without per-edit manual approval. TinyLocalAgents intentionally does **not** support
> `bypassPermissions` or `--dangerously-skip-permissions`.

## Commands Run
### claude
- Command: `{cmd_str}`
- Status: failed
- Exit code: {claude_result['exit_code']}
- Duration: {claude_result['duration']:.2f}s
- Log file: `{loop_rel}/artifacts/claude.log`
- Error summary: {err_summary}

## Skipped Checks
- `install`: skipped because implementation was incomplete
- `typecheck`: skipped because implementation was incomplete
- `type-check`: skipped because implementation was incomplete
- `build`: skipped because implementation was incomplete
- `lint`: skipped because implementation was incomplete
- `test`: skipped because implementation was incomplete

## Failure Summary
- **claude** (`{cmd_str}`): {err_summary}
  - Full log: `{loop_rel}/artifacts/claude.log`

## Scope Notes
- This command does not edit code.
- This command does not auto-fix failures.
- Claude exited cleanly but performed no implementation; nothing was verified afterwards.
- The next loop should re-run with `--claude-permission-mode acceptEdits`, not fix the
  project's code (there is no project code yet).

## Conclusion
- **failed** — Claude did not implement the task (asked for write permission). Install and test were skipped.
"""


def _format_command_log(result: dict) -> str:
    cmd_str = " ".join(result["cmd"])
    return (
        f"Command:    {cmd_str}\n"
        f"Working dir: {result['cwd']}\n"
        f"Started:    {result['started']}\n"
        f"Completed:  {result['completed']}\n"
        f"Duration:   {result['duration']:.2f}s\n"
        f"Exit code:  {result['exit_code']}\n"
        f"\n=== stdout ===\n{result['stdout'] or '(empty)'}\n"
        f"\n=== stderr ===\n{result['stderr'] or '(empty)'}\n"
    )


def _render_dry_run_next_loop(
    loop_path: Path,
    project_path: Path,
    task: str,
    max_turns: int,
) -> str:
    generated_at = datetime.now().isoformat(timespec="seconds")
    return f"""# Next Loop (dry run)

_Generated by `tiny_agents.py run` (dry-run mode) on {generated_at}._

## Current Loop
- Loop: `{loop_path.name}`
- Task: {task}
- Project: `{project_path}`
- Mode: **dry run** — Claude Code was NOT invoked and tests were NOT run.

## What Happened
This was a dry run. The loop folder, `research.md`, `plan.md`,
`context-summary.md`, and `implementation-prompt.md` were prepared, but
Claude Code was not invoked and the project's tests were not executed.

## Recommended Next Step
Re-run the same command with `--execute` to actually invoke Claude:

```bash
python tiny_agents.py run \\
  --project {project_path} \\
  --task "{task}" \\
  --agent claude \\
  --create-if-missing \\
  --execute \\
  --max-turns {max_turns}
```

## Notes
- TinyLocalAgents does not use `--dangerously-skip-permissions`.
- TinyLocalAgents stops after one loop; this is not a continuous autonomous
  runner.
- Inspect `implementation-prompt.md` before re-running with `--execute` to
  confirm the instructions you would be handing to Claude.
"""


def cmd_run(args: argparse.Namespace) -> int:
    task = (args.task or "").strip()
    if not task:
        print("Error: --task must not be empty.", file=sys.stderr)
        return 1
    if args.agent not in SUPPORTED_AGENTS:
        print(
            f"Error: --agent must be one of {SUPPORTED_AGENTS} (got {args.agent!r}).",
            file=sys.stderr,
        )
        return 1
    if not is_initialized():
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    project_path = Path(args.project).expanduser().resolve()
    project_created = False
    if not project_path.exists():
        if args.create_if_missing:
            project_path.mkdir(parents=True)
            (project_path / "README.md").write_text(
                _placeholder_readme(task), encoding="utf-8"
            )
            project_created = True
            print(f"Created project folder: {project_path}")
        else:
            print(f"Error: project path does not exist: {project_path}", file=sys.stderr)
            print("Pass --create-if-missing to create it.", file=sys.stderr)
            return 1
    elif not project_path.is_dir():
        print(f"Error: project path is not a directory: {project_path}", file=sys.stderr)
        return 1

    # Create the loop folder
    try:
        loop_path = _create_loop_for_task(task)
    except FileExistsError as exc:
        print(f"Error: loop folder already exists: {exc}", file=sys.stderr)
        return 1

    # Auto-fill research.md / plan.md.
    # Priority order (highest first):
    #   1. Caller-injected `research_content` / `plan_content` on the args
    #      Namespace — used by `auto` to push the goal spec into Claude's
    #      Research Context (Stage 8.1).
    #   2. AI-Engineer portfolio specialization when the task title matches.
    #   3. Generic Stage 1 starter (already written by _create_loop_for_task).
    research_override = getattr(args, "research_content", None)
    plan_override = getattr(args, "plan_content", None)

    if research_override or plan_override:
        if research_override:
            (loop_path / "research.md").write_text(research_override, encoding="utf-8")
        if plan_override:
            (loop_path / "plan.md").write_text(plan_override, encoding="utf-8")
        template_source = "goal-spec injection (from auto)"
    elif _is_ai_engineer_portfolio_task(task):
        (loop_path / "research.md").write_text(_ai_engineer_research_md(task), encoding="utf-8")
        (loop_path / "plan.md").write_text(_ai_engineer_plan_md(task), encoding="utf-8")
        template_source = "AI-Engineer portfolio specialization"
    else:
        template_source = (
            "generic Stage 1 starter (fill in research.md and plan.md before --execute)"
        )

    print(f"Created loop: {loop_path.relative_to(ROOT)}")
    print(f"Project: {project_path}")
    print(f"Project created: {'yes (new folder)' if project_created else 'no (already existed)'}")
    print(f"Templates: {template_source}")

    # Step: scan
    print()
    print("Step: scan")
    scan_rc = cmd_scan(argparse.Namespace(project=str(project_path)))
    if scan_rc != 0:
        print("(scan returned non-zero; continuing with whatever context is available)")

    # Step: prompt
    print()
    print("Step: prompt")
    prompt_rc = cmd_prompt(argparse.Namespace())
    if prompt_rc != 0:
        print("Error: prompt generation failed; aborting.", file=sys.stderr)
        return prompt_rc

    prompt_path = loop_path / "implementation-prompt.md"
    prompt_text = _read_text_safe(prompt_path) or ""
    if not prompt_text.strip():
        print("Error: implementation-prompt.md is empty after generation; aborting.", file=sys.stderr)
        return 1

    # Build the Claude command (same shape for dry-run and execute)
    claude_cmd = ["claude", "-p", prompt_text, "--max-turns", str(args.max_turns)]
    redacted_argv = [
        "claude",
        "-p",
        f"<prompt from {prompt_path.relative_to(ROOT)} ({len(prompt_text)} chars)>",
        "--max-turns",
        str(args.max_turns),
    ]
    if args.claude_permission_mode == "acceptEdits":
        # argparse choices=["default","acceptEdits"] guarantees the value is
        # safe — bypassPermissions / arbitrary strings are rejected upstream.
        claude_cmd.extend(["--permission-mode", "acceptEdits"])
        redacted_argv.extend(["--permission-mode", "acceptEdits"])

    if not args.execute:
        print()
        print("Dry run (no --execute). Claude would be invoked with:")
        print(f"  cwd:  {project_path}")
        print(f"  argv: {' '.join(redacted_argv)}")
        if args.claude_permission_mode == "acceptEdits":
            print("  permission mode: acceptEdits (file edits would be auto-approved)")
        else:
            print(
                "  permission mode: default (Claude will ask for per-edit approval; "
                "pass --claude-permission-mode acceptEdits for unattended runs)"
            )
        if args.install:
            print("Note: --install is ignored in dry-run mode (no --execute).")
        dry = _render_dry_run_next_loop(loop_path, project_path, task, args.max_turns)
        (loop_path / "next-loop.md").write_text(dry, encoding="utf-8")
        print()
        print("Wrote dry-run note to:")
        print(f"  - {(loop_path / 'next-loop.md').relative_to(ROOT)}")
        print()
        print("To execute Claude, re-run the same command with --execute.")
        print("TinyLocalAgents never passes --dangerously-skip-permissions.")
        return 0

    # Step: invoke Claude
    timeout = getattr(args, "timeout", DEFAULT_TIMEOUT_S)
    print()
    print(f"Step: invoke Claude Code (max-turns={args.max_turns}, timeout={timeout}s)")
    print("This may take several minutes. Streaming Claude's output below:")
    print(f"  cwd: {project_path}")
    print("-" * 60)
    artifacts_dir = loop_path / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    # Stage 6.9: snapshot the project file tree before Claude so we can tell
    # whether it actually changed anything. This is what lets us distinguish
    # "Claude truly failed before doing work" (Stage 6.6) from "Claude was
    # interrupted mid-work" (max-turns, network, etc. — Stage 6.9 partial).
    pre_claude_snapshot = snapshot_project(project_path)
    claude_result = _tee_run(claude_cmd, project_path, timeout=timeout)
    print("-" * 60)
    # Redact the full prompt out of the log; it's already in implementation-prompt.md
    log_result = {**claude_result, "cmd": redacted_argv}
    claude_log_path = artifacts_dir / "claude.log"
    claude_log_path.write_text(_format_command_log(log_result), encoding="utf-8")
    # Compute the per-Claude diff so the executor-failure decision below has
    # real "did anything happen" signal, not just exit code.
    post_claude_snapshot = snapshot_project(project_path)
    claude_diff = diff_snapshots(pre_claude_snapshot, post_claude_snapshot)
    claude_files_changed = (
        len(claude_diff["added"]) + len(claude_diff["changed"]) + len(claude_diff["removed"])
    )
    print(f"Claude exit code: {claude_result['exit_code']}")
    print(
        f"Wrote: {claude_log_path.relative_to(ROOT)} "
        f"(files changed: +{len(claude_diff['added'])} "
        f"~{len(claude_diff['changed'])} -{len(claude_diff['removed'])})"
    )

    # Stage 6.9: track whether we're in the partial-implementation path so
    # the final run summary can be honest about what happened.
    claude_partial = False

    if claude_result.get("spawn_error"):
        print(
            "Error: failed to spawn 'claude'. Install Claude Code "
            "(https://docs.claude.com) and ensure `claude` is on your PATH.",
            file=sys.stderr,
        )
        return 1

    # Stage 6.6: Claude spawned but exited non-zero AND made no file changes
    # is treated as an implementation/executor failure. Skip install + test
    # (running them against a project Claude never modified would just
    # produce misleading signal), synthesize a failure-shaped test-report.md,
    # and let summarize recommend an executor-focused fix loop.
    #
    # Stage 6.9 narrowing: if Claude exited non-zero but *did* make file
    # changes (handled in the elif below), this 6.6 path does NOT fire and
    # we fall through to install/test/summarize so the actual project state
    # drives the next recommendation.
    if claude_result["exit_code"] != 0 and claude_files_changed == 0:
        err_summary = _summarize_failure(claude_result["stderr"], claude_result["stdout"])
        print()
        print(f"Claude executor failed (exit code {claude_result['exit_code']}).")
        if err_summary and err_summary != "(no output captured)":
            print(f"  First meaningful line: {err_summary}")
        print("Treating this as an implementation/executor failure.")
        print("Skipping install and test — they would have nothing meaningful to check.")

        report = _synthesize_executor_failed_test_report(
            project_path=project_path,
            loop_path=loop_path,
            claude_result=claude_result,
            redacted_argv=redacted_argv,
        )
        (loop_path / "test-report.md").write_text(report, encoding="utf-8")
        print("Wrote synthetic test-report.md so summarize can recommend the next loop.")

        print()
        print("Step: summarize")
        summarize_rc = cmd_summarize(argparse.Namespace())

        print()
        print("Run complete (Claude executor failed).")
        print(f"  Loop:    {loop_path.relative_to(ROOT)}")
        print(f"  Project: {project_path}")
        print(f"  Prompt:  {prompt_path.relative_to(ROOT)}")
        print(f"  Claude:  {claude_log_path.relative_to(ROOT)} (exit {claude_result['exit_code']}) — FAILED")
        print("  Install: skipped (Claude executor failed)")
        print("  Tests:   skipped (Claude executor failed; synthetic test-report.md written)")
        print(f"  Next:    {(loop_path / 'next-loop.md').relative_to(ROOT)} (cmd_summarize rc={summarize_rc})")
        print()
        print(
            "Note: Claude did not complete successfully. Read artifacts/claude.log for the exact error, "
            "then run the recommended fix loop printed above."
        )
        # Consistent with existing design: orchestration completed, the failure
        # is captured as input to the next loop. Spawn failures still exit 1
        # above.
        return 0

    # Stage 6.9: Claude exited non-zero BUT changed files. Common case:
    # `--max-turns` hit while Claude was in the middle of a long scaffold.
    # The work it did is real; we shouldn't pretend nothing happened. Print a
    # clear note and fall through to install / test / summarize so the actual
    # project state drives the next recommendation.
    if claude_result["exit_code"] != 0 and claude_files_changed > 0:
        err_summary = _summarize_failure(claude_result["stderr"], claude_result["stdout"])
        print()
        print(
            f"Claude exited with code {claude_result['exit_code']} but made file changes:"
        )
        print(
            f"  diff: +{len(claude_diff['added'])} added, "
            f"~{len(claude_diff['changed'])} changed, "
            f"-{len(claude_diff['removed'])} removed"
        )
        if err_summary and err_summary != "(no output captured)":
            print(f"  First meaningful line: {err_summary}")
        print(
            "Treating this as a partial implementation (e.g. max-turns hit, network "
            "blip, or other mid-session interruption)."
        )
        print(
            "Proceeding with install / test / summarize so the actual project state "
            "drives the next-loop recommendation."
        )
        claude_partial = True
        # Fall through to the install / test / summarize blocks below.

    # Stage 6.7: completion gate. Claude exited 0 but didn't actually do
    # anything — for example, "Not logged in" handled at exit 0 by some
    # versions, or "I need permission to write files" with no edits made.
    # If we can detect a clean exit AND no implementation AND permission
    # language, treat it as implementation-incomplete: skip install + test
    # and recommend re-running with --claude-permission-mode acceptEdits.
    if _is_implementation_incomplete(project_path, claude_result):
        err_summary = (
            "Claude requested write permission but did not create project files. "
            "Re-run with --claude-permission-mode acceptEdits."
        )
        print()
        print("Claude exited 0 but did not produce any implementation:")
        print("  - no package.json in the target project")
        print("  - no homepage entry (app/page.tsx, pages/index.tsx, ...)")
        print("  - Claude output contains permission/request language")
        print("Treating this as implementation INCOMPLETE.")
        print("Skipping install and test — there is nothing to verify.")

        report = _synthesize_implementation_incomplete_test_report(
            project_path=project_path,
            loop_path=loop_path,
            claude_result=claude_result,
            redacted_argv=redacted_argv,
            err_summary=err_summary,
        )
        (loop_path / "test-report.md").write_text(report, encoding="utf-8")
        print("Wrote synthetic test-report.md so summarize can recommend the next loop.")

        print()
        print("Step: summarize")
        summarize_rc = cmd_summarize(argparse.Namespace())

        print()
        print("Run complete (implementation incomplete).")
        print(f"  Loop:    {loop_path.relative_to(ROOT)}")
        print(f"  Project: {project_path}")
        print(f"  Prompt:  {prompt_path.relative_to(ROOT)}")
        print(f"  Claude:  {claude_log_path.relative_to(ROOT)} (exit 0, but no files written)")
        print("  Install: skipped (implementation incomplete)")
        print("  Tests:   skipped (implementation incomplete; synthetic test-report.md written)")
        print(f"  Next:    {(loop_path / 'next-loop.md').relative_to(ROOT)} (cmd_summarize rc={summarize_rc})")
        print()
        print(
            "Note: Claude exited cleanly but did not write any files. Read artifacts/claude.log, "
            "then re-run with --claude-permission-mode acceptEdits."
        )
        return 0

    # Step: install (opt-in via --install, only after Claude succeeds to spawn)
    install_did_run = False
    install_succeeded = False
    install_result: dict | None = None
    install_log_path: Path | None = None
    install_pkg_mgr: str | None = None

    if args.install:
        print()
        print("Step: install (--install requested)")
        if not (project_path / "package.json").is_file():
            print(
                "Skipping install: no package.json was found in the target project after "
                "Claude completed. (Did Claude create one?)"
            )
        else:
            install_pkg_mgr = _normalize_pkg_mgr(_guess_package_manager(project_path))
            install_cmd = _install_command_for(install_pkg_mgr)
            print(f"Package manager: {install_pkg_mgr}")
            print(f"Install command: {' '.join(install_cmd)} (timeout: {timeout}s)")
            print("This may take a couple of minutes...")
            print("-" * 60)
            install_result = _tee_run(install_cmd, project_path, timeout=timeout)
            print("-" * 60)
            install_log_path = artifacts_dir / "install.log"
            install_log_path.write_text(_format_command_log(install_result), encoding="utf-8")
            install_did_run = True
            install_succeeded = (
                not install_result.get("spawn_error")
                and install_result["exit_code"] == 0
            )
            print(f"Install exit code: {install_result['exit_code']}")
            print(f"Wrote: {install_log_path.relative_to(ROOT)}")
            if install_result.get("spawn_error"):
                print(
                    f"Warning: failed to spawn '{install_pkg_mgr}'. Is it installed and on PATH?",
                    file=sys.stderr,
                )

    # Step: test — skipped when install was requested AND failed, because
    # build/lint/typecheck/test would just fail with missing modules.
    skipping_test_due_to_install = install_did_run and not install_succeeded
    if skipping_test_due_to_install:
        report = _synthesize_install_failed_test_report(
            project_path=project_path,
            loop_path=loop_path,
            pkg_mgr=install_pkg_mgr or "(unknown)",
            install_result=install_result,
        )
        (loop_path / "test-report.md").write_text(report, encoding="utf-8")
        print()
        print(
            "Skipping test step: dependency install failed; verification scripts would be "
            "meaningless without modules."
        )
        print("Wrote a synthetic test-report.md so summarize can recommend the next loop.")
        test_rc = 1
    else:
        print()
        print("Step: test")
        test_rc = cmd_test(argparse.Namespace(project=str(project_path), timeout=timeout))

    # Step: summarize
    print()
    print("Step: summarize")
    summarize_rc = cmd_summarize(argparse.Namespace())

    print()
    print("Run complete.")
    print(f"  Loop:    {loop_path.relative_to(ROOT)}")
    print(f"  Project: {project_path}")
    print(f"  Prompt:  {prompt_path.relative_to(ROOT)}")
    claude_status_note = " — partial, proceeded" if claude_partial else ""
    print(
        f"  Claude:  {claude_log_path.relative_to(ROOT)} "
        f"(exit {claude_result['exit_code']}{claude_status_note})"
    )
    if install_did_run:
        status = "passed" if install_succeeded else "failed"
        print(
            f"  Install: {install_log_path.relative_to(ROOT)} "
            f"({install_pkg_mgr} install — {status}, exit {install_result['exit_code']})"
        )
    elif args.install:
        print("  Install: skipped (no package.json after Claude completed)")
    print(f"  Tests:   {(loop_path / 'test-report.md').relative_to(ROOT)} (cmd_test rc={test_rc})")
    print(f"  Next:    {(loop_path / 'next-loop.md').relative_to(ROOT)} (cmd_summarize rc={summarize_rc})")
    if skipping_test_due_to_install:
        print()
        print(
            "Note: install failed, so tests were skipped. The failure was recorded into "
            "test-report.md and summarize has produced a fix-loop recommendation."
        )
    # Run itself returns 0 if the orchestration completed end-to-end. Test
    # *and* install failures are expected input to the next loop, not
    # run-level errors. Only Claude spawn failures abort with exit 1.
    return 0


# ----- Review Agent shared constants (Stage 9.5 / 9.6) -----
#
# Stage 9.6 replaces the legacy 3-level severity (blocker / warning / info)
# with a 5-level model. Issue severities flow into the auto state machine:
#   blocker, must-fix  -> continue-fix
#   human-decision     -> needs-human-feedback (auto pauses)
#   should-fix only    -> done-with-warnings
#   only nice-to-have  -> done

SEVERITY_BLOCKER = "blocker"
SEVERITY_MUST_FIX = "must-fix"
SEVERITY_SHOULD_FIX = "should-fix"
SEVERITY_NICE_TO_HAVE = "nice-to-have"
SEVERITY_HUMAN_DECISION = "human-decision"

ALL_SEVERITIES = (
    SEVERITY_BLOCKER,
    SEVERITY_MUST_FIX,
    SEVERITY_SHOULD_FIX,
    SEVERITY_NICE_TO_HAVE,
    SEVERITY_HUMAN_DECISION,
)

# Used to pick the top issue when several severities are present.
SEVERITY_PRIORITY = {
    SEVERITY_BLOCKER: 0,
    SEVERITY_MUST_FIX: 1,
    SEVERITY_HUMAN_DECISION: 2,
    SEVERITY_SHOULD_FIX: 3,
    SEVERITY_NICE_TO_HAVE: 4,
}

# Categories used in review-decision.json.
CATEGORY_FUNCTIONAL = "functional"
CATEGORY_SCOPE = "scope"
CATEGORY_SECURITY = "security"
CATEGORY_CONTENT = "content"
CATEGORY_DOCS = "docs"
CATEGORY_DESIGN = "design"  # Stage 9.7 — screenshot-based visual review

REVIEW_CATEGORIES = (
    CATEGORY_FUNCTIONAL,
    CATEGORY_SCOPE,
    CATEGORY_SECURITY,
    CATEGORY_CONTENT,
    CATEGORY_DOCS,
    CATEGORY_DESIGN,
)

# File paths whose addition or modification should at minimum surface as
# "you're touching a risky area — confirm this is intentional". Matched as
# substrings against `/<rel_path>`.
RISKY_PATH_PATTERNS = (
    "/auth/",
    "/admin/",
    "/db/",
    "/database/",
    "/migrations/",
    "/secret",
    "/credentials",
    ".env",
    "/payment",
    "/payments/",
    "/billing",
    "/checkout/",
    "/stripe/",
)

# High-confidence secret patterns. Each match becomes a `blocker` (vs the
# more cautious high-entropy heuristic which we leave out of 9.6 to avoid
# false positives).
SECRET_PATTERNS = (
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("openai_key", r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ("github_pat", r"\bghp_[A-Za-z0-9]{36}\b"),
    ("github_oauth", r"\bgho_[A-Za-z0-9]{36}\b"),
    ("github_user", r"\bghu_[A-Za-z0-9]{36}\b"),
    ("github_server", r"\bghs_[A-Za-z0-9]{36}\b"),
    ("slack_token", r"\bxox[bpars]-[0-9]{10,}-[0-9]{10,}-[A-Za-z0-9]{24,}\b"),
    (
        "private_key_pem",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----",
    ),
)

# Only scan these extensions for secrets (skip binaries and lockfiles).
_SCANNABLE_EXTS_FOR_SECRETS = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".yaml",
    ".yml",
    ".html",
    ".css",
)
_MAX_SCAN_BYTES_PER_FILE = 200_000


def _preview_secret_match(text: str) -> str:
    """Show only the first 4 + last 4 chars of a secret match so the report
    is useful for grepping but never reproduces the secret."""
    if len(text) <= 12:
        return "(short match)"
    return f"{text[:4]}…{text[-4:]} ({len(text)} chars)"


def _make_issue(
    id_: str,
    category: str,
    severity: str,
    description: str,
    suggested_next_task: str = "",
    file: str | None = None,
    line: int | None = None,
    snippet: str | None = None,
    auto_generated: bool = True,
) -> dict:
    """Canonical Issue shape used across all review categories."""
    return {
        "id": id_,
        "category": category,
        "severity": severity,
        "description": description,
        "evidence": {"file": file, "line": line, "snippet": snippet},
        "suggested_next_task": suggested_next_task,
        "auto_generated": auto_generated,
    }


# ----- Stage 9.6 review categories: Scope / Security / Content / Docs -----

def run_scope_review(
    project_path: Path,
    diff: dict,
    goal: dict,
    allow_deps: set[str] | None = None,
) -> list[dict]:
    """Deterministic scope-adherence checks. Returns a list of issues.

    Catches:
      - new files at risky paths (auth / admin / db / payments / .env / ...)
      - forbidden dependencies in the current package.json
      - *-cli runtime dependencies
      - unusually large diffs (human-decision)
    """
    allow_deps = allow_deps or set()
    issues: list[dict] = []

    # 1. Risky-path additions.
    for f in diff.get("added", []):
        match_key = ("/" + f).lower()
        for pattern in RISKY_PATH_PATTERNS:
            if pattern in match_key:
                # .env-class files are caught more pointedly in the security
                # review; flag here as scope only when the path *contains*
                # but isn't itself an env file.
                leaf = Path(f).name
                is_env_file = leaf == ".env" or leaf.startswith(".env.")
                if is_env_file and pattern == ".env":
                    break  # let security review own this
                issues.append(_make_issue(
                    id_=f"scope.risky_path.{len(issues)}",
                    category=CATEGORY_SCOPE,
                    severity=SEVERITY_HUMAN_DECISION,
                    description=(
                        f"new file at a risky path: `{f}` (matched pattern "
                        f"`{pattern}`)"
                    ),
                    file=f,
                    suggested_next_task=(
                        f"Confirm whether `{f}` belongs in this project. "
                        f"If not, remove it; if yes, document the reason in "
                        f"the goal's Scope section."
                    ),
                ))
                break

    # 2. Forbidden / risky deps in current package.json.
    pkg_path = project_path / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pkg = None
        if pkg:
            all_deps: dict[str, str] = {}
            for section_key in ("dependencies", "devDependencies", "peerDependencies"):
                section = pkg.get(section_key) or {}
                if isinstance(section, dict):
                    for name, version in section.items():
                        all_deps[name] = str(version)
            combined_forbidden = set(DEFAULT_FORBIDDEN_DEPS) | set(
                goal["hard"]["forbidden_deps"]
            )
            for dep, version in sorted(all_deps.items()):
                if dep in allow_deps:
                    continue
                if dep in combined_forbidden:
                    issues.append(_make_issue(
                        id_=f"scope.forbidden_dep.{len(issues)}",
                        category=CATEGORY_SCOPE,
                        severity=SEVERITY_BLOCKER,
                        description=(
                            f"forbidden dependency in `package.json`: "
                            f"`{dep}@{version}` (on the red-line list)"
                        ),
                        file="package.json",
                        snippet=f'"{dep}": "{version}"',
                        suggested_next_task=(
                            f"Remove `{dep}` from package.json — it is on "
                            f"the red-line forbidden dependency list."
                        ),
                    ))
                elif dep.endswith("-cli"):
                    issues.append(_make_issue(
                        id_=f"scope.cli_dep.{len(issues)}",
                        category=CATEGORY_SCOPE,
                        severity=SEVERITY_MUST_FIX,
                        description=(
                            f"`*-cli` dependency in package.json: `{dep}@{version}` "
                            f"(CLIs usually shouldn't be runtime deps)"
                        ),
                        file="package.json",
                        snippet=f'"{dep}": "{version}"',
                        suggested_next_task=(
                            f"Remove `{dep}` from runtime dependencies. "
                            f"Move to devDependencies if genuinely needed at "
                            f"build time, otherwise drop it."
                        ),
                    ))

    # 3. Unusually large change — human-decision (could be legit, could be drift).
    total_changes = (
        len(diff.get("added", []))
        + len(diff.get("changed", []))
        + len(diff.get("removed", []))
    )
    if total_changes > 100:
        issues.append(_make_issue(
            id_="scope.large_change.0",
            category=CATEGORY_SCOPE,
            severity=SEVERITY_HUMAN_DECISION,
            description=(
                f"unusually large change in one loop: {total_changes} files "
                f"touched (>100 — please confirm this isn't drift)"
            ),
            suggested_next_task=(
                f"Confirm the {total_changes}-file change is intentional, or "
                f"split into smaller loops."
            ),
        ))

    return issues


def run_security_review(
    project_path: Path,
    diff: dict,
) -> list[dict]:
    """Deterministic security checks. Returns a list of issues.

    Catches:
      - .env* files in the diff (always blocker)
      - high-confidence secret patterns inside changed files
      - API route handlers that write files without a NODE_ENV check
      - upload route handlers that don't appear to sanitize filenames
    """
    issues: list[dict] = []

    # 1. .env* files in the diff — never acceptable in commits.
    for f in list(diff.get("added", [])) + list(diff.get("changed", [])):
        leaf = Path(f).name
        if leaf == ".env" or leaf.startswith(".env."):
            issues.append(_make_issue(
                id_=f"security.env_in_diff.{len(issues)}",
                category=CATEGORY_SECURITY,
                severity=SEVERITY_BLOCKER,
                description=f"`.env`-class file in change: `{f}`",
                file=f,
                suggested_next_task=(
                    f"Remove `{f}` from the repo and ensure `.env*` is in "
                    f".gitignore. Move any real secrets out of the repo."
                ),
            ))

    # 2. Secret-pattern scan on changed files.
    for rel in list(diff.get("added", [])) + list(diff.get("changed", [])):
        path = project_path / rel
        if not path.is_file():
            continue
        if not any(rel.endswith(ext) for ext in _SCANNABLE_EXTS_FOR_SECRETS):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(content) > _MAX_SCAN_BYTES_PER_FILE:
            content = content[:_MAX_SCAN_BYTES_PER_FILE]
        for kind, pattern in SECRET_PATTERNS:
            for m in re.finditer(pattern, content):
                line_num = content[: m.start()].count("\n") + 1
                preview = _preview_secret_match(m.group(0))
                issues.append(_make_issue(
                    id_=f"security.secret_match.{len(issues)}",
                    category=CATEGORY_SECURITY,
                    severity=SEVERITY_BLOCKER,
                    description=(
                        f"suspected `{kind}` literal in `{rel}` line {line_num} "
                        f"({preview})"
                    ),
                    file=rel,
                    line=line_num,
                    snippet=preview,
                    suggested_next_task=(
                        f"Remove the `{kind}` value from `{rel}` and move it "
                        f"to an out-of-repo `.env` file (which must be "
                        f"gitignored). Rotate the credential."
                    ),
                ))

    # 3 / 4. API route handlers: writes without NODE_ENV guard / unsanitized uploads.
    api_route_files = [
        f for f in (list(diff.get("added", [])) + list(diff.get("changed", [])))
        if "/api/" in f and f.endswith(("/route.ts", "/route.tsx", "/route.js", "/route.mjs"))
    ]
    fs_write_pattern = re.compile(
        r"\b(?:writeFile|appendFile|mkdir|fs\.write|fs\.cp|fs\.rename|copyFile|writeFileSync)\b"
    )
    for rel in api_route_files:
        path = project_path / rel
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        does_write = bool(fs_write_pattern.search(content))
        if not does_write:
            continue
        # Look for a clear NODE_ENV / development check anywhere in the file.
        guard_present = bool(
            re.search(
                r"NODE_ENV\s*===?\s*['\"]production['\"]|NODE_ENV\s*!==\s*['\"]development['\"]",
                content,
            )
            or re.search(
                r"process\.env\.NODE_ENV.*production",
                content,
            )
        )
        if not guard_present:
            issues.append(_make_issue(
                id_=f"security.unguarded_write.{len(issues)}",
                category=CATEGORY_SECURITY,
                severity=SEVERITY_MUST_FIX,
                description=(
                    f"API route writes to the filesystem without a `NODE_ENV` "
                    f"check: `{rel}`"
                ),
                file=rel,
                suggested_next_task=(
                    f"At the top of `{rel}`, return 403/404 when "
                    f"`process.env.NODE_ENV === 'production'` before any "
                    f"filesystem write."
                ),
            ))

        # Upload-specific: filename sanitization heuristic.
        if "upload" in rel.lower():
            has_sanitize = any(
                pat in content
                for pat in (
                    "path.basename",
                    "basename(",
                    ".replace(",
                    "/\\w",
                    "/[a-z",
                    "/[A-Z",
                    "endsWith(",
                    ".test(",
                    ".match(",
                )
            )
            if not has_sanitize:
                issues.append(_make_issue(
                    id_=f"security.upload_no_sanitize.{len(issues)}",
                    category=CATEGORY_SECURITY,
                    severity=SEVERITY_MUST_FIX,
                    description=(
                        f"upload route does not appear to sanitize the uploaded "
                        f"filename: `{rel}`"
                    ),
                    file=rel,
                    suggested_next_task=(
                        f"In `{rel}`, sanitize the uploaded filename: reject "
                        f"path-separator characters, traversal sequences, and "
                        f"unknown extensions. Use `path.basename()` and a "
                        f"safe-character regex."
                    ),
                ))

    return issues


def run_content_docs_review(
    project_path: Path,
    goal: dict,
) -> list[dict]:
    """Deterministic content and docs checks. Returns a list of issues.

    Catches:
      - portfolio.json invalid JSON
      - app/page.tsx not referencing the loader
      - app/page.tsx with many hardcoded "TODO:" string literals
      - README.md missing or lacking Studio / editing guidance
    """
    issues: list[dict] = []

    # 1. portfolio.json valid JSON.
    portfolio_json_path = project_path / "src/content/portfolio.json"
    if portfolio_json_path.is_file():
        try:
            json.loads(portfolio_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(_make_issue(
                id_="content.invalid_json.0",
                category=CATEGORY_CONTENT,
                severity=SEVERITY_BLOCKER,
                description=(
                    f"`src/content/portfolio.json` is not valid JSON: "
                    f"{str(exc)[:160]}"
                ),
                file="src/content/portfolio.json",
                snippet=str(exc)[:200],
                suggested_next_task=(
                    "Fix the JSON syntax in `src/content/portfolio.json`."
                ),
            ))
        except OSError:
            pass

    # 2 / 3. app/page.tsx — references loader, no obvious hardcoded TODO blocks.
    page_path = project_path / "app/page.tsx"
    if page_path.is_file():
        try:
            page_content = page_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            page_content = ""
        if page_content:
            references_loader = any(
                marker in page_content
                for marker in (
                    "loadPortfolio",
                    "portfolio.json",
                    "@/content/portfolio",
                    "src/content/portfolio",
                )
            )
            if not references_loader:
                issues.append(_make_issue(
                    id_="content.page_no_loader.0",
                    category=CATEGORY_CONTENT,
                    severity=SEVERITY_MUST_FIX,
                    description=(
                        "`app/page.tsx` does not reference the portfolio loader "
                        "or `portfolio.json` — page content is likely hardcoded"
                    ),
                    file="app/page.tsx",
                    suggested_next_task=(
                        "Make `app/page.tsx` import portfolio data via "
                        "`loadPortfolio()` (or import `portfolio.json` directly) "
                        "and render from that object."
                    ),
                ))
            todo_literal_count = (
                page_content.count('"TODO:') + page_content.count("'TODO:")
            )
            if todo_literal_count >= 3:
                issues.append(_make_issue(
                    id_="content.hardcoded_todos.0",
                    category=CATEGORY_CONTENT,
                    severity=SEVERITY_MUST_FIX,
                    description=(
                        f"`app/page.tsx` contains {todo_literal_count} hardcoded "
                        f"`'TODO:'` string literals — personal content appears to "
                        f"be embedded in the component instead of in "
                        f"`portfolio.json`"
                    ),
                    file="app/page.tsx",
                    suggested_next_task=(
                        "Move all personal portfolio content to "
                        "`src/content/portfolio.json` and render it from "
                        "`app/page.tsx` via the loader. Components should hold "
                        "layout, not content."
                    ),
                ))

    # 4. README.md mentions Studio / editing guidance.
    readme_path = project_path / "README.md"
    if not readme_path.is_file():
        issues.append(_make_issue(
            id_="docs.readme_missing.0",
            category=CATEGORY_DOCS,
            severity=SEVERITY_MUST_FIX,
            description="`README.md` is missing",
            file="README.md",
            suggested_next_task=(
                "Create `README.md` with a brief project description, "
                "instructions for running the Studio, and how to edit content "
                "via `src/content/portfolio.json`."
            ),
        ))
    else:
        try:
            readme = readme_path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            readme = ""
        mentions_studio = any(
            phrase in readme
            for phrase in (
                "studio",
                "portfolio.json",
                "edit your portfolio",
                "edit content",
                "edit the portfolio",
            )
        )
        if not mentions_studio:
            issues.append(_make_issue(
                id_="docs.readme_no_studio.0",
                category=CATEGORY_DOCS,
                severity=SEVERITY_SHOULD_FIX,
                description=(
                    "`README.md` does not mention the Studio or how to edit "
                    "portfolio content"
                ),
                file="README.md",
                suggested_next_task=(
                    "Add a `## Using the Studio` (or equivalent) section to "
                    "README.md explaining how to run `npm run dev`, open "
                    "`/studio`, and where content lives on disk."
                ),
            ))

    return issues


# ----- PR-style change summary -----

def build_change_summary(
    project_path: Path,
    diff: dict,
) -> dict:
    """Compact, PR-style summary of what changed during the loop. The full
    file lists are kept (truncated below in the rendered output); the
    risky-touched list is the actionable signal."""
    risky: list[dict] = []
    for f in (
        list(diff.get("added", []))
        + list(diff.get("changed", []))
        + list(diff.get("removed", []))
    ):
        match_key = ("/" + f).lower()
        for pattern in RISKY_PATH_PATTERNS:
            if pattern in match_key:
                risky.append({"file": f, "pattern": pattern})
                break

    # Read the current `dependencies` and `devDependencies` blocks for a
    # snapshot view. (Diffing pre vs post requires snapshotting the pkg
    # before Claude — out of scope for 9.6. We list what's there now.)
    deps_current: dict[str, dict] = {"dependencies": {}, "devDependencies": {}}
    pkg_path = project_path / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies"):
                d = pkg.get(section) or {}
                if isinstance(d, dict):
                    deps_current[section] = {k: str(v) for k, v in d.items()}
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "files_added": list(diff.get("added", [])),
        "files_modified": list(diff.get("changed", [])),
        "files_deleted": list(diff.get("removed", [])),
        "risky_touched": risky,
        "deps_current": deps_current,
    }


# ----- Review Agent (Stage 9.5) -----
#
# The review agent verifies what `hard criteria` and tests cannot:
# - functional: spin up the production build and curl key routes to confirm
#   `local-only` guards actually work, save/upload APIs are blocked, etc.
# - static:    light file-content checks (loader imports, README mentions
#   Studio, page.tsx doesn't carry obvious hardcoded TODO blocks).
# - quality:   a short Claude pass over the key files asking "does this
#   actually satisfy the goal?", returning a JSON issue list.
#
# Review never modifies the target project (it makes a portfolio.json
# backup before exercising POST APIs, restores it if the production guard
# is broken). It never deploys.

DEFAULT_REVIEW_MAX_TURNS = 5
DEFAULT_REVIEW_PORT = 3737  # not 3000 so we don't fight a running dev server
SERVER_READY_TIMEOUT_S = 30
HTTP_CHECK_TIMEOUT_S = 5

# Files the Claude quality review reads. Missing files are silently skipped.
REVIEW_KEY_FILES = (
    "README.md",
    "package.json",
    "app/page.tsx",
    "app/layout.tsx",
    "app/studio/page.tsx",
    "app/api/studio/load/route.ts",
    "app/api/studio/save/route.ts",
    "app/api/studio/upload/route.ts",
    "src/content/portfolio.json",
    "src/content/portfolio.schema.ts",
    "src/content/loadPortfolio.ts",
)

REVIEW_FILE_CHAR_LIMIT = 12000      # per-file truncation
REVIEW_TOTAL_CHAR_LIMIT = 80000     # total prompt budget for files


# ---- Static checks ----------------------------------------------------

def run_static_checks(project_path: Path) -> list[dict]:
    """Lightweight file / content sanity checks. Returns list of
    {check, pass, detail, heuristic}.
    """
    checks: list[dict] = []

    for f in (
        "src/content/portfolio.json",
        "src/content/portfolio.schema.ts",
        "src/content/loadPortfolio.ts",
    ):
        exists = (project_path / f).is_file()
        checks.append({
            "check": f"{f} exists",
            "pass": exists,
            "detail": "" if exists else "missing",
            "heuristic": False,
        })

    page_path = project_path / "app/page.tsx"
    if page_path.is_file():
        try:
            page_content = page_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            page_content = ""
        references_loader = any(
            marker in page_content
            for marker in (
                "loadPortfolio",
                "portfolio.json",
                "@/content/portfolio",
                "src/content/portfolio",
            )
        )
        checks.append({
            "check": "app/page.tsx references the portfolio loader / portfolio.json",
            "pass": references_loader,
            "detail": "" if references_loader else "no loadPortfolio / portfolio.json reference found",
            "heuristic": False,
        })

        # Heuristic: a content-driven page should not contain many literal
        # 'TODO:' string markers — those belong in portfolio.json, not in JSX.
        todo_literal_count = page_content.count('"TODO:') + page_content.count("'TODO:")
        no_hardcoded_todos = todo_literal_count < 3
        checks.append({
            "check": "app/page.tsx does not hardcode TODO content blocks (heuristic)",
            "pass": no_hardcoded_todos,
            "detail": (
                ""
                if no_hardcoded_todos
                else f"found {todo_literal_count} 'TODO:' string literals — likely hardcoded content"
            ),
            "heuristic": True,
        })
    else:
        checks.append({
            "check": "app/page.tsx exists",
            "pass": False,
            "detail": "missing",
            "heuristic": False,
        })

    readme_path = project_path / "README.md"
    if readme_path.is_file():
        try:
            readme = readme_path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            readme = ""
        mentions_studio = any(
            phrase in readme
            for phrase in (
                "studio",
                "portfolio.json",
                "edit your portfolio",
                "edit content",
                "edit the portfolio",
            )
        )
        checks.append({
            "check": "README mentions Studio or how to edit portfolio content",
            "pass": mentions_studio,
            "detail": "" if mentions_studio else "no Studio / editing guidance found in README",
            "heuristic": True,
        })
    else:
        checks.append({
            "check": "README.md exists",
            "pass": False,
            "detail": "missing",
            "heuristic": False,
        })

    return checks


# ---- Functional review: production server + HTTP probes --------------

def _start_production_server(project_path: Path, port: int, timeout: int) -> tuple[subprocess.Popen | None, bool, str]:
    """`npm run build` then `npm start` in background. Returns
    (Popen, ready, error_message). Caller must call _kill_server."""
    # Re-use _run_one for the build (process-group SIGKILL on timeout etc.).
    build_result = _run_one(["npm", "run", "build"], project_path, timeout=timeout)
    if build_result["exit_code"] != 0:
        err = _summarize_failure(build_result["stderr"], build_result["stdout"])
        return None, False, f"production build failed: {err}"

    env = {**os.environ, "PORT": str(port), "NODE_ENV": "production"}
    try:
        proc = subprocess.Popen(
            ["npm", "start"],
            cwd=str(project_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return None, False, f"failed to spawn npm start: {exc}"
    except OSError as exc:
        return None, False, f"failed to spawn npm start: {exc}"

    # Poll the root URL until the server answers (or we hit the deadline).
    deadline = time.time() + SERVER_READY_TIMEOUT_S
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            try:
                err_out = proc.stderr.read() if proc.stderr else ""
            except Exception:
                err_out = ""
            return None, False, f"npm start exited early (code {proc.returncode}): {err_out[:300]}"
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/", timeout=2) as response:
                _ = response.read(64)
                ready = True
                break
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(0.5)

    if not ready:
        _kill_server(proc)
        return None, False, f"production server did not become ready within {SERVER_READY_TIMEOUT_S}s"

    return proc, True, ""


def _kill_server(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    _kill_process_group(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _is_local_only_disabled_page(body: str) -> bool:
    low = body.lower()
    return any(
        phrase in low
        for phrase in (
            "local development only",
            "studio is only available",
            "not available in production",
            "disabled in production",
        )
    )


def _check_get(port: int, path: str) -> dict:
    url = f"http://localhost:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_CHECK_TIMEOUT_S) as response:
            body = response.read(2000).decode("utf-8", errors="ignore")
            return {"status": response.status, "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(2000).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return {"status": exc.code, "body": body, "error": None}
    except urllib.error.URLError as exc:
        return {"status": None, "body": "", "error": str(exc.reason)}
    except (OSError, TimeoutError) as exc:
        return {"status": None, "body": "", "error": str(exc)}


def _check_post(port: int, path: str, body_bytes: bytes = b"{}") -> dict:
    url = f"http://localhost:{port}{path}"
    req = urllib.request.Request(
        url,
        data=body_bytes,
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_CHECK_TIMEOUT_S) as response:
            body = response.read(2000).decode("utf-8", errors="ignore")
            return {"status": response.status, "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(2000).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return {"status": exc.code, "body": body, "error": None}
    except urllib.error.URLError as exc:
        return {"status": None, "body": "", "error": str(exc.reason)}
    except (OSError, TimeoutError) as exc:
        return {"status": None, "body": "", "error": str(exc)}


# ----- Stage 9.7: Visual Review (screenshots + multimodal Claude) -----
#
# The design rule (D-lite operating model): reviewer judges, builder changes,
# verifier verifies, human approves. So this module captures screenshots and
# asks Claude (a separate role-bound call from the quality reviewer) to
# compare them against the goal's design brief — it never modifies code.

# Routes captured by the visual review. The Node helper turns each into a
# `<slug>-<viewport>.png` filename via the same `routeSlug` logic.
SCREENSHOT_ROUTES = (
    {"url_path": "/",        "slug": "homepage"},
    {"url_path": "/studio",  "slug": "studio"},
)

# Stage 9.7 viewports (matches scripts/screenshot.mjs).
# Mobile is intentionally disabled here for now — the user asked to focus on
# desktop visual quality first. To re-enable mobile review, add:
#   {"name": "mobile",  "width": 390,  "height": 844},
# back into this tuple. The Node helper supports both already.
SCREENSHOT_VIEWPORTS_PW = (
    {"name": "desktop", "width": 1440, "height": 1200},
)

# Path to the Node screenshot helper (relative to TinyAgents root).
PLAYWRIGHT_SCRIPT = ROOT / "scripts" / "screenshot.mjs"
PLAYWRIGHT_NODE_MODULES = ROOT / "node_modules" / "playwright"


def _playwright_available() -> tuple[bool, str]:
    """Check that the Node helper + Playwright are installed. Returns
    (available, hint) — `hint` is empty when available, otherwise a
    human-readable explanation of what to install."""
    if not PLAYWRIGHT_SCRIPT.is_file():
        return False, f"missing helper script: {PLAYWRIGHT_SCRIPT.relative_to(ROOT)}"
    # Is Node on PATH?
    import shutil
    if shutil.which("node") is None:
        return False, (
            "Node.js is not installed (or not on PATH). Install Node 18+ from "
            "https://nodejs.org/ and re-run with --visual-review."
        )
    # Is Playwright installed?
    if not PLAYWRIGHT_NODE_MODULES.is_dir():
        return False, (
            "Playwright is not installed in TinyAgents. From the TinyAgents "
            "directory, run:\n"
            "    npm install\n"
            "    npx playwright install chromium\n"
            "Then re-run with --visual-review."
        )
    return True, ""


def capture_screenshots(
    project_path: Path,
    port: int,
    screenshots_dir: Path,
    build_timeout: int,
    capture_timeout: int = 120,
) -> dict:
    """Stage 9.7 visual-review screenshot capture.

    Build the project, start a production server, hand control to the Node
    Playwright helper which captures one full-page screenshot per (route,
    viewport) pair, kill the server. Returns:

      {
        "ran": bool,
        "error": str | None,
        "tool": str | None,   # "playwright"
        "screenshots": [{"name", "url_path", "width", "height", "path",
                         "captured": bool, "error": str | None}, ...],
      }

    `name` here is the per-image label, e.g. "homepage-desktop" — matches
    the Node helper's filename convention.
    """
    # Pre-compute the expected screenshot table so we have a stable shape
    # even if the helper fails halfway through.
    expected: list[dict] = []
    for route in SCREENSHOT_ROUTES:
        for vp in SCREENSHOT_VIEWPORTS_PW:
            expected.append({
                "name": f"{route['slug']}-{vp['name']}",
                "url_path": route["url_path"],
                "width": vp["width"],
                "height": vp["height"],
                # JPEG instead of PNG — see comment in scripts/screenshot.mjs
                # for why (full-page PNGs were exceeding `claude -p`'s
                # attachment size budget).
                "path": screenshots_dir / f"{route['slug']}-{vp['name']}.jpg",
                "captured": False,
                "error": None,
            })

    ok, hint = _playwright_available()
    if not ok:
        return {
            "ran": False,
            "error": (
                f"Playwright screenshot helper unavailable: {hint}\n"
                f"Visual review (Stage 9.7) needs Playwright to capture "
                f"full-page screenshots. The rest of the review is unaffected."
            ),
            "tool": None,
            "screenshots": expected,
        }

    screenshots_dir.mkdir(parents=True, exist_ok=True)

    proc, ready, err = _start_production_server(project_path, port, build_timeout)
    if not ready:
        return {
            "ran": False,
            "error": err,
            "tool": "playwright",
            "screenshots": expected,
        }

    print(f"    Production server ready at http://localhost:{port}")

    routes_arg = ",".join(r["url_path"] for r in SCREENSHOT_ROUTES)
    cmd = [
        "node",
        str(PLAYWRIGHT_SCRIPT),
        "--base-url", f"http://127.0.0.1:{port}",
        "--out", str(screenshots_dir),
        "--routes", routes_arg,
    ]
    helper_result: dict = {"stdout": "", "stderr": "", "returncode": None}
    helper_error: str | None = None
    try:
        try:
            run = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=capture_timeout,
                stdin=subprocess.DEVNULL,
            )
            helper_result = {
                "stdout": run.stdout or "",
                "stderr": run.stderr or "",
                "returncode": run.returncode,
            }
        except subprocess.TimeoutExpired as exc:
            helper_error = (
                f"Playwright helper timed out after {capture_timeout}s "
                f"(consider increasing --timeout)."
            )
            helper_result = {
                "stdout": (exc.stdout or "").decode("utf-8", errors="ignore") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                "stderr": (exc.stderr or "").decode("utf-8", errors="ignore") if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                "returncode": "timeout",
            }
        except (OSError, FileNotFoundError) as exc:
            helper_error = f"failed to spawn `node`: {exc}"
    finally:
        _kill_server(proc)

    # Parse the Node helper's JSON event stream from stdout.
    captured_by_path: dict[str, dict] = {}
    failures_by_path: dict[str, str] = {}
    for line in (helper_result["stdout"] or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("event")
        if kind == "captured":
            captured_by_path[event.get("path", "")] = event
        elif kind == "failed":
            failures_by_path[event.get("path", "")] = event.get("error", "(unknown)")
        elif kind == "fatal":
            helper_error = helper_error or f"helper fatal: {event.get('error', '(unknown)')}"

    # Reconcile the expected table with what actually landed on disk.
    for entry in expected:
        target_path = str(entry["path"])
        if entry["path"].is_file() and entry["path"].stat().st_size >= 1024:
            entry["captured"] = True
            entry["error"] = None
        else:
            entry["captured"] = False
            entry["error"] = failures_by_path.get(
                target_path,
                helper_error or "screenshot not produced (no event from helper)",
            )

    any_failed = any(not e["captured"] for e in expected)
    overall_error = None
    if any_failed:
        if helper_error:
            overall_error = helper_error
        else:
            failed_count = sum(1 for e in expected if not e["captured"])
            overall_error = (
                f"{failed_count} of {len(expected)} screenshots not captured "
                f"(see per-screenshot `error` fields)"
            )
    if helper_result["stderr"]:
        # Surface unexpected stderr (npm noise, deprecation warnings) but
        # don't treat it as fatal if screenshots actually landed.
        print(f"    [helper stderr] {helper_result['stderr'].strip()[:500]}")

    return {
        "ran": True,
        "error": overall_error,
        "tool": "playwright",
        "screenshots": expected,
    }


def run_functional_review(
    project_path: Path,
    goal: dict,
    port: int,
    timeout: int,
) -> dict:
    """Spin up `npm run build && npm start`, exercise the configured routes,
    kill the server. Always restores portfolio.json if a POST mutated it.

    Returns:
      {
        "ran": bool,
        "error": str | None,
        "checks": [...],
        "portfolio_modified": bool,
      }
    """
    review = goal.get("review", {})
    has_runtime_criteria = bool(
        review.get("production_allows_paths")
        or review.get("production_blocks_paths")
        or review.get("production_blocks_posts")
    )
    if not has_runtime_criteria:
        return {
            "ran": False,
            "error": "no runtime review criteria defined in goal file",
            "checks": [],
            "portfolio_modified": False,
        }

    # Defensive backup of portfolio.json so a misbehaving production server
    # that lets writes through is rolled back before we exit.
    portfolio_path = project_path / "src/content/portfolio.json"
    backup_bytes: bytes | None = None
    if portfolio_path.is_file():
        try:
            backup_bytes = portfolio_path.read_bytes()
        except OSError:
            backup_bytes = None

    print(f"  Starting production server on port {port} (this builds first)...")
    proc, ready, err = _start_production_server(project_path, port, timeout)
    if not ready:
        return {
            "ran": False,
            "error": err,
            "checks": [],
            "portfolio_modified": False,
        }

    print(f"  Production server ready at http://localhost:{port}")
    checks: list[dict] = []
    portfolio_modified = False
    try:
        for path in review.get("production_allows_paths", []):
            result = _check_get(port, path)
            ok = result["status"] == 200
            checks.append({
                "kind": "GET",
                "path": path,
                "expected": "200",
                "status": result["status"],
                "error": result["error"],
                "pass": ok,
                "detail": "" if ok else f"got status {result['status']}{(' — ' + result['error']) if result['error'] else ''}",
            })
        for path in review.get("production_blocks_paths", []):
            result = _check_get(port, path)
            ok = (result["status"] is not None and result["status"] != 200) or (
                result["status"] == 200 and _is_local_only_disabled_page(result["body"])
            )
            if result["status"] == 200 and _is_local_only_disabled_page(result["body"]):
                detail = "200 but body is the local-only disabled page (OK)"
            elif ok:
                detail = f"blocked (status {result['status']})"
            else:
                detail = f"NOT BLOCKED — production server returns working content (status {result['status']})"
            checks.append({
                "kind": "GET",
                "path": path,
                "expected": "blocked (non-200 or local-only disabled page)",
                "status": result["status"],
                "error": result["error"],
                "pass": ok,
                "detail": detail,
            })
        for path in review.get("production_blocks_posts", []):
            result = _check_post(port, path)
            ok = result["status"] is not None and result["status"] >= 400
            checks.append({
                "kind": "POST",
                "path": path,
                "expected": "≥400 (403 / 404 / 405)",
                "status": result["status"],
                "error": result["error"],
                "pass": ok,
                "detail": "" if ok else f"got status {result['status']} — production write may have succeeded",
            })
    finally:
        _kill_server(proc)

    # Did any POST actually mutate portfolio.json?
    if backup_bytes is not None and portfolio_path.is_file():
        try:
            after_bytes = portfolio_path.read_bytes()
            if after_bytes != backup_bytes:
                portfolio_modified = True
                # Always restore — review must not leave the project changed.
                portfolio_path.write_bytes(backup_bytes)
        except OSError:
            pass

    return {
        "ran": True,
        "error": None,
        "checks": checks,
        "portfolio_modified": portfolio_modified,
    }


# ---- Quality review: short Claude pass --------------------------------

def _collect_review_files(project_path: Path) -> list[dict]:
    files: list[dict] = []
    total = 0
    for rel in REVIEW_KEY_FILES:
        path = project_path / rel
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(content) > REVIEW_FILE_CHAR_LIMIT:
            content = content[:REVIEW_FILE_CHAR_LIMIT] + "\n... (truncated)\n"
        if total + len(content) > REVIEW_TOTAL_CHAR_LIMIT:
            break
        files.append({"path": rel, "content": content})
        total += len(content)
    return files


def _build_review_prompt(goal_text: str, files: list[dict], project_name: str) -> str:
    parts = [
        "You are reviewing an implementation of a project against its goal specification.",
        "Do NOT modify any code. Your only output is a JSON array of issues.",
        "",
        f"Project: {project_name}",
        "",
        "=== GOAL SPECIFICATION ===",
        goal_text.strip(),
        "",
        "=== KEY FILES ===",
    ]
    for f in files:
        parts.append("")
        parts.append(f"--- {f['path']} ---")
        parts.append(f["content"])
    parts.extend([
        "",
        "=== YOUR TASK ===",
        "Identify places where the implementation does NOT satisfy the goal spec.",
        "Focus on things that mechanical checks cannot catch:",
        "- Architectural drift from the goal's design direction",
        "- Subtle scope creep (features the goal did not ask for)",
        "- README claims that don't match the code",
        "- UX issues you can see from reading the JSX without rendering",
        "- Subjective product/design calls that need human judgment",
        "",
        "Deterministic checks for production guards, secrets, hardcoded content,",
        "and forbidden dependencies are already done elsewhere — focus on the rest.",
        "",
        "Output ONLY a JSON array (no markdown fences, no prose). Use [] if no issues.",
        "Schema:",
        '[{"severity":"blocker"|"must-fix"|"should-fix"|"nice-to-have"|"human-decision","category":"functional"|"scope"|"security"|"content"|"docs"|"design","description":"1-2 sentences","suggested_next_task":"actionable next-loop task title"}]',
        "",
        "Severity guidance:",
        "- blocker: implementation breaks a hard requirement; the product is unsafe or broken.",
        "- must-fix: goal requirement not satisfied (e.g. 'public page must read from JSON').",
        "- should-fix: quality degradation that doesn't break the product.",
        "- nice-to-have: polish observation, no real downside if skipped.",
        "- human-decision: subjective call the user must make (cannot be settled by reading code alone).",
    ])
    return "\n".join(parts)


def _parse_review_json(raw: str) -> tuple[list[dict], str | None]:
    if not raw:
        return [], "empty output"
    # Direct parse.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return _normalize_issues(parsed), None
    except (json.JSONDecodeError, TypeError):
        pass
    # Strip a leading ```json fence if present.
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n", "", cleaned)
    cleaned = re.sub(r"\n```\s*$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return _normalize_issues(parsed), None
    except (json.JSONDecodeError, TypeError):
        pass
    # Locate the outermost [...] block by greedy match across newlines.
    m = re.search(r"\[\s*\{.*\}\s*\]", raw, flags=re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                return _normalize_issues(parsed), None
        except (json.JSONDecodeError, TypeError):
            pass
    # Bare empty array.
    if re.search(r"^\s*\[\s*\]\s*$", raw, flags=re.MULTILINE):
        return [], None
    return [], "could not parse JSON from Claude output"


def _normalize_issues(parsed: list) -> list[dict]:
    """Normalize Claude-emitted issues to the 5-level severity model.

    Accepts both the new 5-level vocabulary and the legacy 3-level one
    (blocker / warning / info), mapping legacy values as follows:
      blocker -> blocker
      warning -> should-fix  (conservative: most warnings shouldn't block done)
      info    -> nice-to-have
    """
    legacy_map = {
        "warning": SEVERITY_SHOULD_FIX,
        "info": SEVERITY_NICE_TO_HAVE,
        # explicit 5-level passthroughs (also accept underscored variants)
        "blocker": SEVERITY_BLOCKER,
        "must-fix": SEVERITY_MUST_FIX,
        "must_fix": SEVERITY_MUST_FIX,
        "should-fix": SEVERITY_SHOULD_FIX,
        "should_fix": SEVERITY_SHOULD_FIX,
        "nice-to-have": SEVERITY_NICE_TO_HAVE,
        "nice_to_have": SEVERITY_NICE_TO_HAVE,
        "human-decision": SEVERITY_HUMAN_DECISION,
        "human_decision": SEVERITY_HUMAN_DECISION,
    }
    valid_categories = set(REVIEW_CATEGORIES) | {"design", "runtime"}
    # "runtime" gets coerced into "functional" since that's the canonical name.
    out: list[dict] = []
    for idx, item in enumerate(parsed):
        if not isinstance(item, dict):
            continue
        raw_sev = str(item.get("severity", "")).lower().strip()
        severity = legacy_map.get(raw_sev, SEVERITY_NICE_TO_HAVE)
        category = str(item.get("category", "scope")).lower().strip()
        if category == "runtime":
            category = CATEGORY_FUNCTIONAL
        if category not in valid_categories:
            category = CATEGORY_SCOPE
        description = str(item.get("description", "")).strip()
        suggested = str(item.get("suggested_next_task", "")).strip()
        if not description:
            continue
        out.append(_make_issue(
            id_=f"quality.{category}.{idx}",
            category=category,
            severity=severity,
            description=description,
            suggested_next_task=suggested,
            auto_generated=False,
        ))
    return out


def run_quality_review(
    project_path: Path,
    goal_text: str,
    max_turns: int,
    timeout: int,
    review_log_path: Path,
) -> dict:
    files = _collect_review_files(project_path)
    if not files:
        return {
            "ran": False,
            "issues": [],
            "raw": "",
            "parse_error": "no review files were readable in the project",
            "claude_exit": None,
        }
    prompt = _build_review_prompt(goal_text, files, project_path.name)
    cmd = ["claude", "-p", prompt, "--max-turns", str(max_turns)]
    redacted_argv = [
        "claude",
        "-p",
        f"<review prompt, {len(prompt)} chars, {len(files)} files>",
        "--max-turns",
        str(max_turns),
    ]
    print(f"  Invoking Claude for quality review (max-turns={max_turns}, files={len(files)})...")
    result = _tee_run(cmd, project_path, timeout=timeout)
    review_log_path.parent.mkdir(parents=True, exist_ok=True)
    review_log_path.write_text(
        _format_command_log({**result, "cmd": redacted_argv}),
        encoding="utf-8",
    )
    if result.get("spawn_error"):
        return {
            "ran": False,
            "issues": [],
            "raw": result.get("stderr", ""),
            "parse_error": "claude could not be spawned",
            "claude_exit": result["exit_code"],
        }
    issues, parse_error = _parse_review_json(result.get("stdout", ""))
    return {
        "ran": True,
        "issues": issues,
        "raw": result.get("stdout", ""),
        "parse_error": parse_error,
        "claude_exit": result["exit_code"],
    }


# ---- Stage 9.7 design preflight (lightweight source checks) -----------

def run_design_preflight(project_path: Path) -> list[dict]:
    """Cheap deterministic source checks that don't replace screenshot review
    but catch structural issues a screenshot can't see.

    Three checks, kept deliberately small:
      1. <h1> count in app/page.tsx (>1 = must-fix; 0 = should-fix)
      2. Responsive class count across app/**/*.tsx (0 = must-fix)
      3. src/components/studio/StudioClient.tsx line count (>500 = should-fix)

    These are PRE-flight signals. The real design verdict comes from the
    screenshot-based visual review below.
    """
    issues: list[dict] = []

    # 1. <h1> count across the homepage component tree.
    #
    # The check is "does the rendered homepage have exactly one <h1>?", not
    # "is the <h1> literally inside app/page.tsx?". A well-structured Next
    # app lives behind small section components (Hero, About, Projects…),
    # so the <h1> usually sits inside e.g. src/components/Hero.tsx. We
    # walk the imports out of app/page.tsx and sum <h1> matches across the
    # page file plus any imported components — that way the preflight
    # doesn't false-positive on the architecturally correct pattern.
    page_path = project_path / "app/page.tsx"
    if page_path.is_file():
        try:
            page_content = page_path.read_text(encoding="utf-8", errors="ignore")
            contents_to_scan = [page_content]
            # Follow imports like `from "@/src/components/Hero"` or
            # `from "@/src/components/studio/StudioClient"`. We accept .tsx
            # first (the common case) and fall back to .ts.
            import_re = re.compile(
                r'from\s+["\']@/(src/components/[A-Za-z0-9_/-]+)["\']'
            )
            for match in import_re.finditer(page_content):
                rel = match.group(1)
                for ext in (".tsx", ".ts"):
                    candidate = project_path / (rel + ext)
                    if candidate.is_file():
                        try:
                            contents_to_scan.append(
                                candidate.read_text(encoding="utf-8", errors="ignore")
                            )
                        except OSError:
                            pass
                        break
            h1_count = sum(
                len(re.findall(r"<h1[\s>]", c)) for c in contents_to_scan
            )
            if h1_count == 0:
                issues.append(_make_issue(
                    id_="design.preflight.no_h1",
                    category=CATEGORY_DESIGN,
                    severity=SEVERITY_SHOULD_FIX,
                    description="The homepage component tree (`app/page.tsx` and the components it imports from `src/components/`) contains no `<h1>` element — the page lacks a top-level heading.",
                    file="app/page.tsx",
                    suggested_next_task="Add a single `<h1>` to the hero section component so the page has a clear top-level heading for accessibility and visual hierarchy.",
                ))
            elif h1_count > 1:
                issues.append(_make_issue(
                    id_="design.preflight.multiple_h1",
                    category=CATEGORY_DESIGN,
                    severity=SEVERITY_MUST_FIX,
                    description=f"The homepage component tree contains {h1_count} `<h1>` elements — there should be exactly one top-level heading per page.",
                    file="app/page.tsx",
                    suggested_next_task="Keep only the hero's `<h1>`; convert other `<h1>` tags across the page tree to `<h2>`/`<h3>` so the heading hierarchy is correct.",
                ))
        except OSError:
            pass

    # 2. Responsive class presence across all .tsx in app/
    app_dir = project_path / "app"
    if app_dir.is_dir():
        total_responsive_classes = 0
        tsx_files_checked = 0
        for tsx_path in app_dir.rglob("*.tsx"):
            try:
                content = tsx_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            tsx_files_checked += 1
            total_responsive_classes += (
                len(re.findall(r"\b(?:sm|md|lg|xl|2xl):[a-z\[]", content))
            )
        if tsx_files_checked > 0 and total_responsive_classes == 0:
            issues.append(_make_issue(
                id_="design.preflight.no_responsive",
                category=CATEGORY_DESIGN,
                severity=SEVERITY_MUST_FIX,
                description=(
                    f"No Tailwind responsive prefixes (`sm:` / `md:` / `lg:` / `xl:`) found across "
                    f"{tsx_files_checked} .tsx file(s) in `app/`. The layout has no responsive behavior."
                ),
                suggested_next_task="Add responsive Tailwind prefixes (at minimum `md:` and `lg:`) to hero, project grid, and Studio layout so the page adapts to mobile and tablet widths.",
            ))

    # 3. StudioClient size (proxy for "is the Studio one giant monolithic component")
    studio_client = project_path / "src/components/studio/StudioClient.tsx"
    if studio_client.is_file():
        try:
            line_count = sum(1 for _ in studio_client.read_text(encoding="utf-8", errors="ignore").splitlines())
            if line_count > 500:
                issues.append(_make_issue(
                    id_="design.preflight.studio_monolithic",
                    category=CATEGORY_DESIGN,
                    severity=SEVERITY_SHOULD_FIX,
                    description=(
                        f"`StudioClient.tsx` is {line_count} lines — likely a monolithic component. "
                        f"The goal recommends per-section components (`ProfileForm`, `ProjectsEditor`, "
                        f"`SkillsEditor`, `WorkPrinciplesEditor`, `ContactEditor`)."
                    ),
                    file="src/components/studio/StudioClient.tsx",
                    suggested_next_task=(
                        "Split StudioClient.tsx into per-section components living in "
                        "src/components/studio/: ProfileForm, ProjectsEditor, ProjectRow, "
                        "SkillsEditor, WorkPrinciplesEditor, ContactEditor, ImageUpload, "
                        "PreviewPane, SaveBar."
                    ),
                ))
        except OSError:
            pass

    return issues


# ---- Stage 9.7 design brief extraction --------------------------------

# Sections we try to pull from the goal markdown to feed to the visual
# reviewer. We accept either exact or case-insensitive matches.
_DESIGN_BRIEF_SECTIONS = (
    r"^design goal",
    r"^design research instructions",
    r"^visual requirements",
    r"^visual direction",
    r"^studio requirements",
    r"^public portfolio requirements",
    r"^content rules",
    r"^soft criteria",
)


def _extract_design_brief(goal_text: str) -> str:
    """Pull the design-relevant sections out of the goal markdown. Returns a
    single concatenated string suitable for feeding to the visual reviewer.

    If no matching sections are found, returns the whole goal text trimmed —
    better to over-include than to send Claude an empty brief.
    """
    blocks: list[str] = []
    for heading_pattern in _DESIGN_BRIEF_SECTIONS:
        section = _extract_section(goal_text, heading_pattern)
        if section:
            heading_match = re.search(
                heading_pattern, goal_text, flags=re.IGNORECASE | re.MULTILINE
            )
            heading_text = heading_match.group(0).strip() if heading_match else heading_pattern.lstrip("^").title()
            blocks.append(f"## {heading_text}\n\n{section}")
    if not blocks:
        return _strip_leading_h1(goal_text).strip()
    return "\n\n".join(blocks)


# ---- Stage 9.7 visual review (screenshot + multimodal Claude) ---------

def _build_visual_review_prompt(
    design_brief: str,
    screenshot_results: list[dict],
) -> str:
    """Stage 9.7 visual design critic prompt.

    Personality: senior product designer + design systems reviewer. Not a
    bug-finder, not a code linter. The job is to look at the rendered
    screenshots and give an honest design opinion against the goal's
    Visual Direction.

    Screenshots are attached via Claude Code CLI's `@/abs/path.png` syntax.
    Output is a strict JSON array — no markdown fences, no prose.
    """
    captured = [s for s in screenshot_results if s.get("captured")]

    parts: list[str] = [
        "You are a senior product designer and design systems reviewer.",
        "",
        "You are reviewing rendered screenshots of a local Portfolio Builder",
        "Studio and the public portfolio it produces. Your job is to judge",
        "visual quality, UX clarity, and alignment with the goal file's",
        "Visual Direction / Design Goal / Design Requirements.",
        "",
        "Constraints (important):",
        "- Do NOT rewrite code. Do NOT propose backend architecture.",
        "- Do NOT focus on security unless it directly affects UX.",
        "- Do NOT invent details that aren't visible in the screenshots.",
        "- If something can only be judged interactively, say so via the",
        "  `requires_rendered_review` flag — don't pretend you can tell.",
        "- Each issue must reference what you actually see in a specific",
        "  screenshot, not the source code (you don't see source).",
        "",
        "=== DESIGN BRIEF (extracted from the goal spec) ===",
        design_brief,
        "",
        "=== SCREENSHOTS (rendered output) ===",
    ]
    if not captured:
        parts.append(
            "(no screenshots were captured — return [] and a single human-decision "
            "item noting that the visual review needs screenshots before it can "
            "give a verdict.)"
        )
    else:
        for s in captured:
            parts.append("")
            parts.append(
                f"**{s['name']}** ({s['width']}×{s['height']}, route `{s['url_path']}`):"
            )
            parts.append(f"@{s['path']}")
    parts.extend([
        "",
        "=== WHAT TO ASSESS ===",
        "Walk through each of these explicitly. Don't skip — say `cannot tell`",
        "if a screenshot doesn't show enough.",
        "  1. Overall visual quality — does this look like a polished product,",
        "     or a generic Tailwind landing page?",
        "  2. Visual hierarchy — does the eye know where to go first?",
        "  3. Spacing rhythm — is the spacing consistent across sections?",
        "  4. Typography hierarchy — h1 / h2 / body distinct? sizes intentional?",
        "  5. Color palette — intentional, technical, premium? or default Tailwind blue?",
        "  6. Contrast — readable text on every surface?",
        "  7. Project card polish — feel like real product cards or template blocks?",
        "  8. Form layout (Studio) — easy to scan, grouped, not a wall of inputs?",
        "  9. Studio editor usability — clear add/delete/reorder affordances?",
        " 10. Preview panel usability — useful, prominent enough?",
        " 11. Empty / placeholder states — graceful with TODO content?",
        " 12. Mobile usability — usable AND coherent (not just non-broken)?",
        " 13. Alignment with the Visual Direction — for each Visual Direction",
        "     line you can evaluate, is it implemented, partial, missing?",
        " 14. Fit for an AI Engineer / full-stack developer audience.",
        "",
        "=== OUTPUT ===",
        "Output ONLY a JSON array (no markdown fences, no preamble, no commentary).",
        "Use [] if the rendered output already looks great.",
        "",
        "Schema:",
        "[{",
        '  "severity": "blocker"|"must-fix"|"should-fix"|"nice-to-have"|"human-decision",',
        '  "category": "design"|"ux"|"layout"|"visual-direction"|"responsive"|"studio-ux"|"content-hierarchy"|"mobile"|"polish",',
        '  "target": "/"|"/studio"|"global",',
        '  "viewport": "desktop"|"mobile"|"both"|"unknown",',
        '  "description": "specific observation tied to a Visual Direction line or a clear UX principle",',
        '  "evidence": "what you actually see in the screenshot (be concrete)",',
        '  "suggested_next_task": "an actionable polish task the implementer can run next loop",',
        '  "requires_rendered_review": false',
        "}]",
        "",
        "Severity guidance (use sparingly — most issues should be should-fix or nice-to-have):",
        '- "blocker": UI is unusable or broken (e.g. content cut off the viewport,',
        "  unreadable contrast, page doesn't render at all). Rare.",
        '- "must-fix": serious UX/design problem that prevents the product from',
        "  feeling polished (e.g. Studio form is a dense unscannable wall).",
        '- "should-fix": meaningful polish (e.g. hero lacks identity, spacing',
        '  inconsistent). Does NOT block done by default.',
        '- "nice-to-have": optional refinement (e.g. subtle animation, gradient',
        "  accent). Never blocks done.",
        '- "human-decision": subjective taste call the user should make',
        "  (e.g. emerald vs cyan accent, dark vs light palette).",
        "",
        "Examples of good issue shapes:",
        '- "Studio editor at mobile (390px) compresses the project card form to a',
        "   single dense column — labels and inputs alternate without grouping,",
        '   producing a wall of fields. Goal says \"feels like a developer tool\"',
        "   — this currently reads like a generic admin form.\" target=/studio,",
        "  viewport=mobile, category=studio-ux, severity=must-fix.",
        '- "Hero (homepage-desktop) uses default Tailwind blue (text-blue-500) for',
        "   the role badge. Visual Direction asks for a technical palette without",
        '   the generic Tailwind feel.\" target=/, viewport=desktop,',
        "  category=visual-direction, severity=should-fix.",
    ])
    return "\n".join(parts)


def run_visual_review(
    project_path: Path,
    goal_text: str,
    screenshot_results: list[dict],
    max_turns: int,
    timeout: int,
    review_log_path: Path,
) -> dict:
    """Send the screenshots + design brief to Claude as a separate role-bound
    review call. Parses the JSON response into normalized issues. Returns:

      {
        "ran": bool,
        "issues": [...],   # normalized via _normalize_issues
        "raw": str,
        "parse_error": str | None,
        "claude_exit": int | None,
        "screenshots_used": list[str],   # names of the screenshots actually attached
      }
    """
    captured = [s for s in screenshot_results if s.get("captured")]
    if not captured:
        return {
            "ran": False,
            "issues": [],
            "raw": "",
            "parse_error": "no screenshots were captured — visual review skipped",
            "claude_exit": None,
            "screenshots_used": [],
        }

    design_brief = _extract_design_brief(goal_text)

    # `claude -p` empirically only loads ~2 of N attached PNGs when N is too
    # large (verified: with 4 screenshots in one prompt, Claude reported it
    # only saw the last 2). Workaround: split into one Claude call per
    # screenshot. Each call carries ONE image — guaranteed within the CLI's
    # attachment budget. Aggregate the per-call JSON outputs at the end.
    valid_subcategories = (
        "design", "ux", "layout", "visual-direction", "responsive",
        "studio-ux", "content-hierarchy", "mobile", "polish",
    )
    valid_targets = ("/", "/studio", "global")
    valid_viewports = ("desktop", "mobile", "both", "unknown")

    all_issues: list[dict] = []
    all_raw_chunks: list[str] = []
    parse_errors: list[str] = []
    last_exit_code: int | None = None
    screenshots_used = [s["name"] for s in captured]
    log_buffer: list[str] = []
    review_log_path.parent.mkdir(parents=True, exist_ok=True)

    for screen in captured:
        prompt = _build_visual_review_prompt(design_brief, [screen])
        cmd = ["claude", "-p", prompt, "--max-turns", str(max_turns)]
        redacted_argv = [
            "claude",
            "-p",
            (
                f"<visual-review prompt for {screen['name']}, "
                f"{len(prompt)} chars, 1 screenshot>"
            ),
            "--max-turns",
            str(max_turns),
        ]
        print(
            f"    Invoking Claude for visual review of {screen['name']} "
            f"(max-turns={max_turns})..."
        )
        result = _tee_run(cmd, project_path, timeout=timeout)
        log_buffer.append(
            f"\n=== Visual review call: {screen['name']} "
            f"(route {screen['url_path']}) ===\n\n"
        )
        log_buffer.append(_format_command_log({**result, "cmd": redacted_argv}))

        if result.get("spawn_error"):
            review_log_path.write_text("".join(log_buffer), encoding="utf-8")
            return {
                "ran": False,
                "issues": [],
                "raw": result.get("stderr", ""),
                "parse_error": "claude could not be spawned for visual review",
                "claude_exit": result["exit_code"],
                "screenshots_used": screenshots_used,
            }

        last_exit_code = result["exit_code"]
        raw = result.get("stdout", "") or ""
        all_raw_chunks.append(f"--- {screen['name']} ---\n{raw}")

        issues, parse_error = _parse_review_json(raw)
        if parse_error:
            parse_errors.append(f"{screen['name']}: {parse_error}")

        # Recover extras (subcategory, target, viewport, evidence,
        # requires_rendered_review) from the raw stdout. These rich fields
        # are dropped by the generic `_normalize_issues` so we walk the raw
        # JSON one more time and merge by positional index.
        extras: list[dict] = []
        if raw:
            for stripped in (
                raw.strip(),
                re.sub(r"^```(?:json)?\s*\n", "", raw.strip()),
            ):
                try:
                    arr = json.loads(stripped)
                    if isinstance(arr, list):
                        extras = [x for x in arr if isinstance(x, dict)]
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

        for i, issue in enumerate(issues):
            # Pin pipeline category to "design" so issues route correctly.
            issue["category"] = CATEGORY_DESIGN
            if i >= len(extras):
                # Fall back to the screenshot's own metadata so target /
                # viewport are still populated even if Claude omitted them.
                issue.setdefault("subcategory", "design")
                issue.setdefault("target", screen["url_path"])
                issue.setdefault(
                    "viewport",
                    "desktop" if "desktop" in screen["name"] else
                    "mobile" if "mobile" in screen["name"] else "unknown",
                )
                issue.setdefault("requires_rendered_review", False)
                continue
            raw_extra = extras[i]
            sub = str(raw_extra.get("category", "design")).lower().strip()
            if sub not in valid_subcategories:
                sub = "design"
            target = str(raw_extra.get("target", screen["url_path"])).strip()
            if target not in valid_targets:
                target = screen["url_path"] if screen["url_path"] in valid_targets else "global"
            viewport = str(raw_extra.get("viewport", "unknown")).lower().strip()
            if viewport not in valid_viewports:
                viewport = "desktop" if "desktop" in screen["name"] else "mobile" if "mobile" in screen["name"] else "unknown"
            evidence_text = str(raw_extra.get("evidence", "")).strip()
            rr = bool(raw_extra.get("requires_rendered_review", False))
            issue["subcategory"] = sub
            issue["target"] = target
            issue["viewport"] = viewport
            issue["requires_rendered_review"] = rr
            if evidence_text:
                existing_ev = issue.get("evidence") or {}
                if isinstance(existing_ev, dict):
                    existing_ev["screenshot_note"] = evidence_text
                    existing_ev["target"] = target
                    existing_ev["viewport"] = viewport
                    existing_ev["screenshot"] = screen["name"]
                    issue["evidence"] = existing_ev

        all_issues.extend(issues)

    review_log_path.write_text("".join(log_buffer), encoding="utf-8")

    combined_raw = "\n\n".join(all_raw_chunks)
    combined_parse_error = "; ".join(parse_errors) if parse_errors else None

    return {
        "ran": True,
        "issues": all_issues,
        "raw": combined_raw,
        "parse_error": combined_parse_error,
        "claude_exit": last_exit_code,
        "screenshots_used": screenshots_used,
    }


# ---- Combining functional + static + quality into one verdict ---------

def classify_review_decision(
    functional: dict,
    scope_issues: list[dict],
    security_issues: list[dict],
    content_docs_issues: list[dict],
    quality: dict,
    design_preflight_issues: list[dict] | None = None,
    visual: dict | None = None,
    screenshots: dict | None = None,
) -> dict:
    """Stage 9.6 review aggregator. Combines all categories into a single
    decision dict suitable for review-decision.json + cmd_auto's state
    machine. Returns:

      {
        "decision_state": "done" | "done-with-warnings" | "continue-fix"
                          | "needs-human-feedback" | "unavailable",
        "all_issues": [...],                 # all issues, all categories
        "by_category": {cat: {ran, issues}},
        "counts": {severity: N for severity in ALL_SEVERITIES},
        "suggested_next_task": "...",
        "suggested_next_task_source": "...",
        "human_questions_count": N,
        "publishable": bool,
      }

    Severity-driven decision rules (per Stage 9.6 spec):
      blocker > 0  OR  must-fix > 0  -> continue-fix
      else if human-decision > 0     -> needs-human-feedback
      else if should-fix > 0         -> done-with-warnings
      else                           -> done
    """
    all_issues: list[dict] = []

    # Functional review check failures become blockers.
    if functional.get("ran"):
        for idx, c in enumerate(functional["checks"]):
            if c["pass"]:
                continue
            all_issues.append(_make_issue(
                id_=f"functional.{c['kind'].lower()}.{idx}",
                category=CATEGORY_FUNCTIONAL,
                severity=SEVERITY_BLOCKER,
                description=f"{c['kind']} {c['path']}: {c['detail']}",
                file=None,
                snippet=c.get("detail"),
                suggested_next_task=(
                    f"Fix production guard for {c['kind']} {c['path']} "
                    f"(expected {c['expected']}, got status {c['status']})"
                ),
            ))
        if functional.get("portfolio_modified"):
            all_issues.append(_make_issue(
                id_="functional.portfolio_mutated.0",
                category=CATEGORY_SECURITY,  # mutation in production IS a security issue
                severity=SEVERITY_BLOCKER,
                description=(
                    "`portfolio.json` was modified by a POST to a production "
                    "API route — production write-guard is broken (the file "
                    "was restored from backup)."
                ),
                file="src/content/portfolio.json",
                suggested_next_task=(
                    "Add `NODE_ENV === 'production'` checks to "
                    "`/api/studio/save` and `/api/studio/upload` so writes "
                    "are refused on deployed instances."
                ),
            ))

    all_issues.extend(scope_issues)
    all_issues.extend(security_issues)
    all_issues.extend(content_docs_issues)

    # Stage 9.7: design preflight (deterministic, cheap source checks) and
    # visual review (multimodal Claude looking at screenshots).
    if design_preflight_issues:
        all_issues.extend(design_preflight_issues)
    if visual and visual.get("ran"):
        all_issues.extend(visual.get("issues", []))

    if quality.get("ran"):
        # Claude issues already have the canonical schema thanks to
        # `_normalize_issues` returning `_make_issue` shapes.
        all_issues.extend(quality.get("issues", []))

    # Severity counts.
    counts = {s: 0 for s in ALL_SEVERITIES}
    for issue in all_issues:
        sev = issue.get("severity", SEVERITY_NICE_TO_HAVE)
        if sev in counts:
            counts[sev] += 1
        else:
            counts[SEVERITY_NICE_TO_HAVE] += 1

    # Group by category.
    by_category: dict[str, dict] = {
        cat: {"ran": True, "issues": []}
        for cat in REVIEW_CATEGORIES
    }
    by_category[CATEGORY_FUNCTIONAL]["ran"] = bool(functional.get("ran"))
    by_category[CATEGORY_FUNCTIONAL]["summary"] = {
        "checks_total": len(functional.get("checks", [])),
        "checks_passed": sum(1 for c in functional.get("checks", []) if c.get("pass")),
        "portfolio_modified": functional.get("portfolio_modified", False),
        "skipped_reason": (
            functional.get("error") if not functional.get("ran") else None
        ),
    }
    # Stage 9.7 design summary: did the screenshot pipeline run, how many
    # screenshots, were any not captured.
    visual_ran = bool(visual and visual.get("ran"))
    screenshots_data = screenshots or {}
    screenshots_list = screenshots_data.get("screenshots", []) if screenshots_data else []
    captured_count = sum(1 for s in screenshots_list if s.get("captured"))
    by_category[CATEGORY_DESIGN]["ran"] = bool(design_preflight_issues is not None or visual_ran)
    by_category[CATEGORY_DESIGN]["summary"] = {
        "preflight_checks_ran": design_preflight_issues is not None,
        "visual_review_ran": visual_ran,
        "screenshots_attempted": len(screenshots_list),
        "screenshots_captured": captured_count,
        "skipped_reason": (
            (screenshots_data.get("error") if not screenshots_data.get("ran", False) else None)
            if screenshots_data else "screenshot capture not attempted"
        ),
    }
    for issue in all_issues:
        cat = issue.get("category", CATEGORY_SCOPE)
        if cat not in by_category:
            cat = CATEGORY_SCOPE
        by_category[cat]["issues"].append(issue)

    # Decide top-level state. Deterministic categories (scope / security /
    # content / docs) always run inside run_review, so an empty issue list
    # is a real "done" signal — not an "unavailable" one. The functional
    # and quality categories' `ran` flags are recorded in the JSON for
    # diagnostic but don't change the state.
    if counts[SEVERITY_BLOCKER] > 0 or counts[SEVERITY_MUST_FIX] > 0:
        state = "continue-fix"
    elif counts[SEVERITY_HUMAN_DECISION] > 0:
        state = "needs-human-feedback"
    elif counts[SEVERITY_SHOULD_FIX] > 0:
        state = "done-with-warnings"
    else:
        state = "done"

    # Suggested next task — pick highest-priority issue with a task line.
    suggested = ""
    suggested_source = ""
    sorted_issues = sorted(
        all_issues, key=lambda i: SEVERITY_PRIORITY.get(i.get("severity", ""), 99)
    )
    for issue in sorted_issues:
        if issue.get("suggested_next_task"):
            suggested = issue["suggested_next_task"]
            suggested_source = issue.get("id", "")
            break

    return {
        "decision_state": state,
        "all_issues": all_issues,
        "by_category": by_category,
        "counts": counts,
        "suggested_next_task": suggested,
        "suggested_next_task_source": suggested_source,
        "human_questions_count": counts[SEVERITY_HUMAN_DECISION],
        "publishable": (state == "done"),
    }


# ---- Review report (review-report.md) ---------------------------------

def _render_change_summary_md(change_summary: dict) -> list[str]:
    """Render the PR-style change summary as Markdown lines."""
    lines: list[str] = []
    add = change_summary.get("files_added", [])
    mod = change_summary.get("files_modified", [])
    rem = change_summary.get("files_deleted", [])
    risky = change_summary.get("risky_touched", [])

    def _short_list(label: str, items: list[str], max_show: int = 20) -> None:
        if not items:
            lines.append(f"- {label}: _(none)_")
            return
        lines.append(f"- {label} ({len(items)}):")
        for f in items[:max_show]:
            lines.append(f"  - `{f}`")
        if len(items) > max_show:
            lines.append(f"  - … and {len(items) - max_show} more")

    _short_list("Files added", add)
    _short_list("Files modified", mod)
    _short_list("Files deleted", rem)
    if risky:
        lines.append(f"- Risky-path touches ({len(risky)}):")
        for entry in risky:
            lines.append(
                f"  - `{entry['file']}` (matched `{entry['pattern']}`)"
            )
    else:
        lines.append("- Risky-path touches: _(none)_")
    return lines


def _render_review_report(
    project_path: Path,
    goal: dict,
    goal_path: Path,
    functional: dict,
    quality: dict,
    decision: dict,
    change_summary: dict | None,
) -> str:
    """Render the Stage 9.6 multi-category review report from the decision
    dict. `change_summary` is optional; when supplied (from auto), a
    PR-style summary block is added at the top."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Review Report")
    lines.append("")
    lines.append(f"_Generated by `tiny_agents.py review` on {generated_at}._")
    lines.append("")

    # Summary block
    try:
        goal_rel = goal_path.relative_to(ROOT)
        goal_label = f"`{goal_rel}`"
    except ValueError:
        goal_label = f"`{goal_path}`"
    counts = decision["counts"]
    lines.append("## Summary")
    lines.append(f"- Project: `{project_path}`")
    lines.append(f"- Goal: **{goal['name']}** ({goal_label})")
    lines.append(f"- Decision state: **{decision['decision_state']}**")
    lines.append(
        f"- Counts: blocker {counts[SEVERITY_BLOCKER]} / "
        f"must-fix {counts[SEVERITY_MUST_FIX]} / "
        f"should-fix {counts[SEVERITY_SHOULD_FIX]} / "
        f"nice-to-have {counts[SEVERITY_NICE_TO_HAVE]} / "
        f"human-decision {counts[SEVERITY_HUMAN_DECISION]}"
    )
    lines.append(f"- Publishable: {'yes' if decision['publishable'] else 'no'}")
    lines.append(f"- Generated: {generated_at}")
    lines.append("")

    # PR-style change summary (only when called from auto with diff in hand).
    if change_summary is not None:
        lines.append("## Change Summary (PR-style)")
        lines.extend(_render_change_summary_md(change_summary))
        lines.append("")

    # Per-category breakdown
    lines.append("## Categories")
    for cat in REVIEW_CATEGORIES:
        cat_data = decision["by_category"].get(cat, {})
        cat_issues = cat_data.get("issues", [])
        ran = cat_data.get("ran", False)
        title = cat.replace("_", " ").title()
        lines.append("")
        lines.append(f"### {title}")
        if not ran:
            reason = ""
            if cat == CATEGORY_FUNCTIONAL:
                summary = cat_data.get("summary") or {}
                reason = summary.get("skipped_reason") or ""
            lines.append(f"_(skipped{(': ' + reason) if reason else ''})_")
            continue
        if cat == CATEGORY_FUNCTIONAL:
            summary = cat_data.get("summary") or {}
            for check in functional.get("checks", []):
                mark = "[x]" if check["pass"] else "[ ]"
                status = check["status"] if check["status"] is not None else "no-response"
                line = f"- {mark} **{check['kind']} {check['path']}** → status `{status}`"
                if check["detail"]:
                    line += f" — {check['detail']}"
                lines.append(line)
            if functional.get("portfolio_modified"):
                lines.append(
                    "- [ ] **portfolio.json was modified by a production POST** "
                    "(restored from backup)."
                )
            elif (functional.get("checks") or []):
                lines.append(
                    "- [x] portfolio.json unchanged after POST tests."
                )
        if cat == CATEGORY_DESIGN:
            summary = cat_data.get("summary") or {}
            cap = summary.get("screenshots_captured", 0)
            att = summary.get("screenshots_attempted", 0)
            if att > 0:
                lines.append(
                    f"- Screenshots captured: **{cap} of {att}** "
                    f"(see `artifacts/screenshots/`)"
                )
            else:
                reason = summary.get("skipped_reason") or "no screenshots attempted"
                lines.append(f"- Screenshots: _(none captured — {reason})_")
            if summary.get("visual_review_ran"):
                lines.append("- Visual review (multimodal Claude): **ran**")
            else:
                lines.append("- Visual review (multimodal Claude): _(skipped)_")
            if summary.get("preflight_checks_ran"):
                lines.append("- Source preflight (heading hierarchy / responsive / monolithic detection): **ran**")
        if not cat_issues:
            lines.append("_(no issues)_")
            continue
        for issue in cat_issues:
            sev = issue["severity"]
            line = f"- **[{sev}]** {issue['description']}"
            ev = issue.get("evidence") or {}
            if ev.get("file"):
                line += f"  \n  📄 `{ev['file']}`"
                if ev.get("line"):
                    line += f":{ev['line']}"
            lines.append(line)
            if issue.get("suggested_next_task"):
                lines.append(f"  - Suggested next task: {issue['suggested_next_task']}")
    lines.append("")

    # Quality review raw output (only if Claude failed to produce JSON).
    if quality.get("ran") is False or quality.get("parse_error"):
        lines.append("## Quality Review (Claude) — Diagnostic")
        if quality.get("ran") is False:
            lines.append(
                f"_(unavailable: {quality.get('parse_error', 'unknown')})_"
            )
        elif quality.get("parse_error"):
            lines.append(
                f"_(could not parse JSON: {quality['parse_error']})_"
            )
        if quality.get("raw"):
            lines.append("")
            lines.append("Raw Claude output:")
            lines.append("```")
            lines.append(quality["raw"][:4000])
            lines.append("```")
        lines.append("")

    # Issues by severity
    lines.append("## Issues by Severity")
    for severity in ALL_SEVERITIES:
        items = [i for i in decision["all_issues"] if i.get("severity") == severity]
        nice_label = severity.replace("-", "-").title()
        lines.append("")
        lines.append(f"### {nice_label}")
        if not items:
            lines.append("_(none)_")
            continue
        for issue in items:
            lines.append(
                f"- **[{issue['category']}]** {issue['description']}"
            )
            if issue.get("suggested_next_task"):
                lines.append(
                    f"  - Suggested next task: {issue['suggested_next_task']}"
                )
    lines.append("")

    # Suggested next task
    lines.append("## Suggested Next Task")
    if decision.get("suggested_next_task"):
        lines.append(f"- {decision['suggested_next_task']}")
        if decision.get("suggested_next_task_source"):
            lines.append(f"  - Source: `{decision['suggested_next_task_source']}`")
    else:
        lines.append("- (no actionable next task — review is clean or only nice-to-have items remain)")
    lines.append("")

    # Notes
    lines.append("## Notes")
    lines.append("- Review does not edit code.")
    lines.append("- Review does not deploy anything.")
    lines.append("- Review does not auto-fix.")
    lines.append(
        "- Review backs up `src/content/portfolio.json` before POST probes and "
        "restores it if the production guard let the write through."
    )
    lines.append(
        "- See `review-decision.json` for the machine-readable version, and "
        "`human-questions.md` if any human-decision items were raised."
    )
    lines.append("")
    return "\n".join(lines)


def _render_review_decision_json(
    project_path: Path,
    goal: dict,
    goal_path: Path,
    decision: dict,
    change_summary: dict | None,
    loop_path: Path | None,
) -> str:
    """Serialize the review decision into JSON."""
    try:
        goal_rel = str(goal_path.relative_to(ROOT))
    except ValueError:
        goal_rel = str(goal_path)
    loop_rel = None
    if loop_path is not None:
        try:
            loop_rel = str(loop_path.relative_to(ROOT))
        except ValueError:
            loop_rel = str(loop_path)
    payload = {
        "schema_version": "1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "goal_file": goal_rel,
        "goal_name": goal.get("name", ""),
        "project_path": str(project_path),
        "loop_path": loop_rel,
        "decision": decision["decision_state"],
        "publishable": decision["publishable"],
        "counts": decision["counts"],
        "suggested_next_task": decision.get("suggested_next_task", ""),
        "suggested_next_task_source": decision.get("suggested_next_task_source", ""),
        "human_questions_count": decision.get("human_questions_count", 0),
        "categories": {},
        "change_summary": change_summary,
    }
    for cat, cat_data in decision["by_category"].items():
        payload["categories"][cat] = {
            "ran": cat_data.get("ran", False),
            "summary": cat_data.get("summary"),
            "issues": cat_data.get("issues", []),
        }
    return json.dumps(payload, indent=2) + "\n"


def _render_design_review_md(
    review_dir: Path,
    goal: dict,
    screenshots: dict,
    visual: dict,
    design_preflight_issues: list[dict],
) -> str:
    """Standalone Markdown report focused only on the visual design verdict.
    The combined review-report.md still includes all categories, but this
    file is convenient when you only want to read the design story."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Design Review")
    lines.append("")
    lines.append(f"_Generated by `tiny_agents.py review` on {generated_at}._")
    lines.append("")
    lines.append(f"## Goal: {goal.get('name', '(unnamed)')}")
    lines.append("")

    lines.append("## Screenshots")
    if not screenshots.get("ran"):
        lines.append(f"_(screenshot capture was skipped: {screenshots.get('error')})_")
    else:
        for s in screenshots.get("screenshots", []):
            if s.get("captured"):
                try:
                    rel = s["path"].relative_to(review_dir)
                    rel_str = str(rel)
                except (ValueError, AttributeError):
                    rel_str = str(s["path"])
                lines.append(
                    f"- **{s['name']}** ({s['width']}×{s['height']}, "
                    f"`{s['url_path']}`) — `{rel_str}`"
                )
                lines.append(f"  ![{s['name']}]({rel_str})")
            else:
                err = s.get("error") or "capture failed"
                lines.append(
                    f"- **{s['name']}** ({s['width']}×{s['height']}, "
                    f"`{s['url_path']}`) — _capture failed: {err}_"
                )
    lines.append("")

    lines.append("## Source Preflight")
    if not design_preflight_issues:
        lines.append("_(no preflight issues — heading hierarchy / responsive classes / component size all look reasonable)_")
    else:
        for issue in design_preflight_issues:
            lines.append(f"- **[{issue['severity']}]** {issue['description']}")
            if issue.get("suggested_next_task"):
                lines.append(f"  - Suggested next task: {issue['suggested_next_task']}")
    lines.append("")

    lines.append("## Visual Review (multimodal Claude)")
    if not visual.get("ran"):
        lines.append(f"_(skipped: {visual.get('parse_error', 'unknown')})_")
    elif visual.get("parse_error"):
        lines.append(f"_(could not parse JSON output: {visual['parse_error']})_")
        if visual.get("raw"):
            lines.append("")
            lines.append("Raw Claude output:")
            lines.append("```")
            lines.append(visual["raw"][:4000])
            lines.append("```")
    elif not visual.get("issues"):
        lines.append("_(no design issues found — the rendered output matches the design brief)_")
    else:
        for issue in visual["issues"]:
            ev = issue.get("evidence") or {}
            ev_screenshot = ev.get("file") or ""
            line = f"- **[{issue['severity']}]** {issue['description']}"
            if ev_screenshot:
                line += f" (screenshot: `{ev_screenshot}`)"
            lines.append(line)
            if issue.get("suggested_next_task"):
                lines.append(f"  - Suggested next task: {issue['suggested_next_task']}")
    lines.append("")

    lines.append("## Notes")
    lines.append("- Design review reads screenshots, not source. Source preflight is a cheap deterministic pre-check, not the verdict.")
    lines.append("- The reviewer does not modify code; design issues become next-loop polish tasks.")
    lines.append(
        "- TinyAgents intentionally separates reviewer (judges) from builder "
        "(changes). If you disagree with a design issue, you can answer it "
        "as a `human-decision` instead of letting the next loop act on it."
    )
    lines.append("")
    return "\n".join(lines)


def _render_human_questions_md(decision: dict, loop_path: Path) -> str:
    """Render human-decision issues as a structured questions file. Stage
    9.6 only generates this file — consuming the answers is Stage 9.8."""
    questions = [
        i for i in decision["all_issues"]
        if i.get("severity") == SEVERITY_HUMAN_DECISION
    ]
    generated_at = datetime.now().isoformat(timespec="seconds")
    try:
        loop_rel = str(loop_path.relative_to(ROOT))
    except ValueError:
        loop_rel = str(loop_path)
    lines: list[str] = []
    lines.append(f"# Human Questions — {loop_path.name}")
    lines.append("")
    lines.append(f"_Generated on {generated_at}._")
    lines.append("")
    lines.append(
        "Auto paused: the review surfaced items that need a human decision. "
        "Read the questions below and write your answer on each `Answer:` line."
    )
    lines.append("")
    lines.append(
        "**Note**: Stage 9.6 only WRITES this file. Auto re-reading the "
        "answers and feeding them back into the next loop is Stage 9.8. "
        "For now, treat this as a manual checklist."
    )
    lines.append("")
    lines.append(f"Source loop: `{loop_rel}`")
    lines.append("")
    if not questions:
        lines.append("_(no human-decision items — this file should not have been written)_")
        return "\n".join(lines) + "\n"
    for idx, q in enumerate(questions, start=1):
        category = q.get("category", "scope")
        evidence = q.get("evidence") or {}
        lines.append(f"## Q{idx} [{category}]")
        lines.append(f"**{q.get('description', '(no description)')}**")
        lines.append("")
        if evidence.get("file"):
            lines.append(f"- File: `{evidence['file']}`")
        if q.get("suggested_next_task"):
            lines.append(f"- If you want auto to act on this: `{q['suggested_next_task']}`")
        lines.append("- Answer:")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---- run_review (used by both cmd_review and cmd_auto) ----------------

def run_review(
    project_path: Path,
    goal: dict,
    goal_path: Path,
    goal_text: str,
    review_dir: Path,
    port: int,
    max_turns: int,
    timeout: int,
    diff: dict | None = None,
    allow_deps: set[str] | None = None,
    visual_review_enabled: bool = False,
    visual_review_port: int = 3738,
    visual_max_turns: int = 5,
) -> dict:
    """Stage 9.6 review orchestrator. Runs Scope / Security / Content+Docs /
    Functional / (Claude) Quality reviews; classifies the result with the
    5-level severity model; writes:

      - review-report.md         (human-readable, multi-category)
      - review-decision.json     (machine-readable, consumed by cmd_auto)
      - human-questions.md       (only if any human-decision items)
      - artifacts/review-claude.log

    `diff` is the per-loop file diff. When called from cmd_auto this is the
    real diff between pre- and post-Claude snapshots; when called from
    standalone `cmd_review` it's an empty diff (in which case scope review
    falls back to checking current state only — dep red-line still works).
    """
    if diff is None:
        diff = {"added": [], "changed": [], "removed": []}
    if allow_deps is None:
        allow_deps = set()

    artifacts_dir = review_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    print("  Running scope review...")
    scope_issues = run_scope_review(project_path, diff, goal, allow_deps)

    print("  Running security review...")
    security_issues = run_security_review(project_path, diff)

    print("  Running content / docs review...")
    content_docs_issues = run_content_docs_review(project_path, goal)

    print("  Running functional review...")
    functional = run_functional_review(project_path, goal, port=port, timeout=timeout)

    print("  Running design preflight (lightweight source checks)...")
    design_preflight_issues = run_design_preflight(project_path)

    # Stage 9.7: visual review (screenshots + multimodal Claude) is opt-in
    # because it requires Playwright (Node + browser binaries) and several
    # extra minutes of build/screenshot/Claude time.
    screenshots: dict
    visual: dict
    if visual_review_enabled:
        print(f"  Capturing full-page screenshots (Playwright, port={visual_review_port})...")
        screenshots_dir = artifacts_dir / "screenshots"
        screenshots = capture_screenshots(
            project_path=project_path,
            port=visual_review_port,
            screenshots_dir=screenshots_dir,
            build_timeout=timeout,
        )
        if not screenshots["ran"]:
            print(f"    (skipped: {screenshots['error']})")
        else:
            captured = sum(1 for s in screenshots["screenshots"] if s.get("captured"))
            total = len(screenshots["screenshots"])
            rel = (
                screenshots_dir.relative_to(ROOT)
                if screenshots_dir.is_relative_to(ROOT)
                else screenshots_dir
            )
            print(f"    Captured {captured}/{total} screenshots in {rel}")
            if screenshots.get("error"):
                print(f"    (note: {screenshots['error']})")

        print("  Running visual review (design critic, multimodal Claude)...")
        visual = run_visual_review(
            project_path=project_path,
            goal_text=goal_text,
            screenshot_results=screenshots.get("screenshots", []),
            max_turns=visual_max_turns,
            timeout=timeout,
            review_log_path=artifacts_dir / "visual-review-claude.log",
        )
        if not visual["ran"]:
            print(f"    (skipped: {visual['parse_error']})")
    else:
        # Visual review not requested. Provide empty stub results so the
        # rest of the pipeline (decision engine, report writers) stays
        # uniform.
        screenshots = {
            "ran": False,
            "error": "visual review not requested (pass --visual-review to enable)",
            "tool": None,
            "screenshots": [],
        }
        visual = {
            "ran": False,
            "issues": [],
            "raw": "",
            "parse_error": "visual review not requested (pass --visual-review to enable)",
            "claude_exit": None,
            "screenshots_used": [],
        }

    print("  Running quality review (Claude — source-level)...")
    quality = run_quality_review(
        project_path=project_path,
        goal_text=goal_text,
        max_turns=max_turns,
        timeout=timeout,
        review_log_path=artifacts_dir / "review-claude.log",
    )

    decision = classify_review_decision(
        functional=functional,
        scope_issues=scope_issues,
        security_issues=security_issues,
        content_docs_issues=content_docs_issues,
        quality=quality,
        design_preflight_issues=design_preflight_issues,
        visual=visual,
        screenshots=screenshots,
    )

    change_summary = build_change_summary(project_path, diff)

    # Write outputs.
    report_md = _render_review_report(
        project_path=project_path,
        goal=goal,
        goal_path=goal_path,
        functional=functional,
        quality=quality,
        decision=decision,
        change_summary=change_summary,
    )
    report_path = review_dir / "review-report.md"
    report_path.write_text(report_md, encoding="utf-8")

    decision_json = _render_review_decision_json(
        project_path=project_path,
        goal=goal,
        goal_path=goal_path,
        decision=decision,
        change_summary=change_summary,
        loop_path=review_dir,
    )
    decision_path = review_dir / "review-decision.json"
    decision_path.write_text(decision_json, encoding="utf-8")

    # Stage 9.7: standalone design-review.md, useful when the user only
    # wants to read the visual story (the full report.md still has it).
    design_review_md = _render_design_review_md(
        review_dir=review_dir,
        goal=goal,
        screenshots=screenshots,
        visual=visual,
        design_preflight_issues=design_preflight_issues,
    )
    design_review_path = review_dir / "design-review.md"
    design_review_path.write_text(design_review_md, encoding="utf-8")

    questions_path: Path | None = None
    if decision["human_questions_count"] > 0:
        questions_path = review_dir / "human-questions.md"
        questions_path.write_text(
            _render_human_questions_md(decision, review_dir),
            encoding="utf-8",
        )

    return {
        "decision_state": decision["decision_state"],
        "all_issues": decision["all_issues"],
        "by_category": decision["by_category"],
        "counts": decision["counts"],
        "suggested_next_task": decision["suggested_next_task"],
        "human_questions_count": decision["human_questions_count"],
        "publishable": decision["publishable"],
        "functional": functional,
        "quality": quality,
        "visual": visual,
        "screenshots": screenshots,
        "design_preflight_issues": design_preflight_issues,
        "change_summary": change_summary,
        "report_path": report_path,
        "decision_path": decision_path,
        "questions_path": questions_path,
        # Back-compat for older callers that look at "blockers"/"warnings".
        # The dominant signal is `decision_state`.
        "blockers": [
            i for i in decision["all_issues"]
            if i.get("severity") in (SEVERITY_BLOCKER, SEVERITY_MUST_FIX)
        ],
        "warnings": [
            i for i in decision["all_issues"]
            if i.get("severity") == SEVERITY_SHOULD_FIX
        ],
        "infos": [
            i for i in decision["all_issues"]
            if i.get("severity") == SEVERITY_NICE_TO_HAVE
        ],
    }


def cmd_review(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    if not project_path.exists():
        print(f"Error: project path does not exist: {project_path}", file=sys.stderr)
        return 1
    if not project_path.is_dir():
        print(f"Error: project path is not a directory: {project_path}", file=sys.stderr)
        return 1
    if args.agent != "claude":
        print(f"Error: --agent must be 'claude' (got {args.agent!r}).", file=sys.stderr)
        return 1
    goal_path = Path(args.goal_file).expanduser().resolve()
    if not goal_path.is_file():
        print(f"Error: goal file does not exist: {goal_path}", file=sys.stderr)
        return 1
    if not is_initialized():
        # `review` is useful even without a TinyAgents project of its own —
        # but our standalone-review folder lives under ROOT, so we still
        # require init.
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    try:
        goal = parse_goal_file(goal_path)
        goal_text = goal_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error: failed to read goal file: {exc}", file=sys.stderr)
        return 1

    # Prefer writing into the latest loop so review sits next to the rest of
    # that loop's artifacts. Fall back to reviews/<timestamp>/ when there is
    # no loop yet.
    latest = get_latest_loop()
    if latest is not None:
        review_dir = latest
        review_dir_label = str(review_dir.relative_to(ROOT))
    else:
        review_dir = ROOT / "reviews" / datetime.now().strftime("%Y%m%d-%H%M%S")
        review_dir.mkdir(parents=True, exist_ok=True)
        review_dir_label = str(review_dir.relative_to(ROOT))

    print("=" * 60)
    print("REVIEW")
    print(f"  Project: {project_path}")
    print(f"  Goal:    {goal['name']}")
    print(f"  Writing to: {review_dir_label}")
    print(f"  Port:    {args.port}")
    print(f"  Max turns (quality review): {args.max_turns}")
    print(f"  Timeout: {args.timeout}s")
    print("=" * 60)

    result = run_review(
        project_path=project_path,
        goal=goal,
        goal_path=goal_path,
        goal_text=goal_text,
        review_dir=review_dir,
        port=args.port,
        max_turns=args.max_turns,
        timeout=args.timeout,
        visual_review_enabled=getattr(args, "visual_review", False),
        visual_review_port=getattr(args, "visual_review_port", 3738),
        visual_max_turns=getattr(args, "visual_max_turns", 5),
    )

    print()
    print("=" * 60)
    print(f"Review complete — decision: **{result['decision_state']}**")
    counts = result["counts"]
    print(
        f"  Counts: blocker {counts[SEVERITY_BLOCKER]} / "
        f"must-fix {counts[SEVERITY_MUST_FIX]} / "
        f"should-fix {counts[SEVERITY_SHOULD_FIX]} / "
        f"nice-to-have {counts[SEVERITY_NICE_TO_HAVE]} / "
        f"human-decision {counts[SEVERITY_HUMAN_DECISION]}"
    )
    print(f"  Report: {result['report_path'].relative_to(ROOT)}")
    print(f"  Decision JSON: {result['decision_path'].relative_to(ROOT)}")
    # Stage 9.7 — show the design-review.md + screenshot count.
    design_summary = result.get("by_category", {}).get(CATEGORY_DESIGN, {}).get("summary", {})
    cap = design_summary.get("screenshots_captured", 0)
    att = design_summary.get("screenshots_attempted", 0)
    if att > 0:
        print(
            f"  Design review: {cap}/{att} screenshots, "
            f"see loops/.../design-review.md"
        )
    if result["questions_path"] is not None:
        print(f"  Human questions: {result['questions_path'].relative_to(ROOT)}")
    if result["suggested_next_task"]:
        print()
        print("Suggested next task:")
        print(f"  {result['suggested_next_task']}")
    print("=" * 60)
    return 0


# ----- Auto: multi-loop runner -----
#
# Stage 8 turns the one-loop `run` into an `auto` that keeps going until
# either the goal's hard criteria are met or one of the safety gates fires.
# Per-loop work is delegated to `cmd_run`. The auto layer adds:
#
#   - A goal-spec format (hard criteria the runner can verify mechanically,
#     plus a soft-criteria checklist that's only surfaced for human review).
#   - A minimal diff/scope gate that snapshots the project before each loop
#     and checks the after-state for red lines (.env writes, forbidden deps,
#     pathological change size).
#   - A decision state machine that decides done / continue / blocked /
#     max-loops / executor-blocked / needs-human-review.
#   - An auto-report.md that records the loop history and the final
#     soft-criteria checklist.

DEFAULT_MAX_LOOPS = 3

# Red-line dependencies — these can never appear in the target project's
# package.json under `auto`. Anything matching `*-cli` is also blocked.
# Override per-run with `--allow-deps next-auth,stripe`.
DEFAULT_FORBIDDEN_DEPS = (
    "stripe",
    "prisma",
    "mongoose", "mongodb",
    "next-auth", "clerk",
    "firebase", "firebase-admin",
    "pg", "mysql2",
    "redis", "ioredis",
)

# Cap on per-loop file additions before we flag the change as scope-violating.
LARGE_CHANGE_THRESHOLD = 200


# ---- Goal-spec parser ----

def parse_goal_file(path: Path) -> dict:
    """Parse a goal-spec Markdown file into a structured dict.

    Recognized line forms inside `## Hard criteria`:
      - `- file_exists: <path>`
      - `- file_absent: <pattern>` (supports `*`/`?` globs)
      - `- script_passes: <npm-script-name>`
      - `- forbidden_dep: <package-name>`

    `## Soft criteria` is free-text bullets; we just collect each `- ...`
    line and surface them as a checklist in the auto report.
    """
    text = path.read_text(encoding="utf-8")

    result: dict = {
        "name": path.stem,
        "first_task": "",
        "hard": {
            "files_exist": [],
            "files_absent": [],
            "scripts_pass": [],
            "forbidden_deps": [],
        },
        "soft": [],
        # Stage 9.5: runtime review criteria the auto / review pipeline can
        # exercise by spinning up the production build and curling it.
        "review": {
            "production_allows_paths": [],
            "production_blocks_paths": [],
            "production_blocks_posts": [],
        },
    }

    m = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if m:
        result["name"] = m.group(1).strip()

    section = _extract_section(text, r"^first task")
    if section:
        for line in section.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                result["first_task"] = stripped
                break
            if stripped.startswith("- "):
                # Allow `- <task>` form too.
                result["first_task"] = stripped[2:].strip()
                break

    section = _extract_section(text, r"^hard criteria")
    if section:
        for line in section.splitlines():
            m = re.match(r"^-\s+(\w+):\s+(.+?)\s*$", line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            if key == "file_exists":
                result["hard"]["files_exist"].append(value)
            elif key == "file_absent":
                result["hard"]["files_absent"].append(value)
            elif key == "script_passes":
                result["hard"]["scripts_pass"].append(value)
            elif key == "forbidden_dep":
                result["hard"]["forbidden_deps"].append(value)

    section = _extract_section(text, r"^soft criteria")
    if section:
        for line in section.splitlines():
            m = re.match(r"^-\s+(.+?)\s*$", line)
            if m:
                result["soft"].append(m.group(1).strip())

    # Stage 9.5: functional review criteria. Accept any heading that
    # contains "functional review" (case-insensitive), or "review criteria",
    # so users can title the section flexibly.
    for heading in (r"^functional review", r"^review criteria"):
        section = _extract_section(text, heading)
        if not section:
            continue
        for line in section.splitlines():
            m = re.match(r"^-\s+(\w+):\s+(.+?)\s*$", line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            if key == "production_allows_path":
                result["review"]["production_allows_paths"].append(value)
            elif key == "production_blocks_path":
                result["review"]["production_blocks_paths"].append(value)
            elif key == "production_blocks_post":
                result["review"]["production_blocks_posts"].append(value)
        break  # only consume the first matching section

    return result


# ---- Project snapshot + diff ----

def _matches_path(project_path: Path, pattern: str) -> list[Path]:
    """Resolve a path pattern under the project; supports glob characters."""
    if "*" in pattern or "?" in pattern or "[" in pattern:
        return [p for p in project_path.glob(pattern) if p.exists()]
    target = project_path / pattern
    return [target] if target.exists() else []


def snapshot_project(project_path: Path) -> dict[str, int]:
    """Map relative path -> mtime_ns for every regular file under the
    project, skipping the same generated directories `scan` excludes
    (node_modules, .next, build, .git, etc.)."""
    snapshot: dict[str, int] = {}
    if not project_path.is_dir():
        return snapshot
    for root, dirs, files in os.walk(project_path):
        # Skip excluded / hidden directories — reuses Stage 2's list.
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for f in files:
            full = Path(root) / f
            try:
                rel = full.relative_to(project_path).as_posix()
                snapshot[rel] = full.stat().st_mtime_ns
            except (OSError, ValueError):
                continue
    return snapshot


def diff_snapshots(before: dict[str, int], after: dict[str, int]) -> dict:
    before_set = set(before.keys())
    after_set = set(after.keys())
    return {
        "added": sorted(after_set - before_set),
        "removed": sorted(before_set - after_set),
        "changed": sorted(
            f for f in (before_set & after_set) if before[f] != after[f]
        ),
    }


def check_scope_violations(
    project_path: Path,
    diff: dict,
    allow_deps: set[str],
    goal_forbidden_deps: list[str],
) -> list[str]:
    """Return a list of red-line scope violations (empty == clean)."""
    violations: list[str] = []

    # .env-class files written or modified.
    for f in diff["added"] + diff["changed"]:
        leaf = Path(f).name
        if leaf == ".env" or leaf.startswith(".env."):
            violations.append(f"wrote .env-class file: {f}")

    # Forbidden deps now in package.json.
    combined_forbidden = set(DEFAULT_FORBIDDEN_DEPS) | set(goal_forbidden_deps)
    pkg = _read_package_json(project_path)
    if pkg:
        seen_deps: set[str] = set()
        for section_key in ("dependencies", "devDependencies", "peerDependencies"):
            section = pkg.get(section_key) or {}
            if isinstance(section, dict):
                seen_deps.update(section.keys())
        for dep in seen_deps:
            if dep in allow_deps:
                continue
            if dep in combined_forbidden:
                violations.append(f"forbidden dependency in package.json: {dep}")
            elif dep.endswith("-cli"):
                violations.append(f"forbidden *-cli dependency in package.json: {dep}")

    # Pathological size.
    if len(diff["added"]) > LARGE_CHANGE_THRESHOLD:
        violations.append(
            f"unusually large change: {len(diff['added'])} files added "
            f"(threshold {LARGE_CHANGE_THRESHOLD})"
        )

    return violations


# ---- Hard-criteria checker ----

def check_hard_criteria(project_path: Path, goal: dict, loop_path: Path) -> dict:
    """Evaluate every hard criterion against the project's current state +
    the latest loop's test-report.md. Returns a structured pass/fail list."""
    results: list[dict] = []

    for pattern in goal["hard"]["files_exist"]:
        matches = _matches_path(project_path, pattern)
        ok = len(matches) > 0
        results.append({
            "check": f"file_exists: {pattern}",
            "pass": ok,
            "detail": "" if ok else "not found",
        })

    for pattern in goal["hard"]["files_absent"]:
        matches = _matches_path(project_path, pattern)
        ok = len(matches) == 0
        detail = "" if ok else f"found: {[m.name for m in matches[:3]]}"
        results.append({"check": f"file_absent: {pattern}", "pass": ok, "detail": detail})

    # script_passes — read the latest loop's test-report.md.
    test_report_md = _read_text_safe(loop_path / "test-report.md")
    state = _summarize_loop_state(test_report_md)
    passed_set = {c["script"].lower() for c in state["passed"]}
    for script in goal["hard"]["scripts_pass"]:
        ok = script.lower() in passed_set
        results.append({
            "check": f"script_passes: {script}",
            "pass": ok,
            "detail": "" if ok else f"not in passed list (passed: {sorted(passed_set) or 'none'})",
        })

    # no forbidden deps — check current package.json.
    pkg = _read_package_json(project_path)
    if pkg:
        seen_deps: set[str] = set()
        for section_key in ("dependencies", "devDependencies", "peerDependencies"):
            section = pkg.get(section_key) or {}
            if isinstance(section, dict):
                seen_deps.update(section.keys())
    else:
        seen_deps = set()
    for fdep in goal["hard"]["forbidden_deps"]:
        ok = fdep not in seen_deps
        results.append({
            "check": f"no_forbidden_dep: {fdep}",
            "pass": ok,
            "detail": "" if ok else "present in package.json",
        })

    return {"all_pass": all(r["pass"] for r in results), "results": results}


# ---- Decision state machine ----

def decide_next_action(
    state_info: dict,
    hard_check: dict,
    scope_violations: list[str],
    previous_failed_scripts: list[str] | None,
    loop_index: int,
    max_loops: int,
    summarize_recommendation_title: str,
    review_result: dict | None = None,
) -> dict:
    """Return {action, reason, next_task}. `action` is one of:
      done / done-with-warnings / continue / continue-fix /
      blocked-scope / blocked-repeat / executor-blocked /
      max-loops / needs-human-review / needs-human-feedback.

    Stage 9.6: when hard criteria pass, the review_result's
    `decision_state` drives the next action:
      continue-fix          (blocker or must-fix found)  -> continue-fix
      needs-human-feedback  (human-decision items)       -> stop, auto pauses
      done-with-warnings    (only should-fix)            -> stop with warnings
      done                  (clean or only nice-to-have) -> stop
    """
    if scope_violations:
        return {
            "action": "blocked-scope",
            "reason": "; ".join(scope_violations),
            "next_task": None,
        }

    if hard_check["all_pass"]:
        if review_result:
            review_state = review_result.get("decision_state", "done")
            counts = review_result.get("counts", {}) or {}
            if review_state == "continue-fix":
                next_task = review_result.get("suggested_next_task") or (
                    f"Fix review findings from loop"
                )
                if len(next_task) > 200:
                    next_task = next_task[:200].rstrip() + "…"
                return {
                    "action": "continue-fix",
                    "reason": (
                        f"hard pass but review found "
                        f"{counts.get(SEVERITY_BLOCKER, 0)} blocker(s) + "
                        f"{counts.get(SEVERITY_MUST_FIX, 0)} must-fix"
                    ),
                    "next_task": next_task,
                }
            if review_state == "needs-human-feedback":
                return {
                    "action": "needs-human-feedback",
                    "reason": (
                        f"hard pass but "
                        f"{counts.get(SEVERITY_HUMAN_DECISION, 0)} "
                        f"human-decision item(s) need answers"
                    ),
                    "next_task": None,
                }
            if review_state == "done-with-warnings":
                return {
                    "action": "done-with-warnings",
                    "reason": (
                        f"hard pass, no blockers/must-fix; "
                        f"{counts.get(SEVERITY_SHOULD_FIX, 0)} should-fix "
                        f"warning(s) recorded"
                    ),
                    "next_task": None,
                }
            # decision_state == "done" or "unavailable"
            return {
                "action": "done",
                "reason": "all hard criteria + review clean",
                "next_task": None,
            }
        return {"action": "done", "reason": "all hard criteria pass (no review)", "next_task": None}

    if state_info["state"] == "failed":
        failed_scripts = [c["script"].lower() for c in state_info["failed"]]

        if failed_scripts == ["claude"]:
            return {
                "action": "executor-blocked",
                "reason": "Claude executor failed or implementation incomplete",
                "next_task": None,
            }

        if previous_failed_scripts is not None:
            prev = sorted(s.lower() for s in previous_failed_scripts)
            curr = sorted(failed_scripts)
            if prev == curr and prev:
                return {
                    "action": "blocked-repeat",
                    "reason": f"same failure script set repeated: {prev}",
                    "next_task": None,
                }

    if loop_index >= max_loops:
        return {
            "action": "max-loops",
            "reason": f"reached --max-loops={max_loops}",
            "next_task": None,
        }

    state = state_info["state"]

    if state == "passed" and not hard_check["all_pass"]:
        missing = [r["check"] for r in hard_check["results"] if not r["pass"]]
        head = ", ".join(missing[:3])
        more = "" if len(missing) <= 3 else f" (and {len(missing) - 3} more)"
        next_task = f"Refine portfolio to satisfy missing criteria: {head}{more}"
        return {
            "action": "continue",
            "reason": "tests pass but hard criteria not met",
            "next_task": next_task,
        }

    if state in ("failed", "no-tests-run", "tests-not-run") and summarize_recommendation_title:
        return {
            "action": "continue",
            "reason": f"using summarize recommendation: {summarize_recommendation_title}",
            "next_task": summarize_recommendation_title,
        }

    return {
        "action": "needs-human-review",
        "reason": "no clear next task could be derived from this loop's state",
        "next_task": None,
    }


# ---- Auto-report rendering ----

def _research_from_goal(task_title: str, goal_text: str) -> str:
    """Stage 8.1: render a research.md that embeds the full goal spec so the
    implementation prompt actually surfaces the design brief to Claude.

    The goal's leading H1 is stripped to avoid heading collisions when the
    prompt builder demotes headings inside the Research Context section.
    """
    stripped = _strip_leading_h1(goal_text).strip()
    return f"""# Research: {task_title}

The full goal specification follows. Treat it as the authoritative source
for what to build, who it is for, and what the design should feel like.
The sections most relevant to research and design (before coding) are:
**Goal**, **Product Concept**, **Target User**, **Design Goal**,
**Design Research Instructions**, **Visual Requirements**,
**Visual Direction**, and **Content Rules**.

---

{stripped}
"""


def _plan_from_goal(task_title: str, goal: dict) -> str:
    """Stage 8.1: render a plan.md focused on this loop's deliverables.

    The full constraints already appear in research.md (which embeds the
    whole goal). The plan stays short on purpose — its job is to surface a
    concrete checklist that summarize / next-loop logic can lean on.
    """
    hard_lines: list[str] = []
    for f in goal["hard"]["files_exist"]:
        hard_lines.append(f"- [ ] file_exists: `{f}`")
    for f in goal["hard"]["files_absent"]:
        hard_lines.append(f"- [ ] file_absent: `{f}`")
    for s in goal["hard"]["scripts_pass"]:
        hard_lines.append(f"- [ ] script_passes: `{s}`")
    for d in goal["hard"]["forbidden_deps"]:
        hard_lines.append(f"- [ ] no_forbidden_dep: `{d}`")
    hard_block = "\n".join(hard_lines) if hard_lines else "- (none defined in goal)"

    soft_lines = [f"- [ ] {s}" for s in goal["soft"]]
    soft_block = "\n".join(soft_lines) if soft_lines else "- (none defined in goal)"

    return f"""# Plan: {task_title}

## What will be done in this loop?
{task_title}

See `research.md` (and the **Research Context** section of the implementation
prompt) for the full design brief, content rules, and scope. The plan below
just surfaces the deliverable checklist for this loop.

## Allowed changes
- Files and directories listed under **Scope → Allowed** in the goal spec.

## Forbidden changes
- Everything listed under **Scope → Forbidden** in the goal spec.
- No backend / database / auth / payments / CMS / external APIs / AI chatbot /
  analytics — these are blocked by both the goal and TinyLocalAgents' default
  scope gate.
- No new dependencies unless required for the existing Next.js setup.

## Acceptance criteria

**Hard criteria** (mechanically verified by TinyLocalAgents after this loop):

{hard_block}

**Soft criteria** (surfaced in `auto-report.md` for human review — do not
fake-pass them):

{soft_block}

## Risks / Unknowns
- The page must look polished even when content is still TODO placeholders.
- Missing project images must not break layout (use a tasteful placeholder).
- No personal content should be hardcoded in React components — all of it
  belongs in `src/content/portfolio.ts`.
"""


def _extract_recommendation_title(next_loop_md: str | None) -> str:
    if not next_loop_md:
        return ""
    m = re.search(r"Suggested loop title:\s*\*\*([^*\n]+)\*\*", next_loop_md)
    return m.group(1).strip() if m else ""


def _render_auto_report(
    goal: dict,
    goal_path: Path,
    project_path: Path,
    loop_history: list[dict],
    settings: dict,
) -> str:
    generated_at = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Auto Run Report")
    lines.append("")
    lines.append(f"_Generated by `tiny_agents.py auto` on {generated_at}._")
    lines.append("")
    lines.append("## Settings")
    lines.append(f"- Goal: **{goal['name']}** (from `{goal_path.relative_to(ROOT) if goal_path.is_relative_to(ROOT) else goal_path}`)")
    lines.append(f"- Project: `{project_path}`")
    lines.append(f"- max-loops: {settings['max_loops']}")
    lines.append(f"- max-turns: {settings['max_turns']}")
    lines.append(f"- timeout: {settings['timeout']}s")
    lines.append(f"- install: {settings['install']}")
    lines.append(f"- claude-permission-mode: {settings['claude_permission_mode']}")
    if settings["allow_deps"]:
        lines.append(f"- allow-deps: {', '.join(sorted(settings['allow_deps']))}")
    lines.append("")

    final = loop_history[-1] if loop_history else None
    lines.append("## Outcome")
    if final:
        lines.append(f"- Loops run: {len(loop_history)}")
        lines.append(f"- Final action: **{final['decision']['action']}**")
        lines.append(f"- Final reason: {final['decision']['reason']}")
        lines.append(
            f"- Final hard criteria: "
            f"{'**ALL PASS**' if final['hard_check']['all_pass'] else 'FAIL'}"
        )
    else:
        lines.append("- (no loops were run)")
    lines.append("")

    lines.append("## Loop History")
    if not loop_history:
        lines.append("_(no loops were run)_")
    for entry in loop_history:
        loop_rel = (
            entry["loop_path"].relative_to(ROOT)
            if entry["loop_path"].is_relative_to(ROOT)
            else entry["loop_path"]
        )
        lines.append("")
        lines.append(f"### Loop {entry['loop_idx']}: {entry['task']}")
        lines.append(f"- Loop folder: `{loop_rel}`")
        lines.append(f"- Test state: `{entry['state']}`")
        d = entry["diff_summary"]
        lines.append(f"- Files: +{d['added']} ~{d['changed']} -{d['removed']}")
        passes = sum(1 for r in entry["hard_check"]["results"] if r["pass"])
        total = len(entry["hard_check"]["results"])
        lines.append(
            f"- Hard criteria: {passes}/{total} pass "
            f"({'ALL PASS' if entry['hard_check']['all_pass'] else 'fail'})"
        )
        if entry["scope_violations"]:
            lines.append("- Scope violations:")
            for v in entry["scope_violations"]:
                lines.append(f"  - {v}")
        if entry.get("review_ran") and entry.get("review_result"):
            rr = entry["review_result"]
            counts = rr["counts"]
            lines.append(
                f"- Review: **{rr['decision_state']}** "
                f"(blocker={counts[SEVERITY_BLOCKER]}, "
                f"must-fix={counts[SEVERITY_MUST_FIX]}, "
                f"should-fix={counts[SEVERITY_SHOULD_FIX]}, "
                f"nice-to-have={counts[SEVERITY_NICE_TO_HAVE]}, "
                f"human-decision={counts[SEVERITY_HUMAN_DECISION]})"
            )
            top_severities = (SEVERITY_BLOCKER, SEVERITY_MUST_FIX, SEVERITY_HUMAN_DECISION)
            top_issues = [
                i for i in rr["all_issues"]
                if i.get("severity") in top_severities
            ][:5]
            for issue in top_issues:
                lines.append(f"  - [{issue['severity']}] {issue['description']}")
            if rr.get("questions_path"):
                try:
                    qrel = rr["questions_path"].relative_to(ROOT)
                except (ValueError, AttributeError):
                    qrel = rr["questions_path"]
                lines.append(f"  - Human questions: `{qrel}`")
        elif entry.get("review_ran") is False:
            lines.append("- Review: _(skipped — hard criteria did not pass)_")
        lines.append(
            f"- Decision: **{entry['decision']['action']}** — "
            f"{entry['decision']['reason']}"
        )
    lines.append("")

    if final:
        lines.append("## Final Hard-Criteria Breakdown")
        for r in final["hard_check"]["results"]:
            mark = "[x]" if r["pass"] else "[ ]"
            extra = f" — {r['detail']}" if r["detail"] else ""
            lines.append(f"- {mark} {r['check']}{extra}")
        lines.append("")

    if goal["soft"]:
        lines.append("## Soft Criteria (manual review)")
        lines.append("_TinyLocalAgents cannot mechanically verify these; tick them yourself after looking at the project._")
        lines.append("")
        for s in goal["soft"]:
            lines.append(f"- [ ] {s}")
        lines.append("")

    return "\n".join(lines)


# ---- The auto command ----

def cmd_auto(args: argparse.Namespace) -> int:
    if not is_initialized():
        print(
            "TinyLocalAgents is not initialized yet.\n"
            "Run: python tiny_agents.py init",
            file=sys.stderr,
        )
        return 1

    if args.agent != "claude":
        print(f"Error: --agent must be 'claude' (got {args.agent!r}).", file=sys.stderr)
        return 1

    goal_path = Path(args.goal_file).expanduser().resolve()
    if not goal_path.is_file():
        print(f"Error: goal file does not exist: {goal_path}", file=sys.stderr)
        return 1

    try:
        goal = parse_goal_file(goal_path)
    except OSError as exc:
        print(f"Error: failed to read goal file: {exc}", file=sys.stderr)
        return 1

    first_task = (args.task or "").strip() or goal["first_task"]
    if not first_task:
        print(
            "Error: no first task specified. Pass --task or add a 'First task' "
            "section to the goal file.",
            file=sys.stderr,
        )
        return 1

    project_path = Path(args.project).expanduser().resolve()
    if not project_path.exists():
        if args.create_if_missing:
            project_path.mkdir(parents=True)
            (project_path / "README.md").write_text(_placeholder_readme(first_task), encoding="utf-8")
            print(f"Created project folder: {project_path}")
        else:
            print(f"Error: project path does not exist: {project_path}", file=sys.stderr)
            print("Pass --create-if-missing to create it.", file=sys.stderr)
            return 1
    elif not project_path.is_dir():
        print(f"Error: project path is not a directory: {project_path}", file=sys.stderr)
        return 1

    allow_deps = (
        {d.strip() for d in args.allow_deps.split(",") if d.strip()}
        if args.allow_deps
        else set()
    )

    settings = {
        "max_loops": args.max_loops,
        "max_turns": args.max_turns,
        "timeout": args.timeout,
        "install": bool(args.install),
        "claude_permission_mode": args.claude_permission_mode,
        "allow_deps": allow_deps,
    }

    print("=" * 60)
    print("AUTO run")
    print(f"  Goal:    {goal['name']}")
    print(f"  Project: {project_path}")
    print(f"  Max loops: {args.max_loops}")
    print(f"  Install:  {args.install}")
    print(f"  Permission mode: {args.claude_permission_mode}")
    print(f"  Per-cmd timeout: {args.timeout}s")
    if allow_deps:
        print(f"  Allowed deps (overrides forbidden list): {', '.join(sorted(allow_deps))}")
    print("=" * 60)

    # Stage 8.1: read the goal file once and pre-render the research/plan
    # content that will be injected into every loop's research.md / plan.md.
    # This is what makes Claude actually see the design brief, Content Rules,
    # and the hard/soft criteria — without this injection, the goal file is
    # only consumed by auto's decision logic after each loop.
    try:
        goal_text = goal_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error: failed to re-read goal file: {exc}", file=sys.stderr)
        return 1

    loop_history: list[dict] = []
    current_task = first_task
    previous_failed_scripts: list[str] | None = None

    for loop_idx in range(1, args.max_loops + 1):
        print()
        print("=" * 60)
        print(f"Auto Loop {loop_idx}/{args.max_loops}")
        print(f"Task: {current_task}")
        print("=" * 60)
        print("(Pausing 3 seconds before invoking Claude. Ctrl-C now to abort.)")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nAuto: aborted by user.")
            return 130

        before_snapshot = snapshot_project(project_path)

        # Stage 8.1: inject the goal-derived research/plan into the new loop
        # so the implementation-prompt.md carries the full design brief.
        run_args = argparse.Namespace(
            project=str(project_path),
            task=current_task,
            agent="claude",
            create_if_missing=False,  # project dir already exists by here
            execute=True,
            install=args.install,
            claude_permission_mode=args.claude_permission_mode,
            max_turns=args.max_turns,
            timeout=args.timeout,
            research_content=_research_from_goal(current_task, goal_text),
            plan_content=_plan_from_goal(current_task, goal),
        )
        rc = cmd_run(run_args)
        if rc != 0:
            print(f"\nAuto: cmd_run returned structural exit code {rc}; stopping.")
            break

        loop_path = get_latest_loop()
        if loop_path is None:
            print("Auto: no loop folder found after cmd_run; stopping.")
            break

        after_snapshot = snapshot_project(project_path)
        diff = diff_snapshots(before_snapshot, after_snapshot)
        scope_violations = check_scope_violations(
            project_path, diff, allow_deps, goal["hard"]["forbidden_deps"]
        )

        hard_check = check_hard_criteria(project_path, goal, loop_path)

        test_report = _read_text_safe(loop_path / "test-report.md")
        state_info = _summarize_loop_state(test_report)
        next_loop_md = _read_text_safe(loop_path / "next-loop.md")
        suggested_title = _extract_recommendation_title(next_loop_md)

        # Stage 9.6: only run review when hard criteria pass. If hard criteria
        # already fail, we're going to continue / stop based on test results
        # anyway; running review on a known-broken state burns Claude turns
        # without changing the outcome.
        review_result: dict | None = None
        review_ran = False
        if hard_check["all_pass"] and not scope_violations:
            print()
            print("Step: review (Stage 9.6 — scope / security / content / docs / functional / quality)")
            review_result = run_review(
                project_path=project_path,
                goal=goal,
                goal_path=goal_path,
                goal_text=goal_text,
                review_dir=loop_path,
                port=args.review_port,
                max_turns=args.review_max_turns,
                timeout=args.timeout,
                diff=diff,
                allow_deps=allow_deps,
                visual_review_enabled=getattr(args, "visual_review", False),
                visual_review_port=getattr(args, "visual_review_port", 3738),
                visual_max_turns=getattr(args, "visual_max_turns", 5),
            )
            review_ran = True
            counts = review_result["counts"]
            print(
                f"Review: {review_result['decision_state']} "
                f"(blocker={counts[SEVERITY_BLOCKER]}, "
                f"must-fix={counts[SEVERITY_MUST_FIX]}, "
                f"should-fix={counts[SEVERITY_SHOULD_FIX]}, "
                f"nice-to-have={counts[SEVERITY_NICE_TO_HAVE]}, "
                f"human-decision={counts[SEVERITY_HUMAN_DECISION]})"
            )

        decision = decide_next_action(
            state_info=state_info,
            hard_check=hard_check,
            scope_violations=scope_violations,
            previous_failed_scripts=previous_failed_scripts,
            loop_index=loop_idx,
            max_loops=args.max_loops,
            summarize_recommendation_title=suggested_title,
            review_result=review_result,
        )

        loop_history.append({
            "loop_idx": loop_idx,
            "loop_path": loop_path,
            "task": current_task,
            "state": state_info["state"],
            "hard_check": hard_check,
            "scope_violations": scope_violations,
            "diff_summary": {
                "added": len(diff["added"]),
                "changed": len(diff["changed"]),
                "removed": len(diff["removed"]),
            },
            "review_ran": review_ran,
            "review_result": review_result,
            "decision": decision,
        })

        print()
        print(f"Auto Loop {loop_idx} decision: {decision['action']}")
        print(f"  Reason: {decision['reason']}")
        passes = sum(1 for r in hard_check["results"] if r["pass"])
        total = len(hard_check["results"])
        print(f"  Hard criteria: {passes}/{total} pass ({'ALL PASS' if hard_check['all_pass'] else 'fail'})")
        if not hard_check["all_pass"]:
            failed = [r for r in hard_check["results"] if not r["pass"]]
            for r in failed[:5]:
                extra = f" — {r['detail']}" if r["detail"] else ""
                print(f"    [ ] {r['check']}{extra}")
            if len(failed) > 5:
                print(f"    ... and {len(failed) - 5} more")
        if scope_violations:
            print("  Scope violations:")
            for v in scope_violations:
                print(f"    - {v}")
        print(f"  Files: +{len(diff['added'])} ~{len(diff['changed'])} -{len(diff['removed'])}")
        if review_ran and review_result is not None:
            counts = review_result["counts"]
            print(
                f"  Review: {review_result['decision_state']} "
                f"(blocker={counts[SEVERITY_BLOCKER]}, "
                f"must-fix={counts[SEVERITY_MUST_FIX]}, "
                f"should-fix={counts[SEVERITY_SHOULD_FIX]}, "
                f"nice-to-have={counts[SEVERITY_NICE_TO_HAVE]}, "
                f"human-decision={counts[SEVERITY_HUMAN_DECISION]})"
            )
            top_priorities = (SEVERITY_BLOCKER, SEVERITY_MUST_FIX, SEVERITY_HUMAN_DECISION)
            for issue in review_result["all_issues"]:
                if issue.get("severity") in top_priorities:
                    print(f"    [{issue['severity']}] {issue['description'][:160]}")
            if review_result.get("questions_path") is not None:
                rel = review_result["questions_path"].relative_to(ROOT)
                print(f"    Human questions written to: {rel}")

        if decision["action"] not in ("continue", "continue-fix"):
            break

        previous_failed_scripts = [c["script"] for c in state_info["failed"]]
        current_task = decision["next_task"]

    report_md = _render_auto_report(goal, goal_path, project_path, loop_history, settings)
    auto_report_path = ROOT / "auto-report.md"
    auto_report_path.write_text(report_md, encoding="utf-8")

    print()
    print("=" * 60)
    print("AUTO complete.")
    if loop_history:
        final = loop_history[-1]
        print(f"  Final action: {final['decision']['action']}")
        print(f"  Final reason: {final['decision']['reason']}")
    print(f"  Loops run: {len(loop_history)}")
    print(f"  Report: {auto_report_path.relative_to(ROOT)}")
    if goal["soft"]:
        print(f"  Soft criteria checklist is in the report — review manually.")
    print("=" * 60)
    return 0


# ----- Entry point -----

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tiny_agents",
        description="TinyLocalAgents - manage Research -> Plan -> Implement -> Test loops.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Initialize the project directory.")
    p_init.set_defaults(func=cmd_init)

    p_new = subparsers.add_parser("new", help="Create a new numbered loop folder.")
    p_new.add_argument("title", help="Short title describing the loop's task.")
    p_new.set_defaults(func=cmd_new)

    p_status = subparsers.add_parser("status", help="Show project and loop status.")
    p_status.set_defaults(func=cmd_status)

    p_scan = subparsers.add_parser(
        "scan",
        help="Scan a target project folder and write context-summary.md into the latest loop.",
    )
    p_scan.add_argument(
        "--project",
        required=True,
        help="Path to the target project folder (e.g. ../portfolio-site).",
    )
    p_scan.set_defaults(func=cmd_scan)

    p_prompt = subparsers.add_parser(
        "prompt",
        help="Synthesize research.md + plan.md + context-summary.md into implementation-prompt.md.",
    )
    p_prompt.set_defaults(func=cmd_prompt)

    p_test = subparsers.add_parser(
        "test",
        help="Run typecheck / build / lint / test against a target project and write test-report.md + artifacts/*.log.",
    )
    p_test.add_argument(
        "--project",
        required=True,
        help="Path to the target project folder (e.g. ../portfolio-site).",
    )
    p_test.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=(
            f"Per-command timeout in seconds (default: {DEFAULT_TIMEOUT_S}). "
            "Any single script that runs longer is killed and recorded as failed."
        ),
    )
    p_test.set_defaults(func=cmd_test)

    p_summarize = subparsers.add_parser(
        "summarize",
        help="Summarize the latest loop's test results into next-loop.md.",
    )
    p_summarize.set_defaults(func=cmd_summarize)

    p_run = subparsers.add_parser(
        "run",
        help="Orchestrate one full loop: new -> scan -> prompt -> (Claude Code) -> test -> summarize.",
    )
    p_run.add_argument("--project", required=True, help="Path to the target project folder.")
    p_run.add_argument("--task", required=True, help="Task title for this loop.")
    p_run.add_argument(
        "--agent",
        required=True,
        choices=list(SUPPORTED_AGENTS),
        help="Which coding agent to invoke. Only 'claude' is supported in Stage 6.",
    )
    p_run.add_argument(
        "--create-if-missing",
        action="store_true",
        help="Create the target project folder (with a placeholder README) if it does not exist.",
    )
    p_run.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke Claude Code. Without --execute the command is a dry run.",
    )
    p_run.add_argument(
        "--install",
        action="store_true",
        help="After Claude completes, run the detected package manager's install command before tests. Opt-in: may create node_modules and a lockfile in the target project.",
    )
    p_run.add_argument(
        "--claude-permission-mode",
        choices=["default", "acceptEdits"],
        default="default",
        help=(
            "Permission mode passed to Claude Code. 'default' = Claude asks for "
            "per-edit approval (existing behavior). 'acceptEdits' = file edits are "
            "auto-approved, useful for unattended runs. bypassPermissions / "
            "--dangerously-skip-permissions are NOT supported."
        ),
    )
    p_run.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"Pass --max-turns to Claude Code (default: {DEFAULT_MAX_TURNS}).",
    )
    p_run.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=(
            f"Per-command timeout in seconds (default: {DEFAULT_TIMEOUT_S}). "
            "Applies to Claude, install, and each verification script. Any "
            "subprocess that runs longer is killed and recorded as failed — "
            "this is the safety net against `next lint` wizards, jest watch "
            "mode, and other accidental interactive prompts."
        ),
    )
    p_run.set_defaults(func=cmd_run)

    p_auto = subparsers.add_parser(
        "auto",
        help="Multi-loop runner: orchestrate up to N `run` loops against a goal-spec until done.",
    )
    p_auto.add_argument("--project", required=True, help="Path to the target project folder.")
    p_auto.add_argument(
        "--goal-file",
        required=True,
        help="Path to the goal-spec Markdown (e.g. goals/portfolio-mvp.md).",
    )
    p_auto.add_argument(
        "--task",
        default="",
        help="Override the first task; defaults to the goal file's 'First task' section.",
    )
    p_auto.add_argument(
        "--agent",
        required=True,
        choices=list(SUPPORTED_AGENTS),
        help="Coding agent to invoke (only 'claude' is supported).",
    )
    p_auto.add_argument(
        "--create-if-missing",
        action="store_true",
        help="Create the target project folder with a placeholder README if it doesn't exist.",
    )
    p_auto.add_argument(
        "--install",
        action="store_true",
        help="Run the detected package manager's install after each loop's Claude.",
    )
    p_auto.add_argument(
        "--claude-permission-mode",
        choices=["default", "acceptEdits"],
        default="default",
        help="Passed through to Claude Code (default | acceptEdits).",
    )
    p_auto.add_argument(
        "--max-loops",
        type=int,
        default=DEFAULT_MAX_LOOPS,
        help=f"Max loops to run before stopping (default: {DEFAULT_MAX_LOOPS}).",
    )
    p_auto.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"Per-loop --max-turns for Claude (default: {DEFAULT_MAX_TURNS}).",
    )
    p_auto.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-command timeout in seconds (default: {DEFAULT_TIMEOUT_S}).",
    )
    p_auto.add_argument(
        "--allow-deps",
        default="",
        help=(
            "Comma-separated dependency names to allow despite the default red-line list "
            "(e.g. 'next-auth,stripe'). The default forbidden list is enforced unless an "
            "exact name appears here."
        ),
    )
    p_auto.add_argument(
        "--review-port",
        type=int,
        default=DEFAULT_REVIEW_PORT,
        help=(
            f"Port for the Stage 9.5 review's production-server probes "
            f"(default: {DEFAULT_REVIEW_PORT}). Chosen to avoid the typical dev port 3000."
        ),
    )
    p_auto.add_argument(
        "--review-max-turns",
        type=int,
        default=DEFAULT_REVIEW_MAX_TURNS,
        help=(
            f"--max-turns passed to Claude during the quality-review step "
            f"(default: {DEFAULT_REVIEW_MAX_TURNS}). Keep this small — the review is a "
            "short JSON-output pass, not implementation."
        ),
    )
    p_auto.add_argument(
        "--visual-review",
        action="store_true",
        help=(
            "Stage 9.7: enable screenshot-based visual review during each "
            "auto loop's review step. Requires Playwright installed in "
            "TinyAgents. Adds ~2-3 minutes per loop (Playwright build + 4 "
            "full-page screenshots + design-critic Claude call). Design "
            "blockers / must-fix become next-loop polish tasks."
        ),
    )
    p_auto.add_argument(
        "--visual-review-port",
        type=int,
        default=3738,
        help="Port for the Stage 9.7 visual-review production server (default: 3738).",
    )
    p_auto.add_argument(
        "--visual-max-turns",
        type=int,
        default=5,
        help="--max-turns for the Stage 9.7 design-critic Claude call (default: 5).",
    )
    p_auto.set_defaults(func=cmd_auto)

    p_review = subparsers.add_parser(
        "review",
        help="Run the Stage 9.5 review agent against a target project: static checks + production-build runtime probes + Claude quality review.",
    )
    p_review.add_argument("--project", required=True, help="Path to the target project folder.")
    p_review.add_argument(
        "--goal-file",
        required=True,
        help="Path to the goal-spec Markdown (the review reads its 'Functional Review Criteria' section).",
    )
    p_review.add_argument(
        "--agent",
        required=True,
        choices=list(SUPPORTED_AGENTS),
        help="Coding agent used for the quality review (only 'claude' is supported).",
    )
    p_review.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_REVIEW_MAX_TURNS,
        help=f"--max-turns for the quality-review Claude pass (default: {DEFAULT_REVIEW_MAX_TURNS}).",
    )
    p_review.add_argument(
        "--port",
        type=int,
        default=DEFAULT_REVIEW_PORT,
        help=f"Port to bind the production server to for runtime probes (default: {DEFAULT_REVIEW_PORT}).",
    )
    p_review.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-command timeout in seconds (default: {DEFAULT_TIMEOUT_S}).",
    )
    p_review.add_argument(
        "--visual-review",
        action="store_true",
        help=(
            "Stage 9.7: enable screenshot-based visual review. Requires "
            "Playwright installed in TinyAgents (`npm install && "
            "npx playwright install chromium`). Captures full-page "
            "screenshots of `/` and `/studio` at desktop (1440x1200) and "
            "mobile (390x844), then asks a design-critic Claude session to "
            "compare them against the goal's Visual Direction."
        ),
    )
    p_review.add_argument(
        "--visual-review-port",
        type=int,
        default=3738,
        help=(
            "Port for the Stage 9.7 visual-review production server "
            "(default: 3738, deliberately non-3000 so it doesn't fight a "
            "running dev server)."
        ),
    )
    p_review.add_argument(
        "--visual-max-turns",
        type=int,
        default=5,
        help=(
            "--max-turns for the Stage 9.7 design-critic Claude call "
            "(default: 5). Kept small — this pass outputs JSON, not code."
        ),
    )
    p_review.set_defaults(func=cmd_review)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
