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

test('summer vocabulary drives the picture target, with no answer reveal on the first miss', () => {
  const game = load('wordBubbles', 'listen-find-summer');
  const words = {
    ice: '冰棍', melon: '西瓜', soup: '绿豆汤', mat: '凉席', coil: '蚊香',
    lotion: '花露水', fan: '蒲扇', chair: '竹椅', firefly: '萤火虫',
  };
  const miss = play(game, 0);
  miss.press('action');
  for (let frame = 0; frame < 30; frame++) miss.press();
  assert.deepEqual(miss.tally, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  for (const [index, level] of game.config.levels.entries()) {
    for (const [round, row] of level.rounds.entries()) {
      const cue = game.config.cues[index].steps[round];
      assert.match(game.speech(cue), new RegExp(words[row.target]));
      assert.equal(row.cards.filter(card => card === row.target).length, 1);
    }
    play(game, index).finish();
  }
});

test('the ant story rejects a later picture before the next event and each stage ends at the flag', () => {
  const game = load('bubbleMaze', 'ant-goes-home');
  const routes = [['A', 'B'], ['B', 'C', 'D'], ['R', 'G', 'F']];
  const hints = [['趴着', '爬上来'], ['爬上来', '背小蚂蚁', '照路'], ['假山', '草坪', '到家']];
  const outOfOrder = play(game, 0);
  for (const direction of ['right', 'down', 'down', 'right']) outOfOrder.press(direction, .34);
  assert.equal(outOfOrder.world.map[3][3], 'B');
  assert.equal(outOfOrder.world.i, 0);
  assert.equal(outOfOrder.world.help, false);
  assert.deepEqual(outOfOrder.tally, {correct: 0, misses: 1});
  for (const [index, level] of game.config.levels.entries()) {
    assert.deepEqual([...level.route], routes[index]);
    assert.ok(level.listenOnly);
    const cues = game.config.cues[index].steps;
    assert.equal(cues.length, level.route.length + 1);
    for (const [step, meaning] of hints[index].entries()) {
      assert.match(game.speech(cues[step]), new RegExp(meaning));
    }
    assert.match(game.speech(cues.at(-1)), /小旗/);
    const run = play(game, index);
    run.finish();
    assert.equal(run.world.i, level.route.length + 1);
  }
});
