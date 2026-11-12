const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lessonDir = path.join(__dirname, '..');
const templates = path.join(__dirname, '../../../kit/game_templates');
const lesson = JSON.parse(fs.readFileSync(path.join(lessonDir, 'lesson.json'), 'utf8'));
const dt = 1 / 60;

function loadGame(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  const K = {gameTemplates: {}, ready() {}, stage: () => ({append() {}}), $() {},
    game(result) { game = result; }};
  const Classic = {
    bot, create: (config, rules) => ({config, rules}), ease: (_, target) => target,
    validToken: value => typeof value === 'string' && value.length > 0,
    clamp: (value, min, max) => Math.min(max, Math.max(min, value))
  };
  const context = vm.createContext({K, Classic});
  vm.runInContext(fs.readFileSync(path.join(templates, template + '.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(lessonDir, 'pages', page + '.js'), 'utf8'), context);
  return {...game, bot};
}

function playLevel({rules, bot}, level) {
  rules.validate(level);
  const world = rules.reset(level);
  let success = 0;
  let misses = 0;
  function update(input) {
    rules.update(world, level, input, dt, {
      award() { success++; },
      lost() { misses++; rules.adapt(world, misses); },
      fx() {}, move() {}, drop() {},
    });
  }
  update(bot('action'));
  assert.equal(success, 0);
  assert.equal(misses, 1);
  for (let i = 0; i < 3600 && success < rules.goal(level); i++) {
    update(rules.pilot(world, level, dt));
  }
  assert.equal(success, rules.goal(level));
  return world;
}

test('delivery commands name the exact item and paper figure direction', () => {
  const game = loadGame('listenDelivery', 'direction-delivery');
  const words = {leaf: '叶子', bell: '铃铛', bookmark: '书签',
    front: '前面', back: '后面', left: '左边', right: '右边'};
  const scene = lesson.scenes.find(scene => scene.key === 'p05');
  const speech = cue => {
    const [key, beat] = scene.gameAudio[cue].split('-');
    return lesson.scenes.find(item => item.key === key).script[Number(beat) - 1].say;
  };
  for (const [i, level] of game.config.levels.entries()) {
    const steps = game.config.cues[i].steps;
    assert.equal(steps.length, level.orders.length * 2);
    level.orders.forEach(([item, recipient], n) => {
      assert.match(speech(steps[n * 2]), new RegExp('先拿' + words[item]));
      assert.match(speech(steps[n * 2 + 1]), new RegExp('送给纸偶' + words[recipient]));
    });
    const world = playLevel(game, level);
    assert.equal(world.order, level.orders.length);
    assert.equal(world.carried, null);
  }
});

test('moving the lamp sideways can finish all shadow positions at the same distance', () => {
  const game = loadGame('shadowStage', 'shadow-projection');
  for (const level of game.config.levels) {
    assert.ok(level.shots.every(shot => shot.d === 228));
    const world = playLevel(game, level);
    assert.equal(world.i, level.shots.length);
    assert.equal(world.d, 228);
  }
});
