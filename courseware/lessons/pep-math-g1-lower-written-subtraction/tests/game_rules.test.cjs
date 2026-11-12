const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const read = file => fs.readFileSync(file, 'utf8');
const scenes = JSON.parse(read(path.join(lesson, 'lesson.json'))).scenes;
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
  engine.validate(level, 0);
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

const games = [['compareSnake', 'enough-to-remove'], ['fallingTiles', 'match-remaining']];
for (const [template, page] of games) {
  test(page + ' has recorded cue bindings and a legal two-pass route through all three levels', () => {
    const {config, engine} = loadGame(template, page);
    const scene = scenes.find(s => s.key === page);
    assert.deepEqual([...new Set(config.cues.flatMap(level => Object.values(level).flat()))].sort(),
      Object.keys(scene.gameAudio).sort());
    for (const actionId of Object.values(scene.gameAudio)) {
      const [, key, number] = /^(.+)-(\d+)$/.exec(actionId);
      assert.ok(scenes.find(s => s.key === key).script[Number(number) - 1].say);
    }
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const target = engine.goal(level);
        const state = runGame(engine, level, world => engine.pilot(world, level, dt), state => state.correct === target);
        assert.equal(state.correct, target);
        assert.equal(state.wrong, 0);
      }
    }
  });
}

test('an equal quantity cannot score in the less-than round', () => {
  const {config, engine} = loadGame('compareSnake', 'enough-to-remove');
  const state = runGame(engine, config.levels[0], () => input('up'), s => s.wrong === 1);
  assert.equal(state.wrong, 1);
  assert.equal(state.correct, 0);
  assert.equal(state.world.round, 0);
  assert.equal(state.world.ref, 6);
});

test('a wrong remainder can miss and then recover on the same level', () => {
  const {config, engine} = loadGame('fallingTiles', 'match-remaining');
  const state = runGame(engine, config.levels[0], (world, frame) => {
    if (frame === 0) return input('action');
    if (world.delay > 0) return input();
    if (world.x > 1) return input('left');
    return input('action');
  }, s => s.correct === 1);
  assert.equal(state.wrong, 1);
  assert.equal(state.correct, 1);
  assert.equal(state.world.board.at(-1)[0], null);
  assert.equal(state.world.board.at(-1)[3], 'stock-32');
});

test('each visible comparison and subtraction has one matching choice', () => {
  const snake = loadGame('compareSnake', 'enough-to-remove').config;
  const tests = [(a,b) => a < b, (a,b) => a === b, (a,b) => a > b];
  snake.levels.forEach((level, index) => {
    let ref = level.start;
    for (const round of level.rounds) {
      assert.equal(round.relation, ['lt','eq','gt'][index]);
      const correct = round.foods.map(x => x[2]).filter(value => tests[index](value, ref));
      assert.equal(correct.length, 1);
      [ref] = correct;
    }
  });
  const tiles = loadGame('fallingTiles', 'match-remaining').config;
  for (const level of tiles.levels) {
    const [record, result] = level.pairs[0];
    const [, top, bottom] = /^ledger-(\d+)-(\d+)$/.exec(record);
    assert.equal(result, 'stock-' + (Number(top) - Number(bottom)));
    assert.equal(level.bottom.filter(v => v === result).length, 1);
    assert.equal(level.bottom.filter(v => v).length, 3);
    assert.equal(level.symbol, record);
  }
});
