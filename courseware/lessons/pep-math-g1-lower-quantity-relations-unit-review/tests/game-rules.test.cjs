const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const templates = path.resolve(__dirname, '../../../kit/game_templates');
const pages = path.resolve(__dirname, '../pages');
const noop = () => {};
const blank = {held: () => false, press: () => false};
const press = key => ({held: () => false, press: input => input === key});
const canvas = new Proxy({}, {get: () => noop});
const dt = 1 / 60;

function load(template, page) {
  const elements = new Map();
  const context = vm.createContext({
    K: {
      $(key) {
        if (!elements.has(key)) {
          elements.set(key, {dataset: {}, removeAttribute(name) { delete this[name]; }});
        }
        return elements.get(key);
      },
      draw: canvas, ready: noop, stage: () => ({append: noop}),
      game(game) { context.bundle.game = game; }
    }
  });
  vm.runInContext(readFileSync(path.join(templates, 'classic.js'), 'utf8'), context);
  // Exercise the approved rule functions without a browser or substitute game.
  vm.runInContext(`
    Classic.create = (config, rules) => {
      config.levels.forEach(rules.validate);
      globalThis.bundle = {config, rules};
      return {draw() {}};
    };
  `, context);
  vm.runInContext(readFileSync(path.join(templates, template + '.js'), 'utf8'), context);
  vm.runInContext(readFileSync(path.join(pages, page + '.js'), 'utf8'), context);
  return {...context.bundle, elements};
}

function run(rules, level) {
  const world = rules.reset(level);
  let awards = 0;
  let losses = 0;
  const feedback = {
    fx: noop, move: noop, jump: noop, drop: noop, resetCheckpoint: noop,
    award: () => awards++,
    lost() { losses++; rules.adapt(world, losses); },
  };
  const step = (input = blank) => rules.update(world, level, input, dt, feedback);
  return {
    world,
    step,
    get losses() { return losses; },
    finish(count = rules.goal(level)) {
      for (let i = 0; i < 5400 && awards < count; i++) step(rules.pilot(world, level, dt));
      assert.equal(awards, count);
    }
  };
}

test('depot classifies the whole, missing part and gap across all three maps', () => {
  const {config, rules, game, elements} = load('sortingDepot', 'sort-by-what-is-missing');
  assert.deepEqual(Array.from(config.levels, rules.goal), [2, 3, 4]);
  assert.deepEqual(Array.from(new Set(config.levels[2].items.map(item => item.group))).sort(), ['gap','part','whole']);
  for (const level of config.levels) {
    const trial = run(rules, level);
    const start = trial.world.state.p;
    trial.step(rules.pilot(trial.world, level, dt));
    assert.notEqual(trial.world.state.p, start);
    trial.step(press('action'));
    assert.equal(trial.world.state.p, start);
    trial.finish();
    assert.equal(trial.losses, 0);
    assert.equal(rules.target(trial.world, level), null);
  }
  const trial = run(rules, config.levels[0]);
  const view = {state: 'play', level: 0, data: {w: trial.world}};
  const nearby = elements.get('#nearby-quantity-card');
  game.draw(view, canvas);
  assert.equal(nearby.src, config.art.icons['card-seeds-total']);
  trial.step(press('down'));
  game.draw(view, canvas);
  assert.equal(nearby.src, config.art.icons['card-seeds-gap']);
});

test('marble orders carry the actual accepted amount and allow a fresh retry', () => {
  const {config, rules, game, elements} = load('magnetMarbles', 'aim-at-the-matching-count');
  const expected = [[13,4],[27,63],[27,35]];
  config.levels.forEach((level, index) => {
    const answers = level.queue.map(order => level.targets.find(t => level.matches(order, t.value)).value);
    assert.deepEqual(Array.from(answers), expected[index]);
    assert.equal(level.matches(undefined, 27), false);
    const trial = run(rules, level);
    trial.finish();
    assert.equal(trial.losses, 0);
    assert.doesNotThrow(() => rules.target(trial.world, level));
  });
  assert.equal(config.levels[2].matches('order-south-35', 41), false);
  const carryLevel = config.levels[2];
  const carry = run(rules, carryLevel);
  const preview = elements.get('#nursery-previous-answer');
  const view = {state: 'play', level: 2, data: {w: carry.world}};
  game.draw(view, canvas);
  assert.equal(preview.hidden, true);
  carry.finish(1);
  assert.ok(carry.world.delay > 0);
  game.draw({...view, state: 'between'}, canvas);
  assert.equal(preview.hidden, true);
  game.draw(view, canvas);
  assert.equal(preview.hidden, false);
  assert.equal(preview.src, config.art.icons[27]);
  carry.finish();
  game.draw({state: 'play', level: 2, data: {w: rules.reset(carryLevel)}}, canvas);
  assert.equal(preview.hidden, true);
  assert.equal(preview.src, undefined);

  const wrong = run(rules, config.levels[1]);
  for (let expectedLosses = 1; expectedLosses <= 2; expectedLosses++) {
    wrong.step(press('action'));
    for (let i = 0; i < 120 && wrong.losses < expectedLosses; i++) wrong.step();
    assert.equal(wrong.losses, expectedLosses);
    while (wrong.world.delay > 0) wrong.step();
  }
  assert.equal(wrong.world.help, true);
  assert.equal(wrong.world.i, 0);
  wrong.finish();
  assert.equal(wrong.losses, 2);
});
