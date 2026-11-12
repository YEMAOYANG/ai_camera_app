const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const lesson = require('../lesson.json');

const root = path.join(__dirname, '..');
const dt = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  const K = {gameTemplates: {}, ready() {}, stage: () => ({append() {}}), $() {}, game(activity) {game = activity;}};
  const Classic = {
    bot, create: (config, rules) => ({config, rules}), ease: (_, next) => next,
    validToken: value => typeof value === 'string' && Boolean(value),
    clamp: (n, min, max) => Math.min(max, Math.max(min, n))
  };
  const context = vm.createContext({K, Classic});
  for (const file of [`../../kit/game_templates/${template}.js`, `pages/${page}.js`]) {
    vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  }
  const audio = lesson.scenes.find(scene => scene.page === page).gameAudio;
  const speech = cue => {
    const ref = audio[cue];
    const separator = ref.lastIndexOf('-');
    const scene = lesson.scenes.find(item => item.key === ref.slice(0, separator));
    return scene.script[Number(ref.slice(separator + 1)) - 1].say;
  };
  return {...game, bot, speech};
}

function play(game, index) {
  const {rules, config, bot} = game;
  const level = config.levels[index];
  rules.validate(level, index);
  const world = rules.reset(level);
  const score = {correct: 0, misses: 0};
  function update(input, seconds = dt) {
    rules.update(world, level, input, seconds, {
      award() {score.correct++;},
      lost() {score.misses++; rules.adapt(world, score.misses);},
      fx() {}, move() {}, drop() {}, jump() {}, resetCheckpoint() {}
    });
  }
  function finish() {
    const goal = rules.goal(level);
    for (let frame = 0; frame < 3600 && score.correct < goal; frame++) {
      update(rules.pilot(world, level, dt));
    }
    assert.equal(score.correct, goal);
  }
  return {world, score, finish, press: (key, seconds) => update(bot(key), seconds)};
}

test('the stage matches each puppet to its story location; a wrong dock does not advance', () => {
  const game = load('sortingDepot', 'sort-the-stage');
  const groups = {swallow:'sky',woodpecker:'trunk',frog:'paddy',ladybug:'leaf'};
  const run = play(game,0);
  const wrongPath = ['up','right','right','down','down','left','right','up','up','left','left',
    'down','right','up','right','down','left','down','right'];
  for (const step of wrongPath) run.press(step,.34);
  assert.deepEqual(run.score,{correct:0,misses:1});
  assert.equal(run.world.wrongGroup,'sky');
  assert.equal(run.world.help,false);
  assert.match(game.speech(game.config.cues[0].goal),/燕子和啄木鸟.*空中、树干里/);
  assert.match(game.speech(game.config.cues[1].goal),/青蛙.*水田/);
  assert.match(game.speech(game.config.cues[2].goal),/七星瓢虫.*叶子/);
  for (const [i,level] of game.config.levels.entries()) {
    for (const card of level.items) {
      assert.equal(card.group,groups[card.token]);
      assert.equal(level.docks.filter(dock=>dock.group===card.group).length,1);
    }
    const fresh=play(game,i);
    fresh.finish();
    assert.ok(fresh.world.state.items.every(pos=>pos<0));
  }
});

test('story jumps follow the six-paragraph sequence and reject the later helper on the first jump', () => {
  const game=load('platformHop','jump-through-story');
  const routes=[['A','B','C'],['C','D','E'],['D','E','F','G']];
  const words={A:/蚜虫/,B:/燕子/,C:/啄木鸟/,D:/青蛙/,E:/瓢虫.*棉花叶/,F:/七点/,G:/绿叶、白棉/};
  const first=play(game,0);
  first.press('action');
  for (let frame=0;frame<25;frame++) first.press('left');
  for (let frame=0;frame<36;frame++) first.press();
  assert.deepEqual(first.score,{correct:0,misses:1});
  assert.equal(first.world.i,0);
  assert.equal(first.world.help,false);
  for (const [i,level] of game.config.levels.entries()) {
    assert.deepEqual([...level.route],routes[i]);
    assert.equal(level.prompt,'scroll');
    level.route.forEach((token,n)=>assert.match(game.speech(game.config.cues[i].steps[n]),words[token]));
    play(game,i).finish();
  }
});
