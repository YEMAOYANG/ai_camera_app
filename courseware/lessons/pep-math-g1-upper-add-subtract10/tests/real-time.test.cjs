const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

function loadGame(pageId) {
  let options;
  const quiet = () => {};
  const K = {
    log: [],
    ready: quiet,
    sfx: {coin: quiet, no: quiet, pop: quiet, whoosh: quiet},
    game(config) {
      options = config;
      return {follow: quiet};
    },
  };
  const file = path.join(__dirname, '..', 'pages', pageId + '.js');
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), {K}, {filename: file});
  const game = {
    autoLoop: false,
    banner: quiet,
    burst: quiet,
    confetti: quiet,
    float: quiet,
    keys: {},
    misses: 0,
    pointer: {x: 0, y: 0, down: false},
    say(text) { this.hint = text; },
    shake: quiet,
    sparkle: quiet,
    state: 'play',
    t: 0,
    taps: [],
    miss() { this.misses++; },
    hurt() { assert.fail('A wrong move must leave the child’s progress intact'); },
  };
  return {game, options};
}

test('all four teacher demonstrations use distinct examples and hand level one back to the player', () => {
  const demos = [
    ['game-02', data => data.n, 3],
    ['game-04', data => data.need, 1],
    ['game-06', data => data.a, 1],
    ['game-08', data => data.waves[0].good[0], '3+7'],
  ];
  for (const [id, read, teacherExample] of demos) {
    const {game, options} = loadGame(id);
    game.autoLoop = true;
    options.reset(game, 0);
    assert.equal(read(game.data), teacherExample, id);
    game.autoLoop = false;
    options.reset(game, 0);
    assert.notEqual(read(game.data), teacherExample, id);
    assert.equal(options.starsFor({levelMisses: 5}), 3);
  }
});

test('a real slingshot pull can reach every lamp and a wrong-color hit keeps the earned point', () => {
  function throwAt(game, options, index) {
    const flight = 0.75;
    const x = 772 + (index % 5) * 96;
    const y = 236 + Math.floor(index / 5) * 118;
    const pullX = -(x - 230) / flight / 9.8;
    const pullY = -(y - 470 - 450 * flight * flight) / flight / 9.8;
    assert.ok(Math.hypot(pullX, pullY) < 150);
    game.pointer = {x: 230, y: 470, down: true};
    options.update(game, 0.01);
    game.pointer = {x: 230 + pullX, y: 470 + pullY, down: true};
    options.update(game, 0.01);
    game.pointer.down = false;
    for (let frame = 0; frame < 20; frame++) options.update(game, 0.05);
  }
  const {game, options} = loadGame('game-04');
  for (let lamp = 0; lamp < 10; lamp++) {
    options.reset(game, 0);
    throwAt(game, options, lamp);
    assert.equal(game.data.lamps[lamp].on, false, 'lamp ' + lamp);
    assert.equal(game.data.off, 1);
  }
  options.reset(game, 2);
  throwAt(game, options, 0);
  throwAt(game, options, 9);
  assert.equal(game.data.off, 1);
  assert.equal(game.misses, 1);
  assert.match(game.hint, /先看.*要求/);
  for (let frame = 0; frame < 20; frame++) options.update(game, 0.05);
  assert.equal(game.data.lamps[9].on, true);
});

test('a missed slice on a later wave gives a hint without erasing the last correct slice', () => {
  const {game, options} = loadGame('game-08');
  options.reset(game, 1);
  function swipe(value) {
    game.data.trail = [{x: 420, y: 360, t: game.t}, {x: 570, y: 360, t: game.t}];
    game.data.bulbs = [{s: value, x: 500, y: 360, st: 'fly', t: 0}];
    options.update(game, 0.02);
  }
  swipe('0+10');
  assert.equal(game.data.cut, 1);
  swipe('0+9');
  assert.equal(game.data.cut, 1);
  assert.equal(game.misses, 1);
  assert.match(game.hint, /它等于 10 吗/);
});

test('fishing waits for the equation to swim fully into view before catching it', () => {
  const {game, options} = loadGame('game-06');
  options.reset(game, 0);
  const data = game.data;
  const fish = {st: 'swim', eq: data.need[0], x: 95, y: 410, vx: 80, lane: 0};
  data.fish = [fish];
  data.bx = data.tx = 110;
  data.hook.st = 'down';
  data.hook.y = 410;
  options.update(game, 0.01);
  assert.equal(data.hook.fish, null);
  fish.x = 140;
  options.update(game, 0.01);
  assert.equal(data.hook.fish, fish);
  assert.equal(data.hook.st, 'up');
});

test('swimming fish keep readable space between equations after catches, misses, and wraparound', () => {
  const {game, options} = loadGame('game-06');
  options.reset(game, 2);
  const data = game.data;
  data.fish[0].st = 'spent';
  data.fish[3].st = 'flee';
  for (let frame = 0; frame < 400; frame++) {
    options.update(game, 0.05);
    for (let lane = 0; lane < 3; lane++) {
      const [left, right] = data.fish.filter(fish => fish.lane === lane);
      assert.ok(Math.abs(left.x - right.x) >= 559);
    }
  }
  assert.ok(data.fish.every(fish => fish.st === 'swim'));
});
