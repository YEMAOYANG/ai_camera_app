const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const kit = path.resolve(lesson, '../../kit/game_templates');
const load = file => fs.readFileSync(file, 'utf8');
const dt = 1 / 60;

function mechanics(template, page) {
  const context = vm.createContext({K: {ready() {}, game() {}}});
  vm.runInContext(load(path.join(kit, 'classic.js')), context);
  vm.runInContext(
    'globalThis.capture = {...Classic, create: (config, engine) => {globalThis.run = {config, engine}; return {};}}',
    context,
  );
  const templateSource = load(path.join(kit, template + '.js')).replace(/=\s*Classic;/, '=capture;');
  vm.runInContext(templateSource, context);
  vm.runInContext(load(path.join(lesson, 'pages', page + '.js')), context);
  return context.run;
}

function play(engine, level, select, stop) {
  const world = engine.reset(level);
  const result = {world, progress: 0, misses: 0};
  const feedback = {
    fx() {}, move() {}, drop() {}, jump() {},
    award() { result.progress++; },
    lost() { result.misses++; engine.adapt?.(world, result.misses); },
  };
  for (let frame = 0; frame < 4200; frame++) {
    engine.update(world, level, select(world, frame), dt, feedback);
    if (stop(result)) break;
  }
  return result;
}

function keys(...pressed) {
  return {held: key => pressed.includes(key), press: key => pressed.includes(key)};
}

const pages = {magnetMarbles: 'marble-pack', listenDelivery: 'parcel-delivery'};
for (const [template, page] of Object.entries(pages)) {
  test(`${page} completes three levels twice through the approved mechanics`, () => {
    const {engine, config} = mechanics(template, page);
    const lessonSource = JSON.parse(load(path.join(lesson, 'lesson.json')));
    const scene = lessonSource.scenes.find(scene => scene.key === page);
    const usedCues = config.cues.flatMap(level => [...level.steps, level.goal, level.hint, level.hint2, level.praise]);
    assert.deepEqual([...new Set(usedCues)].sort(), Object.keys(scene.gameAudio).sort());
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const [index, level] of config.levels.entries()) {
        engine.validate(level);
        const expected = engine.goal(level);
        assert.equal(config.cues[index].steps.length, expected);
        const result = play(engine, level, world => engine.pilot(world, level, dt), state => state.progress === expected);
        assert.equal(result.progress, expected);
        if (template === 'listenDelivery') {
          assert.equal(result.world.order, level.orders.length);
          assert.equal(result.world.carried, null);
          for (const [cargo, station] of level.orders) assert.equal(result.world.delivered.get(station), cargo);
        } else {
          assert.equal(result.misses, 0);
        }
      }
    }
  });
}

test('hitting the tied bundle cannot answer the ten-loose-sticks cue', () => {
  const {engine, config} = mechanics('magnetMarbles', 'marble-pack');
  const level = config.levels[0];
  engine.validate(level);
  const result = play(engine, level, (_, frame) => {
    if (frame < 15) return keys('right');
    return frame === 15 ? keys('action') : keys();
  }, state => state.misses === 1);
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 0);
  assert.ok(Math.abs(result.world.x - 773) < level.targetWidth / 2);
});

test('a single stick cannot be picked up for a bundle order', () => {
  const {engine, config} = mechanics('listenDelivery', 'parcel-delivery');
  const level = config.levels[0];
  engine.validate(level);
  const result = play(engine, level, world => world.col < 6 ? keys('right') : keys('action'),
    state => state.misses === 1);
  assert.equal(result.world.col, 6);
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 0);
  assert.equal(result.world.carried, null);
});

test('a bundle stays on the truck when offered at the one-unit station', () => {
  const {engine, config} = mechanics('listenDelivery', 'parcel-delivery');
  const level = config.levels[0];
  engine.validate(level);
  const result = play(engine, level, world => {
    if (!world.carried || world.row > 0) return engine.pilot(world, level, dt);
    return world.col < 6 ? keys('right') : keys('action');
  }, state => state.misses === 1);
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 1);
  assert.equal(result.world.carried, 'stick-bundle');
  assert.equal(result.world.delivered.size, 0);
});
