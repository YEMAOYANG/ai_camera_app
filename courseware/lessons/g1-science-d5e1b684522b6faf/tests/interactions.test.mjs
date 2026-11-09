import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const require = createRequire(path.join(root, 'student-web/package.json'));
const { JSDOM } = require('jsdom');
const source = path.join(root, 'courseware/lessons/g1-science-d5e1b684522b6faf');
const pause = () => new Promise(resolve => setTimeout(resolve, 50));
function page(id) {
  const html = execFileSync(path.join(root, 'backend/.venv/bin/python'), ['-B', '-c', 'from pathlib import Path;from courseware.kit.page import page;import sys;p=Path(sys.argv[1]);k=sys.argv[2];print(page(k,(p/"pages"/(k+".html")).read_text(),(p/"pages"/(k+".css")).read_text(),(p/"pages"/(k+".js")).read_text()))', source, id], { cwd: root, encoding: 'utf8' });
  const dom = new JSDOM(html, { runScripts: 'dangerously', beforeParse(window) {
    const native = window.setTimeout.bind(window);
    window.setTimeout = (callback, ms, ...args) => native(callback, ms >= 800 ? 10 : ms, ...args);
  }});
  const win = dom.window;
  const click = selector => {
    const el = win.document.querySelector(selector);
    assert.ok(el, selector);
    el.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
  };
  click('#start-btn');
  return { dom, win, click, $: selector => win.document.querySelector(selector) };
}

test('observation game keeps first miss neutral, moves images, completes and resets', async () => {
  const p = page('p02');
  try {
    p.click('#nature-1');
    assert.equal(p.win.K.stars, 0);
    assert.equal(p.$('#collected-pictures').children.length, 0);
    assert.ok(!p.$('#nature-0').classList.contains('teach-hl'));
    for (const id of [0, 1, 2]) { p.click('#nature-' + id); await pause(); }
    assert.ok(p.$('#finish') && !p.$('#finish').classList.contains('gone'));
    assert.equal(p.$('#collected-pictures').children.length, 3);
    p.click('#btn-again');
    assert.equal(p.win.K.stars, 0);
    assert.equal(p.$('#collected-pictures').children.length, 0);
    assert.equal(p.win.document.querySelectorAll('#nature-choices img').length, 3);
    p.win.K.onState({ demo: 'match' });
    p.win.K.onState({ demo: 'match' });
    assert.equal(p.$('#collected-pictures').children.length, 1);
    p.win.K.onState({ phase: 'play' });
    assert.equal(p.$('#collected-pictures').children.length, 0);
    assert.deepEqual(Array.from(p.win.K.errs), []);
  } finally { p.dom.window.close(); }
});

test('sequence game permits swapping assigned cards and resets teacher state', async () => {
  const p = page('p05');
  const place = (key, slot) => { p.click('#step-card-' + key); p.click('#step-slot-' + slot); };
  try {
    place('try', 0); place('guess', 1); place('observe', 2); p.click('#check-sequence');
    assert.equal(p.win.K.stars, 0);
    assert.equal(p.$('#step-slot-0 .step-card').dataset.step, 'try');
    place('guess', 0);
    assert.equal(p.$('#step-slot-1 .step-card').dataset.step, 'try');
    p.click('#check-sequence'); await pause();
    assert.ok(p.$('#finish') && !p.$('#finish').classList.contains('gone'));
    p.click('#btn-again');
    assert.equal(p.win.document.querySelectorAll('.step-slot .step-card').length, 0);
    assert.equal(p.$('#steps-tray').children.length, 3);
    p.win.K.onState({ demo: 'first' });
    assert.equal(p.$('#step-slot-0 .step-card').dataset.step, 'guess');
    p.win.K.onState({ phase: 'play' });
    assert.equal(p.$('#steps-tray').children.length, 3);
    assert.deepEqual(Array.from(p.win.K.errs), []);
  } finally { p.dom.window.close(); }
});

test('record game rejects mismatching evidence then completes all three forms and replays', async () => {
  const p = page('p07');
  try {
    p.click('#record-out'); p.click('#discovery-book');
    assert.equal(p.win.K.stars, 0);
    assert.equal(p.$('#saved-records').children.length, 0);
    assert.ok(!p.$('#record-in').classList.contains('teach-hl'));
    for (const key of ['in', 'out', 'still']) {
      p.click('#record-' + key); p.click('#discovery-book');
      assert.equal(p.$('#saved-records').children.length, 1);
      await pause();
    }
    assert.ok(p.$('#finish') && !p.$('#finish').classList.contains('gone'));
    p.click('#btn-again');
    assert.equal(p.win.K.stars, 0);
    assert.equal(p.$('#saved-records').children.length, 0);
    p.win.K.onState({ demo: 'record' }); p.win.K.onState({ demo: 'record' });
    assert.equal(p.$('#saved-records').children.length, 1);
    p.win.K.onState({ phase: 'play' });
    assert.equal(p.$('#saved-records').children.length, 0);
    assert.deepEqual(Array.from(p.win.K.errs), []);
  } finally { p.dom.window.close(); }
});
