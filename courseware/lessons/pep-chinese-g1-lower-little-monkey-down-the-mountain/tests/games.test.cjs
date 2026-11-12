const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const lesson = require('../lesson.json');

const root = path.join(__dirname, '..');
const frame = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  let images = [];
  const strip = {replaceChildren(...frames) {images = frames.map(frame => frame.src);}};
  const K = {
    gameTemplates: {}, ready() {}, stage: () => ({append() {}}),
    $: () => strip, game(activity) {game = activity;}
  };
  const Classic = {
    bot, create: (config, rules) => ({config, rules, draw() {}}), ease: (_, next) => next,
    validToken: value => typeof value === 'string' && Boolean(value),
    clamp: (n, min, max) => Math.min(max, Math.max(min, n))
  };
  const context = vm.createContext({K, Classic, document: {createElement: () => ({})}});
  for (const file of [`../../kit/game_templates/${template}.js`, `pages/${page}.js`]) {
    vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  }
  const audio = lesson.scenes.find(scene => scene.page === page).gameAudio;
  const speech = cue => {
    const ref = audio[cue];
    const separator = ref.lastIndexOf('-');
    const scene = lesson.scenes.find(s => s.key === ref.slice(0, separator));
    return scene.script[Number(ref.slice(separator + 1)) - 1].say;
  };
  return {...game, bot, speech, images: () => images};
}

function play(game, index) {
  const {rules, config, bot} = game;
  const level = config.levels[index];
  rules.validate(level);
  const world = rules.reset(level);
  const score = {correct: 0, misses: 0};
  function update(input, dt = frame) {
    rules.update(world, level, input, dt, {
      award() {score.correct++;},
      lost() {score.misses++; rules.adapt(world, score.misses);},
      fx() {}, move() {}, drop() {}, jump() {}
    });
  }
  function finish() {
    const goal = rules.goal(level);
    for (let step = 0; step < 3600 && score.correct < goal; step++) {
      update(rules.pilot(world, level, frame));
    }
    assert.equal(score.correct, goal);
  }
  return {world, score, level, finish, press: (key, dt) => update(bot(key), dt)};
}

test('recorded plot cues follow the story; wrong turn keeps the filmstrip empty', () => {
  const game = load('bubbleMaze', 'walk-the-stage-map');
  const expected = [
    [/玉米的地方/,/桃子挂在枝头/,/满地有西瓜/,/小旗/],
    [/玉米离开手/,/树枝取下桃子/,/托着桃子到了瓜地/,/小旗/],
    [/抱住西瓜/,/跑在兔子后面/,/兔子跑进树林/,/两手空空/,/小旗/]
  ];
  const miss = play(game, 0);
  for (let i = 0; i < 2; i++) miss.press('down', .34);
  game.draw({data: {level: miss.level, w: miss.world}});
  assert.deepEqual(game.images(), []);
  assert.deepEqual(miss.score, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  for (const [index, cues] of game.config.cues.entries()) {
    assert.equal(cues.steps.length, expected[index].length);
    cues.steps.forEach((cue, i) => assert.match(game.speech(cue), expected[index][i]));
    const current = play(game, index);
    current.finish();
    game.draw({data: {level: current.level, w: current.world}});
    assert.deepEqual(game.images(), Array.from(current.level.route, key => game.config.art.icons[key]));
  }
  const replay = play(game, 0);
  game.draw({data: {level: replay.level, w: replay.world}});
  assert.deepEqual(game.images(), []);
});

test('a bubble must meet the stated action and first miss never highlights the target', () => {
  const game = load('wordBubbles', 'catch-the-action');
  const miss = play(game, 0);
  miss.press('action');
  for (let step = 0; step < 32; step++) miss.press();
  assert.deepEqual(miss.score, {correct: 0, misses: 1});
  assert.equal(miss.world.help, false);
  const action = {split:'掰',pluck:'摘',shoulder:'扛',cup:'捧',hug:'抱',ballToss:'扔',ballCup:'捧',ballHug:'抱'};
  for (const [index, level] of game.config.levels.entries()) {
    level.rounds.forEach((round, i) => {
      assert.match(game.speech(game.config.cues[index].steps[i]), new RegExp(action[round.target]));
      assert.equal(round.cards.filter(card => card === round.target).length, 1);
    });
    play(game, index).finish();
  }
});
