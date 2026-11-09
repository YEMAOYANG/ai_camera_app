const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {createRequire} = require('node:module');

const lessonDir = path.resolve(__dirname, '..');
const root = path.resolve(lessonDir, '../../..');
const {JSDOM, VirtualConsole} = createRequire(path.join(root, 'student-web/package.json'))('jsdom');
const lesson = JSON.parse(fs.readFileSync(path.join(lessonDir, 'lesson.json'), 'utf8'));

function page(t, key) {
  const source = `from pathlib import Path
import sys
from courseware.kit.page import page
p=Path(sys.argv[1]);k=sys.argv[2]
print(page(k,(p/'pages'/f'{k}.html').read_text(),(p/'pages'/f'{k}.css').read_text(),(p/'pages'/f'{k}.js').read_text()))`;
  const html = execFileSync('python3', ['-B', '-c', source, lessonDir, key], {cwd: root, encoding: 'utf8'});
  const errors = [], pending = new Map();
  let timerId = 0;
  const console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(html, {runScripts: 'dangerously', virtualConsole: console, beforeParse(w) {
    w.setTimeout = (fn, ms) => { const id = ++timerId; if (ms >= 900 && ms <= 1000) pending.set(id, fn); return id; };
    w.clearTimeout = id => pending.delete(id);
  }});
  const w = dom.window, d = w.document;
  t.after(() => { assert.deepEqual(errors, []); assert.deepEqual(Array.from(w.K.errs), []); dom.window.close(); });
  const find = selector => { const e = d.querySelector(selector); assert.ok(e, selector); return e; };
  function tap(selectorOrElement) {
    const e = typeof selectorOrElement === 'string' ? find(selectorOrElement) : selectorOrElement;
    e.dispatchEvent(new w.MouseEvent('pointerdown', {bubbles: true, cancelable: true, button: 0}));
    d.dispatchEvent(new w.MouseEvent('pointerup', {bubbles: true, cancelable: true, button: 0}));
  }
  function advance() { const actions = Array.from(pending.values()); pending.clear(); actions.forEach(fn => fn()); }
  function chooseQuantity(n) {
    const e = Array.from(d.querySelectorAll('#answer-options button')).find(b => b.querySelectorAll('i').length === n);
    assert.ok(e, 'quantity option ' + n); e.click();
  }
  function again(stars) {
    assert.equal(w.K.stars, stars);
    assert.ok(d.querySelector('#finish:not(.gone)'));
    find('#btn-again').click();
    assert.equal(w.K.stars, 0);
    assert.equal(find('#star-n').textContent, '0');
    assert.equal(d.querySelector('#finish:not(.gone)'), null);
  }
  w.K.begin();
  return {w, d, find, tap, advance, chooseQuantity, again};
}

test('teacher demonstrations perform the narrated operation before speaking, then reset', t => {
  for (const key of ['p02', 'p04', 'p07', 'p09']) {
    const p = page(t, key), scene = lesson.scenes.find(s => s.key === key);
    for (const action of scene.script) {
      if (action.setState) p.w.K.onState(action.setState);
      if (key === 'p02' && action.say === '写成二加四等于六。') assert.equal(p.find('#equation').textContent, '2 + 4 = 6');
      if (key === 'p04' && action.say === '所以六减二等于四。') {
        assert.equal(p.find('#equation').textContent, '6 − 2 = 4');
        assert.equal(p.d.querySelectorAll('#removed-zone .bead').length, 2);
        assert.equal(p.d.querySelectorAll('#whole-row .bead').length, 4);
      }
      if (key === 'p07' && action.say === '两道加法放在加号区域。') {
        assert.equal(p.d.querySelectorAll('#addition-bank .bank-line').length, 2);
        assert.equal(p.d.querySelectorAll('#subtraction-bank .bank-line').length, 0);
      }
      if (key === 'p07' && action.say === '两道减法都要从整体七开始。') {
        assert.equal(p.d.querySelectorAll('#addition-bank .bank-line').length, 2);
        assert.equal(p.d.querySelectorAll('#subtraction-bank .bank-line').length, 2);
      }
      if (key === 'p09' && action.say === '看图核对，移出二片，留下四片。') {
        assert.equal(p.find('#ask-sub').textContent, '6 − 2 = 4');
        assert.equal(p.d.querySelectorAll('.reveal-part.removed .bead').length, 2);
        assert.equal(p.d.querySelectorAll('.reveal-part.remaining .bead').length, 4);
      }
    }
    assert.equal(p.w.K.stars, 0);
    assert.equal(p.d.querySelectorAll('.bank-line').length, 0);
    if (key === 'p02' || key === 'p04') assert.match(p.find('#equation').textContent, /\?$/);
    if (key === 'p09') {
      assert.match(p.find('#ask-sub').textContent, /\?$/);
      assert.equal(p.d.querySelectorAll('.reveal-part').length, 0);
    }
  }
});

test('replaying a teacher demonstration clears the previous student error state', t => {
  for (const [key, wrong] of [['p02', 6], ['p04', 2], ['p09', 3]]) {
    const p = page(t, key);
    p.chooseQuantity(wrong);
    assert.equal(p.find('#say').className, 'no');
    p.w.K.onState({demo: true});
    assert.equal(p.find('#say').className, '');
  }
  const p = page(t, 'p07');
  p.tap(Array.from(p.d.querySelectorAll('.formula')).find(e => e.textContent === '2 + 4 = 5'));
  assert.equal(p.find('#say').className, 'no');
  p.w.K.onState({demo: true});
  assert.equal(p.find('#say').className, '');
});

test('merge requires both physical groups, first error does not give the result, all levels and replay work', t => {
  const p = page(t, 'p02');
  p.chooseQuantity(6);
  assert.equal(p.w.K.stars, 0);
  assert.equal(p.find('#equation').textContent, '2 + 4 = ?');
  assert.equal(p.d.querySelectorAll('#merge-zone .bead').length, 0);
  for (let level = 0; level < 3; level++) {
    const quantity = p.d.querySelectorAll('#part-a .bead, #part-b .bead').length;
    p.tap('#part-a'); p.tap('#part-b');
    assert.equal(p.d.querySelectorAll('#merge-zone .bead').length, quantity);
    p.chooseQuantity(quantity); p.advance();
  }
  p.again(3);
  assert.equal(p.d.querySelectorAll('#merge-zone .bead').length, 0);
  assert.equal(p.find('#equation').textContent, '2 + 4 = ?');
});

test('subtraction requires exactly the removed part, can restore mistakes, and replays all levels', t => {
  const p = page(t, 'p04');
  p.chooseQuantity(2);
  assert.equal(p.w.K.stars, 0);
  assert.equal(p.find('#equation').textContent, '6 − 4 = ?');
  p.tap(p.find('#whole-row .bead'));
  assert.equal(p.d.querySelectorAll('#removed-zone .bead').length, 1);
  p.tap(p.find('#removed-zone .bead'));
  assert.equal(p.d.querySelectorAll('#removed-zone .bead').length, 0);
  assert.equal(p.d.querySelectorAll('#whole-row .bead').length, 6);
  p.tap(p.find('#whole-row .bead'));
  p.find('#restore-all').click();
  assert.equal(p.d.querySelectorAll('#removed-zone .bead').length, 0);
  for (let level = 0; level < 3; level++) {
    const [total, take] = p.find('#equation').textContent.match(/\d+/g).map(Number);
    for (let i = 0; i < take; i++) p.tap(p.find('#whole-row .bead'));
    assert.equal(p.d.querySelectorAll('#whole-row .bead').length, total - take);
    p.chooseQuantity(total - take); p.advance();
  }
  p.again(3);
  assert.equal(p.d.querySelectorAll('#whole-row .bead').length, 6);
  assert.equal(p.d.querySelectorAll('#removed-zone .bead').length, 0);
});

test('formula classification rejects the mathematically wrong card, completes both families, and fully resets', t => {
  const p = page(t, 'p07');
  function matchesPicture(text) {
    const a = p.d.querySelectorAll('#part-picture-a .bead').length;
    const b = p.d.querySelectorAll('#part-picture-b .bead').length;
    const [x, y, z] = text.match(/\d+/g).map(Number);
    return text.includes('+') ? x + y === z && z === a + b && [a, b].includes(x) && [a, b].includes(y)
      : x - y === z && x === a + b && [a, b].includes(y) && [a, b].includes(z);
  }
  p.tap(Array.from(p.d.querySelectorAll('.formula')).find(e => !matchesPicture(e.textContent)));
  assert.equal(p.d.querySelectorAll('.bank-line').length, 0);
  assert.equal(p.w.K.stars, 0);
  for (let level = 0; level < 2; level++) {
    for (let i = 0; i < 4; i++) {
      p.tap(Array.from(p.d.querySelectorAll('.formula:not(.used)')).find(e => matchesPicture(e.textContent)));
    }
    assert.equal(p.d.querySelectorAll('#addition-bank .bank-line').length, 2);
    assert.equal(p.d.querySelectorAll('#subtraction-bank .bank-line').length, 2);
    p.advance();
  }
  p.again(2);
  assert.equal(p.d.querySelectorAll('.bank-line').length, 0);
  assert.equal(p.d.querySelectorAll('.formula.used').length, 0);
});

test('inverse relation keeps the first error hidden, reveals the correct two parts and replays', t => {
  const p = page(t, 'p09');
  p.chooseQuantity(3);
  assert.equal(p.w.K.stars, 0);
  assert.equal(p.d.querySelectorAll('.reveal-part').length, 0);
  assert.match(p.find('#ask-sub').textContent, /\?$/);
  for (let level = 0; level < 3; level++) {
    const [total, take] = p.find('#ask-sub').textContent.match(/\d+/g).map(Number);
    p.chooseQuantity(total - take);
    assert.equal(p.d.querySelectorAll('.reveal-part.removed .bead').length, take);
    assert.equal(p.d.querySelectorAll('.reveal-part.remaining .bead').length, total - take);
    p.advance();
  }
  p.again(3);
  assert.equal(p.d.querySelectorAll('.reveal-part').length, 0);
  assert.equal(p.find('#ask-sub').textContent, '6 − 2 = ?');
});

test('assessment operand families are held out from class operations and the equal-parts question changes the task', () => {
  const scripts = ['p02', 'p04', 'p07', 'p09'].map(key => fs.readFileSync(path.join(lessonDir, 'pages', key + '.js'), 'utf8'));
  const exercises = scripts.join('\n');
  assert.doesNotMatch(exercises, /\[1,5(?:,|\])|\[5,1(?:,|\])|\[3,4(?:,|\])|\[4,3(?:,|\])/);
  const questions = lesson.scenes.flatMap(scene => scene.questions || []);
  assert.match(questions.find(q => q.id === 'as67-q1').question, /五枚.*一枚/);
  assert.match(questions.find(q => q.id === 'as67-q3').question, /四加三/);
  assert.match(questions.find(q => q.id === 'as67-q5').question, /几道不同的加减算式/);
  assert.deepEqual(questions.find(q => q.id === 'as67-q5').answer, ['C']);
});
