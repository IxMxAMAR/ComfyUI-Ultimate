/* Real-browser test for PodPanel.
 *
 *   python scripts/podpanel.py --port 8090 --output <dir> &
 *   node tests/ui_podpanel.mjs
 *
 * Drives the actual page in Chrome: gallery, thumbnails, lightbox, selection,
 * filters, and the drop-in runner end to end. CI does not run this (it globs
 * test_*.sh and has no node/Chrome); tests/test_podpanel.sh is the CI gate and
 * covers the HTTP surface this exercises through the DOM.
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const BASE = process.env.PODPANEL_URL || "http://127.0.0.1:8090";

function loadPlaywright() {
  const tries = ["playwright", "playwright-core"];
  const pnpm = "C:/AI/deepseek-harness/node_modules/.pnpm";
  if (fs.existsSync(pnpm)) {
    for (const dir of fs.readdirSync(pnpm)) {
      if (/^playwright@/.test(dir)) tries.push(path.join(pnpm, dir, "node_modules", "playwright"));
    }
  }
  for (const t of tries) {
    try { return require(t); } catch { /* keep looking */ }
  }
  throw new Error("playwright not found");
}

function findChrome() {
  return [
    process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  ].filter(Boolean).find((c) => fs.existsSync(c));
}

let pass = 0, fail = 0;
function check(label, ok, detail = "") {
  if (ok) { pass++; console.log(`  PASS  ${label}`); }
  else { fail++; console.log(`  FAIL  ${label}${detail ? "  -- " + detail : ""}`); }
}

const { chromium } = loadPlaywright();
const executablePath = findChrome();
if (!executablePath) { console.log("no Chrome/Edge found; set CHROME_PATH"); process.exit(2); }

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => { errors.push(e.message); });
page.on("console", (m) => {
  if (m.type() !== "error") return;
  // A video whose poster frame cannot be decoded legitimately 404s on /thumb/
  // and the card falls back to a placeholder tile; that is not a page error.
  const url = (m.location() && m.location().url) || "";
  if (/\/thumb\//.test(url)) return;
  errors.push("console: " + m.text());
});

console.log(`PodPanel UI test against ${BASE}`);
await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForSelector(".card", { timeout: 15000 });

// --- gallery ------------------------------------------------------------
const cards = await page.locator(".card").count();
check("the gallery renders every output", cards === 5, `got ${cards}`);

const names = await page.locator(".card .nm").allTextContents();
check("filenames are shown", names.some((n) => n === "clip_00001.mp4"), names.join(","));

const stats = await page.locator("#stats").textContent();
check("the header counts outputs and bytes", /5 outputs/.test(stats) && /KiB|MiB|B/.test(stats), stats);

// Thumbnails are generated server-side; a broken <img> would still be a card,
// so check the pixels actually decoded.
const imgOk = await page.evaluate(() => {
  const imgs = [...document.querySelectorAll(".card .thumb img")];
  return { n: imgs.length, loaded: imgs.filter((i) => i.complete && i.naturalWidth > 0).length };
});
check("image thumbnails really load", imgOk.n >= 3 && imgOk.loaded === imgOk.n, JSON.stringify(imgOk));

const placeholders = await page.locator(".card .ph").count();
check("video/audio without a frame get a placeholder tile", placeholders === 2, `got ${placeholders}`);

// The bug that killed the first page of the other tool: an overlay covering the
// app at load. Check what a click at the centre of the grid actually hits.
const hit = await page.evaluate(() => {
  const r = document.querySelector(".card").getBoundingClientRect();
  const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { tag: el.tagName, inCard: !!el.closest(".card"), lb: document.getElementById("lightbox").className };
});
check("nothing covers the gallery at load", hit.inCard && !hit.lb.includes("on"), JSON.stringify(hit));
check("the lightbox starts closed",
  !(await page.locator("#lightbox").evaluate((el) => el.classList.contains("on"))));

// --- filters ------------------------------------------------------------
await page.click('.chip[data-kind="image"]');
await page.waitForFunction(() => document.querySelectorAll(".card").length === 3);
check("the Images filter leaves three", (await page.locator(".card").count()) === 3);
await page.click('.chip[data-kind="video"]');
await page.waitForFunction(() => document.querySelectorAll(".card").length === 1);
check("the Videos filter leaves one", (await page.locator(".card").count()) === 1);
await page.click('.chip[data-kind="all"]');
await page.waitForFunction(() => document.querySelectorAll(".card").length === 5);

await page.fill("#search", "tune");
await page.waitForFunction(() => document.querySelectorAll(".card").length === 1);
check("search narrows the grid", (await page.locator(".card").count()) === 1);
await page.fill("#search", "");
await page.waitForFunction(() => document.querySelectorAll(".card").length === 5);

const dirs = await page.locator("#dirFilter option").count();
check("the folder dropdown is populated", dirs === 3, `got ${dirs} (All + 2 folders)`);

// --- selection ----------------------------------------------------------
check("Download selected starts disabled", await page.locator("#zipBtn").isDisabled());
await page.locator('.card:has(.nm:text-is("clip_00001.mp4")) .tick').check();
await page.locator('.card:has(.nm:text-is("tune_00001.mp3")) .tick').check();
await page.waitForFunction(() => !document.getElementById("zipBtn").disabled);
const label = await page.locator("#zipBtn").textContent();
check("selecting updates the download button", /Download 2 selected/.test(label), label);
await page.click("#selNone");
check("Clear resets the selection", await page.locator("#zipBtn").isDisabled());

// --- lightbox -----------------------------------------------------------
await page.locator('.card:has(.nm:text-is("clip_00001.mp4"))').click();
await page.waitForSelector("#lightbox.on");
check("a video opens in the lightbox", (await page.locator("#lbStage video").count()) === 1);
check("the lightbox names the file", (await page.locator("#lbName").textContent()) === "clip_00001.mp4");
check("the lightbox offers a download", (await page.locator("#lbDown").count()) === 1);

await page.keyboard.press("ArrowRight");
await page.waitForFunction(() => document.getElementById("lbName").textContent !== "clip_00001.mp4");
const second = await page.locator("#lbName").textContent();
check("arrow keys move to the next item", second.length > 0, second);

await page.keyboard.press("Escape");
await page.waitForFunction(() => !document.getElementById("lightbox").classList.contains("on"));
check("Escape closes the lightbox", true);

// An image item must render as an <img> pointing at /media/.
await page.locator('.card:has(.nm:text-is("sample1.png"))').click();
await page.waitForSelector("#lightbox.on img");
const src = await page.locator("#lbStage img").getAttribute("src");
check("an image opens at its /media URL", src === "/media/2026-10-08/sample1.png", src);
const decoded = await page.evaluate(() => {
  const i = document.querySelector("#lbStage img");
  return i.complete && i.naturalWidth > 0;
});
check("the full-size image decodes in the browser", decoded);
await page.keyboard.press("Escape");

// --- the runner ---------------------------------------------------------
await page.click("#tabRun");
check("the runner view opens", await page.locator("#viewRun").isVisible());

const marker = "ui-runner-marker-" + Date.now();
await page.click("#viewRun details > summary");   // the paste box is collapsed
await page.fill("#paste", `#!/usr/bin/env bash\necho "${marker}"\necho "cwd=$(pwd)"\nexit 0\n`);
await page.fill("#runName", "ui smoke preset");
await page.waitForFunction(() => !document.getElementById("runBtn").disabled);
await page.click("#runBtn");
await page.waitForFunction(
  (m) => document.getElementById("log").textContent.includes(m),
  marker, { timeout: 60000 });
check("a pasted script runs and streams its log", true);

await page.waitForFunction(
  () => /ok|failed/.test(document.getElementById("logName").textContent), null, { timeout: 60000 });
const logName = await page.locator("#logName").textContent();
check("the run finishes as ok", /\bok\b/.test(logName), logName);
check("the log records the working directory", (await page.locator("#log").textContent()).includes("cwd="));

const rows = await page.locator("#jobs tr").count();
check("the run appears in the history table", rows >= 1, `rows=${rows}`);
const badge = await page.locator("#jobs tr").first().locator(".badge").textContent();
check("the history shows its status", badge === "ok", badge);

await page.click("#tabOut");
check("switching back shows the gallery", await page.locator("#viewOut").isVisible());

check("no uncaught JavaScript errors", errors.length === 0, errors.join(" | "));

// Screenshots for a human to eyeball; PODPANEL_SHOT sets the base name.
const shotBase = (process.env.PODPANEL_SHOT || "podpanel.png").replace(/\.png$/i, "");
fs.mkdirSync(path.dirname(shotBase) || ".", { recursive: true });
await page.click("#tabRun");
await page.screenshot({ path: shotBase + "-run.png", fullPage: true });
await page.click("#tabOut");
await page.screenshot({ path: shotBase + "-gallery.png", fullPage: true });

await browser.close();
console.log(`\nUI_RESULT ${pass} ${fail}`);
process.exit(fail === 0 ? 0 : 1);
