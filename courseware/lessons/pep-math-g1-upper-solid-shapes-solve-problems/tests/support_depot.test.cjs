const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const load = file => fs.readFileSync(file, 'utf8');
const dt = 1 / 60;

function mechanics() {
  const game = {data: {}, level: 0, follow(selector, resolve) { this.anchor = {selector, resolve}; }};
  const context = vm.createContext({K: {ready() {}, game: () => game}});
  vm.runInContext(load(path.join(templates, 'classic.js')), context);
  vm.runInContext(
    'globalThis.capture = {...Classic, create: (config, engine) => {globalThis.depot = {config, engine}; return {};}}',
    context,
  );
  vm.runInContext(load(path.join(templates, 'sortingDepot.js')).replace('=Classic;', '=capture;'), context);
  vm.runInContext(load(path.join(lesson, 'pages/support-depot.js')), context);
  return {...context.depot, game};
}

function runLevel(engine, level) {
  engine.validate(level);
  const world = engine.reset(level);
  const result = {world, progress: 0, misses: 0};
  const feedback = {
    fx() {},
    move() {},
    award() { result.progress++; },
    lost() { engine.adapt(world, ++result.misses); },
  };
  const tick = input => engine.update(world, level, input, dt, feedback);
  return {result, tick};
}

function runPilot(engine, level, wanted) {
  const {result, tick} = runLevel(engine, level);
  for (let frame = 0; frame < 3600 && result.progress < wanted; frame++) {
    tick(engine.pilot(result.world, level, dt));
  }
  assert.equal(result.progress, wanted);
  assert.equal(result.misses, 0);
  return result.world;
}

test('all three levels can be cleared twice using the template’s movement and category rules', () => {
  const {config, engine} = mechanics();
  const course = JSON.parse(load(path.join(lesson, 'lesson.json')));
  const scene = course.scenes.find(item => item.page === 'support-depot');
  const cueIds = new Set(config.cues.flatMap(cues => Object.values(cues)));
  assert.deepEqual([...cueIds].sort(), Object.keys(scene.gameAudio).sort());
  assert.deepEqual(Array.from(config.levels, level => level.items.length), [2, 3, 4]);
  for (let replay = 0; replay < 2; replay++) {
    for (const level of config.levels) {
      const world = runPilot(engine, level, level.items.length);
      const width = level.map[0].length;
      for (const [index, item] of level.items.entries()) {
        const position = -1 - world.state.items[index];
        const dock = level.docks.find(place => place.x + place.y * width === position);
        assert.equal(dock?.group, item.group);
      }
    }
  }
});

test('side rails still leave a rolling path, so the support dock rejects that picture', () => {
  const {config, engine} = mechanics();
  const level = config.levels[0];
  const {result, tick} = runLevel(engine, level);
  function press(key) {
    tick({held: value => value === key, press: value => value === key});
    for (let frame = 0; frame < 26; frame++) tick({held: () => false, press: () => false});
  }
  for (const key of ['right', 'up', 'right', 'down', 'left', 'down']) press(key);
  const position = result.world.state.items[0];
  assert.equal(position, 3 * 8 + 4);
  press('right');
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 0);
  assert.equal(result.world.state.items[0], position);
  assert.equal(result.world.help, false);
  press('right');
  assert.equal(result.misses, 2);
  assert.equal(result.world.help, true);
});

test('the teacher’s first move parks the side-rails picture in the arrow dock', () => {
  const {config, engine, game} = mechanics();
  const first = config.levels[0];
  const world = runPilot(engine, first, 1);
  assert.equal(world.state.items[0], -1 - (2 * 8 + 5));
  assert.equal(world.state.items[1], 3 * 8 + 2);
  const dockCenterX = world.ox + 5.5 * world.s;
  const dockCenterY = world.oy + 2.5 * world.s;
  game.data.w = world;
  const {x, y, w, h} = game.anchor.resolve();
  assert.equal(game.anchor.selector, '#depot-demo-dock');
  assert.equal(x + w / 2, dockCenterX);
  assert.equal(y + h / 2, dockCenterY);
});
