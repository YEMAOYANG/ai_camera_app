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
  rules.validate(level, index);
  const world = rules.reset(level);
  const tally = {correct: 0, misses: 0};
  function update(input, seconds = dt) {
    rules.update(world, level, input, seconds, {
      award() {tally.correct++;},
      lost() {tally.misses++; rules.adapt(world, tally.misses);},
      fx() {}, move() {}, drop() {}, jump() {}, resetCheckpoint() {},
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

test('a wrong story platform does not advance the route, and the first cue has a fixed scroll', () => {
  const game = load('platformHop', 'hop-through-the-story');
  const routes = [['A','B','C'],['C','D','E'],['F','G','H','I']];
  const clues = {A:'老虎把任务交给狗熊',B:'喊第一条',C:'狐狸来问哪一天',D:'得到明天',
    E:'大灰狼来追问几点',F:'上午八点',G:'梅花鹿来问',H:'森林广场',I:'来到广场|到广场'};
  const miss = play(game, 0);
  miss.press('action');
  for (let frame=0; frame<25; frame++) miss.press('left');
  for (let frame=0; frame<36; frame++) miss.press();
  assert.deepEqual(miss.tally, {correct:0,misses:1});
  assert.equal(miss.world.help,false);
  assert.equal(miss.world.i,0);
  for (const [index,level] of game.config.levels.entries()) {
    assert.deepEqual([...level.route],routes[index]);
    assert.equal(level.prompt,'scroll');
    for (const [step,token] of level.route.entries()) {
      assert.match(game.speech(game.config.cues[index].steps[step]),new RegExp(clues[token]));
    }
    play(game,index).finish();
  }
});

test('cards only park at the matching date, time, venue or complete dock', () => {
  const game = load('sortingDepot','sort-announcements');
  const kinds = {'missing-day':'day','missing-time':'time','missing-place':'place',complete:'full'};
  const miss = play(game,0);
  const wrongRoute=['up','right','right','down','down','left','right','up','up','left','left',
    'down','right','up','right','down','left','down','right'];
  for (const key of wrongRoute) miss.press(key,.34);
  assert.deepEqual(miss.tally,{correct:0,misses:1});
  assert.equal(miss.world.help,false);
  assert.equal(miss.world.wrongGroup,'day');
  for (const [index,level] of game.config.levels.entries()) {
    for (const item of level.items) {
      assert.equal(kinds[item.token],item.group);
      assert.equal(level.docks.filter(dock=>dock.group===item.group).length,1);
    }
    const run=play(game,index);
    run.finish();
    assert.ok(run.world.state.items.every(p=>p<0));
  }
});
