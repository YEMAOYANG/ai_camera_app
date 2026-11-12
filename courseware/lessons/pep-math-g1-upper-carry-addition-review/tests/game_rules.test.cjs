const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const read = file => fs.readFileSync(file, 'utf8');
const dt = 1 / 60;

function loadGame(template, page) {
  const context = vm.createContext({K: {ready() {}, game() {}}});
  vm.runInContext(read(path.join(templates, 'classic.js')), context);
  vm.runInContext('globalThis.capture = {...Classic, create(config, engine) {globalThis.game = {config, engine}; return {};}}', context);
  vm.runInContext(read(path.join(templates, template + '.js')).replace(/=\s*Classic;/, '=capture;'), context);
  vm.runInContext(read(path.join(lesson, 'pages', page + '.js')), context);
  return context.game;
}

function runGame(engine, level, choose, finished) {
  engine.validate(level);
  const world = engine.reset(level);
  const state = {world, correct: 0, wrong: 0};
  const feedback = {
    fx() {}, move() {}, drop() {}, jump() {},
    award() { state.correct++; },
    lost() { state.wrong++; engine.adapt(world, state.wrong); },
  };
  for (let frame = 0; frame < 4200 && !finished(state); frame++) {
    engine.update(world, level, choose(world, frame), dt, feedback);
  }
  return state;
}

function input(...keys) {
  return {held: key => keys.includes(key), press: key => keys.includes(key)};
}

const pages = [['magnetMarbles', 'sort-the-rows'], ['bubbleMaze', 'find-the-next-card']];
for (const [template, page] of pages) {
  test(page + ' follows the approved rules through three levels twice', () => {
    const {config, engine} = loadGame(template, page);
    const scene = JSON.parse(read(path.join(lesson, 'lesson.json'))).scenes.find(s => s.key === page);
    const cueNames = config.cues.flatMap(level => Object.values(level).flat());
    assert.deepEqual([...new Set(cueNames)].sort(), Object.keys(scene.gameAudio).sort());
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const target = engine.goal(level);
        const state = runGame(engine, level, world => engine.pilot(world, level, dt), state => state.correct === target);
        assert.equal(state.correct, target);
      }
    }
  });
}

test('hitting the central eleven card fails the call for twelve', () => {
  const {config, engine} = loadGame('magnetMarbles', 'sort-the-rows');
  const state = runGame(engine, config.levels[0], (_,frame) => frame===0 ? input('action') : input(), s => s.wrong===1);
  assert.equal(state.correct, 0);
  assert.equal(state.wrong, 1);
  assert.equal(state.world.i, 0);
  assert.ok(Math.abs(state.world.x-640)<4);
});

test('maze cannot collect the second card before the first', () => {
  const {config, engine} = loadGame('bubbleMaze', 'find-the-next-card');
  const state = runGame(engine, config.levels[0], () => input('down'), s => s.wrong===1);
  assert.equal(state.correct, 0);
  assert.equal(state.wrong, 1);
  assert.equal(state.world.map[3][1], 'B');
  assert.equal(state.world.i, 0);
});

test('configured sum pairs and three route rules match each arithmetic card', () => {
  const decode = card => card.match(/card-(\d)-(\d)/).slice(1).map(Number);
  const marble = loadGame('magnetMarbles', 'sort-the-rows').config;
  for (const level of marble.levels) {
    for (const [sum, card] of level.pairs) {
      const [a, b] = decode(card);
      assert.equal(a + b, sum);
    }
  }
  const maze = loadGame('bubbleMaze', 'find-the-next-card').config;
  const cards = maze.levels.map(level => level.route.map(id => decode(maze.art.icons[id])));
  assert.deepEqual(JSON.stringify(cards), JSON.stringify([[[8,3],[8,4],[8,5]],[[5,7],[6,7],[7,7]],[[9,7],[8,8],[7,9]]]));
});
