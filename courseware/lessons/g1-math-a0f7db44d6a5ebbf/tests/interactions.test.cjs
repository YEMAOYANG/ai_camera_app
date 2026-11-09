const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const source = path.resolve(__dirname, '..');
const { JSDOM } = createRequire(path.resolve(source, '../../../student-web/package.json'))('jsdom');

test('explanation diagram conserves thirteen units when ten counters become one ten rod', () => {
  const dom = new JSDOM(fs.readFileSync(path.join(source, 'assets/ten-ones.svg'), 'utf8'), {contentType: 'image/svg+xml'});
  try {
    const d = dom.window.document;
    const before = d.querySelectorAll('#before-group .counter').length + d.querySelectorAll('#before-extra .counter').length;
    const after = d.querySelectorAll('#after-rod .one-unit').length + d.querySelectorAll('#after-extra .counter').length;
    assert.equal(before, 13);
    assert.equal(after, before);
    assert.equal(d.querySelectorAll('#after-rod .one-unit').length, 10);
  } finally {dom.window.close();}
});

function open(id) {
  const dom = new JSDOM('<div id="star-n">0</div>' + fs.readFileSync(path.join(source, `pages/${id}.html`)), {runScripts: 'outside-only'});
  const w = dom.window, d = w.document, timers = [];
  w.setTimeout = fn => (timers.push(fn), timers.length);
  w.clearTimeout = () => {};
  w.K = {
    $: s => d.querySelector(s),
    el(tag, cls, html, parent) { const e = d.createElement(tag); e.className = cls; e.innerHTML = html || ''; if (parent) parent.appendChild(e); return e; },
    hud() {}, owl() {}, ready() {}, levels() {}, say(t) {w.lastSay = t;}, stars: 0,
    star(n) { this.stars += n; }, finish(o) {w.finished = o;},
    shuffle: a => a, drag() {}, sfx: {tick() {}, drop() {}, ok() {}, no() {}},
  };
  w.eval(fs.readFileSync(path.join(source, `pages/${id}.js`), 'utf8'));
  w.K.onStart();
  return {w, d, next() {assert.ok(timers.length); timers.shift()();}, close() {w.close();}};
}

test('counting starts after the first addend and requires exactly the second addend in steps', () => {
  const p = open('p03');
  try {
    p.d.querySelector('#check-walk').click();
    assert.equal(p.w.K.stars, 0);
    assert.equal(p.d.querySelector('#sum-blank').textContent, '?');
    for (const [a, b] of [[6, 5], [8, 6], [9, 3]]) {
      assert.equal(p.d.querySelector('#sum-blank').textContent, '?');
      for (let i = 1; i <= b; i++) {
        p.d.querySelector('#go-one').click();
        assert.equal(p.d.querySelectorAll('#step-dots .filled').length, i);
        assert.equal(p.d.querySelector('#walk-dot').style.left, `${(a + i) * 5}%`);
      }
      p.d.querySelector('#check-walk').click();
      assert.equal(p.d.querySelector('#sum-blank').textContent, String(a + b));
      p.next();
    }
    assert.ok(p.w.finished);
    p.w.finished.again();
    assert.equal(p.w.K.stars, 0);
    assert.equal(p.d.querySelectorAll('#step-dots .filled').length, 0);
  } finally {p.close();}
});

test('regrouping conserves counters and refuses exchanging before a full ten', () => {
  const p = open('p05');
  try {
    p.d.querySelector('#exchange').click();
    assert.equal(p.w.K.stars, 0);
    assert.equal(p.d.querySelector('#ten-rod').classList.contains('hide'), true);
    for (const [a, b] of [[6, 6], [7, 5], [8, 5]]) {
      for (let i = 0; i < 10 - a; i++) p.d.querySelector('.pool-point:not(.used)').click();
      assert.equal(p.d.querySelectorAll('#ten-frame .point').length, 10);
      assert.equal(p.d.querySelectorAll('.pool-point:not(.used)').length, a + b - 10);
      p.d.querySelector('#exchange').click();
      assert.equal(p.d.querySelector('#ten-frame').classList.contains('hide'), true);
      assert.equal(p.d.querySelector('#ten-rod').classList.contains('hide'), false);
      assert.equal(p.d.querySelectorAll('#ten-rod i em').length, 10);
      while (p.d.querySelector('.pool-point:not(.used)')) {
        p.d.querySelector('.pool-point:not(.used)').click();
        assert.equal(10 + p.d.querySelectorAll('#ones-tray .point').length + p.d.querySelectorAll('.pool-point:not(.used)').length, a + b);
      }
      assert.equal(p.d.querySelector('#group-sum').textContent, String(a + b));
      p.next();
    }
    assert.ok(p.w.finished);
    p.w.finished.again();
    assert.equal(p.d.querySelectorAll('#ten-frame .point').length, 6);
    assert.equal(p.d.querySelectorAll('#ones-tray .point').length, 0);
  } finally {p.close();}
});

test('two-hop play rejects a wrong first move without revealing the answer, then preserves the split', () => {
  const p = open('p08');
  const option = n => [...p.d.querySelectorAll('.hop-choice')].find(e => e.querySelectorAll('i').length === n);
  try {
    option(2).click();
    assert.equal(p.d.querySelector('#jump-arcs').children.length, 0);
    assert.equal(p.d.querySelector('#jump-total').textContent, '?');
    assert.equal(p.w.K.stars, 0);
    for (const [a, b] of [[7, 6], [8, 7], [9, 6]]) {
      option(10 - a).click();
      assert.equal(p.d.querySelector('#jump-foot').style.left, '50%');
      assert.equal(p.d.querySelectorAll('#jump-arcs path').length, 1);
      option(b - (10 - a)).click();
      assert.equal(p.d.querySelector('#jump-total').textContent, String(a + b));
      assert.equal(p.d.querySelectorAll('#jump-arcs path').length, 2);
      p.next();
    }
    assert.ok(p.w.finished);
    p.w.finished.again();
    assert.equal(p.d.querySelectorAll('#jump-arcs path').length, 0);
    assert.equal(p.w.K.stars, 0);
  } finally {p.close();}
});

test('classification moves the actual quantity card and replay clears all previous cards', () => {
  const p = open('p10');
  try {
    const first = p.d.querySelector('#sum-card');
    p.d.querySelector('#bin-12').click();
    assert.equal(p.d.querySelector('#sum-card'), first);
    assert.equal(p.d.querySelectorAll('.accepted .sum-card').length, 0);
    assert.equal(p.w.K.stars, 0);
    for (const [a, b] of [[6, 5], [5, 7], [8, 3], [4, 8], [6, 6], [7, 4]]) {
      const card = p.d.querySelector('#sum-card');
      assert.equal(card.querySelectorAll('i').length, a + b);
      p.d.querySelector(`#bin-${a + b}`).click();
      assert.equal(card.parentElement.id, `accepted-${a + b}`);
      p.next();
    }
    assert.ok(p.w.finished);
    assert.equal(p.d.querySelectorAll('#accepted-11 .sum-card').length, 3);
    assert.equal(p.d.querySelectorAll('#accepted-12 .sum-card').length, 3);
    p.w.finished.again();
    assert.equal(p.d.querySelectorAll('.accepted .sum-card').length, 0);
    assert.equal(p.w.K.stars, 0);
  } finally {p.close();}
});

test('teacher states visibly demonstrate the exact narrated examples and hand back a clean exercise', () => {
  for (const id of ['p03', 'p05', 'p08', 'p10']) {
    const p = open(id);
    try {
      const staleFinish = p.d.createElement('div'); staleFinish.id = 'finish'; p.d.body.appendChild(staleFinish);
      p.w.K.stars = 3; p.d.querySelector('#star-n').textContent = '3';
      p.w.K.onState({demo: true});
      assert.equal(staleFinish.classList.contains('gone'), true);
      assert.equal(p.w.K.stars, 0);
      assert.equal(p.w.lastSay, '先看老师示范，再轮到你。');
      assert.equal(p.d.querySelector('#star-n').textContent, '0');
      if (id === 'p03') {
        p.d.querySelector('#go-one').click();
        assert.equal(p.d.querySelectorAll('#step-dots .filled').length, 0);
        p.w.K.onState({step: 6});
        assert.equal(p.d.querySelector('#sum-blank').textContent, '13');
      } else if (id === 'p05') {
        p.w.K.onState({demoStage: 1});
        assert.equal(p.d.querySelectorAll('#ten-frame .point').length, 10);
        p.w.K.onState({demoStage: 2});
        assert.equal(p.d.querySelectorAll('#ones-tray .point').length, 3);
      } else if (id === 'p08') {
        p.w.K.onState({first: true});
        assert.equal(p.d.querySelector('#remaining').textContent.trim(), '5＝ 4 ＋ ?');
        p.w.K.onState({second: true});
        assert.equal(p.d.querySelector('#jump-total').textContent, '11');
      } else {
        p.w.K.onState({place: true});
        assert.equal(p.d.querySelector('#accepted-11 .formula').textContent, '6＋5');
        p.w.K.onState({exampleTwelve: true});
        assert.equal(p.d.querySelector('#sum-card .formula').textContent, '5＋7');
        p.w.K.onState({placeTwelve: true});
        p.w.K.onState({placeTwelve: true});
        assert.equal(p.d.querySelector('#accepted-12 .formula').textContent, '5＋7');
        assert.equal(p.d.querySelectorAll('.accepted .sum-card').length, 2);
      }
      p.w.K.onState({play: true});
      assert.equal(p.w.K.stars, 0);
      assert.equal(p.d.querySelectorAll('.accepted .sum-card').length, 0);
    } finally {p.close();}
  }
});
