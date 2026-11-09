const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function load(page) {
  const ids = new Map();
  const elements = [];
  const timers = new Map();
  let tick = 0;
  const state = { stars: 0, message: '', finishes: [], audio: [] };
  function element(tag = 'div') {
    const e = { tagName: tag.toUpperCase(), children: [], dataset: {}, style: {}, disabled: false,
      classList: { values: new Set(), add(v) { this.values.add(v); } },
      setAttribute(k, v) { this[k] = v; }, addEventListener() {}, remove() {} };
    Object.defineProperty(e, 'innerHTML', { set() { this.children = []; }, get() { return ''; } });
    Object.defineProperty(e, 'textContent', { set(v) { this.text = v; }, get() { return this.text || ''; } });
    elements.push(e);
    return e;
  }
  const html = fs.readFileSync(path.join(__dirname, '../pages', page + '.html'), 'utf8');
  for (const id of [...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]).concat('star-n', 'start-btn')) ids.set(id, element());
  const K = {
    stars: 0, hud() {}, owl() {}, ready() {}, levels() {}, shake() {},
    shuffle(v) { return [...v].reverse(); },
    $(q) { return q.startsWith('#') ? ids.get(q.slice(1)) : elements.find(e => e.dataset.colour === q.match(/data-colour="([^"]+)"/)[1]); },
    el(tag, cls, content, parent) { const e = element(tag); e.className = cls; if (parent) parent.children.push(e); return e; },
    say(message, kind) { state.message = message; state.kind = kind; },
    star(n) { this.stars += n; state.stars += n; },
    sfx: { no() {}, ok() {} },
    finish(v) { state.finishes.push(v); }
  };
  const window = { K, addEventListener() {} };
  const ctx = { K, window, Audio: class { constructor(src) { state.audio.push(src); } play() { return Promise.resolve(); } pause() {} },
    setTimeout(fn) { timers.set(++tick, fn); return tick; }, clearTimeout(id) { timers.delete(id); } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../pages', page + '.js'), 'utf8'), ctx);
  return { K, window, ids, state, flush() { const jobs = [...timers.values()]; timers.clear(); jobs.forEach(fn => fn()); } };
}

test('listening task keeps the first wrong choice retryable and transfers the correct umbrella', () => {
  const g = load('p05');
  g.K.onState({ mode: 'demo', demoColor: 'red' });
  assert.equal(g.state.audio.length, 0);
  g.K.onState({ mode: 'practice' });
  assert.equal(g.state.audio.length, 1);
  g.window.colourGame.choose('red');
  assert.equal(g.window.colourGame.snapshot().round, 0);
  assert.equal(g.window.colourGame.snapshot().attempts, 1);
  assert.equal(g.state.stars, 0);
  assert.ok(!g.state.message.includes('blue'));
  assert.equal(g.ids.get('colour-display').children.length, 0);
  for (const colour of ['blue', 'red', 'white', 'yellow', 'black', 'green']) {
    g.window.colourGame.choose(colour);
    assert.equal(g.ids.get('colour-display').children[0].alt, ({blue:'蓝',red:'红',white:'白',yellow:'黄',black:'黑',green:'绿'})[colour] + '色雨伞');
    g.flush();
  }
  assert.equal(g.state.finishes.length, 1);
  g.state.finishes[0].again();
  assert.equal(g.window.colourGame.snapshot().round, 0);
  assert.equal(g.K.stars, 0);
  assert.equal(g.ids.get('colour-display').children.length, 0);
});

test('now task rejects a prior colour, stores the current object and resets all collected objects', () => {
  const g = load('p07');
  g.K.onState({ mode: 'demo', demoColor: 'yellow' });
  assert.equal(g.state.audio.length, 0);
  assert.equal(g.ids.get('now-old-image').children[0].alt, '红色雨伞');
  assert.equal(g.ids.get('now-main-image').children[0].alt, '黄色雨伞');
  g.K.onState({ mode: 'practice' });
  assert.equal(g.state.audio.length, 1);
  g.window.nowGame.choose('yellow');
  assert.equal(g.window.nowGame.snapshot().round, 0);
  assert.equal(g.state.stars, 0);
  assert.equal(g.ids.get('now-finished').children.length, 0);
  assert.ok(!g.state.message.includes('green'));
  for (const colour of ['green', 'white', 'black']) {
    g.window.nowGame.choose(colour);
    g.flush();
  }
  assert.equal(g.ids.get('now-finished').children.length, 3);
  assert.equal(g.state.finishes.length, 1);
  g.state.finishes[0].again();
  assert.equal(g.ids.get('now-finished').children.length, 0);
  assert.equal(g.window.nowGame.snapshot().previous, 'yellow');
  assert.equal(g.K.stars, 0);
});
