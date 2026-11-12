const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const templates = path.resolve(__dirname, '../../../kit/game_templates');
const pages = path.resolve(__dirname, '../pages');
const noOp = () => {};
const emptyInput = { held: () => false, press: () => false };
const action = key => ({ held: () => false, press: value => value === key });
const drawing = new Proxy({}, { get: () => noOp });
const images = { icons: new Map(), frames: [] };
const frame = 1 / 60;

function readGame(template, page) {
  const elements = new Map();
  const context = vm.createContext({
    K: {
      $(selector) {
        if (!elements.has(selector)) elements.set(selector, { dataset: {} });
        return elements.get(selector);
      },
      draw: drawing,
      ready: noOp,
      stage: () => ({ append: noOp }),
      game(game) { context.lessonGame.game = game; },
    },
  });
  vm.runInContext(readFileSync(path.join(templates, 'classic.js'), 'utf8'), context);
  // Capture the real template rules before Classic attaches the browser UI.
  vm.runInContext(`
    Classic.create = (config, rules) => {
      globalThis.lessonGame = { config, rules };
      config.levels.forEach(rules.validate);
      return { draw() {} };
    };
  `, context);
  vm.runInContext(readFileSync(path.join(templates, template + '.js'), 'utf8'), context);
  vm.runInContext(readFileSync(path.join(pages, page + '.js'), 'utf8'), context);
  return { ...context.lessonGame, elements };
}

function exercise(rules, level, world = rules.reset(level)) {
  let won = 0;
  let lost = 0;
  const feedback = {
    fx: noOp, move: noOp, jump: noOp, drop: noOp, resetCheckpoint: noOp,
    award: () => won++,
    lost: () => { lost++; rules.adapt(world, lost); },
  };
  const step = (input = emptyInput) => rules.update(world, level, input, frame, feedback);
  return {
    world,
    step,
    get lost() { return lost; },
    finish() {
      for (let i = 0; i < 5400 && won < rules.goal(level); i++) {
        step(rules.pilot(world, level, frame));
      }
      assert.equal(won, rules.goal(level));
      return lost;
    },
  };
}

test('pairing-card routes deliver all exact categories after a restart', () => {
  const { config, rules, game, elements } = readGame('sortingDepot', 'sort-the-pairing-cards');
  assert.deepEqual(Array.from(config.levels, rules.goal), [2, 3, 4]);
  for (const level of config.levels) {
    const initial = rules.reset(level);
    const trial = exercise(rules, level);
    trial.step(rules.pilot(trial.world, level, frame));
    assert.notEqual(trial.world.state.p, initial.state.p);
    trial.step(action('action'));
    assert.equal(trial.world.state.p, initial.state.p);
    assert.equal(trial.finish(), 0);
    assert.equal(rules.target(trial.world, level), null);
  }

  const level = config.levels[0];
  const trial = exercise(rules, level);
  const view = { state: 'play', level: 0, data: { w: trial.world } };
  const nearbyCard = elements.get('#nearby-pairing-card');
  game.draw(view, drawing);
  assert.equal(nearbyCard.src, config.art.icons['pair-card-1-equal']);
  trial.step(action('down'));
  game.draw(view, drawing);
  assert.equal(nearbyCard.src, config.art.icons['pair-card-1-gap']);
  view.state = 'done';
  game.draw(view, drawing);
  assert.equal(elements.get('#pairing-legend').hidden, true);
});

test('lantern orders match the difference in either row order and ignore the third row', () => {
  const { config, rules } = readGame('magnetMarbles', 'light-the-gap');
  const differences = [[4, 2], [6, 5], [8, 9, 7]];
  config.levels.forEach((level, i) => {
    const expected = level.queue.map(id => level.targets.find(t => level.matches(id, t.value)).value);
    assert.deepEqual(Array.from(expected), differences[i]);
    assert.equal(exercise(rules, level).finish(), 0);
  });

  const level = config.levels[1];
  const trial = exercise(rules, level);
  for (let wrong = 1; wrong <= 2; wrong++) {
    trial.step(action('action'));
    for (let i = 0; i < 120 && trial.lost < wrong; i++) trial.step();
    assert.equal(trial.lost, wrong);
    while (trial.world.delay > 0) trial.step();
  }
  assert.equal(trial.world.help, true);
  assert.equal(trial.world.i, 0);
  assert.equal(trial.finish(), 2);
  assert.equal(trial.world.i, level.queue.length);
  assert.ok(rules.target(trial.world, level));
  assert.doesNotThrow(() => rules.draw(trial.world, level, drawing, images));
});
