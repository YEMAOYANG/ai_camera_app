const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

function loadGame(id, mechanic) {
  let config, game;
  const noop = () => {};
  const K = {
    ready: noop,
    game(options) { game = options; },
    gameTemplates: {
      tools: {assert: assert.ok, validateVisual: noop, hint(g) { g.hinted = true; }},
      [mechanic](options) {
        config = options;
        return {
          reset(g, level) {
            const plan = options.levels[level];
            g.data = {plan: {rounds: g.autoLoop ? plan.demoRounds : plan.rounds}, round: 0, next: 0};
          },
          update(g) {
            if (g.collect != null) g.data.world.count += g.collect;
            if (g.succeed) g.data.next = 0.85;
            if (g.advance) {
              g.data.round++;
              g.data.next = 0;
            }
          },
        };
      },
    },
  };
  const file = path.join(__dirname, '..', 'pages', id + '.js');
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), {K});
  return {config, game};
}

test('each runner course requires all three specified groups, in their track order', () => {
  const {config} = loadGame('g02', 'runner');
  for (const level of config.levels) {
    for (const round of [...level.rounds, ...(level.demoRounds || [])]) {
      const solutions = [];
      for (let mask = 0; mask < 2 ** round.track.length; mask++) {
        const selected = Array.from(round.track.filter((_, index) => mask & (1 << index)));
        if (selected.reduce((sum, item) => sum + item.value, 0) === round.collect) {
          solutions.push(selected.map(item => item.value));
        }
      }
      assert.deepEqual(solutions, [Array.from(round.goal.groups, group => group.count)]);
      const palette = new Set(Array.from(round.goal.groups, group => group.color));
      assert.ok(round.track.every(item => palette.has(item.visual.color)));
    }
  }
});

test('an extra package cannot make the runner display a count outside the lesson range', () => {
  const {game} = loadGame('g02', 'runner');
  const state = {data: {world: {count: 8}}, collect: 5};
  game.update(state);
  assert.equal(state.data.world.count, 8);
  assert.equal(state.data.world.retry, 1.3);
  assert.equal(state.hinted, true);
});

test('every second slingshot round starts with the lights still on after the first', () => {
  const {config} = loadGame('g04', 'slingshot');
  for (const level of config.levels) {
    for (const rounds of [level.rounds, level.demoRounds].filter(Boolean)) {
      const [first, second] = rounds;
      assert.equal(second.lamps.length, first.lamps.length - first.turnOff);
      assert.ok(second.turnOff > 0 && second.turnOff < second.lamps.length);
    }
  }
});

test('the live stock changes only on successful collisions and carries into the next step', () => {
  const {config, game} = loadGame('g06', 'bumper');
  for (const level of config.levels) {
    for (const round of [...level.rounds, ...(level.demoRounds || [])]) {
      assert.equal(round.options[round.answer].count, round.before + round.change);
      assert.equal(new Set(Array.from(round.options, item => item.count)).size, round.options.length);
    }
  }
  const state = {pointer: {active: true}};
  game.reset(state, 0);
  assert.equal(state.data.stock, 3);
  assert.equal(state.pointer.active, false);
  game.update(state);
  assert.equal(state.data.stock, 3);
  state.succeed = true;
  game.update(state);
  game.update(state);
  assert.equal(state.data.stock, 5);
  state.succeed = false;
  state.advance = true;
  state.pointer.active = true;
  game.update(state);
  assert.equal(state.data.stock, 5);
  assert.equal(state.pointer.active, false);
  state.succeed = true;
  state.advance = false;
  game.update(state);
  assert.equal(state.data.stock, 4);
});
