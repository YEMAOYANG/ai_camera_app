const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const source = path.resolve(__dirname, '..');
const studentRequire = createRequire(path.resolve(source, '../../../student-web/package.json'));
const {JSDOM} = studentRequire('jsdom');

function page(id) {
  const html = '<style>' + fs.readFileSync(path.join(source, 'pages', id + '.css'), 'utf8') + '</style><div id="star-n">0</div>' + fs.readFileSync(path.join(source, 'pages', id + '.html'), 'utf8');
  const dom = new JSDOM(html, {runScripts: 'outside-only'});
  const w = dom.window, d = w.document, timers = new Map(); let timerId = 0;
  w.setTimeout = fn => {timers.set(++timerId, fn); return timerId;};
  w.clearTimeout = id => timers.delete(id);
  w.K = {
    stars: 0, $: s => d.querySelector(s), shuffle: a => a.slice(),
    el(tag, cls, html, parent) {
      const el = d.createElement(tag); el.className = cls;
      if (html != null) el.innerHTML = html;
      if (parent) parent.appendChild(el);
      return el;
    },
    hud() {}, owl() {}, ready() {}, levels() {}, highlight() {}, shake() {},
    say(text, kind) {w.message = {text, kind};},
    star(n) {this.stars += n;},
    finish(options) {w.finished = options;},
    drag(el, options) {el.__drag = options; el.onclick = options.onTap;},
    sfx: {no() {}, ok() {}, pick() {}, drop() {}},
  };
  w.eval(fs.readFileSync(path.join(source, 'pages', id + '.js'), 'utf8'));
  return {
    w, d, count: selector => d.querySelectorAll(selector).length,
    choice(n) {const el = [...d.querySelectorAll('.answer')].find(e => e.querySelectorAll('i').length === n); assert.ok(el); el.click();},
    next() {const first = timers.entries().next(); assert.equal(first.done, false); const [id, fn] = first.value; timers.delete(id); fn();},
    close() {w.close();},
  };
}

test('merge requires both physical parts, conserves counters, finishes and resets', () => {
  const p = page('p02');
  try {
    p.w.K.onStart(); p.choice(8);
    assert.equal(p.w.K.stars, 0);
    assert.match(p.d.querySelector('#merge-equation').textContent, /\?/);
    assert.equal(p.count('#merge-zone .counter'), 0, 'first miss does not merge or reveal');
    for (const total of [8, 9, 9]) {
      const first = p.d.querySelector('#part-a');
      first.__drag.onDrop(first, p.d.querySelector('#merge-zone'));
      p.d.querySelector('#part-b').click();
      assert.equal(p.count('#merge-zone .counter'), total);
      assert.equal(p.count('#part-a .counter, #part-b .counter'), 0, 'moved objects leave their original trays');
      assert.match(p.d.querySelector('#merge-equation').textContent, /\?/, 'learner result is not revealed before answering');
      p.d.querySelector('#swap-groups').click();
      assert.equal(p.count('#merge-zone .counter'), total, 'exchange conserves the whole');
      p.choice(total); p.next();
    }
    assert.ok(p.w.finished); p.w.finished.again();
    assert.equal(p.count('#merge-zone .counter'), 0);
    assert.equal(p.w.K.stars, 0);
    p.w.K.onState({demo:true}); p.d.querySelector('#part-a').click();
    assert.equal(p.count('#merge-zone .counter'), 0);
    p.w.K.onState({demoMerged:true}); assert.equal(p.count('#merge-zone .counter'), 8);
    p.w.K.onState({play:true}); assert.equal(p.count('#merge-zone .counter'), 0);
  } finally {p.close();}
});

test('subtraction moves an exact part, supports undo, and never accepts a guessed remainder', () => {
  const p = page('p04');
  try {
    p.w.K.onStart(); p.choice(5);
    assert.equal(p.count('#covered-zone .counter'), 0);
    assert.equal(p.w.K.stars, 0);
    for (const [total, removed] of [[8,3], [9,7], [8,5]]) {
      p.d.querySelector('#cover-counter-1').click();
      p.d.querySelector('#cover-counter-1').click();
      assert.equal(p.count('#covered-zone .counter'), 0);
      for (let i = 1; i <= removed; i++) p.d.querySelector('#cover-counter-' + i).click();
      assert.equal(p.count('#whole-row .counter'), total - removed);
      assert.equal(p.count('#covered-zone .counter'), removed);
      for (const image of p.d.querySelectorAll('#covered-zone .counter img')) assert.equal(p.w.getComputedStyle(image).visibility, 'hidden', 'covered objects must actually disappear under the lids');
      assert.equal(p.count('#whole-row .counter, #covered-zone .counter'), total);
      p.choice(total - removed); p.next();
    }
    assert.ok(p.w.finished); p.w.finished.again();
    assert.equal(p.count('#whole-row .counter'), 8);
    assert.equal(p.count('#covered-zone .counter'), 0);
    p.w.K.onState({demo:true}); p.w.K.onState({demoCovered:true});
    assert.equal(p.count('#covered-zone .counter'), 3);
    p.d.querySelector('#cover-counter-1').click();
    assert.equal(p.count('#covered-zone .counter'), 3, 'demonstration blocks learner edits');
    p.w.K.onState({play:true}); assert.equal(p.count('#covered-zone .counter'), 0);
  } finally {p.close();}
});

test('family matching rejects incorrect equations and all accepted formulas solve independently', () => {
  const p = page('p07');
  try {
    p.w.K.onStart(); p.d.querySelectorAll('.formula')[4].click();
    assert.equal(p.count('.bank-line'), 0);
    assert.equal(p.count('.formula.rejected'), 0, 'a first error does not identify the distractors');
    for (const total of [8,9]) {
      assert.equal(p.count('#family-diagram .counter'), total);
      for (let i = 1; i <= 4; i++) {
        const el = p.d.querySelector('#family-formula-' + i);
        const m = el.textContent.match(/(\d+)\s*([+−])\s*(\d+)\s*=\s*(\d+)/);
        const actual = m[2] === '+' ? +m[1] + +m[3] : +m[1] - +m[3];
        assert.equal(actual, +m[4]); el.click();
      }
      assert.equal(p.count('#addition-bank .bank-line'), 2);
      assert.equal(p.count('#subtraction-bank .bank-line'), 2);
      assert.equal(p.count('.formula.rejected'), 2, 'after all four matches, unaccepted equations are visibly crossed out');
      p.next();
    }
    assert.ok(p.w.finished); p.w.finished.again(); assert.equal(p.count('.bank-line'), 0);
    p.w.K.onState({demo:true}); p.w.K.onState({demoAdd:true});
    assert.equal(p.count('.bank-line'), 2);
    p.w.K.onState({demoAll:true}); assert.equal(p.count('.bank-line'), 4);
    p.w.K.onState({play:true}); assert.equal(p.count('.bank-line'), 0);
  } finally {p.close();}
});

test('hidden part stays covered after a wrong answer and is revealed only on correct completion', () => {
  const p = page('p09');
  try {
    p.w.K.onStart(); p.choice(4);
    assert.equal(p.d.querySelector('#hidden-part').classList.contains('revealed'), false);
    assert.match(p.d.querySelector('#missing-equation').textContent, /\?/);
    for (const [visible, hidden] of [[3,5], [7,2], [5,4]]) {
      assert.equal(p.count('#visible-part .counter'), visible);
      assert.equal(p.count('#hidden-counters .counter'), hidden);
      p.choice(hidden);
      assert.equal(p.d.querySelector('#hidden-part').classList.contains('revealed'), true);
      p.next();
    }
    assert.ok(p.w.finished); p.w.finished.again();
    assert.equal(p.d.querySelector('#hidden-part').classList.contains('revealed'), false);
    p.w.K.onState({demo:true}); p.w.K.onState({demoReveal:true});
    assert.equal(p.count('#hidden-counters .counter'), 5);
    p.w.K.onState({play:true});
    assert.equal(p.d.querySelector('#hidden-part').classList.contains('revealed'), false);
  } finally {p.close();}
});

test('equal parts require exchange then collapse four instances to two distinct equations', () => {
  const p = page('p12');
  try {
    p.w.K.onStart(); p.d.querySelector('#equal-formula-1').click();
    assert.equal(p.count('.formula-card.placed'), 0, 'exchange is required first');
    assert.equal(p.count('#equal-diagram .counter'), 8);
    p.d.querySelector('#swap-equal').click();
    const wrong = p.d.querySelector('#equal-formula-1');
    wrong.__drag.onDrop(wrong, p.d.querySelector('#sub-stack'));
    assert.equal(p.count('.formula-card.placed'), 0, 'cannot stack add on subtract');
    for (let i = 1; i <= 4; i++) p.d.querySelector('#equal-formula-' + i).click();
    assert.equal(p.count('.stack.complete'), 2);
    assert.deepEqual([...p.d.querySelectorAll('.stack-formula')].map(e => e.textContent), ['4 + 4 = 8','8 − 4 = 4']);
    p.next(); assert.ok(p.w.finished); p.w.finished.again();
    assert.equal(p.count('.formula-card.placed'), 0);
    assert.equal(p.d.querySelector('#equal-diagram').classList.contains('swapped'), false);
    p.w.K.onState({demo:true}); p.w.K.onState({demoSwap:true}); p.w.K.onState({demoStack:true});
    assert.equal(p.count('.stack.complete'), 2);
    p.w.K.onState({play:true}); assert.equal(p.count('.stack.complete'), 0);
  } finally {p.close();}
});
