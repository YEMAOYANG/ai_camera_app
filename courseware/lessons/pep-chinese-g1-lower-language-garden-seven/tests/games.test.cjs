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
  let pictures;
  const strip = {replaceChildren(...frames) {pictures = frames.map(frame => frame.src);}};
  const K = {
    gameTemplates: {}, ready() {}, stage: () => ({append() {}}),
    $: () => strip, game(activity) {game = activity;}
  };
  const Classic = {
    bot, create: (config, rules) => ({config, rules, draw() {}}), ease: (_, next) => next,
    validToken: value => typeof value === 'string' && Boolean(value)
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
  return {...game, bot, speech, pictures: () => pictures};
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
    for (let step = 0; step < 4800 && score.correct < goal; step++) {
      update(rules.pilot(world, level, frame));
    }
    assert.equal(score.correct, goal);
  }
  return {world, score, level, finish, press: (key, dt) => update(bot(key), dt)};
}

test('choosing a wrong tool or recipient does not complete a delivery', () => {
  const game = load('listenDelivery', 'take-to-the-sink');
  const run = play(game, 0);
  for (const key of ['right','right','action']) run.press(key,.35);
  assert.equal(run.world.carried,null);
  assert.equal(run.world.help,false);
  assert.deepEqual(run.score,{correct:0,misses:1});
  for (const key of ['left','left','left','left','action']) run.press(key,.35);
  assert.equal(run.world.carried,'comb');
  assert.equal(run.score.correct,1);
  run.world.row=0;
  run.world.col=6;
  run.press('action',.35);
  assert.equal(run.world.carried,'comb');
  assert.equal(run.world.delivered.size,0);
  const goals = {
    comb: [/梳头/,/头发/], towel: [/擦手/,/湿手/], brush: [/刷牙/,/刷牙/],
    basin: [/洗脸/,/洗脸/], soap: [/洗澡/,/浴帘/]
  };
  for (const [i,level] of game.config.levels.entries()) {
    const steps=game.config.cues[i].steps;
    assert.equal(steps.length,level.orders.length*2);
    level.orders.forEach(([good],n) => {
      goals[good].forEach((words,j) => assert.match(game.speech(steps[2*n+j]),words));
    });
    const fresh=play(game,i);
    fresh.finish();
    assert.equal(fresh.world.delivered.size,level.orders.length);
  }
});

test('ordered plot captures show real recorded cards and clear on replay', () => {
  const game = load('bubbleMaze', 'story-tram');
  const run = play(game,0);
  run.press('down',.35);
  run.press('down',.35);
  game.draw({data:{w:run.world,level:run.level}});
  assert.deepEqual(game.pictures(),[]);
  assert.deepEqual(run.score,{correct:0,misses:1});
  assert.equal(run.world.help,false);
  const expected = [
    [/玉米种子/,/收下玉米/,/花生种进/,/收起花生/,/小旗/],
    [/花生种进/,/收起花生/,/土坑/,/一篮鱼/,/小旗/],
    [/戴着帽子/,/风吹/,/捡到/,/还回/,/小旗/]
  ];
  for (const [i,level] of game.config.levels.entries()) {
    const steps=game.config.cues[i].steps;
    assert.equal(steps.length,level.route.length+1);
    steps.forEach((step,j) => assert.match(game.speech(step),expected[i][j]));
    const fresh=play(game,i);
    fresh.finish();
    game.draw({data:{w:fresh.world,level:fresh.level}});
    assert.deepEqual(game.pictures(),Array.from(level.route,id=>game.config.art.icons[id]));
  }
  const retry=play(game,0);
  game.draw({data:{w:retry.world,level:retry.level}});
  assert.deepEqual(game.pictures(),[]);
});
