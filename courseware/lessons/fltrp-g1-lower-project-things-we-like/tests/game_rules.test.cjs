const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const lesson = require('../lesson.json');

const lessonRoot = path.join(__dirname, '..');
const frameTime = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({
    press: key => keys.includes(key),
    held: key => keys.includes(key)
  });
  const center = (x, y, w, h) => ({x: x - w / 2, y: y - h / 2, w, h});
  let game;
  const K = {
    gameTemplates: {}, ready() {}, stage: () => ({append() {}}), $() {},
    game(activity) { game = activity; }
  };
  const Classic = {
    bot, center, create: (config, rules) => ({config, rules}), ease: (_, next) => next,
    validToken: value => typeof value === 'string' && Boolean(value)
  };
  const context = vm.createContext({K, Classic});
  for (const file of [`../../kit/game_templates/${template}.js`, `pages/${page}.js`]) {
    vm.runInContext(fs.readFileSync(path.join(lessonRoot, file), 'utf8'), context);
  }
  const scene = lesson.scenes.find(item => item.page === page);
  function speech(cue) {
    const action = scene.gameAudio[cue];
    const split = action.lastIndexOf('-');
    const source = lesson.scenes.find(item => item.key === action.slice(0, split));
    return source.script[Number(action.slice(split + 1)) - 1].say;
  }
  function anchor(id) {
    const html = fs.readFileSync(path.join(lessonRoot, 'pages', page + '.html'), 'utf8');
    const values = html.match(new RegExp(`id="${id}"[^>]*left:(\\d+)px;top:(\\d+)px;width:(\\d+)px;height:(\\d+)px`));
    const [left, top, width, height] = values.slice(1).map(Number);
    return [left + width / 2, top + height / 2];
  }
  return {...game, bot, speech, anchor};
}

function play(game, index) {
  const {config, rules, bot} = game;
  const level = config.levels[index];
  rules.validate(level, index);
  const world = rules.reset(level);
  const score = {correct: 0, misses: 0};
  const feedback = {
    award() { score.correct++; },
    lost() { score.misses++; rules.adapt(world, score.misses); },
    fx() {}, move() {}, drop() {}, resetCheckpoint() {}
  };
  function update(input, seconds = frameTime) {
    rules.update(world, level, input, seconds, feedback);
  }
  function until(condition, drive = () => rules.pilot(world, level, frameTime)) {
    for (let frame = 0; frame < 4800 && !condition(); frame++) update(drive());
    assert.ok(condition(), 'legal controls did not reach the expected state');
  }
  return {
    level, world, score, until,
    press: (key, seconds) => update(bot(key), seconds),
    finish: () => until(() => score.correct === rules.goal(level))
  };
}

test('stalls distinguish living animals, toys, actions and colour samples', () => {
  const game = load('sortingDepot', 'sort-the-stalls');
  const groups = {
    rabbits: 'animals', ducks: 'animals', football: 'sports', skating: 'sports',
    blocks: 'toys', robot: 'toys', yellow: 'colours', purple: 'colours'
  };
  assert.match(game.speech('sort-first'), /动物图.*动物展台.*运动图.*运动展台/);
  for (const [index, level] of game.config.levels.entries()) {
    for (const item of level.items) {
      assert.equal(item.group, groups[item.token]);
      const target = level.docks.find(dock => dock.group === item.group);
      assert.notEqual(target.sample, item.token);
    }
    const run = play(game, index);
    run.finish();
    assert.ok(run.world.state.items.every(position => position < 0));
  }
});

test('a wrong stall yields a hint without awarding a point or immediately showing the answer', () => {
  const game = load('sortingDepot', 'sort-the-stalls');
  const run = play(game, 0);
  const wrongRoute = ['up', 'right', 'right', 'down', 'down', 'left', 'right', 'up',
    'up', 'left', 'left', 'down', 'right', 'up', 'right', 'down', 'left', 'down', 'right'];
  for (const key of wrongRoute) run.press(key, .35);
  assert.deepEqual(run.score, {correct: 0, misses: 1});
  assert.equal(run.world.wrongGroup, 'animals');
  assert.equal(run.world.help, false);
  run.press('right', .35);
  assert.equal(run.world.help, true);
});

test('survey delivery uses the actual spoken noun and response at each step', () => {
  const game = load('listenDelivery', 'deliver-the-survey');
  const answers = {swimming: 'yes', kites: 'no', tigers: 'yes', green: 'yes'};
  for (const [index, level] of game.config.levels.entries()) {
    const cues = game.config.cues[index];
    assert.equal(cues.steps.length, (index + 1) * 2);
    for (const [i, [object, response]] of level.orders.entries()) {
      assert.equal(response, answers[object]);
      assert.equal(game.speech(cues.steps[2 * i]), `Do you like ${object}?`);
      assert.equal(game.speech(cues.steps[2 * i + 1]), response === 'yes' ? 'Yes, I do.' : 'No, I don’t.');
    }
    const run = play(game, index);
    run.finish();
    assert.equal(run.world.order, level.orders.length);
    assert.equal(run.world.carried, null);
    for (const [object, response] of level.orders) {
      const last = level.orders.findLast(([, answer]) => answer === response);
      if (last[0] === object) assert.equal(run.world.delivered.get(response), object);
    }
  }
});

test('wrong pickup and wrong vote box award nothing and allow a correct retry', () => {
  const game = load('listenDelivery', 'deliver-the-survey');
  const run = play(game, 0);
  run.press('action');
  assert.deepEqual(run.score, {correct: 0, misses: 1});
  assert.equal(run.world.carried, null);
  assert.equal(run.world.help, false);
  run.until(() => run.world.carried === 'swimming');
  assert.equal(run.score.correct, 1);
  assert.equal(run.world.order, 0);

  const wrongBox = run.world.recipients.get('no');
  const wrongRecipients = new Map(run.world.recipients);
  wrongRecipients.set('yes', wrongBox);
  run.until(() => run.world.col === wrongBox && run.world.row === 0 && run.world.cooldown === 0,
    () => game.rules.pilot({...run.world, recipients: wrongRecipients}, run.level, frameTime));
  const missesBefore = run.score.misses;
  run.press('action');
  assert.deepEqual(run.score, {correct: 1, misses: missesBefore + 1});
  assert.equal(run.world.carried, 'swimming');
  assert.equal(run.world.delivered.size, 0);
  run.finish();
  assert.equal(run.world.delivered.get('yes'), 'swimming');
});

test('teacher anchors coincide with the first real template target and its correct destination', () => {
  const sort = load('sortingDepot', 'sort-the-stalls');
  const sorting = play(sort, 0);
  const midpoint = rect => [rect.x + rect.w / 2, rect.y + rect.h / 2];
  assert.deepEqual(sort.anchor('first-sort-card'), midpoint(sort.rules.target(sorting.world, sorting.level)));
  const stall = sorting.level.docks[0];
  const {ox, oy, s} = sorting.world;
  assert.deepEqual(sort.anchor('first-sort-dock'), [ox + (stall.x + .5) * s, oy + (stall.y + .5) * s]);

  const delivery = load('listenDelivery', 'deliver-the-survey');
  const survey = play(delivery, 0);
  assert.deepEqual(delivery.anchor('first-survey-card'), midpoint(delivery.rules.target(survey.world, survey.level)));
  survey.until(() => survey.world.carried === 'swimming');
  assert.deepEqual(delivery.anchor('first-survey-box'), midpoint(delivery.rules.target(survey.world, survey.level)));
});
