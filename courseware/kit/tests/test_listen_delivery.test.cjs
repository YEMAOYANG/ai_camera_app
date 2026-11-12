const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const kit = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(kit, 'game_templates/listenDelivery.js'), 'utf8');
const sample = JSON.parse(fs.readFileSync(path.join(kit, 'examples/classic-arcade/listen-delivery.json'), 'utf8'));
const voice = JSON.parse(fs.readFileSync(path.join(kit, 'examples/arcade-voice.json'), 'utf8'));
const dt = 1 / 60;

function gameFor(level) {
  const K = {gameTemplates: {}};
  const Classic = {
    create: (_, mechanic) => mechanic,
    bot: (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)}),
    ease: (_, target) => target,
    validToken: value => typeof value === 'string' && value.length > 0 || Number.isFinite(value),
  };
  vm.runInNewContext(source, {K, Classic});
  const game = K.gameTemplates.listenDelivery({});
  game.validate(level);
  const world = game.reset(level);
  let progress = 0;
  let misses = 0;
  function update(input) {
    game.update(world, level, input, dt, {
      award() { progress++; },
      lost() { misses++; game.adapt(world, misses); },
      fx() {}, move() {}, drop() {},
    });
  }
  return {
    world, game,
    get progress() { return progress; },
    get misses() { return misses; },
    press(key) {
      for (let i = 0; world.cooldown > dt && i < 60; i++) update(Classic.bot());
      update(Classic.bot(key));
    },
    autopilot() {
      for (let i = 0; i < 3600 && progress < game.goal(level); i++) update(game.pilot(world, level, dt));
    },
  };
}

test('only the ordered item can be collected and only its recipient can accept it', () => {
  const level = structuredClone(sample.levels[0]);
  level.lanes[0].phase = 2; // Keep the path clear during the deliberate wrong-stop checks.
  const play = gameFor(level);
  play.press('right');
  play.press('right');
  play.press('action');
  assert.equal(play.progress, 0);
  assert.equal(play.world.carried, null, 'banana cannot substitute for the requested apple');
  for (let i = 0; i < 3; i++) play.press('left');
  play.press('action');
  assert.equal(play.progress, 1);
  assert.equal(play.world.carried, 'apple');
  for (let i = 0; i < 4; i++) play.press('up');
  assert.equal(play.world.row, 0);
  for (let i = 0; i < 3; i++) play.press('right');
  play.press('action');
  assert.equal(play.progress, 1);
  assert.equal(play.world.carried, 'apple');
  assert.equal(play.world.help, true, 'second miss unlocks assistance');
  for (let i = 0; i < 3; i++) play.press('left');
  play.press('action');
  assert.equal(play.progress, 2);
  assert.equal(play.world.delivered.get('dog'), 'apple');
  assert.equal(play.world.carried, null);
});

test('a lane collision returns the loaded car to the last safe row', () => {
  const level = structuredClone(sample.levels[0]);
  level.lanes[0] = {row: 2, speed: .65, spacing: 6, phase: 2.34};
  const play = gameFor(level);
  for (const key of ['left', 'action', 'up', 'up']) play.press(key);
  assert.equal(play.misses, 1);
  assert.equal(play.world.row, 3);
  assert.equal(play.world.carried, 'apple');
  assert.equal(play.progress, 1);
});

test('the same controls complete every order with unrelated content and shifted traffic', () => {
  for (const original of sample.levels) {
    const level = structuredClone(original);
    for (const station of [...level.pickup, ...level.drop]) station[0] = 'new-' + station[0];
    level.orders = level.orders.map(order => order.map(id => 'new-' + id));
    level.lanes.forEach(lane => lane.phase += 1.7);
    const play = gameFor(level);
    play.autopilot();
    assert.equal(play.progress, level.orders.length * 2);
    assert.equal(play.world.order, level.orders.length);
    assert.equal(play.world.carried, null);
    assert.equal(play.misses, 0);
  }
});

test('each sample step has a registered English command for the exact item or recipient', () => {
  const scripts = new Map(voice.lines.map(line => [line.id, line]));
  for (const [index, level] of sample.levels.entries()) {
    const {steps} = voice.cues['listen-delivery'][index];
    assert.equal(steps.length, level.orders.length * 2);
    level.orders.forEach(([item, recipient], order) => {
      const pickup = scripts.get(steps[order * 2]);
      const drop = scripts.get(steps[order * 2 + 1]);
      assert.match(pickup.text, new RegExp('Pick up the ' + item + '\\.'));
      assert.match(drop.text, new RegExp('take it to the ' + recipient + '\\.'));
      assert.equal(pickup.voice, drop.voice);
    });
  }
});
