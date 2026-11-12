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

test('stationery must be picked up and sent to its actual case in separate actions', () => {
  const game = load('listenDelivery', 'take-stationery-home');
  const names = {pencil: '铅笔', eraser: '橡皮', sharpener: '转笔刀'};
  const miss = play(game, 0);
  miss.press('action', .05);
  assert.deepEqual(miss.tally, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  assert.equal(miss.world.carried, null);
  for (const [index, level] of game.config.levels.entries()) {
    for (const [order, [good, destination]] of level.orders.entries()) {
      assert.equal(destination, 'case');
      assert.match(game.speech(game.config.cues[index].steps[2 * order]), new RegExp(names[good]));
      assert.match(game.speech(game.config.cues[index].steps[2 * order + 1]), /文具盒/);
    }
    const run = play(game, index);
    run.finish();
    assert.equal(run.world.order, level.orders.length);
    assert.equal(run.world.carried, null);
    assert.equal(run.world.delivered.get('case'), level.orders.at(-1)[0]);
  }
});

test('the word-family boat uses concrete spoken targets and a first miss does not reveal the answer', () => {
  const game = load('wordBubbles', 'listen-and-find-word-family');
  const words = {book: '新书', year: '新年', safe: '回到家', flat: '平平', partners: '小伙伴', together: '结伴'};
  const miss = play(game, 0);
  miss.press('action');
  for (let frame = 0; frame < 30; frame++) miss.press();
  assert.deepEqual(miss.tally, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  for (const [index, level] of game.config.levels.entries()) {
    for (const [step, round] of level.rounds.entries()) {
      assert.match(game.speech(game.config.cues[index].steps[step]), new RegExp(words[round.target]));
      assert.equal(round.cards.filter(card => card === round.target).length, 1);
      assert.ok(!(round.cards.includes('partners') && round.cards.includes('together')));
    }
    play(game, index).finish();
  }
});
