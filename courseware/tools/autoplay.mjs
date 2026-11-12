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
    const label = el.getAttribute('aria-label') || '';
    const text = (el.textContent || '').trim();
    candidateNodes.add(el);
    // Keep the child's reset control out of ordinary exploration. Replay is
    // still exercised through the finish screen on every successful run.
    if (el.matches('[data-activity-reset],button[type="reset"],input[type="reset"]')
        || (/^(重新|重置|重来|Reset\b|Restart\b)/i.test(label) && /^[↺↶⟲]$/.test(text))) continue;
    const baseClasses = [...el.classList].filter((name) => !stateClass.test(name)).sort().join('.');
    const parent = el.parentElement;
    const parentKey = parent && (parent.id ? `#${parent.id}` : `.${[...parent.classList].filter((name) => !stateClass.test(name)).sort().join('.') || parent.tagName}`);
    const group = `${parentKey || '#play'}|${el.tagName}|${baseClasses || '-'}`;
    const position = positions[group] || 0;
    positions[group] = position + 1;
    candidates.push({
      group, position, id: el.id || '', label, text,
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
    feedbackRevision: window.__miraAutoplayFeedbackRevision || 0,
  };
};

// Real-time pages built on the shared game engine (courseware/kit/game.py, K.game) cannot be finished by blind
// tapping. For them the bot first presses, drags and types at random to surface script errors, then lets the engine's
// own autopilot play every level from level 1, presses 'play again' and requires a second complete run. Engine frame
// errors arrive in K.errs. The receipt records the method, so it never claims that random play finished a game.
const GAME_RANDOM_INPUTS = 40;
const GAME_SECONDS_PER_LEVEL = Number(args['game-seconds-per-level'] || 150);
const playGame = async (page, file, errors) => {
  const result = { file, finishes: [], errors, stuck: null, method: 'game-autopilot', seconds: [] };
  const status = () => page.evaluate(() => window.K.game.status());
  const finished = async () => (await page.evaluate(snapshot)).finished;
  const engineErrors = () => page.evaluate(() => (window.K.errs || []).map(String));
  let inputs = 0;
  for (; inputs < GAME_RANDOM_INPUTS && !(await finished()); inputs += 1) {
    const x = 20 + rand() * 1240;
    const y = 20 + rand() * 680;
    if (rand() < 0.3) {
      await page.mouse.move(x, y); await page.mouse.down();
      await page.mouse.move(20 + rand() * 1240, 20 + rand() * 680, { steps: 6 }); await page.mouse.up();
    } else await page.mouse.click(x, y);
    if (rand() < 0.3) await page.keyboard.press(['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'][Math.floor(rand() * 5)]);
    await page.waitForTimeout(120);
  }
  const { levels } = await status();
  const expected = Array.from({ length: levels }, (_, i) => i + 1);
  if (await finished()) await page.locator('#btn-again').click();
  let logStart = await page.evaluate(() => window.K.log.length);
  for (let round = 1; round <= 2 && !result.stuck; round += 1) {
    const started = Date.now();
    if (round === 1) await page.evaluate(() => { window.K.game.autoplay(true); window.K.onState({ level: 1 }); });
    while (Date.now() - started < levels * GAME_SECONDS_PER_LEVEL * 1000 && !(await finished())) {
      if (errors.length || (await engineErrors()).length) break;
      await page.waitForTimeout(250);
    }
    if (!(await finished())) { result.stuck = `game autopilot did not finish round ${round}`; break; }
    const won = await page.evaluate((from) => window.K.log.slice(from).filter((x) => x.startsWith('win:'))
      .map((x) => Number(x.split(':')[1])), logStart);
    const final = await status();
    if (final.state !== 'done' || final.stars.length !== levels || expected.some(i => ![1, 2, 3].includes(final.stars[i - 1])) ||
        won.length !== levels || expected.some((level, index) => won[index] !== level)) {
      result.stuck = `game autopilot round ${round} needs one win per level in order (${won.join(', ')}; expected ${expected.join(', ')})`;
      break;
    }
    result.finishes.push(inputs + round);
    result.seconds.push(Math.round((Date.now() - started) / 1000));
    if (round === 2) break;
    const again = await page.$('#btn-again');
    if (!again) { result.stuck = 'no play-again button'; break; }
    logStart = await page.evaluate(() => window.K.log.length);
    await again.click();
    const restart = await page.$('#ready button');
    if (restart && await restart.isVisible()) await restart.click();
    if (await finished()) { result.stuck = 'finish still showing after play again'; break; }
    const now = await status();
    const replayStarted = await page.evaluate(from => window.K.log.slice(from).includes('level:1'), logStart);
    if (!replayStarted || !now.auto) result.stuck = `play again did not restart level 1 (${now.state} ${now.level})`;
  }
  errors.push(...await engineErrors());
  return result;
};

// Guided media activities have their own completion contract. Exercise the
// child's controls and observe real playback from start through the media end.
const guidedSelector = '[data-guided-media-activity]';
async function playGuidedMedia(page, file, errors) {
  const result = { file, finishes: [], errors, stuck: null, method: 'guided-media', seconds: [] };
  const root = page.locator(guidedSelector);
  const media = root.locator('audio[data-guided-media]');
  const trigger = root.locator('[data-media-trigger]');
  for (let round = 1; round <= 2; round += 1) {
    const started = Date.now();
    try {
      if (round === 2) await page.reload();
      await media.evaluate(element => {
        if (!element.paused || element.currentTime !== 0) throw new Error('media started before the child acted');
        const events = { played: false, ended: false, altered: false };
        element.__miraGuidedEvents = events;
        element.addEventListener('playing', () => { events.played = true; });
        element.addEventListener('ended', () => { events.ended = true; });
        for (const type of ['seeking', 'ratechange']) {
          element.addEventListener(type, () => { events.altered = true; });
        }
      }, undefined, { timeout: 5000 });
      await page.evaluate(() => window.postMessage({type:'SET_WIDGET_STATE', state:{activityReady:true}}, '*'));
      await page.waitForFunction(selector => document.querySelector(selector)?.dataset.phase === 'ready', guidedSelector,
                                 { timeout: 5000 });
      const gesture = root.locator('[data-media-gesture]');
      if (round === 1 && await gesture.count()) {
        const bounds = await gesture.boundingBox({ timeout: 5000 });
        if (!bounds) throw new Error('guided gesture is hidden');
        const x = bounds.x + bounds.width / 2;
        const y = bounds.y + bounds.height / 2;
        await page.mouse.move(x, y);
        await page.mouse.down();
        await page.mouse.move(x, Math.min(700, y + 156), { steps: 12 });
        await page.mouse.up();
      } else {
        await trigger.click({ timeout: 5000 });
      }
      await page.waitForFunction(selector => {
        const phase = document.querySelector(selector)?.dataset.phase;
        return phase === 'done' || phase === 'error';
      }, guidedSelector, { timeout: 95000 });
      const played = await media.evaluate(element => {
        const events = element.__miraGuidedEvents;
        return events.played && events.ended && !events.altered && element.ended
          && !element.muted && element.volume > 0 && element.playbackRate === 1;
      });
      if (!played || await root.getAttribute('data-phase') !== 'done') {
        throw new Error('activity did not finish with complete, unaltered media playback');
      }
      result.finishes.push(round);
      result.seconds.push(Math.round((Date.now() - started) / 1000));
    } catch (error) {
      result.stuck = 'guided media round ' + round + ': ' + String(error.message).split('\n')[0];
      break;
    }
  }
  for (const message of await page.evaluate(() => (window.K?.errs || []).map(String))) errors.push(message);
  return result;
}

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
  await page.evaluate(() => {
    const feedback = document.querySelector('#say');
    if (!feedback) return;
    window.__miraAutoplayFeedbackRevision = 0;
    new MutationObserver(() => { window.__miraAutoplayFeedbackRevision += 1; })
      .observe(feedback, { childList: true, characterData: true, subtree: true });
  });
  if (args.inspect === '1') {
    report.push({ file, snapshot: await page.evaluate(snapshot) });
    await page.close();
    continue;
  }
  if (await page.locator(guidedSelector).count()) {
    report.push(await playGuidedMedia(page, file, errors));
    await page.close();
    continue;
  }
  if (await page.evaluate(() => !!(window.K && window.K.game && typeof window.K.game.status === 'function'
      && window.K.game.status()))) {
    report.push(await playGame(page, file, errors));
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
    if (after.finished) return { changed: true, after };
    const newMessage = before.sayKind !== after.sayKind || before.sayText !== after.sayText;
    // A correct intermediate action can repeat the same visible feedback
    // before any star or level changes. It only guides the next exploration.
    const success = after.sayKind === 'ok' && (newMessage || after.feedbackRevision !== before.feedbackRevision);
    if (advanced(before, after) || success) {
      wrongs = 0;
      await page.waitForTimeout(1200);
      after = await page.evaluate(snapshot);
    } else if (newMessage && after.sayKind === 'no') {
      wrongs += 1;
      await page.waitForTimeout(wrongs % 3 === 0 ? 1900 : 300);
      after = await page.evaluate(snapshot);
    }
    return { changed: success || advanced(before, after), after };
  };
  const click = async (reference) => {
    if (steps >= maxSteps) return { changed: false, after: await page.evaluate(snapshot) };
    const before = await page.evaluate(snapshot);
    const current = before.candidates.find((item) => reference.id && item.id === reference.id)
      || before.candidates.find((item) => item.group === reference.group && item.position === reference.position);
    if (!current) return { changed: false, after: before };
    await page.mouse.click(current.x, current.y);
    steps += 1;
    return settle(before);
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
    return settle(before);
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
      // A drag may build a quantity without completing the level. Try the
      // visible answer groups at each intermediate state, before another drag
      // changes it. Singleton controls (often reset/undo) must not erase that
      // state before the choices have been explored. No answer is read here.
      const choices = grouped(outcome.after.candidates.filter((item) => !item.canvas && !item.draggable))
        .filter((group) => group.members.length >= 2 && group.members.length <= 12);
      for (const group of choices) for (const member of shuffle(group.members)) {
        const response = await click(member);
        if (response.changed || response.after.finished) return true;
      }
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
