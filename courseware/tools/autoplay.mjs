// A random-play bot for the interactive pages of a lesson (run by courseware/tools/autoplay.py).
// It opens each saved page, presses start, then taps and drags at random until the finish overlay shows, presses "play
// again" and plays on until the finish shows a second time. A page that never finishes (a soft lock), throws, or does not
// reset has a defect a child would meet. Prints one JSON array: [{file, finishes, errors, stuck}].
// Usage: node autoplay.mjs --playwright <dir holding node_modules/playwright-core> --chrome <executable> --dir <pages> [--max-steps N] [--seed N]
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, i, all) => (value.startsWith('--') ? [...pairs, [value.slice(2), all[i + 1]]] : pairs), []));
const require = createRequire(path.join(args.playwright, 'package.json'));
const { chromium } = require('playwright-core');
const maxSteps = Number(args['max-steps'] || 400);
let seed = Number(args.seed || 7);
const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const pick = (list) => list[Math.floor(rand() * list.length)];

const finished = () => { const f = document.querySelector('#finish'); return !!f && !f.classList.contains('gone') && getComputedStyle(f).display !== 'none'; };
const visibleRect = (el) => {
  const style = getComputedStyle(el);
  if (style.visibility === 'hidden' || style.display === 'none' || style.pointerEvents === 'none') return null;
  const r = el.getBoundingClientRect();
  if (r.right < 0 || r.bottom < 0 || r.left > 1280 || r.top > 720) return null;
  return r;
};
const candidates = () => {
  const out = [];
  for (const el of document.querySelectorAll('#play *, #finish *')) {
    const r = visibleRect(el);
    if (!r || r.width < 24 || r.height < 24) continue;
    const style = getComputedStyle(el);
    if (!(['pointer', 'grab'].includes(style.cursor) || ['BUTTON', 'CANVAS'].includes(el.tagName) || el.getAttribute('role') === 'button')) continue;
    out.push({ x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, canvas: el.tagName === 'CANVAS' });
  }
  return out;
};
const bigThings = () => {
  const out = [];
  for (const el of document.querySelectorAll('#play *')) {
    const r = visibleRect(el);
    if (!r || r.width < 60 || r.height < 60 || r.width > 700 || r.height > 560) continue;
    out.push({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
  }
  return out;
};

const browser = await chromium.launch({ executablePath: args.chrome, headless: true });
const files = fs.readdirSync(args.dir).filter((f) => /^scene-\d+\.html$/.test(f)).sort();
const report = [];
for (const file of files) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e.message)));
  await page.goto(pathToFileURL(path.join(args.dir, file)).href);
  await page.waitForTimeout(500);
  const start = await page.$('#ready button');
  if (start) { await start.click(); await page.waitForTimeout(500); }
  const result = { file, finishes: [], errors, stuck: null };
  let steps = 0, rounds = 0;
  while (steps < maxSteps && rounds < 2 && !result.stuck) {
    if (await page.evaluate(finished)) {
      rounds += 1;
      result.finishes.push(steps);
      if (rounds === 2) break;
      const again = await page.$('#btn-again');
      if (!again) { result.stuck = 'no play-again button'; break; }
      await again.click();
      await page.waitForTimeout(500);
      const restart = await page.$('#ready button');
      if (restart && await restart.isVisible()) { await restart.click(); await page.waitForTimeout(400); }
      if (await page.evaluate(finished)) result.stuck = 'finish still showing after play again';
      continue;
    }
    const list = await page.evaluate(candidates);
    steps += 1;
    if (!list.length) { await page.waitForTimeout(250); if (steps > 40 && !result.finishes.length) result.stuck = 'nothing to tap'; continue; }
    const canvases = list.filter((c) => c.canvas);
    if (canvases.length && rand() < 0.6) {
      // A drawing page: scribble over the whole drawing area, then press every button once in random order.
      const a = canvases[canvases.length - 1];
      const x0 = a.x - a.w * 0.45, y0 = a.y - a.h * 0.45;
      await page.mouse.move(x0, y0); await page.mouse.down();
      for (let row = 0; row < 12; row++) {
        const y = y0 + (a.h * 0.9) * (row / 11);
        await page.mouse.move(row % 2 ? x0 : x0 + a.w * 0.9, y, { steps: 8 });
        await page.mouse.move(row % 2 ? x0 + a.w * 0.9 : x0, y, { steps: 8 });
      }
      await page.mouse.up();
      for (const b of list.filter((c) => !c.canvas).sort(() => rand() - 0.5)) { await page.mouse.click(b.x, b.y); await page.waitForTimeout(150); }
      await page.waitForTimeout(1300);
      continue;
    }
    const a = pick(list);
    if (a.canvas) {
      await page.mouse.move(a.x - a.w * 0.4, a.y); await page.mouse.down();
      await page.mouse.move(a.x + a.w * 0.4, a.y + a.h * 0.2, { steps: 12 }); await page.mouse.up();
    } else if (rand() < 0.5 && list.length > 1) {
      const big = rand() < 0.5 ? await page.evaluate(bigThings) : [];
      const b = big.length ? pick(big) : pick(list.filter((c) => c !== a));
      await page.mouse.move(a.x, a.y); await page.mouse.down();
      await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 4 });
      await page.mouse.move(b.x, b.y, { steps: 4 }); await page.mouse.up();
    } else {
      await page.mouse.click(a.x, a.y);
    }
    await page.waitForTimeout(130);
  }
  if (!result.finishes.length && !result.stuck) result.stuck = `never finished in ${steps} steps`;
  report.push(result);
  await page.close();
}
await browser.close();
console.log(JSON.stringify(report));
