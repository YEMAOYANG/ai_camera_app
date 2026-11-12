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

test('the story board only accepts the next event and finishes each ordered route', () => {
  const game = load('bubbleMaze', 'story-board-route');
  const routes = [['A', 'B', 'C'], ['D', 'G', 'F'], ['F', 'H', 'I', 'J']];
  const clues = {A: '叫醒', B: '坐起来', C: '离开家', D: '停在路边', G: '斑马线',
    F: '公交就开走', H: '车站等待', I: '人行道', J: '已经开课'};
  const miss = play(game, 0);
  miss.press('down', .34);
  miss.press('down', .34);
  assert.deepEqual(miss.tally, {correct: 0, misses: 1});
  assert.equal(miss.world.map[3][1], 'B');
  assert.equal(miss.world.help, false);
  for (const [index, level] of game.config.levels.entries()) {
    assert.deepEqual([...level.route], routes[index]);
    assert.ok(level.listenOnly);
    const cues = game.config.cues[index].steps;
    assert.equal(cues.length, level.route.length + 1);
    for (const [step, token] of level.route.entries()) {
      assert.match(game.speech(cues[step]), new RegExp(clues[token]));
    }
    assert.match(game.speech(cues.at(-1)), /小旗/);
    const run = play(game, index);
    run.finish();
    assert.equal(run.world.i, level.route.length + 1);
  }
});

test('the boat matches both meanings of 背 and keeps the first miss recoverable', () => {
  const game = load('wordBubbles', 'catch-the-meaning');
  const words = {alarm: '闹钟', watch: '手表', wait: '等公交', sit: '坐在长凳',
    carry: '篮筐背在身后', back: '自己后背', front: '篮筐用两手抱在身前'};
  const miss = play(game, 0);
  miss.press('action');
  for (let frame = 0; frame < 30; frame++) miss.press();
  assert.deepEqual(miss.tally, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  for (const [index, level] of game.config.levels.entries()) {
    for (const [step, round] of level.rounds.entries()) {
      assert.match(game.speech(game.config.cues[index].steps[step]), new RegExp(words[round.target]));
      assert.equal(round.cards.filter(card => card === round.target).length, 1);
    }
    play(game, index).finish();
  }
});
