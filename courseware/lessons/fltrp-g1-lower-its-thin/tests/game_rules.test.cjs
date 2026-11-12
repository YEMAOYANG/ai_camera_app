const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const read = file => fs.readFileSync(file, 'utf8');
const scenes = JSON.parse(read(path.join(lesson, 'lesson.json'))).scenes;
const cards = JSON.parse(read(path.join(lesson, 'art-source/farm-cards.json')));
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
  return {held: value => value === key, press: value => value === key};
}

for (const [template, page] of [['magnetMarbles', 'aim-at-the-photo'], ['listenDelivery', 'deliver-the-photo']]) {
  test(page + ' binds every cue and finishes all three levels twice', () => {
    const {config, engine} = game(template, page);
    const scene = scenes.find(candidate => candidate.key === page);
    assert.deepEqual([...new Set(config.cues.flatMap(level => Object.values(level).flat()))].sort(),
      Object.keys(scene.gameAudio).sort());
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const target = engine.goal(level);
        const state = play(engine, level, world => engine.pilot(world, level, dt), result => result.correct === target);
        assert.equal(state.correct, target);
        if (level.queue) assert.equal(state.world.targets.filter(item => item.used).length, level.queue.length);
        else for (const [photo, frame] of level.orders) assert.equal(state.world.delivered.get(frame), photo);
      }
    }
  });
}

test('a straight shot hits the wrong body shape and gives no score', () => {
  const {config, engine} = game('magnetMarbles', 'aim-at-the-photo');
  const state = play(engine, config.levels[0], (_, frame) => input(frame === 0 ? 'action' : ''), result => result.wrong === 1);
  assert.deepEqual([state.wrong, state.correct, state.world.i, state.world.help], [1, 0, 0, false]);
  assert.equal(state.world.targets.some(target => target.used), false);
});

test('a pickup that matches only size or only color never takes the photo', () => {
  const {config, engine} = game('listenDelivery', 'deliver-the-photo');
  for (const wrongColumn of [1, 6]) {
    const state = play(engine, config.levels[0], world =>
      input(world.col === wrongColumn ? 'action' : world.col < wrongColumn ? 'right' : 'left'), result => result.wrong === 1);
    assert.deepEqual([state.wrong, state.correct, state.world.order, state.world.carried, state.world.help], [1, 0, 0, null, false]);
  }
});

test('comparisons preserve the intended object, count and common frame', () => {
  const figures = name => cards['farm-' + name].figures;
  assert.equal(figures('shape-fat')[0][1], figures('shape-thin')[0][1]);
  assert.equal(figures('one-big')[0][0], figures('one-little')[0][0]);
  assert(figures('one-big')[0][1] > figures('one-little')[0][1]);
  assert.deepEqual(figures('two-little'), [figures('one-little')[0], figures('one-little')[0]]);
  assert.equal(figures('five-pigs').length, 5);
  assert.equal(figures('five-pigs').filter(([kind]) => kind === 'black-pig').length, 1);
  assert.equal(figures('five-pigs').filter(([, width]) => width === 131).length, 2);
  assert.deepEqual(cards['farm-pair-black-little'].canvas, cards['farm-pair-black-big'].canvas);
  assert.deepEqual(figures('pair-black-little'), [['black-pig', 106], ['black-pig', 106]]);
  assert.deepEqual(figures('pair-black-big'), [['black-pig', 145], ['black-pig', 145]]);
  assert.deepEqual(figures('pair-pink-little'), [['fat-pig', 106], ['fat-pig', 106]]);
});
