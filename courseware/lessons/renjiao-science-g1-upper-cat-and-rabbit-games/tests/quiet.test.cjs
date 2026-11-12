const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

function game() {
  let rules;
  vm.runInNewContext(readFileSync(path.resolve(__dirname, '../pages/quiet.js'), 'utf8'), {
    K: {ready() {}, game(config) { rules = config; }},
    Image: class {},
    window: {}
  });
  const g = {
    data: {}, taps: [], keys: {}, events: [], misses: 0, won: false,
    say(text, kind) { this.events.push({text, kind}); },
    miss() { this.misses++; },
    burst() {},
    win() { this.won = true; }
  };
  return {rules, g};
}

function update(rules, g, dt, tap) {
  if (tap) g.taps.push(tap);
  rules.update(g, dt);
  g.taps.length = 0;
}

test('the same pointer-input path can complete both levels', () => {
  const {rules, g} = game();
  assert.equal(rules.levels, 2);
  for (let level = 0; level < rules.levels; level++) {
    rules.reset(g, level);
    g.won = false;
    for (let frame = 0; frame < 720 && !g.won; frame++) {
      rules.autopilot(g);
      update(rules, g, 1 / 60);
    }
    assert.equal(g.won, true, 'level ' + (level + 1));
    assert.deepEqual(Array.from(g.data.steps), level === 0 ? [3, 3] : [0, 4]);
  }
});

test('off-beat taps and bare-lane noise do not pass or remove stars', () => {
  const {rules, g} = game();
  rules.reset(g, 1);
  update(rules, g, 0.05, {x: 177, y: 305});
  update(rules, g, 0.1, {x: 1040, y: 630});
  assert.deepEqual(Array.from(g.data.steps), [0, 0]);
  assert.equal(g.misses, 1);
  assert.equal(g.won, false);
  update(rules, g, 0.53, {x: 1040, y: 630});
  assert.equal(g.data.steps[0], 1);
  assert.equal(g.won, false);
  update(rules, g, 0.75);
  assert.equal(g.data.selected, null);
  assert.equal(rules.starsFor(g), 3);
});

test('keyboard and pointer share one beat and a second tap cannot take a second step', () => {
  const {rules, g} = game();
  rules.reset(g, 1);
  g.keys.down = true;
  update(rules, g, 0.65, {key: true});
  assert.equal(g.data.selected, 1);
  assert.equal(g.data.steps[1], 1);
  update(rules, g, 0.04, {x: 1040, y: 630});
  assert.equal(g.data.steps[1], 1);
  assert.equal(g.misses, 0);
});
