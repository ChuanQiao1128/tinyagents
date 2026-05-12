#!/usr/bin/env node
//
// TinyAgents Stage 9.7 — Visual Review Agent screenshot helper.
//
// Captures full-page screenshots of the given routes at desktop + mobile
// viewports using Playwright (the same browser-automation library most
// production AI-design-QA pipelines use).
//
// Usage:
//   node scripts/screenshot.mjs \
//     --base-url http://127.0.0.1:3738 \
//     --out      loops/<NNN>/artifacts/screenshots \
//     --routes   /,/studio
//
// Output: one PNG per (route, viewport) pair:
//   homepage-desktop.png  homepage-mobile.png
//   studio-desktop.png    studio-mobile.png
//
// Each captured / failed step prints a JSON line on stdout (`event:
// "captured"` or `event: "failed"`), and a final `event: "summary"` line
// reports the full result list. Exit code is 0 only if every requested
// screenshot was captured successfully; non-zero otherwise.
//
// This file is intentionally the only Node code TinyAgents owns. It does
// one thing: call Playwright's `page.screenshot({ fullPage: true })`.
// Anything more advanced belongs in TinyAgents Python.

import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

// Viewport spec per Stage 9.7 design doc: desktop 1440x1200, mobile 390x844.
// Mobile is commented out for now — the user asked to focus on desktop
// visual quality first. Re-enable by uncommenting the mobile entry.
const VIEWPORTS = [
  {
    name: "desktop",
    width: 1440,
    height: 1200,
    deviceScaleFactor: 1,
    isMobile: false,
    hasTouch: false,
  },
  // {
  //   name: "mobile",
  //   width: 390,
  //   height: 844,
  //   deviceScaleFactor: 2,
  //   isMobile: true,
  //   hasTouch: true,
  // },
];

function parseArgs(argv) {
  const args = {
    baseUrl: null,
    out: null,
    routes: ["/"],
    waitTimeoutMs: 30000,
    hydrationGraceMs: 1500,
  };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = argv[i + 1];
    if (k === "--base-url") {
      args.baseUrl = v;
      i++;
    } else if (k === "--out") {
      args.out = v;
      i++;
    } else if (k === "--routes") {
      args.routes = v.split(",").map((s) => s.trim()).filter(Boolean);
      i++;
    } else if (k === "--wait-timeout-ms") {
      args.waitTimeoutMs = parseInt(v, 10);
      i++;
    } else if (k === "--hydration-grace-ms") {
      args.hydrationGraceMs = parseInt(v, 10);
      i++;
    }
  }
  if (!args.baseUrl || !args.out) {
    throw new Error(
      "Usage: node scripts/screenshot.mjs --base-url URL --out DIR [--routes /,/studio]",
    );
  }
  return args;
}

function routeSlug(route) {
  if (route === "/" || route === "") return "homepage";
  const trimmed = route.replace(/^\/+|\/+$/g, "");
  return trimmed.replace(/\//g, "-");
}

function emit(event) {
  // One JSON event per line — easy for Python to readline + json.loads.
  process.stdout.write(JSON.stringify(event) + "\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  await mkdir(args.out, { recursive: true });

  emit({
    event: "starting",
    baseUrl: args.baseUrl,
    out: args.out,
    routes: args.routes,
    viewports: VIEWPORTS.map((v) => v.name),
  });

  const browser = await chromium.launch({ headless: true });
  const results = [];
  let anyFailed = false;

  try {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: vp.deviceScaleFactor,
        isMobile: vp.isMobile,
        hasTouch: vp.hasTouch,
      });
      try {
        for (const route of args.routes) {
          const url = args.baseUrl.replace(/\/$/, "") + route;
          const slug = routeSlug(route);
          // JPEG instead of PNG: full-page portfolio screenshots run ~1-2 MB
          // as PNG which exceeded `claude -p`'s attachment size budget
          // (Claude reported "permission was not granted to read the image"
          // for the larger homepage capture while the smaller /studio
          // capture worked). The empirical threshold sits around ~255 KB:
          // quality-85 JPEG ran fine at 252 KB but tipped over at 266 KB
          // after a polish loop made the homepage taller. Quality 72 keeps
          // the current desktop homepage at ~180 KB while still being
          // visually indistinguishable for design review (hierarchy,
          // spacing, palette, alignment), giving us ~30% headroom as the
          // page grows with real content.
          const filename = `${slug}-${vp.name}.jpg`;
          const outPath = resolve(args.out, filename);
          const page = await context.newPage();
          try {
            await page.goto(url, {
              waitUntil: "networkidle",
              timeout: args.waitTimeoutMs,
            });
            // Belt-and-suspenders: give the page a brief grace period for
            // hydration / lazy fonts / late images to settle before we snap.
            await page.waitForTimeout(args.hydrationGraceMs);
            await page.screenshot({
              path: outPath,
              fullPage: true,
              type: "jpeg",
              quality: 72,
            });
            const screenshotInfo = {
              event: "captured",
              route,
              viewport: vp.name,
              width: vp.width,
              height: vp.height,
              filename,
              path: outPath,
              url,
            };
            results.push({ ...screenshotInfo, ok: true });
            emit(screenshotInfo);
          } catch (e) {
            anyFailed = true;
            const failureInfo = {
              event: "failed",
              route,
              viewport: vp.name,
              width: vp.width,
              height: vp.height,
              filename,
              path: outPath,
              url,
              error: String(e && e.message ? e.message : e),
            };
            results.push({ ...failureInfo, ok: false });
            emit(failureInfo);
          } finally {
            await page.close().catch(() => {});
          }
        }
      } finally {
        await context.close().catch(() => {});
      }
    }
  } finally {
    await browser.close().catch(() => {});
  }

  emit({ event: "summary", any_failed: anyFailed, results });
  process.exit(anyFailed ? 1 : 0);
}

main().catch((err) => {
  emit({ event: "fatal", error: String(err && err.message ? err.message : err) });
  process.exit(2);
});
