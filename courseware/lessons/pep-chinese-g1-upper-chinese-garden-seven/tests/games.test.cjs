const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lessonDir = path.join(__dirname, '..');
const templates = path.join(__dirname, '../../../kit/game_templates');
const lesson = require('../lesson.json');
const dt = 1 / 60;

function loadGame(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  const anchors = new Map();
  const mounted = [];
  let activity;
  const K = {
    gameTemplates: {}, ready() {}, stage: () => ({append: (...nodes) => mounted.push(...nodes)}),
    $(id) {
      const img = {style: {}};
      if (!anchors.has(id)) anchors.set(id, {id, querySelector: () => img});
      return anchors.get(id);
    },
    game(result) { activity = result; },
  };
  const Classic = {
    bot, ease: (_, target) => target, validToken: value => typeof value === 'string' && value.length > 0,
    center: (x, y, width, height) => ({x, y, width, height}),
    create: (config, rules) => ({config, rules, reset: (game, level) => {
      game.world = rules.reset(config.levels[level]);
    }}),
  };
  const context = vm.createContext({K, Classic});
  vm.runInContext(fs.readFileSync(path.join(templates, template + '.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(lessonDir, 'pages', page + '.js'), 'utf8'), context);
  return {...activity, bot, mounted};
}

function playLevel({rules, config, bot, reset}, index) {
  const level = config.levels[index];
  rules.validate(level, index);
  const game = {};
  reset(game, index);
  const world = game.world;
  const evidence = {awards: 0, misses: 0};
  function update(input, seconds = dt) {
    rules.update(world, level, input, seconds, {
      award() { evidence.awards++; },
      lost() { evidence.misses++; rules.adapt(world, evidence.misses); },
      fx() {}, move() {}, jump() {}, drop() {}, resetCheckpoint() {},
    });
  }
  function complete() {
    let frames = 0;
    for (; frames < 3600 && evidence.awards < rules.goal(level); frames++) {
      update(rules.pilot(world, level, dt));
    }
    assert.equal(evidence.awards, rules.goal(level));
    return frames * dt;
  }
  return {world, evidence, complete, move: key => update(bot(key), level.step + dt)};
}

test('depot rejects the wrong component tray before any hints and solves all three boards', () => {
  const game = loadGame('sortingDepot', 'radical-sort');
  assert.deepEqual(game.mounted.map(anchor => anchor.id), ['#garden-first-dock']);
  const component = {nai:'woman', ma:'woman', jie:'woman', mei:'woman',
    ming:'sun', wan:'sun', zuo:'sun', chun:'sun'};
  const wrong = playLevel(game, 0);
  for (const key of ['up','right','right','down','down','left','right','up','up','left','left',
    'down','right','up','right','down','left','down','right']) wrong.move(key);
  assert.deepEqual(wrong.evidence, {awards: 0, misses: 1});
  assert.equal(wrong.world.wrongGroup, 'woman');
  assert.equal(wrong.world.help, false);
  for (const [index, level] of game.config.levels.entries()) {
    for (const item of level.items) assert.equal(item.group, component[item.token]);
    assert.ok(level.docks.every(dock => dock.sample === dock.group));
    const play = playLevel(game, index);
    assert.ok(play.complete() < 30);
    assert.ok(play.world.state.items.every(pos => pos < 0));
  }
});

test('maze turns the reference figure, checks spoken directions and plays every ordered route', () => {
  const game = loadGame('bubbleMaze', 'sound-route');
  const [actor] = game.mounted;
  assert.equal(actor.id, '#garden-facing');
  const bearings = {east: ['C','B','A','D'], north: ['A','D','B','C']};
  const cueKeys = ['go-front','go-back','go-left','go-right'];
  const words = ['前面','后面','左边','右边'];
  const audio = lesson.scenes.find(scene => scene.key === 'sound-route').gameAudio;
  const beats = lesson.scenes.find(scene => scene.key === 'face-and-turn').script;
  for (const [index, level] of game.config.levels.entries()) {
    const play = playLevel(game, index);
    assert.equal(actor.querySelector('img').style.transform, index < 2 ? 'rotate(90deg)' : '');
    assert.equal(level.listenOnly, true);
    const cues = game.config.cues[index].steps;
    assert.equal(cues.at(-1), 'go-exit');
    level.route.forEach((token, step) => {
      const direction = cueKeys.indexOf(cues[step]);
      assert.equal(token, bearings[level.facing][direction]);
      const beat = Number(audio[cues[step]].split('-').at(-1));
      assert.match(beats[beat - 1].say, new RegExp(words[direction]));
    });
    if (index === 0) {
      for (let i = 0; i < 6; i++) play.move('right');
      assert.deepEqual(play.evidence, {awards: 0, misses: 1});
      assert.equal(play.world.help, false);
    }
    assert.ok(play.complete() < 30);
    assert.equal(play.world.i, level.route.length + 1);
  }
});
