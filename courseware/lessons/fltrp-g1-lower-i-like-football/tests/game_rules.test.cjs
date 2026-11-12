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
    fx() {}, move() {}, drop() {}, jump() {},
    award() { result.awarded++; },
    lost() { result.misses++; engine.adapt(result.world, result.misses); },
    resetCheckpoint() { result.resetCheckpoints++; },
  };
  return {result, tick: input => engine.update(result.world, level, input, dt, feedback)};
}

function input(...keys) {
  return {held: key => keys.includes(key), press: key => keys.includes(key)};
}

for (const [template, page] of [['magnetMarbles', 'aim-the-club'], ['sortingDepot', 'sort-the-clubs']]) {
  test(page + ' completes all three levels twice', () => {
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
        if (level.queue) assert.equal(result.world.locked.value, level.queue.at(-1));
        if (level.items) assert.ok(result.world.state.items.every(position => position < 0));
      }
    }
  });
}

test('the same number of football players with the wrong speaker gives no point', () => {
  const {config, engine} = game('magnetMarbles', 'aim-the-club');
  const level = config.levels[0];
  const {result, tick} = start(engine, level);
  assert.equal(level.queue[0], 'we-foot');
  assert.deepEqual({...level.targets[1]}, {x: 640, value: 'they-foot'});
  tick(input('action'));
  for (let frame = 0; frame < 180 && !result.misses; frame++) tick(input());
  assert.deepEqual([result.awarded, result.misses, result.world.i, result.world.locked, result.world.help], [0, 1, 0, null, false]);
});

test('pushing the football preference card to the basketball dock leaves it unparked', () => {
  const {config, engine} = game('sortingDepot', 'sort-the-clubs');
  const level = config.levels[0];
  const {result, tick} = start(engine, level);
  for (const key of ['right','up','right','down','left','down','right']) {
    tick(input(key));
    for (let frame = 0; frame < 22; frame++) tick(input());
  }
  assert.deepEqual([result.awarded, result.misses, result.world.help], [0, 1, false]);
  assert.equal(result.world.state.items[0], 3 * 9 + 4);
});
