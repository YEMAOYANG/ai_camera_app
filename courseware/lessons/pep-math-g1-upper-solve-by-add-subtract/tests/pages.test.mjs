// Logic regression checks for the actual lesson page handlers; G6 separately checks real browser layout and play.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import test from 'node:test';

const pages = path.resolve(import.meta.dirname, '../pages');

function load(name, shuffle = a => a.slice()) {
  const elements = [];
  const ids = new Map();
  const timers = new Map();
  let serial = 0;
  function element(tag = 'div', cls = '', html = '', parent) {
    const classes = new Set(cls.split(/\s+/).filter(Boolean));
    const e = { tag, children: [], dataset: {}, style: {}, disabled: false, parentElement: parent,
      setAttribute(k, v) { this[k] = v; },
      classList: { add(...x) { x.forEach(v => classes.add(v)); }, remove(...x) { x.forEach(v => classes.delete(v)); },
        toggle(k, yes) { if (yes ?? !classes.has(k)) classes.add(k); else classes.delete(k); }, contains(k) { return classes.has(k); } },
      querySelector() { return { style: {}, parentElement: this }; },
    };
    Object.defineProperty(e, 'innerHTML', { get() { return this.html; }, set(v) { this.html = v; this.children = []; } });
    e.innerHTML = html;
    elements.push(e);
    if (parent) parent.children.push(e);
    return e;
  }
  const html = fs.readFileSync(path.join(pages, name + '.html'), 'utf8');
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) ids.set(id, element());
  ids.set('star-n', element());
  const K = { drags: [], stars: 0, messages: [], finishes: [],
    $: s => ids.get(s.slice(1)),
    $$: s => elements.filter(e => e.classList.contains(s.slice(1))),
    el: element, shuffle,
    hud() {}, owl() {}, ready() {}, levels() {}, shake() {}, highlight() {},
    say(t, kind) { this.messages.push({ text: t, kind }); },
    star(n) { this.stars += n; },
    finish(value) { this.finishes.push(value); ids.set('finish', element()); },
    drag(el, options) { this.drags.push({ el, options }); },
    sfx: { pick() {}, no() {}, ok() {}, drop() {} },
  };
  vm.runInNewContext(fs.readFileSync(path.join(pages, name + '.js'), 'utf8'), { K,
    setTimeout(f) { timers.set(++serial, f); return serial; }, clearTimeout(i) { timers.delete(i); },
  });
  K.onStart();
  return { K, get: id => ids.get(id), next() { const [id, fn] = timers.entries().next().value; timers.delete(id); fn(); } };
}

function replayHasReset(page, id) {
  assert.equal(page.K.finishes.length, 1);
  page.K.finishes[0].again();
  assert.equal(page.K.stars, 0);
  assert.ok(page.get('finish').classList.contains('gone'));
  assert.ok(page.get(id).children.length > 0);
}

test('related information: irrelevant first choice never wins; three pairs finish and reset', () => {
  const p = load('p02');
  p.get('info-other').onclick();
  assert.equal(p.K.stars, 0);
  assert.match(p.K.messages.at(-1).text, /哪一种物品/);
  for (let i = 0; i < 3; i++) {
    p.get('info-total').onclick();
    p.get('info-away').onclick();
    assert.equal(p.K.stars, i + 1);
    p.next();
  }
  replayHasReset(p, 'info-birds');
});

test('removal: objects leave the remaining group, wrong quantity keeps the physical model', () => {
  const p = load('p04');
  for (const removed of [2, 2, 3]) {
    const before = p.get('bird-remain').children.length;
    for (let i = 0; i < removed; i++) p.get('bird-remain').children[0].onclick();
    assert.equal(p.get('bird-remain').children.length, before - removed);
    assert.equal(p.get('bird-away').children.length, removed);
    const stars = p.K.stars;
    p.get('bird-options').children[0].onclick();
    assert.equal(p.K.stars, stars);
    assert.equal(p.get('bird-remain').children.length, before - removed);
    p.get('bird-options').children[1].onclick();
    assert.equal(p.K.stars, stars + 1);
    p.next();
  }
  replayHasReset(p, 'bird-remain');
});

test('joining: each drag preserves the total and wrong answer never discards a boat', () => {
  const p = load('p06');
  for (let level = 0; level < 3; level++) {
    const total = p.get('boat-left').children.length + p.get('boat-right').children.length;
    while (p.get('boat-right').children.length) {
      const source = p.K.drags[0];
      source.options.onDrop(source.el, p.get('boat-left'));
      assert.equal(p.get('boat-left').children.length + p.get('boat-right').children.length, total);
    }
    const stars = p.K.stars;
    p.get('boat-options').children[0].onclick();
    assert.equal(p.K.stars, stars);
    assert.equal(p.get('boat-left').children.length, total);
    p.get('boat-options').children[1].onclick();
    p.next();
  }
  replayHasReset(p, 'boat-left');
});

function dropBundle(p, count) {
  const bundle = p.K.drags.find(entry => entry.el.id === `cup-bundle-${count}`);
  bundle.options.onDrop(bundle.el, p.get('cup-box'));
}

test('missing part: the two parts must equal the stated whole in every round, then replay resets', () => {
  const p = load('p08');
  for (const missing of [5, 4, 3]) {
    const stars = p.K.stars;
    dropBundle(p, missing + 1);
    assert.equal(p.K.stars, stars);
    assert.equal(p.get('cup-box').children.length, missing + 1);
    dropBundle(p, missing);
    assert.equal(p.get('cup-box').children.length, missing);
    assert.equal(p.K.stars, stars + 1);
    p.next();
  }
  assert.equal(p.K.finishes.length, 1);
  p.K.onState({ demo: true });
  assert.ok(p.get('finish').classList.contains('gone'));
  p.K.finishes[0].again();
  assert.equal(p.K.stars, 0);
  assert.equal(p.get('cup-box').children.length, 0);
});

test('teacher demonstration replay restores a fresh child attempt on every page', () => {
  for (const [name, demonstrate, model, count] of [
    ['p02', 'demoSelected', 'info-birds', 8],
    ['p04', 'demoRemove', 'bird-remain', 8],
    ['p06', 'demoJoin', 'boat-right', 4],
    ['p08', 'demoFill', 'cup-box', 0],
  ]) {
    const p = load(name);
    p.K.onState({ demo: true });
    p.K.onState({ [demonstrate]: true });
    assert.equal(p.K.stars, 0);
    p.K.onState({ play: true });
    assert.equal(p.get(model).children.length, count, name);
    assert.equal(p.K.stars, 0);
  }
});

test('a later-round prompt cannot survive the teacher returning to the first flowerpot example', () => {
  const p = load('p08');
  dropBundle(p, 5);
  p.next();
  assert.match(p.K.messages.at(-1).text, /一共8个/);
  p.K.onState({ demo: true });
  p.K.onState({ demoFill: true });
  assert.match(p.K.messages.at(-1).text, /一共9个/);
  assert.equal(p.get('cup-equation').textContent, '9 − 4 = 5');
  assert.equal(p.K.stars, 0);
});

test('trying a different flowerpot group returns the earlier group to its source card', () => {
  let shuffles = 0;
  const p = load('p08', a => { const i = shuffles++ % a.length; return a.slice(i).concat(a.slice(0, i)); });
  const card = n => p.get('cup-palette').children.find(e => e.id === `cup-bundle-${n}`);
  const order = () => p.get('cup-palette').children.map(e => e.id);
  const startingOrder = order();
  dropBundle(p, 4);
  assert.equal(p.K.stars, 0);
  assert.equal(p.get('cup-box').children.length, 4);
  assert.ok(card(4).classList.contains('placed'));
  assert.deepEqual(order(), startingOrder);
  dropBundle(p, 5);
  assert.equal(p.get('cup-box').children.length, 5);
  assert.ok(!card(4).classList.contains('placed'));
  assert.ok(card(5).classList.contains('placed'));
  assert.deepEqual(order(), startingOrder);
  assert.equal(p.K.stars, 1);
});
