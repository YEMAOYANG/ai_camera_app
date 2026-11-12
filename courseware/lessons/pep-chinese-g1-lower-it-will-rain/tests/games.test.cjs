const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const lesson = require('../lesson.json');
const dt = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  const K = {gameTemplates: {}, ready() {}, stage: () => ({append() {}}), $() {}, game(activity) {game = activity;}};
  const Classic = {
    bot, create: (config, rules) => ({config, rules}), ease: (_, next) => next,
    validToken: value => typeof value === 'string' && value.length > 0,
    clamp: (n, min, max) => Math.min(max, Math.max(min, n)),
  };
  const context = vm.createContext({K, Classic});
  for (const file of [`../../kit/game_templates/${template}.js`, `pages/${page}.js`]) {
    vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  }
  const audio = lesson.scenes.find(scene => scene.page === page).gameAudio;
  function speech(cue) {
    const ref = audio[cue];
    const separator = ref.lastIndexOf('-');
    const scene = lesson.scenes.find(item => item.key === ref.slice(0, separator));
    assert.equal(scene.type, 'slide');
    return scene.script[Number(ref.slice(separator + 1)) - 1].say;
  }
  return {...game, bot, speech};
}

function play(game, index) {
  const {rules, config, bot} = game;
  const level = config.levels[index];
  rules.validate(level);
  const world = rules.reset(level);
  const tally = {correct: 0, misses: 0};
  function update(input, seconds = dt) {
    rules.update(world, level, input, seconds, {
      award() {tally.correct++;},
      lost() {tally.misses++; rules.adapt(world, tally.misses);},
      fx() {}, move() {}, drop() {}, jump() {},
    });
  }
  function finish() {
    const goal = rules.goal(level);
    for (let frame = 0; frame < 3600 && tally.correct < goal; frame++) {
      update(rules.pilot(world, level, dt));
    }
    assert.equal(tally.correct, goal);
  }
  return {world, tally, finish, press: (key, seconds) => update(bot(key), seconds)};
}

test('weather words use recorded cues for each changing picture and a first miss does not reveal the answer', () => {
  const game = load('wordBubbles', 'listen-for-weather-words');
  const vocabulary = {
    dark: '阴沉沉', wet: '潮湿', surface: '水面', stuffy: '闷热', rush: '连忙',
    bend: '弯腰', news: '消息', free: '有空',
  };
  const miss = play(game, 0);
  miss.press('action');
  for (let frame = 0; frame < 30; frame++) miss.press();
  assert.deepEqual(miss.tally, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  for (const [index, level] of game.config.levels.entries()) {
    for (const [round, row] of level.rounds.entries()) {
      const cue = game.config.cues[index].steps[round];
      assert.match(game.speech(cue), new RegExp(vocabulary[row.target]));
      assert.equal(row.cards.filter(card => card === row.target).length, 1);
    }
    play(game, index).finish();
  }
});

test('maze takes swallow, fish, ant and falling rain in story order before the flag', () => {
  const game = load('bubbleMaze', 'choose-the-scene');
  const story = ['A', 'B', 'C', 'D'];
  const outOfOrder = play(game, 0);
  for (const direction of ['right', 'down', 'down', 'right']) outOfOrder.press(direction, .34);
  assert.equal(outOfOrder.world.map[3][3], 'B');
  assert.equal(outOfOrder.world.i, 0);
  assert.equal(outOfOrder.world.help, false);
  assert.deepEqual(outOfOrder.tally, {correct: 0, misses: 1});
  for (const [index, level] of game.config.levels.entries()) {
    assert.deepEqual([...level.route], story.slice(0, index + 2));
    assert.ok(level.listenOnly);
    const cues = game.config.cues[index].steps;
    assert.equal(cues.length, level.route.length + 1);
    assert.match(game.speech(cues[0]), /第一位/);
    assert.match(game.speech(cues[1]), /水面/);
    if (index >= 1) assert.match(game.speech(cues[2]), /搬东西/);
    if (index === 2) assert.match(game.speech(cues[3]), /雷声/);
    assert.match(game.speech(cues.at(-1)), /小旗/);
    const run = play(game, index);
    run.finish();
    assert.equal(run.world.i, level.route.length + 1);
  }
});
