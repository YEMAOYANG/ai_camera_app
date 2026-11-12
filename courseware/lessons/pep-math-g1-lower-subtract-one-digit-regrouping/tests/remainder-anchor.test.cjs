const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function loadLessonGame() {
  const lesson = path.resolve(__dirname, '..');
  const K = {
    gameTemplates: {},
    ready() {},
    $: () => ({}),
    game: definition => ({...definition, follow() {}}),
  };
  const Classic = {
    create(config, mechanic) {
      config.levels.forEach(mechanic.validate);
      return {config, mechanic};
    },
    bot: (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)}),
    clamp: (n, min, max) => Math.max(min, Math.min(max, n)),
    center: (x, y, w, h) => ({x: x - w / 2, y: y - h / 2, w, h}),
    validToken: value => Number.isFinite(value) || typeof value === 'string',
    match: (key, value, level) => level.matches(key, value),
  };
  const context = vm.createContext({K, Classic});
  const template = path.resolve(lesson, '../../kit/game_templates/magnetMarbles.js');
  vm.runInContext(fs.readFileSync(template, 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(lesson, 'pages/aim-at-the-actual-remainder.js'), 'utf8'), context);
  return vm.runInContext('game', context);
}

test('after the final collision the teacher anchor still points to the accepted remainder', () => {
  const {config, mechanic} = loadLessonGame();
  const dt = 1 / 60;
  for (const level of config.levels) {
    const world = mechanic.reset(level);
    let accepted = 0;
    const feedback = {
      move() {}, fx() {}, jump() {}, drop() {},
      award() { accepted++; },
      lost() { assert.fail('The template pilot should hit the correct target'); },
    };
    for (let frame = 0; frame < 1200 && accepted < level.queue.length; frame++) {
      mechanic.update(world, level, mechanic.pilot(world, level), dt, feedback);
      assert.ok(mechanic.target(world, level));
    }
    assert.equal(accepted, level.queue.length);
    assert.equal(world.i, level.queue.length);
    assert.equal(level.matches(undefined, world.locked.value), false);
    assert.ok(Math.abs(mechanic.target(world, level).x + level.targetWidth / 2 - world.locked.x) <= level.drift);
  }
});
