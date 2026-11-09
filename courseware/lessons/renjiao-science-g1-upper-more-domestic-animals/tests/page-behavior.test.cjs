// DOM behavior regressions only. These do not establish G6 visual/browser acceptance.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {execFileSync} = require('node:child_process');
const ROOT = path.resolve(__dirname, '../../../..');
const source = path.resolve(__dirname, '..');
const {JSDOM, VirtualConsole} = createRequire(path.join(ROOT, 'student-web/package.json'))('jsdom');
const lesson = JSON.parse(fs.readFileSync(path.join(source, 'lesson.json'), 'utf8'));

function openPage(t, key) {
  const program = 'import sys;from pathlib import Path;from courseware.kit.page import page;'
    + 'p=Path(sys.argv[1])/"pages";k=sys.argv[2];print(page(k,(p/(k+".html")).read_text(),'
    + '(p/(k+".css")).read_text(),(p/(k+".js")).read_text()))';
  const html = execFileSync(path.join(ROOT, 'backend/.venv/bin/python'), ['-B', '-c', program, source, key],
    {cwd: ROOT, encoding: 'utf8'});
  let timers = [], sequence = 0;
  const errors = [], console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(html, {runScripts: 'dangerously', url: 'http://lesson.test/', virtualConsole: console,
    beforeParse(window) {
      window.setTimeout = fn => {const id = ++sequence; timers.push({id, fn}); return id;};
      window.clearTimeout = id => {timers = timers.filter(timer => timer.id !== id);};
    }});
  const {window} = dom, K = window.K, $ = selector => window.document.querySelector(selector);
  const flush = () => {let rounds = 0; while (timers.length) {
    assert.ok(rounds++ < 20, 'timer queue must settle');
    const pending = timers; timers = []; pending.forEach(timer => timer.fn());
  }};
  t.after(() => {assert.deepEqual([...K.errs, ...errors], []); dom.window.close();});
  $('#start-btn').click();
  return {window, K, $, flush,
    keyPress(selector) {$(selector).dispatchEvent(new window.KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));},
    again() {$('#btn-again').click(); flush(); assert.equal(K.stars, 0);},
  };
}

test('growth teacher places each picture before describing the completed placement', () => {
  const script = lesson.scenes.find(scene => scene.key === 'p08').script;
  for (const [demo, text] of [['early', '老师先把幼小个体'], ['late', '成体放在后面的相框']]) {
    const action = script.findIndex(item => item.setState?.demo === demo);
    const speech = script.findIndex(item => item.say?.startsWith(text));
    assert.ok(action >= 0 && action < speech);
  }
});

test('picture quiz uses transfer examples outside the taught dog/hen activities', () => {
  const q3 = lesson.scenes.flatMap(scene => scene.questions || []).find(question => question.id === 'da-q3');
  assert.match(q3.question, /牛和鹅/);
  const prompts = JSON.parse(fs.readFileSync(path.join(source, 'pictures.json'), 'utf8'));
  assert.match(prompts.find(item => item.key === 'both-eat').prompt, /奶牛.*白鹅/);
  const taught = lesson.scenes.filter(scene => scene.type !== 'quiz');
  const text = JSON.stringify(taught);
  for (const picture of ['both-eat', 'goose-family', 'goose-grow', 'cow-eat', 'goose-move', 'both-move']) {
    assert.ok(!text.includes('"' + picture + '"'), 'quiz image must not be taught verbatim: ' + picture);
    for (const scene of taught.filter(scene => scene.page)) {
      for (const extension of ['html', 'js']) assert.ok(!fs.readFileSync(path.join(source, 'pages', scene.page + '.' + extension), 'utf8').includes('__IMG:' + picture + '__'));
    }
  }
});

test('album records unique observations, completes and resets', t => {
  const p = openPage(t, 'p03');
  for (const key of ['eat', 'eat', 'move', 'grow', 'family']) p.$('#album-' + key).click();
  assert.equal(p.$('#album-record').children.length, 4);
  assert.equal(p.K.stars, 4);
  p.flush(); assert.ok(p.$('#btn-again'));
  p.again(); assert.equal(p.$('#album-record').children.length, 0);
});

test('comparison first miss reveals no target; correct matches finish and reset', t => {
  const p = openPage(t, 'p05');
  const correct = () => p.$('#match-photo').getAttribute('src').match(/hen-(eat|move|grow|family)/)[1];
  p.keyPress('#match-source');
  p.$('#match-' + (correct() === 'eat' ? 'move' : 'eat')).click();
  assert.equal(p.K.stars, 0);
  assert.equal(p.window.document.querySelectorAll('.teach-hl').length, 0);
  for (let i = 0; i < 4; i++) {p.keyPress('#match-source'); p.$('#match-' + correct()).click(); p.flush();}
  assert.equal(p.$('#match-table').querySelectorAll('.match-filled').length, 4);
  p.again(); assert.equal(p.$('#match-table').querySelectorAll('.match-filled').length, 0);
});

test('growth distinguishes species and age, then fully resets the completed sequence', t => {
  const p = openPage(t, 'p08');
  p.$('#grow-chick').click();
  assert.equal(p.K.stars, 0); assert.equal(p.$('#grow-early').children.length, 0);
  assert.equal(p.window.document.querySelectorAll('.teach-hl').length, 0);
  for (const choice of ['puppy', 'dog', 'chick', 'hen']) {p.$('#grow-' + choice).click(); p.flush();}
  assert.equal(p.K.stars, 2); assert.ok(p.$('#btn-again'));
  p.again(); assert.equal(p.$('#grow-early').children.length, 0); assert.equal(p.$('#grow-late').children.length, 0);
});

test('book teacher reveals cumulative pages, play clears demo, and both books can be completed again', t => {
  const p = openPage(t, 'p10');
  for (const [demo, count] of [['look', 1], ['eat', 2], ['move', 3]]) {
    p.K.onState({demo}); assert.equal(p.$('#book-record').children.length, count);
  }
  p.K.onState({phase: 'play'}); assert.equal(p.$('#book-record').children.length, 0);
  p.keyPress('#book-choice-eat');
  assert.equal(p.K.stars, 0); assert.equal(p.$('#book-record').children.length, 0);
  assert.equal(p.window.document.querySelectorAll('.teach-hl').length, 0);
  for (let i = 0; i < 2; i++) for (const kind of ['look', 'eat', 'move']) {p.keyPress('#book-choice-' + kind); p.flush();}
  assert.equal(p.K.stars, 2); assert.ok(p.$('#btn-again'));
  p.again(); assert.equal(p.$('#book-record').children.length, 0);
  assert.match(p.$('#book-animal').getAttribute('src'), /__IMG:dog__/);
});

test('care choices first miss does not disclose answer and successful scenes reset', t => {
  const p = openPage(t, 'p12');
  p.$('#care-choice-chase').click();
  assert.equal(p.K.stars, 0); assert.equal(p.window.document.querySelectorAll('.teach-hl').length, 0);
  for (let i = 0; i < 2; i++) {p.$('#care-choice-quiet').click(); p.flush();}
  assert.equal(p.$('#care-record').children.length, 2);
  p.again(); assert.equal(p.$('#care-record').children.length, 0);
  assert.match(p.$('#care-photo').getAttribute('src'), /__IMG:chase__/);
});
