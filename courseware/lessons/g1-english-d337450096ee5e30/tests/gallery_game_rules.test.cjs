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

function play(engine, level, choose, stop) {
  engine.validate(level);
  const state = {world: engine.reset(level), correct: 0, wrong: 0};
  const feedback = {
    fx() {}, move() {}, drop() {}, jump() {},
    award() { state.correct++; },
    lost() { state.wrong++; engine.adapt(state.world, state.wrong); },
  };
  for (let frame = 0; frame < 4200 && !stop(state); frame++) {
    engine.update(state.world, level, choose(state.world, frame), dt, feedback);
  }
  return state;
}

function input(key) {
  return {held: candidate => candidate === key, press: candidate => candidate === key};
}

for (const [template, page] of [['wordBubbles', 'listen-to-the-job'], ['listenDelivery', 'send-the-photo']]) {
  test(page + ' binds every voice cue and runs all three levels twice', () => {
    const {config, engine} = game(template, page);
    const scene = scenes.find(candidate => candidate.key === page);
    const cueKeys = config.cues.flatMap(level => Object.values(level).flat());
    assert.deepEqual([...new Set(cueKeys)].sort(), Object.keys(scene.gameAudio).sort());
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const target = engine.goal(level);
        const state = play(engine, level, world => engine.pilot(world, level, dt), result => result.correct === target);
        assert.equal(state.correct, target);
        if (level.rounds) {
          assert.equal(state.world.round, level.rounds.length);
          assert.equal(state.world.caught.token, level.rounds.at(-1).target);
        } else {
          for (const [photo, frame] of level.orders) assert.equal(state.world.delivered.get(frame), photo);
        }
      }
    }
  });
}

test('a first shot between the nurse and driver photos scores nothing and shows no answer', () => {
  const {config, engine} = game('wordBubbles', 'listen-to-the-job');
  const state = play(engine, config.levels[0], (_, frame) => input(frame === 0 ? 'action' : ''), result => result.wrong === 1);
  assert.equal(state.wrong, 1);
  assert.equal(state.correct, 0);
  assert.equal(state.world.round, 0);
  assert.equal(state.world.caught, null);
  assert.equal(state.world.help, false);
});

test('a male doctor photo does not satisfy the female doctor order', () => {
  const {config, engine} = game('listenDelivery', 'send-the-photo');
  const state = play(engine, config.levels[1], world => input(world.col < 6 ? 'right' : 'action'), result => result.wrong === 1);
  assert.equal(state.wrong, 1);
  assert.equal(state.correct, 0);
  assert.equal(state.world.order, 0);
  assert.equal(state.world.carried, null);
  assert.equal(state.world.help, false);
});
