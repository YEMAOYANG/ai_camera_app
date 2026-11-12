const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const kit = path.resolve(lesson, '../../kit/game_templates');
const load = file => fs.readFileSync(file, 'utf8');
const step = 1 / 60;

function mechanics(template, page) {
  const context = vm.createContext({K: {ready() {}, game() {}}});
  vm.runInContext(load(path.join(kit, 'classic.js')), context);
  vm.runInContext(
    'globalThis.capture = {...Classic, create: (config, engine) => {globalThis.run = {config, engine}; return {};}}',
    context,
  );
  const templateSource = load(path.join(kit, template + '.js')).replace('=Classic;', '=capture;');
  vm.runInContext(templateSource, context);
  vm.runInContext(load(path.join(lesson, 'pages', page + '.js')), context);
  return context.run;
}

function play(engine, level, select, stop) {
  const world = engine.reset(level, 0);
  const outcome = {progress: 0, misses: 0, resets: 0, world};
  const feedback = {
    fx() {}, move() {}, drop() {}, jump() {},
    award() { outcome.progress++; },
    lost() { outcome.misses++; engine.adapt?.(world, outcome.misses); },
    resetCheckpoint() { outcome.progress = 0; outcome.resets++; },
  };
  for (let frame = 0; frame < 60 * 70; frame++) {
    engine.update(world, level, select(world, frame), step, feedback);
    if (stop(outcome)) break;
  }
  return outcome;
}

const gamePages = {platformHop: 'cloud-route', orchardCatch: 'orchard-sort', fallingTiles: 'tile-fit'};
for (const [template, page] of Object.entries(gamePages)) {
  test(`${page} uses its native rules to finish all three levels twice`, () => {
    const {engine, config} = mechanics(template, page);
    assert.equal(config.levels.length, 3);
    const lessonSource = JSON.parse(load(path.join(lesson, 'lesson.json')));
    const scene = lessonSource.scenes.find(scene => scene.key === page);
    const usedCues = config.cues.flatMap(level => Object.values(level));
    assert.deepEqual([...new Set(usedCues)].sort(), Object.keys(scene.gameAudio).sort());
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        engine.validate(level);
        const expected = engine.goal(level);
        const result = play(engine, level, world => engine.pilot(world, level, step), state => state.progress === expected);
        assert.equal(result.progress, expected);
        assert.equal(result.misses, 0);
        if (template === 'orchardCatch') assert.deepEqual([...result.world.fill], [...level.capacity]);
      }
    }
  });
}

function keys(...pressed) {
  return {held: key => pressed.includes(key), press: key => pressed.includes(key)};
}

test('landing on the higher distractor does not count as the next number', () => {
  const {engine, config} = mechanics('platformHop', 'cloud-route');
  const result = play(engine, config.levels[0], (_, frame) => {
    if (frame === 0) return keys('right', 'action');
    return frame < 14 ? keys('right') : keys();
  }, state => state.misses === 1);
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 0);
  assert.equal(result.world.platform[3], 10);
});

test('a caught bunch that does not fit its basket cannot score', () => {
  const {engine, config} = mechanics('orchardCatch', 'orchard-sort');
  const result = play(engine, config.levels[0], (world, frame) => {
    if (frame === 0) return keys('action');
    const landing = world.index === 0 ? 350 : 930;
    if (Math.abs(world.x - landing) < 16) return keys();
    return keys(world.x > landing ? 'left' : 'right');
  }, state => state.resets === 1);
  assert.equal(result.resets, 1);
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 0);
  assert.deepEqual([...result.world.fill], [0, 0]);
});

test('an adjacent pair with the wrong sum leaves an obstacle and scores nothing', () => {
  const {engine, config} = mechanics('fallingTiles', 'tile-fit');
  const result = play(engine, config.levels[0], (_, frame) => (
    frame < 2 ? keys('left') : keys('action')
  ), state => state.misses === 1);
  assert.equal(result.misses, 1);
  assert.equal(result.progress, 0);
  assert.equal(result.world.board.at(-1)[0], 4);
  assert.equal(result.world.board.at(-1)[1], 1);
});
