// Randomized systematic play-through of every interactive page (run by autoplay.py).
// The bot uses only the shared page contract: visible controls, level dots and drag registrations made by K.drag.
// It has no lesson-specific answers. It verifies finish -> play again -> finish and prints one JSON array.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const argv = process.argv.slice(2);
const args = Object.fromEntries(argv.reduce((pairs, value, i, all) =>
  value.startsWith('--') ? [...pairs, [value.slice(2), all[i + 1]]] : pairs, []));
const maxSteps = Number(args['max-steps'] || 400);
let seed = Number(args.seed || 7);
const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const shuffle = (values) => {
  const copy = [...values];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
};
const grouped = (items) => {
  const groups = new Map();
  for (const item of items) {
    if (!groups.has(item.group)) groups.set(item.group, []);
    groups.get(item.group).push(item);
  }
  return [...groups.entries()].map(([key, members]) => ({ key, members }))
    .sort((a, b) => b.members.length - a.members.length || a.key.localeCompare(b.key));
};
const hintFirst = (members, hints) => {
  if (hints.length !== 1) return shuffle(members);
  const number = String(hints[0]);
  const matches = (item) => item.text === number || new RegExp(`(?:^|\\D)${number}$`).test(`${item.id} ${item.label}`);
  return [...members.filter(matches), ...shuffle(members.filter((item) => !matches(item)))];
};

if (argv.includes('--self-test')) {
  const groups = grouped([{ group: 'a' }, { group: 'b' }, { group: 'a' }]);
  const ordered = hintFirst([
    { id: 'station-2', label: '车站 2', text: '' },
    { id: 'station-6', label: '车站 6', text: '' },
  ], [6]);
  if (groups[0].key !== 'a' || groups[0].members.length !== 2 || ordered[0].id !== 'station-6') process.exit(1);
  console.log(JSON.stringify({ ok: true, groups: groups.length, first: ordered[0].id }));
  process.exit(0);
}

const require = createRequire(path.join(args.playwright, 'package.json'));
const { chromium } = require('playwright-core');

// This function runs inside the lesson page and returns only serializable state.
const snapshot = () => {
  const visibleRect = (el) => {
    const style = getComputedStyle(el);
    if (el.disabled || style.visibility === 'hidden' || style.display === 'none' || style.pointerEvents === 'none') return null;
    const rect = el.getBoundingClientRect();
    if (rect.width < 24 || rect.height < 24 || rect.right < 0 || rect.bottom < 0 || rect.left > 1280 || rect.top > 720) return null;
    return rect;
  };
  const stateClass = /^(active|chosen|counted|flagged|marked|on|paired|placed|selected|stored|success|turned)$/;
  const dragEntries = window.K && Array.isArray(window.K.drags) ? window.K.drags : [];
  const liveDragElements = new Set(dragEntries.filter((entry) => entry && entry.el && entry.el.isConnected).map((entry) => entry.el));
  const candidates = [];
  const candidateNodes = new Set();
  const positions = {};
  for (const el of document.querySelectorAll('#play *')) {
    const owningControl = el.closest('button,[role="button"]');
    if (owningControl && owningControl !== el) continue;
    const rect = visibleRect(el);
    if (!rect) continue;
    const style = getComputedStyle(el);
    const clickable = el.tagName === 'BUTTON' || el.tagName === 'CANVAS' || el.getAttribute('role') === 'button'
      || ['pointer', 'grab'].includes(style.cursor) || style.touchAction === 'none';
    if (!clickable) continue;
    const baseClasses = [...el.classList].filter((name) => !stateClass.test(name)).sort().join('.');
    const parent = el.parentElement;
    const parentKey = parent && (parent.id ? `#${parent.id}` : `.${[...parent.classList].filter((name) => !stateClass.test(name)).sort().join('.') || parent.tagName}`);
    const group = `${parentKey || '#play'}|${el.tagName}|${baseClasses || '-'}`;
    const position = positions[group] || 0;
    positions[group] = position + 1;
    candidateNodes.add(el);
    candidates.push({
      group, position, id: el.id || '', label: el.getAttribute('aria-label') || '', text: (el.textContent || '').trim(),
      x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, w: rect.width, h: rect.height,
      canvas: el.tagName === 'CANVAS', draggable: liveDragElements.has(el),
      active: [...el.classList].some((name) => stateClass.test(name)),
    });
  }
  const drags = [];
  for (const entry of dragEntries) {
    if (!entry || !entry.el || !entry.el.isConnected || !entry.options) continue;
    const source = visibleRect(entry.el);
    if (!source) continue;
    try {
      if (entry.options.enabled && !entry.options.enabled(entry.el)) continue;
      const targets = (entry.options.targets ? entry.options.targets() : []).filter((target) => target && target.isConnected)
        .map((target, index) => {
          const rect = visibleRect(target);
          return rect ? {
            id: target.id || '', key: `${target.id || target.getAttribute('aria-label') || target.className || target.tagName}:${index}`,
            x: rect.left + rect.width / 2, y: rect.top + rect.height / 2,
          } : null;
        }).filter(Boolean);
      if (targets.length) drags.push({
        id: entry.el.id || '', key: entry.el.id || entry.el.getAttribute('aria-label') || entry.el.className || entry.el.tagName,
        text: (entry.el.textContent || '').trim(),
        x: source.left + source.width / 2, y: source.top + source.height / 2, targets,
      });
    } catch (_) { /* A changing level may briefly have no targets. */ }
  }
  const numbers = [];
  for (const el of document.querySelectorAll('#play *')) {
    if (el.children.length || [...candidateNodes].some((candidate) => candidate === el || candidate.contains(el))) continue;
    if (!visibleRect(el)) continue;
    const match = (el.textContent || '').trim().match(/(?:^|\D)(\d{1,2})(?:\D|$)/);
    if (match) numbers.push(Number(match[1]));
  }
  const visualCounts = [];
  for (const container of document.querySelectorAll('#play *')) {
    if ([...candidateNodes].some((candidate) => candidate.contains(container))) continue;
    const children = [...container.children].filter((child) => visibleRect(child));
    if (children.length >= 2 && children.length <= 12 && children.every((child) => !candidateNodes.has(child))) {
      visualCounts.push(children.length);
    }
  }
  const finish = document.querySelector('#finish');
  const say = document.querySelector('#say');
  return {
    candidates, drags, hints: [...new Set(numbers)], visualCounts: [...new Set(visualCounts)],
    finished: !!finish && !finish.classList.contains('gone') && getComputedStyle(finish).display !== 'none',
    done: document.querySelectorAll('#dots i.done').length,
    stars: Number((document.querySelector('#star-n') || {}).textContent || 0),
    sayKind: say ? say.className : '',
    sayText: say ? say.textContent : '',
  };
};

const browser = await chromium.launch({ executablePath: args.chrome, headless: true });
const files = fs.readdirSync(args.dir).filter((file) => /^scene-\d+\.html$/.test(file)).sort();
const report = [];

for (const file of files) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error.message)));
  await page.goto(pathToFileURL(path.join(args.dir, file)).href);
  await page.waitForTimeout(300);
  const start = await page.$('#ready button');
  if (start) { await start.click(); await page.waitForTimeout(300); }
  if (args.inspect === '1') {
    report.push({ file, snapshot: await page.evaluate(snapshot) });
    await page.close();
    continue;
  }
  const result = { file, finishes: [], errors, stuck: null };
  let steps = 0;
  let rounds = 0;
  let wrongs = 0;

  const advanced = (before, after) => after.finished || after.done > before.done || after.stars > before.stars;
  const settle = async (before) => {
    await page.waitForTimeout(90);
    let after = await page.evaluate(snapshot);
    if (after.finished) return after;
    const newMessage = before.sayKind !== after.sayKind || before.sayText !== after.sayText;
    if (advanced(before, after) || (newMessage && after.sayKind === 'ok')) {
      wrongs = 0;
      await page.waitForTimeout(1200);
      after = await page.evaluate(snapshot);
    } else if (newMessage && after.sayKind === 'no') {
      wrongs += 1;
      await page.waitForTimeout(wrongs % 3 === 0 ? 1900 : 300);
      after = await page.evaluate(snapshot);
    }
    return after;
  };
  const click = async (reference) => {
    if (steps >= maxSteps) return { changed: false, after: await page.evaluate(snapshot) };
    const before = await page.evaluate(snapshot);
    const current = before.candidates.find((item) => reference.id && item.id === reference.id)
      || before.candidates.find((item) => item.group === reference.group && item.position === reference.position);
    if (!current) return { changed: false, after: before };
    await page.mouse.click(current.x, current.y);
    steps += 1;
    const after = await settle(before);
    return { changed: advanced(before, after), after };
  };
  const scribble = async (reference) => {
    if (steps >= maxSteps) return;
    const now = await page.evaluate(snapshot);
    const canvas = now.candidates.find((item) => reference.id && item.id === reference.id)
      || now.candidates.find((item) => item.group === reference.group && item.position === reference.position);
    if (!canvas) return;
    const left = canvas.x - canvas.w * 0.45;
    const top = canvas.y - canvas.h * 0.45;
    await page.mouse.move(left, top); await page.mouse.down();
    await page.evaluate(({ x, y, width, height }) => {
      const target = document.elementFromPoint(x, y);
      if (!target) return;
      for (let row = 0; row < 40; row += 1) for (let column = 0; column < 40; column += 1) {
        const offset = row % 2 ? 39 - column : column;
        target.dispatchEvent(new PointerEvent('pointermove', {
          bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', buttons: 1,
          clientX: x + width * (offset / 39), clientY: y + height * (row / 39),
        }));
      }
    }, { x: left, y: top, width: canvas.w * 0.9, height: canvas.h * 0.9 });
    await page.mouse.up();
    steps += 1;
    await page.waitForTimeout(100);
  };
  const drag = async (sourceKey, targetKey) => {
    if (steps >= maxSteps) return { changed: false, after: await page.evaluate(snapshot) };
    const before = await page.evaluate(snapshot);
    const source = before.drags.find((item) => item.key === sourceKey);
    const target = source && source.targets.find((item) => item.key === targetKey);
    if (!source || !target) return { changed: false, after: before };
    await page.mouse.move(source.x, source.y); await page.mouse.down();
    await page.mouse.move((source.x + target.x) / 2, (source.y + target.y) / 2, { steps: 4 });
    await page.mouse.move(target.x, target.y, { steps: 4 }); await page.mouse.up();
    steps += 1;
    const after = await settle(before);
    return { changed: advanced(before, after), after };
  };
  const dragSweep = async () => {
    const tried = new Set();
    for (let attempt = 0; attempt < 40 && steps < maxSteps; attempt += 1) {
      const now = await page.evaluate(snapshot);
      if (now.finished) return true;
      const visibleQuantities = new Set(grouped(now.candidates.filter((item) => !item.canvas && !item.draggable))
        .map((group) => group.members.length).filter((count) => count >= 2));
      const pairs = [];
      for (const source of now.drags) for (const target of source.targets) {
        const key = `${source.key}->${target.key}`;
        const sourceNumber = /^\s*(\d{1,2})\s*$/.exec(source.text || '');
        const targetNumbers = [...target.key.matchAll(/\d{1,2}/g)].map((match) => Number(match[0]));
        const score = targetNumbers.some((number) => visibleQuantities.has(number)) ? 2
          : sourceNumber && targetNumbers.includes(Number(sourceNumber[1])) ? 1 : 0;
        if (!tried.has(key)) pairs.push({ source, target, key, score });
      }
      if (!pairs.length) return false;
      const pair = shuffle(pairs).sort((a, b) => b.score - a.score)[0];
      tried.add(pair.key);
      for (const canvas of now.candidates.filter((item) => item.canvas)) await scribble(canvas);
      const outcome = await drag(pair.source.key, pair.target.key);
      if (outcome.changed || outcome.after.finished) return true;
    }
    return false;
  };
  const reverseControls = async () => {
    const now = await page.evaluate(snapshot);
    for (const control of now.candidates.filter((item) => !item.canvas && !item.draggable).reverse().slice(0, 16)) {
      const outcome = await click(control);
      if (outcome.changed || outcome.after.finished) return true;
    }
    return false;
  };
  const sweep = async (group, reverse) => {
    for (const member of reverse ? [...group.members].reverse() : group.members) {
      const outcome = await click(member);
      if (outcome.changed || outcome.after.finished) return true;
    }
    return false;
  };
  const prefixTrial = async (main, controls, hints) => {
    if (!controls.length) return false;
    const preferred = hints.length === 1 && hints[0] > 0 && hints[0] <= main.members.length ? [hints[0]] : [];
    const counts = [...new Set([...preferred, ...Array.from({ length: main.members.length }, (_, index) => index + 1)])];
    for (const count of counts) for (const control of controls.slice(0, 4)) {
      let now = await page.evaluate(snapshot);
      for (const item of now.candidates.filter((candidate) => candidate.group === main.key && candidate.active)) {
        const outcome = await click(item);
        if (outcome.changed || outcome.after.finished) return true;
      }
      now = await page.evaluate(snapshot);
      for (const item of now.candidates.filter((candidate) => candidate.group === main.key).slice(0, count)) {
        const outcome = await click(item);
        if (outcome.changed || outcome.after.finished) return true;
      }
      const outcome = await click(control);
      if (outcome.changed || outcome.after.finished) return true;
    }
    return false;
  };
  const pairGroups = async (left, right, hints) => {
    for (const first of hintFirst(left.members, hints)) {
      let selected = false;
      let seconds = shuffle(right.members);
      for (let index = 0; index < seconds.length; index += 1) {
        let outcome = await click(first);
        if (outcome.changed || outcome.after.finished) return true;
        if (!selected) {
          const counts = outcome.after.visualCounts || [];
          seconds = [...seconds.filter((item) => counts.includes(Number(item.text))),
            ...seconds.filter((item) => !counts.includes(Number(item.text)))];
          selected = true;
        }
        outcome = await click(seconds[index]);
        if (outcome.changed || outcome.after.finished) return true;
      }
    }
    return false;
  };

  while (steps < maxSteps && rounds < 2 && !result.stuck) {
    let now = await page.evaluate(snapshot);
    if (now.finished) {
      rounds += 1;
      result.finishes.push(steps);
      if (rounds === 2) break;
      const again = await page.$('#btn-again');
      if (!again) { result.stuck = 'no play-again button'; break; }
      await again.click(); await page.waitForTimeout(400);
      const restart = await page.$('#ready button');
      if (restart && await restart.isVisible()) { await restart.click(); await page.waitForTimeout(300); }
      if ((await page.evaluate(snapshot)).finished) result.stuck = 'finish still showing after play again';
      wrongs = 0;
      continue;
    }
    const firstGroups = grouped(now.candidates.filter((item) => !item.canvas));
    const firstMain = firstGroups[0];
    const firstControls = firstGroups.slice(1).flatMap((group) => group.members)
      .filter((item) => !item.draggable).reverse();
    const containerGroup = firstGroups.find((group) => now.drags.some((source) => source.id && group.key.startsWith(`#${source.id}|`)));
    if (containerGroup) {
      if (await sweep(containerGroup, false)) continue;
      if (await dragSweep()) continue;
    }
    if (!now.drags.length && now.candidates.some((item) => item.canvas)) {
      for (const canvas of now.candidates.filter((item) => item.canvas)) await scribble(canvas);
      if (await reverseControls()) continue;
    }
    if (firstGroups.length === 1) {
      if (await sweep(firstGroups[0], false)) continue;
      if (await sweep(firstGroups[0], true)) continue;
    }
    if (firstMain && firstMain.members.length >= 4 && firstControls.length > 0 && firstControls.length <= 3
        && await prefixTrial(firstMain, firstControls, now.hints)) continue;
    if (firstGroups.length === 2 && firstGroups.every((group) => group.members.length >= 2) && now.hints.length === 1
        && await pairGroups(firstGroups[0], firstGroups[1], now.hints)) continue;
    if (await dragSweep()) continue;
    if (await reverseControls()) continue;
    if (await dragSweep()) continue;

    now = await page.evaluate(snapshot);
    const groups = grouped(now.candidates.filter((item) => !item.canvas));
    const main = groups[0];
    const others = groups.slice(1).flatMap((group) => group.members).reverse();
    if (main && main.members.length >= 4 && others.length <= 3 && await prefixTrial(main, others, now.hints)) continue;

    let changed = false;
    for (const group of groups.slice(0, 4)) {
      for (const reverse of shuffle([false, true])) {
        if (await sweep(group, reverse)) { changed = true; break; }
      }
      if (changed) break;
    }
    if (changed) continue;
    if (await dragSweep()) continue;

    now = await page.evaluate(snapshot);
    const pairable = grouped(now.candidates.filter((item) => !item.canvas)).filter((group) => group.members.length >= 2).slice(0, 3);
    for (let left = 0; left < pairable.length && !changed; left += 1) for (let right = left + 1; right < pairable.length; right += 1) {
      if (await pairGroups(pairable[left], pairable[right], now.hints)) { changed = true; break; }
    }
    if (changed) continue;

    now = await page.evaluate(snapshot);
    const finalGroups = grouped(now.candidates.filter((item) => !item.canvas));
    if (finalGroups[0] && finalGroups[0].members.length >= 4
        && await prefixTrial(finalGroups[0], finalGroups.slice(1).flatMap((group) => group.members).reverse(), now.hints)) continue;
    const fallback = shuffle(now.candidates.filter((item) => !item.canvas))[0];
    if (fallback) await click(fallback);
    else { await page.waitForTimeout(200); steps += 1; }
  }

  if (!result.finishes.length && !result.stuck) result.stuck = `never finished in ${steps} steps`;
  else if (rounds < 2 && !result.stuck) result.stuck = `no second finish after ${steps} steps`;
  report.push(result);
  await page.close();
}
await browser.close();
console.log(JSON.stringify(report));
