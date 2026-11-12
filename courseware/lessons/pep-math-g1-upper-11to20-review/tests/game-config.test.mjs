import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const no = () => {};
const bot = (...keys) => ({press: (key) => keys.includes(key), held: (key) => keys.includes(key)});

function mechanic(page, template) {
  let config;
  let rules;
  const target = {};
  const context = vm.createContext({
    K: {gameTemplates: {}, ready: no, game: no, $: () => target, stage: () => ({appendChild: no})},
    Classic: {
      bot,
      ease: (_, value) => value,
      validToken: (token) => typeof token === 'string' && /^[a-z0-9-]+$/.test(token),
      create(given, mechanics) {
        config = given;
        rules = mechanics;
        config.levels.forEach(rules.validate);
        return {draw: no};
      },
    },
  });
  vm.runInContext(read(`../../../kit/game_templates/${template}.js`), context);
  vm.runInContext(read(`../pages/${page}.js`), context);
  return {config, rules};
}

function drive({rules}, level, input, frames, observe = () => {}) {
  const world = rules.reset(level);
  const log = {awards: 0, misses: 0};
  const feedback = {
    fx: no, move: no, jump: no, drop: no, resetCheckpoint: no,
    award: () => { log.awards++; },
    lost: () => { log.misses++; },
  };
  for (let frame = 0; frame < frames && log.awards < rules.goal(level); frame++) {
    rules.update(world, level, input(world, level, frame), 1 / 30, feedback);
    observe(log, frame);
  }
  return log;
}

test('depot artwork at each dock represents the same total as the shipped piece', () => {
  const game = mechanic('depot', 'sortingDepot');
  const visualValue = (id) => Number(id.split('-').at(-1));
  for (const level of game.config.levels) {
    for (const item of level.items) {
      const dock = level.docks.find(({group}) => group === item.group);
      assert.ok(dock);
      assert.equal(visualValue(item.token), visualValue(dock.sample));
      assert.notEqual(item.token, dock.sample);
      assert.ok(game.config.art.icons[item.token] && game.config.art.icons[dock.sample]);
    }
    assert.equal(drive(game, level, game.rules.pilot, 5000).awards, level.items.length);
  }
});

test('each accepted station adds one, and an out-of-order station holds progress', () => {
  const game = mechanic('route-by-result', 'bubbleMaze');
  for (const level of game.config.levels) {
    for (const [index, token] of level.route.entries()) {
      const [, left, operator, right] = /^(\d+)([+−])(\d+)$/.exec(level.labels[token]);
      const result = Number(left) + (operator === '+' ? 1 : -1) * Number(right);
      assert.equal(result, level.start + index + 1);
      assert.ok(game.config.art.icons[token]);
    }
    assert.equal(drive(game, level, game.rules.pilot, 9000).awards, level.route.length + 1);
  }

  // Skip the first station by heading down the left spur, then approach the
  // third station. It is reachable but cannot count toward the route yet.
  const approach = (_, __, frame) => frame < 18 ? bot('down') : bot('right');
  let firstMiss;
  drive(game, game.config.levels[0], approach, 35, (log) => {
    if (log.misses && firstMiss === undefined) firstMiss = log.awards;
  });
  assert.equal(firstMiss, 0);
});
