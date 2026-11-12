const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function game(name, level = 0) {
  let config;
  const K = {ready() {}, game(definition) { config = definition; }, sfx: {ok() {}}};
  const source = readFileSync(path.join(__dirname, '..', 'pages', `${name}.js`), 'utf8');
  vm.runInNewContext(source, {K, window: {}, Image: class { naturalWidth = 1024; naturalHeight = 576; }});
  const g = {level, data: {}, pointer: {down: false}, taps: [], keys: {}, messages: [],
    misses: 0, wins: 0, burst() {}, sparkle() {}, miss() { this.misses++; },
    win() { this.wins++; }, say(text, kind) { this.messages.push({text, kind}); }};
  config.reset(g, level);
  const tick = (seconds, auto = false) => {
    for (let frame = 0; frame < Math.round(seconds * 100) && !g.wins; frame++) {
      if (auto) config.autopilot(g, 0.01);
      config.update(g, 0.01);
      g.taps.length = 0;
    }
  };
  const press = (x, y) => {
    Object.assign(g.pointer, {x, y, down: true});
    g.taps.push({x, y});
    tick(0.01);
  };
  const release = () => { g.pointer.down = false; tick(0.01); };
  return {config, g, tick, press, release};
}

function slide(lens, index, to) {
  const photo = {x: [46, 670][index], y: 109, w: 564, h: 317};
  const y = photo.y + photo.h * (lens.g.data.sheet.height + 112) / 576 - 5;
  lens.press(photo.x + photo.w * lens.g.data.positions[index] / 1024, y);
  lens.g.pointer.x = photo.x + photo.w * to / 1024;
  lens.tick(0.08);
  lens.release();
  lens.tick(0.58);
}

test('a live compare window does not record unlike parts, and stores both matched crops', () => {
  const lens = game('lens');
  slide(lens, 0, 246);
  assert.equal(lens.g.data.locked, false);
  slide(lens, 1, 765);
  assert.equal(lens.g.data.locked, false);
  assert.equal(lens.g.misses, 1);
  assert.equal(lens.g.messages[0].kind, 'no');
  slide(lens, 1, 418);
  assert.equal(lens.g.data.locked, true);
  assert.deepEqual(Array.from(lens.g.data.positions), [246, 418]);
  lens.config.reset(lens.g, 1);
  assert.deepEqual(Array.from(lens.g.data.earlier), [246, 418]);
  assert.equal(lens.g.data.sheet.flip[1], true);
  slide(lens, 0, 818);
  slide(lens, 1, 798);
  assert.equal(lens.g.data.locked, false);
  slide(lens, 1, 226);
  lens.tick(1);
  assert.equal(lens.g.wins, 1);
  assert.deepEqual(Array.from(lens.g.data.positions), [818, 226]);
});

test('both lens rounds finish through pointer events driven by autopilot', () => {
  for (const level of [0, 1]) {
    const lens = game('lens', level);
    lens.tick(8, true);
    assert.equal(lens.g.wins, 1);
    assert.equal(lens.g.misses, 0);
  }
});

test('a teacher restart leaves both window positions alone until a new held gesture', () => {
  const lens = game('lens');
  const {g} = lens;
  lens.tick(1.5, true);
  assert.equal(g.pointer.down, true);
  lens.config.reset(g, 0);
  assert.equal(g.pointer.down, false);
  const start = Array.from(g.data.positions);
  Object.assign(g.pointer, {x: 190, y: 170});
  g.taps.push({x: 190, y: 170});
  lens.tick(1);
  assert.deepEqual(Array.from(g.data.positions), start);
  lens.press(332, 174);
  g.pointer.x = 250;
  lens.tick(0.12);
  assert.notEqual(g.data.positions[0], start[0]);
});

test('a short press is safe and a valid release records two equal heights and different waves', () => {
  const trial = game('quiet');
  trial.press(640, 578); trial.tick(0.15); trial.release();
  assert.equal(trial.g.misses, 1);
  assert.equal(trial.g.data.results.every(result => !result), true);
  trial.press(640, 578); trial.tick(1.30); trial.release(); trial.tick(2.1);
  const [bare, soft] = trial.g.data.results;
  assert.equal(trial.g.wins, 1);
  assert.equal(bare.height, soft.height);
  assert.ok(bare.amplitude > soft.amplitude);
});

test('the second trial keeps its first result across an invalid release, then matches its height', () => {
  const trial = game('quiet', 1);
  trial.press(640, 578); trial.tick(1.22); trial.release(); trial.tick(0.41);
  const first = trial.g.data.results[0];
  assert.ok(first);
  assert.equal(trial.g.data.results[1], null);
  trial.press(640, 578); trial.tick(0.25); trial.release();
  assert.equal(trial.g.data.results[0], first);
  assert.equal(trial.g.data.results[1], null);
  trial.g.keys.jump = true;
  trial.g.taps.push({key: true});
  trial.tick(1.21);
  trial.g.keys.jump = false;
  trial.tick(2);
  assert.equal(trial.g.wins, 1);
  assert.equal(trial.g.data.results[1].height, first.height);
});

test('the drop autopilot uses the press and release controls for both rounds', () => {
  for (const level of [0, 1]) {
    const trial = game('quiet', level);
    trial.tick(10, true);
    assert.equal(trial.g.wins, 1);
    assert.equal(trial.g.misses, 0);
    assert.equal(trial.g.data.results[0].height, trial.g.data.results[1].height);
  }
});

test('handoff during the demo discards a held probe without making an observation', () => {
  const trial = game('quiet');
  trial.tick(2.4, true);
  assert.equal(trial.g.data.charge, 'pointer');
  trial.config.reset(trial.g, 0);
  trial.tick(1);
  assert.equal(trial.g.pointer.down, false);
  assert.equal(trial.g.data.height, 0);
  assert.equal(trial.g.data.results.some(Boolean), false);
  trial.press(640, 578);
  trial.tick(1.27);
  trial.release();
  trial.tick(2.1);
  assert.equal(trial.g.wins, 1);
});
