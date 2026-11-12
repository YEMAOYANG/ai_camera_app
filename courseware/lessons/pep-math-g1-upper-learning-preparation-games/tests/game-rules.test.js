const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const UP = {down: false, x: 640, y: 494};
const stepSeconds = 1 / 60;

function loadPage(page, level = 0, demo = false) {
  let options;
  const K = {
    hud() {}, ready() {}, $: () => ({}),
    game(value) { options = value; },
    sfx: new Proxy({}, {get: () => () => {}})
  };
  const source = readFileSync(join(__dirname, '..', 'pages', page + '.js'), 'utf8');
  vm.runInNewContext(source, {K, Image: class {}});
  const g = {
    level, auto: demo, autoLoop: demo, data: {}, keys: {}, pointer: UP,
    levelMisses: 0, won: false, messages: [],
    miss() { this.levelMisses++; },
    say(text, kind) { this.messages.push({text, kind}); },
    after() {}, sparkle() {}, win() { this.won = true; }
  };
  options.reset(g, level);
  function step(seconds, input = UP) {
    g.pointer = input;
    const frames = Math.round(seconds / stepSeconds);
    for (let i = 0; i < frames && !g.won; i++) {
      if (g.auto) options.autopilot(g, stepSeconds);
      options.update(g, stepSeconds);
    }
  }
  return {g, step};
}

function drag(page, x, y, targetX, targetY) {
  page.step(0.1, {down: true, x, y});
  page.step(0.25, {down: true, x: targetX, y: targetY});
  page.step(0.75, {down: false, x: targetX, y: targetY});
}

test('holding early never crosses before or after the bell without a fresh decision', () => {
  const page = loadPage('g02');
  page.step(3.0, {down: true, x: 988, y: 292});
  assert.equal(page.g.data.ringing, true);
  assert.deepEqual([page.g.data.x, page.g.data.y], [640, 596]);
  assert.equal(page.g.levelMisses, 1);
  page.step(0.1);
  page.step(2.1, {down: true, x: 988, y: 292});
  assert.equal(page.g.won, true);
});

test('the classroom switches sides on the second level and the wrong location can be retried', () => {
  const page = loadPage('g02', 1);
  page.step(3.8);
  page.step(1.5, {down: true, x: 988, y: 292});
  assert.equal(page.g.won, false);
  assert.equal(page.g.levelMisses, 1);
  page.step(0.12);
  page.step(1.5, {down: true, x: 292, y: 292});
  assert.equal(page.g.won, true);
});

test('seat-relative placement rejects a mirrored side and lets a supply return', () => {
  const page = loadPage('g04');
  drag(page, 120, 325, 989, 396);
  const book = page.g.data.items[0];
  assert.equal(book.placed, false);
  assert.equal(book.x, 120);
  assert.equal(page.g.messages[0].kind, 'no');
  drag(page, 120, 325, 424, 396);
  assert.equal(book.placed, true);
  assert.equal(page.g.won, false);
});

test('the notebook must be placed after the math book in the stacking level', () => {
  const page = loadPage('g04', 1);
  drag(page, 120, 577, 424, 387);
  assert.equal(page.g.data.items[2].placed, false);
  drag(page, 120, 325, 424, 396);
  drag(page, 120, 577, 424, 387);
  drag(page, 120, 451, 716, 388);
  assert.equal(page.g.won, true);
});

test('the child must hear both peers and wait for a turn before sending', () => {
  const page = loadPage('g06', 1);
  drag(page, 640, 494, 640, 390);
  assert.equal(page.g.levelMisses, 1);
  assert.equal(page.g.data.phase, 'listen');
  page.step(4.2);
  assert.equal(page.g.data.phase, 'ready');
  page.step(0.1, {down: true, x: 640, y: 494});
  page.step(0.1, {down: false, x: 640, y: 390});
  assert.equal(page.g.data.phase, 'waiting');
  page.step(0.1, {down: true, x: 640, y: 494});
  page.step(0.1, {down: false, x: 745, y: 494});
  assert.equal(page.g.data.phase, 'waiting');
  assert.equal(page.g.levelMisses, 2);
  page.step(1.5);
  assert.equal(page.g.data.phase, 'speak');
  drag(page, 640, 494, 750, 494);
  assert.equal(page.g.won, true);
});

test('autopilots follow ordinary player transitions in both levels and in the teacher example', () => {
  for (const name of ['g02', 'g04', 'g06']) {
    for (const [level, demo] of [[0, true], [0, false], [1, false]]) {
      const page = loadPage(name, level, demo);
      page.g.auto = true;
      page.step(17);
      assert.equal(page.g.won, true, name + ' level ' + (level + 1) + ' demo ' + demo);
      assert.equal(page.g.levelMisses, 0);
    }
  }
});
