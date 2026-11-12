const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const templates = path.join(root, '../../kit/game_templates');
const lesson = require('../lesson.json');
const dt = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  const K = {
    gameTemplates: {}, ready() {}, stage: () => ({append() {}}), $() {},
    game(result) { game = result; },
  };
  const Classic = {
    bot, create: (config, rules) => ({config, rules}),
    ease: (_, target) => target, validToken: value => typeof value === 'string' && value.length > 0,
    clamp: (value, min, max) => Math.min(max, Math.max(min, value)),
  };
  const context = vm.createContext({K, Classic});
  vm.runInContext(fs.readFileSync(path.join(templates, template + '.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(root, 'pages', page + '.js'), 'utf8'), context);
  const cueMap = lesson.scenes.find(scene => scene.page === page).gameAudio;
  const speech = cue => {
    const ref = cueMap[cue];
    const split = ref.lastIndexOf('-');
    return lesson.scenes.find(scene => scene.key === ref.slice(0, split)).script[Number(ref.slice(split+1))-1].say;
  };
  return {...game, bot, speech};
}

function play({rules, bot}, level, aimAway = false) {
  rules.validate(level);
  const world = rules.reset(level);
  let awards = 0;
  let misses = 0;
  const update = input => rules.update(world, level, input, dt, {
    award() { awards++; },
    lost() { misses++; rules.adapt(world, misses); },
    fx() {}, move() {}, drop() {},
  });
  if (aimAway) {
    for (let i = 0; i < 60; i++) update(bot('left'));
  }
  update(bot('action'));
  for (let i = 0; i < 30; i++) update(bot());
  assert.equal(awards, 0);
  assert.equal(misses, 1);
  assert.equal(world.help, false);
  for (let i = 0; i < 3600 && awards < rules.goal(level); i++) {
    update(rules.pilot(world, level, dt));
  }
  assert.equal(awards, rules.goal(level));
  return world;
}

test('each drifting card matches the action heard, and aiming at the wrong place earns no point', () => {
  const game = load('wordBubbles', 'listen-for-a-scene');
  const spoken = {count:'数灯笼', grow:'长出', ask:'提问', answer:'回答'};
  for (const [i, level] of game.config.levels.entries()) {
    const steps = game.config.cues[i].steps;
    assert.equal(steps.length, level.rounds.length);
    level.rounds.forEach((round, j) => {
      assert.ok(game.speech(steps[j]).includes(spoken[round.target]));
    });
    assert.equal(play(game, level, true).round, level.rounds.length);
  }
});

test('the two rain characters keep their story destinations when the station columns change', () => {
  const game = load('listenDelivery', 'deliver-a-role');
  const pairing = {big:'empty', small:'plants'};
  const speech = {big:'大雨点儿', small:'小雨点儿', empty:'没有花草', plants:'有花有草'};
  assert.notEqual(game.config.levels[0].drop[0][1], game.config.levels[1].drop[0][1]);
  for (const [i, level] of game.config.levels.entries()) {
    const steps = game.config.cues[i].steps;
    assert.equal(steps.length, level.orders.length * 2);
    level.orders.forEach(([actor, destination], j) => {
      assert.equal(destination, pairing[actor]);
      assert.ok(game.speech(steps[j * 2]).includes(speech[actor]));
      assert.ok(game.speech(steps[j * 2 + 1]).includes(speech[destination]));
    });
    const world = play(game, level);
    assert.equal(world.order, level.orders.length);
    assert.equal(world.carried, null);
  }
});
