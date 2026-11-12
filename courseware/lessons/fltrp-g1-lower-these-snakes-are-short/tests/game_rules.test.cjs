const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const read = file => fs.readFileSync(file, 'utf8');
const scenes = JSON.parse(read(path.join(lesson, 'lesson.json'))).scenes;
const cards = JSON.parse(read(path.join(lesson, 'art-source/zoo-cards.json')));
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

function input(...keys) {
  return {held: key => keys.includes(key), press: key => keys.includes(key)};
}

for (const [template, page] of [['wordBubbles', 'bubble-portraits'], ['platformHop', 'jump-to-the-group']]) {
  test(page + ' binds every cue and runs all three levels twice', () => {
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
        if (level.rounds) assert.equal(state.world.caught.token, level.rounds.at(-1).target);
        else assert.equal(state.world.checkpoint[3], level.route.at(-1));
      }
    }
  });
}

test('hitting the long snakes when the short group was named gives no score', () => {
  const {config, engine} = game('wordBubbles', 'bubble-portraits');
  const state = play(engine, config.levels[0], world => {
    if (world.x < 795) return input('right');
    return world.shot ? input() : input('action');
  }, result => result.wrong === 1);
  assert.deepEqual([state.wrong, state.correct, state.world.round, state.world.help], [1, 0, 0, false]);
  assert.equal(state.world.caught, null);
});

test('landing on a reachable long-snake decoy does not establish a checkpoint', () => {
  const {config, engine} = game('platformHop', 'jump-to-the-group');
  const state = play(engine, config.levels[0], (world, frame) =>
    frame === 0 ? input('left', 'action') : world.x > 154 ? input('left') : input(), result => result.wrong === 1);
  assert.deepEqual([state.wrong, state.correct, state.world.i, state.world.help], [1, 0, 0, false]);
  assert.equal(state.world.platform[3], 'long');
  assert.equal(state.world.checkpoint[3], 'start');
});

test('paired illustrations use the same reference origin and exact visible group sizes', () => {
  const get = name => cards['zoo-' + name];
  const long = get('long-group');
  const short = get('short-group');
  assert.deepEqual(long.canvas, short.canvas);
  assert.deepEqual(long.guides, short.guides);
  assert.deepEqual(long.subjects.map(subject => subject.slice(3)), short.subjects.map(subject => subject.slice(3)));
  assert(long.subjects.every((subject, i) => subject[2] > short.subjects[i][2]));
  const tall = get('tall-group');
  const low = get('low-group');
  assert.deepEqual(tall.guides, low.guides);
  assert(tall.subjects.every((subject, i) => subject[1] === 'height' && subject[2] > low.subjects[i][2]));
  assert.equal(get('quiz-short-one').subjects.length, 1);
  assert.equal(get('quiz-short-pair').subjects.length, 2);
  assert.equal(get('quiz-tiger-trio').subjects.length, 3);
});
