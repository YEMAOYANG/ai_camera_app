const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const read = file => fs.readFileSync(file, 'utf8');
const scenes = JSON.parse(read(path.join(lesson, 'lesson.json'))).scenes;
const cards = JSON.parse(read(path.join(lesson, 'art-source/shore-cards.json')));
const dt = 1 / 60;

function game(template, page) {
  const context = vm.createContext({K: {ready() {}, game() {}}});
  vm.runInContext(read(path.join(templates, 'classic.js')), context);
  vm.runInContext('globalThis.capture = {...Classic, create(config, engine) {globalThis.game = {config, engine}; return {};}}', context);
  vm.runInContext(read(path.join(templates, template + '.js')).replace(/=\s*Classic;/, '=capture;'), context);
  vm.runInContext(read(path.join(lesson, 'pages', page + '.js')), context);
  return context.game;
}

function start(engine, level) {
  engine.validate(level);
  const result = {world: engine.reset(level), awarded: 0, misses: 0, resetCheckpoints: 0};
  const feedback = {
    fx() {}, move() {}, drop() {},
    award() { result.awarded++; },
    lost() { result.misses++; engine.adapt(result.world, result.misses); },
    resetCheckpoint() { result.resetCheckpoints++; },
  };
  return {result, tick: input => engine.update(result.world, level, input, dt, feedback)};
}

function input(...keys) {
  return {held: key => keys.includes(key), press: key => keys.includes(key)};
}

for (const [template, page] of [['orchardCatch', 'catch-the-shoes'], ['listenDelivery', 'deliver-to-owners']]) {
  test(page + ' binds every cue and completes three fresh levels twice', () => {
    const {config, engine} = game(template, page);
    const source = scenes.find(scene => scene.key === page);
    assert.equal(config.levels.length, 3);
    const cues = config.cues.flatMap(level => Object.values(level).flat());
    assert.deepEqual([...new Set(cues)].sort(), Object.keys(source.gameAudio).sort());
    for (const action of Object.values(source.gameAudio)) {
      const index = action.lastIndexOf('-');
      const line = scenes.find(scene => scene.key === action.slice(0, index)).script[Number(action.slice(index + 1)) - 1];
      assert.ok(line.say);
    }
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const {result, tick} = start(engine, level);
        const target = engine.goal(level);
        for (let frame = 0; frame < 6000 && result.awarded < target; frame++) {
          tick(engine.pilot(result.world, level, dt));
        }
        assert.equal(result.awarded, target);
        if (level.capacity) assert.deepEqual(Array.from(result.world.fill), Array.from(level.capacity));
        if (level.orders) assert.equal(result.world.order, level.orders.length);
      }
    }
  });
}

test('a two-shoe batch does not fit the one-space basket', () => {
  const {config, engine} = game('orchardCatch', 'catch-the-shoes');
  const {result, tick} = start(engine, config.levels[0]);
  Object.assign(result.world, {x: 350, side: 1, fall: .999, delay: 0});
  tick(input());
  assert.deepEqual([result.awarded, result.misses, result.world.index, result.resetCheckpoints], [0, 1, 0, 1]);
  assert.equal(result.world.help, false);
});

test('same shorts beside the duck and the wrong owner both give no progress', () => {
  const {config, engine} = game('listenDelivery', 'deliver-to-owners');
  const {result, tick} = start(engine, config.levels[0]);
  const {world} = result;
  tick(input('action'));
  assert.deepEqual([result.awarded, result.misses, world.carried, world.help], [0, 1, null, false]);
  Object.assign(world, {col: 3, row: 4, cooldown: 0});
  tick(input('action'));
  assert.deepEqual([result.awarded, world.carried], [1, 'under']);
  Object.assign(world, {col: 2, row: 0, cooldown: 0});
  tick(input('action'));
  assert.deepEqual([result.awarded, result.misses, world.order, world.carried], [1, 2, 0, 'under']);
  Object.assign(world, {col: 6, row: 0, cooldown: 0});
  tick(input('action'));
  assert.deepEqual([result.awarded, world.order, world.carried], [2, 1, null]);
});

test('pair, count and location distractors use identical cutouts where intended', () => {
  const pieces = name => cards[name].pieces;
  assert.deepEqual(pieces('quiz-pair-shoes').map(piece => piece[0]), ['rain-shoe', 'rain-shoe']);
  assert.equal(pieces('quiz-one-shoe').length, 1);
  assert.equal(pieces('quiz-three-socks').length, 3);
  assert.equal(pieces('quiz-two-shorts').length, 2);
  assert.deepEqual(pieces('pick-under').map(piece => piece[0]), pieces('pick-beside').map(piece => piece[0]));
  assert.equal(pieces('pick-under')[0][1], pieces('pick-under')[1][1]);
  assert(pieces('pick-under')[0][2] < pieces('pick-under')[1][2]);
  assert.equal(pieces('pick-beside')[0][2], pieces('pick-beside')[1][2]);
});
