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

function runner(engine, level, index) {
  engine.validate(level, index);
  const world = engine.reset(level);
  const state = {world, correct: 0, wrong: 0};
  const feedback = {
    fx() {}, move() {}, drop() {}, resetCheckpoint() { state.correct = 0; },
    award() { state.correct++; },
    lost() { state.wrong++; engine.adapt(world, state.wrong); },
  };
  const tick = input => engine.update(world, level, input, dt, feedback);
  return {state, tick};
}

function input(...keys) {
  return {held: key => keys.includes(key), press: key => keys.includes(key)};
}

for (const [template, page] of [['fallingTiles', 'swap-pair-play'], ['sortingDepot', 'sort-by-total']]) {
  test(page + ' follows the approved rules through three levels twice', () => {
    const {config, engine} = loadGame(template, page);
    const scene = JSON.parse(read(path.join(lesson, 'lesson.json'))).scenes.find(s => s.key === page);
    assert.deepEqual([...new Set(config.cues.flatMap(level => Object.values(level)))].sort(),
      Object.keys(scene.gameAudio).sort());
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const [index, level] of config.levels.entries()) {
        const {state, tick} = runner(engine, level, index);
        const target = engine.goal(level);
        for (let frame = 0; frame < 4200 && state.correct < target; frame++) {
          tick(engine.pilot(state.world, level, dt));
        }
        assert.equal(state.correct, target);
        assert.equal(state.wrong, 0);
      }
    }
  });
}

test('a total of twelve does not make six plus six a swap of four plus eight', () => {
  const {config, engine} = loadGame('fallingTiles', 'swap-pair-play');
  const {state, tick} = runner(engine, config.levels[2], 2);
  assert.equal(state.world.x, 2);
  tick(input('right'));
  tick(input('right'));
  // This empty cell touches two cards whose sum is twelve but whose
  // addends are not the reverse of four and eight.
  assert.equal(state.world.x, 4);
  tick(input('action'));
  assert.equal(state.correct, 0);
  assert.equal(state.wrong, 1);
  assert.equal(state.world.i, 0);
});

test('a first-level cargo cannot park at the adjacent wrong total', () => {
  const {config, engine} = loadGame('sortingDepot', 'sort-by-total');
  const level = config.levels[0];
  const {state, tick} = runner(engine, level, 0);
  function move(key) {
    tick(input(key));
    while (state.world.cool > 0) tick(input());
  }
  const route = ['up','right','right','down','down','left','left','up','up','right','down','left','down','right','right'];
  route.forEach(move);
  assert.equal(state.correct, 0);
  assert.equal(state.wrong, 1);
  assert.equal(state.world.wrongGroup, 11);
  assert.ok(state.world.state.items.every(position => position >= 0));
});
