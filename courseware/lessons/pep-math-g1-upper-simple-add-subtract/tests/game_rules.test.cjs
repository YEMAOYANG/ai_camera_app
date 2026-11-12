const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const load = file => fs.readFileSync(file, 'utf8');
const dt = 1 / 60;

function mechanics(template, page) {
  const context = vm.createContext({K: {ready() {}, game: () => ({follow() {}})}});
  vm.runInContext(load(path.join(templates, 'classic.js')), context);
  vm.runInContext(
    'globalThis.capture = {...Classic, create: (config, engine) => {globalThis.courseGame = {config, engine}; return {};}}',
    context,
  );
  const source = load(path.join(templates, template + '.js')).replace(/=\s*Classic;/, '=capture;');
  vm.runInContext(source, context);
  vm.runInContext(load(path.join(lesson, 'pages', page + '.js')), context);
  return context.courseGame;
}

function keys(...values) {
  return {held: key => values.includes(key), press: key => values.includes(key)};
}

function play(engine, level, input, shouldStop) {
  engine.validate(level);
  const world = engine.reset(level);
  const result = {world, progress: 0, misses: 0};
  const feedback = {
    fx() {}, move() {}, drop() {},
    award() { result.progress++; },
    lost() { engine.adapt(world, ++result.misses); },
  };
  for (let frame = 0; frame < 4800 && !shouldStop(result); frame++) {
    engine.update(world, level, input(world), dt, feedback);
  }
  return result;
}

const pages = {fallingTiles: 'match-workbench', listenDelivery: 'deliver-materials'};
for (const [template, page] of Object.entries(pages)) {
  test(page + ' clears all three levels twice using the native mechanics', () => {
    const {config, engine} = mechanics(template, page);
    const course = JSON.parse(load(path.join(lesson, 'lesson.json')));
    const scene = course.scenes.find(entry => entry.page === page);
    const cues = config.cues.flatMap(level => [level.goal, level.hint, level.hint2, level.praise, ...(level.steps ?? [])]);
    assert.deepEqual([...new Set(cues)].sort(), Object.keys(scene.gameAudio).sort());
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const expected = engine.goal(level);
        const result = play(engine, level, world => engine.pilot(world, level, dt),
          state => state.progress === expected);
        assert.equal(result.progress, expected);
        assert.equal(result.misses, 0);
      }
    }
  });
}

test('the lesson’s pairs encode the exact remaining quantity', () => {
  const {config} = mechanics('fallingTiles', 'match-workbench');
  for (const level of config.levels) {
    for (const [result, expression] of level.pairs) {
      const [original, removed] = expression.slice(5).split('-').map(Number);
      assert.equal(Number(result.slice(4)), original - removed);
    }
  }
});

test('a free landing spot beside the wrong subtraction cannot clear a tile', () => {
  const {config, engine} = mechanics('fallingTiles', 'match-workbench');
  const result = play(engine, config.levels[1], world => world.x < 4 ? keys('right') : keys('action'),
    state => state.misses === 1);
  assert.equal(result.progress, 0);
  assert.equal(result.world.board[6][4], 'rem-02');
  assert.equal(result.world.board[6][3], 'take-17-07');
  assert.equal(result.world.board[6][5], 'take-16-10');
});

test('each delivery order must match the stated change in the ones place', () => {
  const {config} = mechanics('listenDelivery', 'deliver-materials');
  const delta = {'plus-five':5, 'plus-three':3, 'minus-four':-4, 'plus-six':6, 'minus-five':-5};
  for (const [index, level] of config.levels.entries()) {
    for (const [order, [cargo, destination]] of level.orders.entries()) {
      const start = Number(cargo.slice(6));
      const change = delta[config.cues[index].steps[2 * order + 1]];
      const end = Number(destination.slice(5));
      assert.equal(end, start + change);
      assert.ok(end >= 10 && end < 20);
    }
  }
});

test('delivery to the unchanged original quantity is rejected after pickup', () => {
  const {config, engine} = mechanics('listenDelivery', 'deliver-materials');
  const level = config.levels[0];
  const result = play(engine, level, world => {
    if (world.carried === null || world.row > 0) return engine.pilot(world, level, dt);
    return world.col < 6 ? keys('right') : keys('action');
  }, state => state.misses === 1);
  assert.equal(result.progress, 1);
  assert.equal(result.world.carried, 'stock-12');
  assert.equal(result.world.col, 6);
  assert.equal(result.world.delivered.size, 0);
});
