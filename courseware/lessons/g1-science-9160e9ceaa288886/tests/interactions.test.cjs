const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Run the real page scripts against a tiny DOM; assertions cover scoring,
// demonstration isolation, incomplete experiments, stale timers and replay.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {};
    this.style = {}; this.events = {}; this.id = ''; this.textContent = '';
    const classes = new Set();
    this.classList = { add: (...xs) => xs.forEach(x => classes.add(x)), remove: (...xs) => xs.forEach(x => classes.delete(x)),
      contains: x => classes.has(x), toggle: (x, force) => { const on = force === undefined ? !classes.has(x) : force; on ? classes.add(x) : classes.delete(x); return on; } };
  }
  set innerHTML(value) { this.children = []; this._html = value; }
  get innerHTML() { return this._html || ''; }
  appendChild(el) { this.children.push(el); el.parentElement = this; return el; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(name, callback) { (this.events[name] ||= []).push(callback); }
  emit(name, e = {}) { for (const f of this.events[name] || []) f({ preventDefault() {}, ...e }); }
}
function loadPage(id) {
  const root = new Element(); const stack = [root];
  const dir = path.join(__dirname, '..', 'pages');
  const html = fs.readFileSync(path.join(dir, id + '.html'), 'utf8');
  for (const match of html.matchAll(/<\/?([a-z][\w:-]*)([^>]*)>/gi)) {
    if (match[0].startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
    const el = new Element(match[1]);
    for (const attr of match[2].matchAll(/([\w-]+)="([^"]*)"/g)) {
      const [, key, value] = attr;
      if (key === 'class') value.split(/\s+/).forEach(x => el.classList.add(x));
      else if (key.startsWith('data-')) el.dataset[key.slice(5)] = value;
      else el[key] = value;
    }
    stack.at(-1).appendChild(el);
    if (!['img', 'path', 'circle', 'br', 'input'].includes(match[1]) && !match[0].endsWith('/>')) stack.push(el);
  }
  function all(node = root) { return node.children.flatMap(x => [x, ...all(x)]); }
  const matches = (el, selector) => selector[0] === '#' ? el.id === selector.slice(1) : selector[0] === '.' ? el.classList.contains(selector.slice(1)) : el.tagName === selector.toUpperCase();
  const queue = []; const highlights = []; const finishes = []; const messages = [];
  const K = { started: true, stars: 0, drags: [],
    $: (selector, node = root) => all(node).find(el => matches(el, selector)),
    $$: (selector, node = root) => all(node).filter(el => matches(el, selector)),
    el: (tag, cls, html, parent) => { const el = new Element(tag); if (cls) cls.split(/\s+/).forEach(x => el.classList.add(x)); if (parent) parent.appendChild(el); return el; },
    hud() { const n = new Element('b'); n.id = 'star-n'; root.appendChild(n); }, owl() {}, ready() {},
    levels(n, i) { K.level = i; }, say(text) { messages.push(text); },
    star(n) { K.stars += n; }, shake() {}, highlight(s) { highlights.push(s); },
    finish(o) { finishes.push(o); }, shuffle: xs => xs.slice().reverse(),
    drag(el, options) { K.drags.push({ el, options }); },
    sfx: { no() {}, ok() {}, pick() {} }
  };
  class Image { set src(value) { this._src = value; if (this.onload) this.onload(); } }
  vm.runInNewContext(fs.readFileSync(path.join(dir, id + '.js'), 'utf8'), { K, Image, setTimeout: (f, ms) => queue.push({ f, ms }) }, { filename: id + '.js' });
  const flush = () => { let count = 0; while (queue.length) { queue.sort((a, b) => a.ms - b.ms); queue.shift().f(); if (++count > 50) throw new Error('timer loop'); } };
  const click = selector => { const el = K.$(selector); assert.ok(el, selector); el.emit('click'); };
  const drag = target => K.drags[0].options.onDrop(K.drags[0].el, K.$(target));
  const nextTimer = () => { queue.sort((a, b) => a.ms - b.ms); assert.ok(queue.length); queue.shift().f(); };
  return { K, highlights, finishes, messages, flush, nextTimer, click, drag };
}

test('observation: first miss gives no answer; both objects, demonstration and replay stay separate', () => {
  const p = loadPage('p03'); p.click('#observe-choice-guess');
  assert.equal(p.K.stars, 0); assert.deepEqual(p.highlights, []);
  assert.equal(p.K.$('#observe-window').classList.contains('open'), false);
  p.click('#observe-choice-observe'); p.flush(); p.click('#observe-choice-observe'); p.flush();
  assert.equal(p.K.stars, 2); assert.equal(p.finishes.length, 1);
  p.finishes[0].again(); assert.equal(p.K.stars, 0); assert.equal(p.K.$('#observe-record').children.length, 0);
  p.K.onState({ demo: 'observe' }); assert.equal(p.K.stars, 0);
  p.click('#observe-choice-observe'); p.flush(); assert.equal(p.K.stars, 0);
  p.K.onState({ phase: 'play' }); assert.equal(p.K.$('#observe-record').children.length, 0);
});

test('rolling: a conclusion needs both distinct trials and a correct comparison; replay clears evidence', () => {
  const p = loadPage('p06'); p.click('#roll-choice-high'); assert.equal(p.K.stars, 0);
  p.click('#roll-low'); p.flush(); assert.equal(p.K.stars, 1); const near = parseFloat(p.K.$('#roll-ball').style.left);
  p.click('#roll-low'); p.flush(); assert.equal(p.K.stars, 1);
  p.click('#roll-high'); p.flush(); assert.equal(p.K.stars, 2); assert.ok(parseFloat(p.K.$('#roll-ball').style.left) > near);
  p.click('#roll-choice-low'); assert.equal(p.K.stars, 2); assert.deepEqual(p.highlights, []);
  p.click('#roll-choice-high'); p.flush(); assert.equal(p.K.stars, 3); assert.equal(p.finishes.length, 1);
  p.finishes[0].again(); assert.equal(p.K.stars, 0); assert.equal(p.K.$('#roll-observed').children.length, 0);
  assert.ok(p.K.$('#roll-choice-high').classList.contains('hide'));
});

test('rolling: resetting during motion rejects stale results and teacher demo earns no stars', () => {
  const p = loadPage('p06'); p.click('#roll-high'); p.click('#roll-reset'); p.flush();
  assert.equal(p.K.stars, 0); assert.equal(p.K.$('#roll-observed').children.length, 0);
  p.K.onState({ demo: 'low' }); p.K.onState({ demo: 'high' }); assert.equal(p.K.stars, 0);
  p.click('#roll-choice-high'); p.flush(); assert.equal(p.finishes.length, 0);
  p.K.onState({ phase: 'play' }); assert.equal(p.K.$('#roll-observed').children.length, 0);
});

test('material comparison: wrong heights never count; changed start requires a fresh matching placement', () => {
  const p = loadPage('p09'); p.drag('#compare-target-high'); assert.equal(p.K.stars, 0); assert.deepEqual(p.highlights, []);
  p.drag('#compare-target-mid'); p.flush(); assert.equal(p.K.stars, 1);
  p.drag('#compare-target-mid'); assert.equal(p.K.stars, 1);
  p.drag('#compare-target-high'); p.flush(); assert.equal(p.K.stars, 2); assert.equal(p.finishes.length, 1);
  p.finishes[0].again(); assert.equal(p.K.stars, 0); assert.equal(p.K.$('#compare-record').children.length, 0);
  assert.ok(p.K.$('#compare-placed').classList.contains('hide'));
  p.K.onState({ demo: 'same-start' }); assert.equal(p.K.stars, 0); p.drag('#compare-target-mid'); p.flush(); assert.equal(p.K.stars, 0);
  p.K.onState({ phase: 'play' }); assert.equal(p.K.$('#compare-record').children.length, 0);
});

test('research fields: misplaced objects do not count; all stations must fill and replay clears them', () => {
  const p = loadPage('p11'); p.drag('#field-animal'); assert.equal(p.K.stars, 0); assert.deepEqual(p.highlights, []);
  p.drag('#field-star'); p.flush(); p.drag('#field-plant'); p.flush(); p.drag('#field-animal'); p.flush();
  assert.equal(p.K.stars, 3); assert.equal(p.finishes.length, 1);
  assert.equal(p.K.$$('.field-record').filter(x => x.children.length === 1).length, 3);
  p.finishes[0].again(); assert.equal(p.K.stars, 0); assert.equal(p.K.$$('.field-record').some(x => x.children.length), false);
  p.K.onState({ demo: 'rabbit' }); p.drag('#field-animal'); p.flush(); assert.equal(p.K.stars, 0);
  p.K.onState({ phase: 'play' }); assert.equal(p.K.$$('.field-record').some(x => x.children.length), false);
});

test('rolling path reaches the end of the slope before moving along the level ground', () => {
  const p = loadPage('p06'); p.click('#roll-high');
  p.nextTimer(); assert.equal(p.K.$('#roll-ball').style.left, '326px'); assert.equal(p.K.$('#roll-ball').style.top, '252px');
  p.nextTimer(); assert.equal(p.K.$('#roll-ball').style.top, '252px'); assert.ok(parseFloat(p.K.$('#roll-ball').style.left) > 326);
  p.flush(); assert.equal(p.K.stars, 1);
});
